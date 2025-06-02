import logging
import secrets
import uuid
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from ..db import dynamodb
from config.settings import settings
from config.legal_versions import CURRENT_TERMS_VERSION, CURRENT_PRIVACY_VERSION
from auth import create_access_token
from models import Tenant, TenantCreate
from models.tenant import PaymentStatus, SubscriptionTier
from models.tenant_limits import SUBSCRIPTION_PLANS
from models.user_tenant import UserRole
from .terms_acceptance_service import terms_acceptance_service
from .user_tenant_service import user_tenant_service

logger = logging.getLogger(__name__)


class TenantService:
    """Service for tenant management"""
    
    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """
        Get tenant by ID
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Tenant or None if not found
        """
        try:
            # Get tenant from DynamoDB
            item = await dynamodb.get_item(
                table_name=settings.TENANT_TABLE_NAME,
                key={"id": tenant_id}
            )
            
            if not item:
                return None
                
            # Convert to Tenant model
            return Tenant(**item)
        except Exception as e:
            logger.error(f"Error getting tenant {tenant_id}: {e}")
            raise
            
    async def create_tenant(self, tenant_data: TenantCreate) -> Dict:
        """
        Create a new tenant
        
        Args:
            tenant_data: Tenant data
            
        Returns:
            Dict with tenant ID, API key, and admin token
        """
        try:
            # Generate tenant ID
            tenant_id = str(uuid.uuid4())
            
            # Generate API key
            api_key = f"art_{secrets.token_urlsafe(32)}"
            
            # Generate admin token
            admin_token_data = {
                "tenant_id": tenant_id,
                "role": "admin",
                "email": tenant_data.admin_email
            }
            admin_token = create_access_token(data=admin_token_data)
            
            # Prepare tenant data
            tenant_dict = tenant_data.dict()
            tenant_dict["id"] = tenant_id
            tenant_dict["status"] = "active"
            tenant_dict["api_key"] = api_key

            # Add payment and subscription information
            tenant_dict["payment_status"] = PaymentStatus.ACTIVE  # Default to active for all new tenants
            tenant_dict["subscription_expires_at"] = None  # No expiration for free plans
            tenant_dict["created_at"] = datetime.utcnow().isoformat()
            tenant_dict["last_payment_date"] = None

            # Set usage limits based on subscription tier
            tier = tenant_dict.get("subscription_tier", "free")  # Default to free tier
            tenant_dict["subscription_plan"] = tier  # Set the plan explicitly
            
            # Get subscription plan details
            plan = SUBSCRIPTION_PLANS.get(tier)
            if plan:
                # Apply limits from the plan
                tenant_dict["max_agents"] = plan.limits.max_agents
                tenant_dict["max_channels"] = plan.limits.max_channels
                tenant_dict["max_messages_per_day"] = plan.limits.max_messages_per_day
                tenant_dict["max_storage_gb"] = plan.limits.max_storage_gb
                tenant_dict["max_concurrent_connections"] = plan.limits.max_concurrent_connections
                tenant_dict["max_api_calls_per_minute"] = plan.limits.max_api_calls_per_minute
                tenant_dict["max_ssh_keys"] = plan.limits.max_ssh_keys
                # Feature flags - convert to numbers for DynamoDB
                tenant_dict["custom_domains_enabled"] = 1 if plan.limits.custom_domains_enabled else 0
                tenant_dict["advanced_analytics_enabled"] = 1 if plan.limits.advanced_analytics_enabled else 0
                tenant_dict["priority_support"] = 1 if plan.limits.priority_support else 0
            else:
                # Fallback to basic limits if tier not found
                logger.warning(f"Unknown subscription tier: {tier}, using basic limits")
                tenant_dict["max_agents"] = 5
                tenant_dict["max_channels"] = 10
                tenant_dict["max_messages_per_day"] = 1000

            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=settings.TENANT_TABLE_NAME,
                item=tenant_dict
            )
            
            # Create initial usage metrics
            await self._initialize_usage_metrics(tenant_id)
            
            # Initialize subscriber tracking
            await self._initialize_subscriber_tracking(tenant_id)
            
            # Create terms acceptance record if provided
            if tenant_data.terms_acceptance:
                try:
                    acceptance_data = tenant_data.terms_acceptance
                    logger.info(f"Creating terms acceptance with data: {acceptance_data}")
                    
                    # Ensure all values are strings or numbers, not booleans
                    acceptance_dict = {
                        "user_id": tenant_data.metadata.get("user_id", tenant_data.admin_email) if tenant_data.metadata else tenant_data.admin_email,
                        "email": tenant_data.admin_email,
                        "terms_version": acceptance_data.get("terms_version", CURRENT_TERMS_VERSION),
                        "privacy_version": acceptance_data.get("privacy_version", CURRENT_PRIVACY_VERSION),
                        "ip_address": acceptance_data.get("ip_address", "unknown"),
                        "user_agent": acceptance_data.get("user_agent", "unknown"),
                        "tenant_id": tenant_id
                    }
                    logger.info(f"Terms acceptance dict: {acceptance_dict}")
                    
                    await terms_acceptance_service.create_acceptance(**acceptance_dict)
                    logger.info(f"Created terms acceptance for tenant {tenant_id}")
                except Exception as e:
                    logger.error(f"Error creating terms acceptance: {e}")
                    # Don't fail tenant creation if terms acceptance fails
            
            # Create user-tenant mapping for the admin
            user_id = tenant_data.metadata.get("user_id") if tenant_data.metadata else None
            if user_id:
                await user_tenant_service.create_user_tenant_mapping(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=UserRole.OWNER,
                    user_email=tenant_data.admin_email,
                    tenant_name=tenant_data.name
                )
                logger.info(f"Created user-tenant mapping for owner {user_id}")
            
            return {
                "tenant_id": tenant_id,
                "api_key": api_key,
                "admin_token": admin_token,
                "success": 1  # Convert boolean to number for DynamoDB
            }
        except Exception as e:
            logger.error(f"Error creating tenant: {e}")
            raise
            
    async def _initialize_usage_metrics(self, tenant_id: str) -> None:
        """Initialize usage metrics for a new tenant"""
        today = datetime.utcnow().date().isoformat()

        # Create usage metrics record
        await dynamodb.put_item(
            table_name=settings.USAGE_METRICS_TABLE_NAME,
            item={
                "tenant_id": tenant_id,
                "date": today,
                "messages": 0,
                "api_calls": 0,
                "storage_mb": 0
            }
        )
        
    async def _initialize_subscriber_tracking(self, tenant_id: str) -> None:
        """Initialize subscriber tracking for a new tenant"""
        try:
            # Create a default system channel for administrative messages
            system_channel_id = f"channel-system-{str(uuid.uuid4()).lower()}"
            
            await dynamodb.put_item(
                table_name=settings.CHANNEL_TABLE_NAME,
                item={
                    "tenant_id": tenant_id,
                    "id": system_channel_id,
                    "name": "System Notifications",
                    "description": "Channel for system notifications and administrative messages",
                    "status": "active",
                    "subscriber_count": 0,
                    "active_subscribers": 0,
                    "total_messages": 0,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            # Create a default agent for system operations
            system_agent_id = f"agent-system-{str(uuid.uuid4()).lower()}"
            
            await dynamodb.put_item(
                table_name=settings.AGENT_TABLE_NAME,
                item={
                    "tenant_id": tenant_id,
                    "id": system_agent_id,
                    "name": "System Agent",
                    "type": "system",
                    "status": "online",
                    "channel_subscriptions": [system_channel_id],
                    "active_connections": 0,
                    "total_messages_sent": 0,
                    "total_messages_received": 0,
                    "last_seen": datetime.utcnow().isoformat(),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            # Subscribe system agent to system channel
            subscription_id = f"sub-{str(uuid.uuid4()).lower()}"
            
            await dynamodb.put_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                item={
                    "channel_id": system_channel_id,
                    "agent_id": system_agent_id,
                    "id": subscription_id,
                    "tenant_id": tenant_id,
                    "role": "admin",
                    "status": "active",
                    "permissions": {
                        "read": 1,  # Convert boolean to number for DynamoDB
                        "write": 1,
                        "publish": 1,
                        "subscribe": 1,
                        "manage": 1
                    },
                    "subscribed_at": datetime.utcnow().isoformat(),
                    "messages_sent": 0,
                    "messages_received": 0,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Initialized subscriber tracking for tenant {tenant_id}")
            
        except Exception as e:
            logger.error(f"Error initializing subscriber tracking for tenant {tenant_id}: {e}")
            # Don't fail tenant creation if subscriber tracking fails
            # This can be initialized later if needed

    async def update_payment_status(
        self,
        tenant_id: str,
        payment_status: str,
        payment_reference: Optional[str] = None
    ) -> Tenant:
        """
        Update tenant payment status

        Args:
            tenant_id: Tenant ID
            payment_status: New payment status
            payment_reference: Optional payment reference

        Returns:
            Updated tenant
        """
        try:
            # Get current tenant data
            tenant = await self.get_tenant(tenant_id)
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")

            # Update payment information
            update_data = {"payment_status": payment_status}

            # Only update payment date for paid plans
            if payment_status == PaymentStatus.ACTIVE and payment_reference:
                update_data["last_payment_date"] = datetime.utcnow().isoformat()
                update_data["payment_reference"] = payment_reference

            # Update in DynamoDB
            await dynamodb.update_item(
                table_name=settings.TENANT_TABLE_NAME,
                key={"id": tenant_id},
                updates=update_data
            )

            # Get updated tenant
            updated_tenant = await self.get_tenant(tenant_id)
            return updated_tenant

        except Exception as e:
            logger.error(f"Error updating tenant payment status: {e}")
            raise

    async def list_tenants(
        self,
        payment_status: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Tenant]:
        """
        List tenants with optional filtering

        Args:
            payment_status: Filter by payment status
            limit: Maximum number of tenants to return

        Returns:
            List of tenants
        """
        try:
            # Get tenants from DynamoDB
            # Note: This is a simple scan operation which won't be efficient for large datasets
            # For production, this should be replaced with a proper query using a GSI
            items = await dynamodb.scan(
                table_name=settings.TENANT_TABLE_NAME,
                limit=limit
            )

            # Convert to Tenant models
            tenants = [Tenant(**item) for item in items]

            # Filter by payment status if provided
            if payment_status:
                tenants = [t for t in tenants if t.payment_status == payment_status]

            return tenants

        except Exception as e:
            logger.error(f"Error listing tenants: {e}")
            raise

    async def check_expired_subscriptions(self) -> int:
        """
        Legacy method - no longer needed as free plans don't expire
        Kept for backward compatibility

        Returns:
            Always returns 0
        """
        # Free plans don't expire - they have usage limits instead
        # This method is kept for backward compatibility but does nothing
        return 0
    
    async def get_user_tenants(self, user_id: str) -> List[Tenant]:
        """
        Get all tenants for a specific user
        
        Args:
            user_id: User ID
            
        Returns:
            List of tenants the user has access to
        """
        try:
            # Get user-tenant mappings
            user_tenants = await user_tenant_service.get_user_tenants(user_id)
            
            # Get full tenant details for each mapping
            tenants = []
            for mapping in user_tenants:
                if mapping.active:  # This is checking a boolean attribute, not storing it in DynamoDB
                    tenant = await self.get_tenant(mapping.tenant_id)
                    if tenant:
                        # Add role information to the tenant object
                        tenant_dict = tenant.dict()
                        tenant_dict["user_role"] = mapping.role
                        tenants.append(Tenant(**tenant_dict))
            
            return tenants
            
        except Exception as e:
            logger.error(f"Error getting user tenants: {e}")
            return []


# Singleton instance
tenant_service = TenantService()

# Helper function for dependency injection
async def get_tenant(tenant_id: str) -> Optional[Tenant]:
    """Get tenant by ID"""
    return await tenant_service.get_tenant(tenant_id)