from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum

from .base import BaseSchema


class InvoiceStatus(str, Enum):
    """Invoice status"""
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    """Payment method types"""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CRYPTO = "crypto"


class LineItemType(str, Enum):
    """Line item types"""
    SUBSCRIPTION = "subscription"
    USAGE = "usage"
    ADDON = "addon"
    CREDIT = "credit"
    DISCOUNT = "discount"
    TAX = "tax"


class Invoice(BaseSchema):
    """Invoice model"""
    tenant_id: str
    invoice_id: str
    invoice_number: str  # Human-readable invoice number
    invoice_date: str  # YYYY-MM-DD format for GSI
    
    # Status
    status: InvoiceStatus = InvoiceStatus.DRAFT
    
    # Billing period
    period_start: datetime
    period_end: datetime
    
    # Customer info
    customer_name: str
    customer_email: str
    customer_address: Optional[Dict[str, str]] = None
    
    # Amounts (stored as strings for DynamoDB Decimal compatibility)
    subtotal: str = "0.00"
    tax_amount: str = "0.00"
    discount_amount: str = "0.00"
    total_amount: str = "0.00"
    paid_amount: str = "0.00"
    balance_due: str = "0.00"
    
    # Currency
    currency: str = "USD"
    
    # Payment info
    payment_method: Optional[PaymentMethod] = None
    payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    
    # Due date
    due_date: datetime
    
    # Line items
    line_items: List[Dict[str, Any]] = []
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = {}
    notes: Optional[str] = None
    
    # PDF storage
    pdf_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    
    @validator('subtotal', 'tax_amount', 'discount_amount', 'total_amount', 'paid_amount', 'balance_due')
    def validate_amounts(cls, v):
        """Ensure amounts are valid decimal strings"""
        try:
            Decimal(v)
            return v
        except:
            raise ValueError("Invalid decimal amount")


class LineItem(BaseModel):
    """Invoice line item"""
    type: LineItemType
    description: str
    quantity: int = 1
    unit_price: str  # Decimal string
    amount: str  # Decimal string
    
    # Optional fields
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class InvoiceCreate(BaseModel):
    """Invoice creation model"""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    
    # Line items
    line_items: List[LineItem]
    
    # Optional
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class PaymentRecord(BaseSchema):
    """Payment record model"""
    payment_id: str
    tenant_id: str
    invoice_id: Optional[str] = None
    
    # Payment details
    amount: str  # Decimal string
    currency: str = "USD"
    payment_method: PaymentMethod
    
    # Status
    status: str  # succeeded, failed, pending
    
    # Payment processor info
    processor: str  # stripe, paypal, etc.
    processor_payment_id: str
    processor_customer_id: Optional[str] = None
    
    # Additional info
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    
    # Failure info
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None


class BillingHistory(BaseModel):
    """Billing history for dashboard"""
    invoices: List[Invoice] = []
    payments: List[PaymentRecord] = []
    
    # Summary
    total_paid: str = "0.00"
    total_due: str = "0.00"
    last_payment_date: Optional[datetime] = None
    next_invoice_date: Optional[datetime] = None
    
    # Stats
    invoice_count: int = 0
    payment_count: int = 0
    overdue_count: int = 0


class PaymentMethodInfo(BaseModel):
    """Payment method information"""
    method_id: str
    tenant_id: str
    
    # Method details
    type: PaymentMethod
    is_default: bool = False
    
    # Card info (if applicable)
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None
    
    # PayPal info (if applicable)
    paypal_email: Optional[str] = None
    
    # Bank info (if applicable)
    bank_name: Optional[str] = None
    bank_last4: Optional[str] = None
    
    # Processor info
    processor: str  # stripe, paypal, etc.
    processor_method_id: str
    
    # Metadata
    created_at: datetime
    updated_at: datetime


class UsageRecord(BaseSchema):
    """Usage record for billing calculations"""
    tenant_id: str
    usage_id: str
    
    # Period
    period_start: datetime
    period_end: datetime
    
    # Usage metrics
    agent_count: int = 0
    message_count: int = 0
    storage_bytes: int = 0
    compute_seconds: int = 0
    api_calls: int = 0
    
    # Calculated costs (as decimal strings)
    agent_cost: str = "0.00"
    message_cost: str = "0.00"
    storage_cost: str = "0.00"
    compute_cost: str = "0.00"
    api_cost: str = "0.00"
    total_cost: str = "0.00"
    
    # Status
    billed: bool = False
    invoice_id: Optional[str] = None


class SubscriptionInfo(BaseModel):
    """Current subscription information"""
    tenant_id: str
    plan_id: str
    plan_name: str
    
    # Status
    status: str  # active, cancelled, expired
    
    # Billing
    billing_cycle: str  # monthly, yearly
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    
    # Pricing (as decimal strings)
    base_price: str
    usage_charges: str = "0.00"
    total_price: str
    
    # Limits
    included_agents: int
    included_messages: int
    included_storage_gb: int
    
    # Current usage
    used_agents: int = 0
    used_messages: int = 0
    used_storage_gb: float = 0
    
    # Payment method
    payment_method_id: Optional[str] = None
    
    # Processor info
    processor_subscription_id: Optional[str] = None