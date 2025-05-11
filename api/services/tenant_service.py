import logging
import secrets
import ulid
from typing import Dict, Optional
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from auth import create_access_token
from models import Tenant, TenantCreate

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
            tenant_id = str(ulid.new())
            
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
            
            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=settings.TENANT_TABLE_NAME,
                item=tenant_dict
            )
            
            # Create initial usage metrics
            await self._initialize_usage_metrics(tenant_id)
            
            return {
                "tenant_id": tenant_id,
                "api_key": api_key,
                "admin_token": admin_token,
                "success": True
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


# Singleton instance
tenant_service = TenantService()