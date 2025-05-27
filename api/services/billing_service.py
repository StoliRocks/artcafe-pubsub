import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import stripe
import os

from models.billing import (
    Invoice, InvoiceCreate, InvoiceStatus, LineItem, LineItemType,
    PaymentRecord, BillingHistory, PaymentMethodInfo, PaymentMethod,
    UsageRecord, SubscriptionInfo
)
from models.tenant import SubscriptionTier
from api.db import dynamodb
from config.settings import settings
from api.services.notification_service import notification_service
from api.services.tenant_service import tenant_service
from api.services.usage_service import usage_service
from models.notification import NotificationCreate, NotificationType, NotificationPriority

logger = logging.getLogger(__name__)

# Table names
INVOICE_TABLE = "artcafe-billing-history"
PAYMENT_TABLE = "artcafe-payments"
PAYMENT_METHOD_TABLE = "artcafe-payment-methods"
USAGE_RECORD_TABLE = "artcafe-usage-records"

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Pricing configuration (per month)
PRICING = {
    SubscriptionTier.FREE: {
        "base_price": "0.00",
        "included_agents": 2,
        "included_messages": 1000,
        "included_storage_gb": 1,
        "per_agent": "0.00",
        "per_1k_messages": "0.00",
        "per_gb_storage": "0.00"
    },
    SubscriptionTier.BASIC: {
        "base_price": "29.00",
        "included_agents": 5,
        "included_messages": 10000,
        "included_storage_gb": 10,
        "per_agent": "5.00",
        "per_1k_messages": "1.00",
        "per_gb_storage": "0.50"
    },
    SubscriptionTier.PRO: {
        "base_price": "99.00",
        "included_agents": 20,
        "included_messages": 100000,
        "included_storage_gb": 100,
        "per_agent": "3.00",
        "per_1k_messages": "0.50",
        "per_gb_storage": "0.25"
    },
    SubscriptionTier.ENTERPRISE: {
        "base_price": "499.00",
        "included_agents": 100,
        "included_messages": 1000000,
        "included_storage_gb": 1000,
        "per_agent": "2.00",
        "per_1k_messages": "0.25",
        "per_gb_storage": "0.10"
    }
}


class BillingService:
    """Service for billing and payments"""
    
    async def create_invoice(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
        auto_charge: bool = True
    ) -> Invoice:
        """
        Create invoice for a billing period
        
        Args:
            tenant_id: Tenant ID
            period_start: Billing period start
            period_end: Billing period end
            auto_charge: Automatically charge the invoice
            
        Returns:
            Created invoice
        """
        try:
            # Get tenant info
            tenant = await tenant_service.get_tenant(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")
            
            # Get subscription info
            subscription_tier = tenant.subscription_tier
            pricing = PRICING.get(subscription_tier, PRICING[SubscriptionTier.BASIC])
            
            # Calculate usage for period
            usage = await self._calculate_period_usage(tenant_id, period_start, period_end)
            
            # Create line items
            line_items = []
            
            # Base subscription
            line_items.append({
                "type": LineItemType.SUBSCRIPTION,
                "description": f"{subscription_tier.upper()} Plan - {period_start.strftime('%B %Y')}",
                "quantity": 1,
                "unit_price": pricing["base_price"],
                "amount": pricing["base_price"]
            })
            
            # Agent overage
            agent_overage = max(0, usage["agent_count"] - pricing["included_agents"])
            if agent_overage > 0:
                agent_cost = str(Decimal(pricing["per_agent"]) * agent_overage)
                line_items.append({
                    "type": LineItemType.USAGE,
                    "description": f"Additional Agents ({agent_overage} agents)",
                    "quantity": agent_overage,
                    "unit_price": pricing["per_agent"],
                    "amount": agent_cost
                })
            
            # Message overage
            message_overage = max(0, usage["message_count"] - pricing["included_messages"])
            if message_overage > 0:
                message_units = (message_overage + 999) // 1000  # Round up to nearest 1k
                message_cost = str(Decimal(pricing["per_1k_messages"]) * message_units)
                line_items.append({
                    "type": LineItemType.USAGE,
                    "description": f"Additional Messages ({message_overage:,} messages)",
                    "quantity": message_units,
                    "unit_price": pricing["per_1k_messages"],
                    "amount": message_cost
                })
            
            # Storage overage
            storage_overage = max(0, usage["storage_gb"] - pricing["included_storage_gb"])
            if storage_overage > 0:
                storage_cost = str(Decimal(pricing["per_gb_storage"]) * Decimal(str(storage_overage)))
                line_items.append({
                    "type": LineItemType.USAGE,
                    "description": f"Additional Storage ({storage_overage:.2f} GB)",
                    "quantity": int(storage_overage),
                    "unit_price": pricing["per_gb_storage"],
                    "amount": storage_cost
                })
            
            # Calculate totals
            subtotal = sum(Decimal(item["amount"]) for item in line_items)
            tax_rate = Decimal("0.0875")  # 8.75% sales tax (configurable)
            tax_amount = subtotal * tax_rate
            total_amount = subtotal + tax_amount
            
            # Add tax line item
            line_items.append({
                "type": LineItemType.TAX,
                "description": f"Sales Tax ({float(tax_rate * 100):.2f}%)",
                "quantity": 1,
                "unit_price": str(tax_amount),
                "amount": str(tax_amount)
            })
            
            # Create invoice
            invoice = Invoice(
                tenant_id=tenant_id,
                invoice_id=str(uuid.uuid4()),
                invoice_number=await self._generate_invoice_number(),
                invoice_date=datetime.utcnow().strftime("%Y-%m-%d"),
                status=InvoiceStatus.PENDING,
                period_start=period_start,
                period_end=period_end,
                customer_name=tenant.name,
                customer_email=tenant.admin_email,
                subtotal=str(subtotal),
                tax_amount=str(tax_amount),
                total_amount=str(total_amount),
                balance_due=str(total_amount),
                due_date=datetime.utcnow() + timedelta(days=30),
                line_items=line_items,
                created_at=datetime.utcnow()
            )
            
            # Save invoice
            await dynamodb.put_item(
                table_name=INVOICE_TABLE,
                item=invoice.dict()
            )
            
            # Generate PDF
            pdf_url = await self._generate_invoice_pdf(invoice)
            if pdf_url:
                await dynamodb.update_item(
                    table_name=INVOICE_TABLE,
                    key={"tenant_id": tenant_id, "invoice_id": invoice.invoice_id},
                    updates={"pdf_url": pdf_url, "pdf_generated_at": datetime.utcnow()}
                )
            
            # Auto charge if enabled and payment method exists
            if auto_charge:
                payment_method = await self.get_default_payment_method(tenant_id)
                if payment_method:
                    await self.charge_invoice(invoice.invoice_id, payment_method.method_id)
            
            # Send notification
            await self._send_invoice_notification(tenant, invoice)
            
            return invoice
            
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            raise
    
    async def charge_invoice(
        self,
        invoice_id: str,
        payment_method_id: str
    ) -> PaymentRecord:
        """
        Charge an invoice using a payment method
        
        Args:
            invoice_id: Invoice ID
            payment_method_id: Payment method ID
            
        Returns:
            Payment record
        """
        try:
            # Get invoice
            invoices = await self.get_invoices(limit=1000)
            invoice = next((i for i in invoices if i.invoice_id == invoice_id), None)
            if not invoice:
                raise ValueError("Invoice not found")
            
            # Get payment method
            payment_method = await self.get_payment_method(payment_method_id)
            if not payment_method:
                raise ValueError("Payment method not found")
            
            # Process payment based on processor
            if payment_method.processor == "stripe":
                payment_record = await self._process_stripe_payment(invoice, payment_method)
            else:
                raise ValueError(f"Unsupported payment processor: {payment_method.processor}")
            
            # Update invoice status
            if payment_record.status == "succeeded":
                await dynamodb.update_item(
                    table_name=INVOICE_TABLE,
                    key={"tenant_id": invoice.tenant_id, "invoice_id": invoice_id},
                    updates={
                        "status": InvoiceStatus.PAID,
                        "paid_amount": invoice.total_amount,
                        "balance_due": "0.00",
                        "payment_date": datetime.utcnow(),
                        "payment_reference": payment_record.processor_payment_id
                    }
                )
            
            return payment_record
            
        except Exception as e:
            logger.error(f"Error charging invoice: {e}")
            raise
    
    async def get_invoices(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[InvoiceStatus] = None,
        limit: int = 50
    ) -> List[Invoice]:
        """Get invoices"""
        try:
            if tenant_id:
                # Query by tenant
                result = await dynamodb.query(
                    table_name=INVOICE_TABLE,
                    key_condition_expression="tenant_id = :tenant_id",
                    expression_attribute_values={":tenant_id": tenant_id},
                    scan_index_forward=False,
                    limit=limit
                )
            else:
                # Scan all (admin only)
                result = await dynamodb.scan(
                    table_name=INVOICE_TABLE,
                    limit=limit
                )
            
            invoices = [Invoice(**item) for item in result.get("items", [])]
            
            # Filter by status if provided
            if status:
                invoices = [i for i in invoices if i.status == status]
            
            return invoices
            
        except Exception as e:
            logger.error(f"Error getting invoices: {e}")
            return []
    
    async def get_billing_history(self, tenant_id: str) -> BillingHistory:
        """Get complete billing history for a tenant"""
        try:
            # Get invoices
            invoices = await self.get_invoices(tenant_id, limit=100)
            
            # Get payments
            payments = await self._get_payments(tenant_id)
            
            # Calculate summary
            total_paid = sum(Decimal(i.paid_amount) for i in invoices)
            total_due = sum(Decimal(i.balance_due) for i in invoices)
            
            last_payment = max((p.created_at for p in payments), default=None)
            
            # Get next invoice date
            tenant = await tenant_service.get_tenant(tenant_id)
            next_invoice_date = None
            if tenant and tenant.subscription_expires_at:
                next_invoice_date = tenant.subscription_expires_at
            
            return BillingHistory(
                invoices=invoices,
                payments=payments,
                total_paid=str(total_paid),
                total_due=str(total_due),
                last_payment_date=last_payment,
                next_invoice_date=next_invoice_date,
                invoice_count=len(invoices),
                payment_count=len(payments),
                overdue_count=len([i for i in invoices if i.status == InvoiceStatus.OVERDUE])
            )
            
        except Exception as e:
            logger.error(f"Error getting billing history: {e}")
            return BillingHistory()
    
    async def add_payment_method(
        self,
        tenant_id: str,
        method_type: PaymentMethod,
        processor_method_id: str,
        details: Dict[str, Any],
        set_as_default: bool = True
    ) -> PaymentMethodInfo:
        """Add a payment method"""
        try:
            # Create payment method record
            method = PaymentMethodInfo(
                method_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                type=method_type,
                is_default=set_as_default,
                processor="stripe",  # Currently only Stripe
                processor_method_id=processor_method_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                **details
            )
            
            # If setting as default, unset other defaults
            if set_as_default:
                await self._unset_default_payment_methods(tenant_id)
            
            # Save payment method
            await dynamodb.put_item(
                table_name=PAYMENT_METHOD_TABLE,
                item=method.dict()
            )
            
            return method
            
        except Exception as e:
            logger.error(f"Error adding payment method: {e}")
            raise
    
    async def get_payment_methods(self, tenant_id: str) -> List[PaymentMethodInfo]:
        """Get payment methods for a tenant"""
        try:
            result = await dynamodb.query(
                table_name=PAYMENT_METHOD_TABLE,
                key_condition_expression="tenant_id = :tenant_id",
                expression_attribute_values={":tenant_id": tenant_id}
            )
            
            return [PaymentMethodInfo(**item) for item in result.get("items", [])]
            
        except Exception as e:
            logger.error(f"Error getting payment methods: {e}")
            return []
    
    async def get_default_payment_method(self, tenant_id: str) -> Optional[PaymentMethodInfo]:
        """Get default payment method"""
        methods = await self.get_payment_methods(tenant_id)
        return next((m for m in methods if m.is_default), None)
    
    async def get_payment_method(self, method_id: str) -> Optional[PaymentMethodInfo]:
        """Get a specific payment method"""
        try:
            # Scan for method (could optimize with GSI)
            result = await dynamodb.scan(
                table_name=PAYMENT_METHOD_TABLE,
                filter_expression="method_id = :method_id",
                expression_attribute_values={":method_id": method_id}
            )
            
            items = result.get("items", [])
            if items:
                return PaymentMethodInfo(**items[0])
            return None
            
        except Exception as e:
            logger.error(f"Error getting payment method: {e}")
            return None
    
    # Private helper methods
    
    async def _calculate_period_usage(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> Dict[str, Any]:
        """Calculate usage for a billing period"""
        try:
            # Get usage metrics
            metrics = await usage_service.get_usage_summary(
                tenant_id=tenant_id,
                start_date=period_start,
                end_date=period_end
            )
            
            return {
                "agent_count": metrics.get("max_agents", 0),
                "message_count": metrics.get("total_messages", 0),
                "storage_gb": metrics.get("storage_gb", 0.0),
                "api_calls": metrics.get("api_calls", 0)
            }
            
        except Exception as e:
            logger.error(f"Error calculating usage: {e}")
            return {
                "agent_count": 0,
                "message_count": 0,
                "storage_gb": 0.0,
                "api_calls": 0
            }
    
    async def _generate_invoice_number(self) -> str:
        """Generate unique invoice number"""
        # Format: INV-YYYYMM-XXXX
        prefix = f"INV-{datetime.utcnow().strftime('%Y%m')}"
        
        # Get count of invoices this month
        result = await dynamodb.query(
            table_name=INVOICE_TABLE,
            index_name="date-index",
            key_condition_expression="invoice_date >= :start",
            expression_attribute_values={
                ":start": datetime.utcnow().strftime("%Y-%m-01")
            }
        )
        
        count = len(result.get("items", [])) + 1
        return f"{prefix}-{count:04d}"
    
    async def _generate_invoice_pdf(self, invoice: Invoice) -> Optional[str]:
        """Generate PDF for invoice"""
        # TODO: Implement PDF generation
        # For now, return None
        return None
    
    async def _process_stripe_payment(
        self,
        invoice: Invoice,
        payment_method: PaymentMethodInfo
    ) -> PaymentRecord:
        """Process payment via Stripe"""
        try:
            # Create Stripe payment intent
            intent = stripe.PaymentIntent.create(
                amount=int(Decimal(invoice.total_amount) * 100),  # Convert to cents
                currency=invoice.currency.lower(),
                payment_method=payment_method.processor_method_id,
                customer=payment_method.processor_customer_id,
                description=f"Invoice {invoice.invoice_number}",
                metadata={
                    "tenant_id": invoice.tenant_id,
                    "invoice_id": invoice.invoice_id
                },
                confirm=True
            )
            
            # Create payment record
            payment = PaymentRecord(
                payment_id=str(uuid.uuid4()),
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.invoice_id,
                amount=invoice.total_amount,
                currency=invoice.currency,
                payment_method=payment_method.type,
                status=intent.status,
                processor="stripe",
                processor_payment_id=intent.id,
                processor_customer_id=payment_method.processor_customer_id,
                description=f"Payment for invoice {invoice.invoice_number}",
                created_at=datetime.utcnow()
            )
            
            # Save payment record
            await dynamodb.put_item(
                table_name=PAYMENT_TABLE,
                item=payment.dict()
            )
            
            return payment
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe payment error: {e}")
            
            # Create failed payment record
            payment = PaymentRecord(
                payment_id=str(uuid.uuid4()),
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.invoice_id,
                amount=invoice.total_amount,
                currency=invoice.currency,
                payment_method=payment_method.type,
                status="failed",
                processor="stripe",
                processor_payment_id="",
                failure_reason=str(e),
                created_at=datetime.utcnow()
            )
            
            await dynamodb.put_item(
                table_name=PAYMENT_TABLE,
                item=payment.dict()
            )
            
            raise
    
    async def _get_payments(self, tenant_id: str) -> List[PaymentRecord]:
        """Get payments for a tenant"""
        try:
            result = await dynamodb.query(
                table_name=PAYMENT_TABLE,
                key_condition_expression="tenant_id = :tenant_id",
                expression_attribute_values={":tenant_id": tenant_id},
                limit=100
            )
            
            return [PaymentRecord(**item) for item in result.get("items", [])]
            
        except Exception as e:
            logger.error(f"Error getting payments: {e}")
            return []
    
    async def _unset_default_payment_methods(self, tenant_id: str):
        """Unset default flag on all payment methods"""
        methods = await self.get_payment_methods(tenant_id)
        for method in methods:
            if method.is_default:
                await dynamodb.update_item(
                    table_name=PAYMENT_METHOD_TABLE,
                    key={"tenant_id": tenant_id, "method_id": method.method_id},
                    updates={"is_default": False}
                )
    
    async def _send_invoice_notification(self, tenant: Any, invoice: Invoice):
        """Send invoice notification"""
        try:
            # Get tenant users
            from api.services.user_tenant_service import user_tenant_service
            users = await user_tenant_service.get_tenant_users(tenant.id)
            
            for user in users:
                if user.is_admin:
                    notification = NotificationCreate(
                        user_id=user.user_id,
                        type=NotificationType.BILLING_PAYMENT_DUE,
                        priority=NotificationPriority.MEDIUM,
                        title=f"Invoice {invoice.invoice_number} Generated",
                        message=f"Your invoice for {invoice.total_amount} {invoice.currency} is ready.",
                        tenant_id=tenant.id,
                        resource_id=invoice.invoice_id,
                        resource_type="invoice",
                        action_url=f"/dashboard/billing/invoices/{invoice.invoice_id}",
                        action_label="View Invoice"
                    )
                    
                    await notification_service.create_notification(notification)
                    
        except Exception as e:
            logger.error(f"Error sending invoice notification: {e}")


# Create singleton instance
billing_service = BillingService()