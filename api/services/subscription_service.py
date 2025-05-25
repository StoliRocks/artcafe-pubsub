import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import ulid

from models.subscription import Subscription, SubscriptionCreate, SubscriptionResponse, SubscriptionStatus, SubscriptionTier
from api.db.dynamodb import DynamoDBService

# Create DynamoDB instance
dynamodb = DynamoDBService()

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Service for managing subscriptions"""
    
    @staticmethod
    async def get_current_subscription(tenant_id: str, user_id: str) -> Optional[SubscriptionResponse]:
        """Get the current active subscription for a user"""
        try:
            # Query subscriptions by tenant_id and filter for active status
            items = await dynamodb.query_items(
                "subscriptions",
                partition_key="tenant_id",
                partition_value=tenant_id,
                filter_expression="user_id = :user_id AND #status = :status",
                expression_values={
                    ":user_id": user_id,
                    ":status": SubscriptionStatus.ACTIVE
                },
                expression_names={
                    "#status": "status"  # status is a reserved word
                }
            )
            
            if not items:
                # Return free tier subscription if no active subscription found
                return SubscriptionResponse(
                    id="free-tier",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    subscription_id=None,
                    plan_id=None,
                    tier_name="Starter",  # Using correct tier name from pricing.js
                    billing_cycle="monthly",
                    status=SubscriptionStatus.ACTIVE,
                    start_date=datetime.utcnow(),
                    end_date=None,
                    amount=0.0,
                    currency="USD",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            
            # Return the first active subscription (there should only be one)
            subscription = items[0]
            return SubscriptionResponse(**subscription)
            
        except Exception as e:
            logger.error(f"Error getting current subscription: {e}")
            # Return free tier on error
            return SubscriptionResponse(
                id="free-tier",
                tenant_id=tenant_id,
                user_id=user_id,
                subscription_id=None,
                plan_id=None,
                tier_name="Starter",  # Using correct tier name from pricing.js
                billing_cycle="monthly",
                status=SubscriptionStatus.ACTIVE,
                start_date=datetime.utcnow(),
                end_date=None,
                amount=0.0,
                currency="USD",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
    
    @staticmethod
    async def create_subscription(
        tenant_id: str,
        user_id: str,
        subscription_data: SubscriptionCreate
    ) -> SubscriptionResponse:
        """Create a new subscription"""
        try:
            # Cancel any existing active subscriptions
            existing = await SubscriptionService.get_current_subscription(tenant_id, user_id)
            if existing and existing.id != "free-tier":
                await SubscriptionService.cancel_subscription(tenant_id, existing.subscription_id)
            
            # Create new subscription
            subscription = Subscription(
                tenant_id=tenant_id,
                user_id=user_id or subscription_data.user_id,
                subscription_id=subscription_data.subscription_id,
                plan_id=subscription_data.plan_id,
                tier_name=subscription_data.tier_name,
                billing_cycle=subscription_data.billing_cycle,
                status=SubscriptionStatus.ACTIVE,
                amount=SubscriptionService._get_plan_amount(subscription_data.plan_id),
                currency="USD"
            )
            
            # Save to DynamoDB
            subscription_dict = subscription.model_dump()
            subscription_dict["id"] = str(ulid.new())
            
            await dynamodb.put_item("subscriptions", subscription_dict)
            
            return SubscriptionResponse(**subscription_dict)
            
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            raise
    
    @staticmethod
    async def cancel_subscription(tenant_id: str, subscription_id: str) -> bool:
        """Cancel a subscription"""
        try:
            # Find the subscription
            items = await dynamodb.query_items(
                "subscriptions",
                partition_key="tenant_id",
                partition_value=tenant_id,
                filter_expression="subscription_id = :sub_id",
                expression_values={
                    ":sub_id": subscription_id
                }
            )
            
            if not items:
                logger.warning(f"Subscription not found: {subscription_id}")
                return False
            
            subscription = items[0]
            
            # Update subscription status
            subscription["status"] = SubscriptionStatus.CANCELLED
            subscription["cancelled_at"] = datetime.utcnow().isoformat()
            subscription["updated_at"] = datetime.utcnow().isoformat()
            
            # Save updated subscription
            await dynamodb.put_item("subscriptions", subscription)
            
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling subscription: {e}")
            raise
    
    @staticmethod
    async def get_organization_subscriptions(tenant_id: str) -> List[SubscriptionResponse]:
        """Get all subscriptions for an organization"""
        try:
            items = await dynamodb.query_items(
                "subscriptions",
                partition_key="tenant_id",
                partition_value=tenant_id
            )
            
            return [SubscriptionResponse(**item) for item in items]
            
        except Exception as e:
            logger.error(f"Error getting organization subscriptions: {e}")
            return []
    
    @staticmethod
    def _get_plan_amount(plan_id: str) -> float:
        """Get the amount for a plan ID"""
        # PayPal plan ID to amount mapping from pricing.js
        plan_amounts = {
            # Starter plans (Free)
            'P-2MX74475V9687691NNAWRYIA': 0.0,    # Starter monthly
            'P-5C2917741Y8188153NAXS4OI': 0.0,    # Starter annually
            
            # Scale plans
            'P-45199968FW821915CNAWR2NQ': 99.0,   # Scale monthly
            'P-61H36713YF2056340NAXS3FQ': 990.0,  # Scale annually (with discount)
        }
        return plan_amounts.get(plan_id, 0.0)