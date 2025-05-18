import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from models.tenant import Tenant
from models.tenant_limits import TenantLimits, TenantUsage, SUBSCRIPTION_PLANS
from api.services.tenant_service import tenant_service
from api.db import dynamodb
from config.settings import settings

logger = logging.getLogger(__name__)


class LimitsService:
    """Service for checking and enforcing tenant usage limits"""
    
    async def check_limit(self, tenant_id: str, resource: str, current_count: int = 0, increment: int = 1) -> bool:
        """
        Check if adding resources would exceed limits
        
        Args:
            tenant_id: Tenant ID
            resource: Resource type (agents, channels, ssh_keys, etc.)
            current_count: Current count of resource
            increment: How many to add
            
        Returns:
            bool: True if within limits, False otherwise
        """
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get the limit for this resource
        limit_field = f"max_{resource}"
        limit = getattr(tenant.limits, limit_field, None)
        
        if limit is None:
            logger.warning(f"Unknown resource type: {resource}")
            return True  # Allow if we don't know the resource
        
        # Check if adding would exceed limit
        if current_count + increment > limit:
            return False
        
        return True
    
    async def enforce_limit(self, tenant_id: str, resource: str, current_count: int = 0, increment: int = 1) -> None:
        """
        Enforce usage limits, raising exception if exceeded
        
        Args:
            tenant_id: Tenant ID
            resource: Resource type
            current_count: Current count
            increment: How many to add
            
        Raises:
            HTTPException: If limit would be exceeded
        """
        if not await self.check_limit(tenant_id, resource, current_count, increment):
            tenant = await tenant_service.get_tenant(tenant_id)
            limit_field = f"max_{resource}"
            limit = getattr(tenant.limits, limit_field, 0)
            
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "Usage limit exceeded",
                    "resource": resource,
                    "current": current_count,
                    "limit": limit,
                    "plan": tenant.subscription_plan,
                    "message": f"Your {tenant.subscription_plan} plan allows up to {limit} {resource}. Please upgrade to add more."
                }
            )
    
    async def track_usage(self, tenant_id: str, metric: str, increment: int = 1) -> None:
        """
        Track usage metrics
        
        Args:
            tenant_id: Tenant ID
            metric: Metric to track (messages_today, api_calls_this_minute)
            increment: Amount to increment
        """
        try:
            tenant = await tenant_service.get_tenant(tenant_id)
            if not tenant:
                return
            
            # Update usage
            current_value = getattr(tenant.usage, metric, 0)
            setattr(tenant.usage, metric, current_value + increment)
            
            # Reset daily counters if needed
            if metric == "messages_today":
                if datetime.utcnow().date() > tenant.usage.last_reset.date():
                    tenant.usage.messages_today = increment
                    tenant.usage.last_reset = datetime.utcnow()
            
            # Reset per-minute counters
            elif metric == "api_calls_this_minute":
                if datetime.utcnow() > tenant.usage.last_api_call + timedelta(minutes=1):
                    tenant.usage.api_calls_this_minute = increment
                    tenant.usage.last_api_call = datetime.utcnow()
            
            # Save updated usage
            await dynamodb.update_item(
                table_name=settings.TENANT_TABLE_NAME,
                key={"id": tenant_id},
                updates={
                    "usage": tenant.usage.dict()
                }
            )
            
        except Exception as e:
            logger.error(f"Error tracking usage for tenant {tenant_id}: {e}")
    
    async def check_rate_limit(self, tenant_id: str, resource: str = "api_calls") -> bool:
        """
        Check if rate limit is exceeded
        
        Args:
            tenant_id: Tenant ID
            resource: Resource to check (api_calls, messages)
            
        Returns:
            bool: True if within rate limit, False if exceeded
        """
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            return True  # Allow if tenant not found
        
        if resource == "api_calls":
            # Check API calls per minute
            if datetime.utcnow() > tenant.usage.last_api_call + timedelta(minutes=1):
                # Reset counter
                tenant.usage.api_calls_this_minute = 0
                tenant.usage.last_api_call = datetime.utcnow()
            
            return tenant.usage.api_calls_this_minute < tenant.limits.max_api_calls_per_minute
        
        elif resource == "messages":
            # Check daily message limit
            if datetime.utcnow().date() > tenant.usage.last_reset.date():
                # Reset counter
                tenant.usage.messages_today = 0
                tenant.usage.last_reset = datetime.utcnow()
            
            return tenant.usage.messages_today < tenant.limits.max_messages_per_day
        
        return True
    
    async def get_usage_summary(self, tenant_id: str) -> Dict:
        """
        Get usage summary for tenant
        
        Returns:
            Dict with usage vs limits for all resources
        """
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get current counts from database
        agent_count = await self._count_resources(tenant_id, "agents")
        channel_count = await self._count_resources(tenant_id, "channels")
        ssh_key_count = await self._count_resources(tenant_id, "ssh_keys")
        
        return {
            "plan": tenant.subscription_plan,
            "usage": {
                "agents": {
                    "current": agent_count,
                    "limit": tenant.limits.max_agents,
                    "percentage": (agent_count / tenant.limits.max_agents * 100) if tenant.limits.max_agents > 0 else 0
                },
                "channels": {
                    "current": channel_count,
                    "limit": tenant.limits.max_channels,
                    "percentage": (channel_count / tenant.limits.max_channels * 100) if tenant.limits.max_channels > 0 else 0
                },
                "ssh_keys": {
                    "current": ssh_key_count,
                    "limit": tenant.limits.max_ssh_keys,
                    "percentage": (ssh_key_count / tenant.limits.max_ssh_keys * 100) if tenant.limits.max_ssh_keys > 0 else 0
                },
                "messages_today": {
                    "current": tenant.usage.messages_today,
                    "limit": tenant.limits.max_messages_per_day,
                    "percentage": (tenant.usage.messages_today / tenant.limits.max_messages_per_day * 100) if tenant.limits.max_messages_per_day > 0 else 0
                },
                "storage_gb": {
                    "current": tenant.usage.storage_used_gb,
                    "limit": tenant.limits.max_storage_gb,
                    "percentage": (tenant.usage.storage_used_gb / tenant.limits.max_storage_gb * 100) if tenant.limits.max_storage_gb > 0 else 0
                }
            },
            "features": {
                "custom_domains": tenant.limits.custom_domains_enabled,
                "advanced_analytics": tenant.limits.advanced_analytics_enabled,
                "priority_support": tenant.limits.priority_support
            }
        }
    
    async def _count_resources(self, tenant_id: str, resource_type: str) -> int:
        """Count resources of a specific type for a tenant"""
        table_map = {
            "agents": settings.AGENT_TABLE_NAME,
            "channels": settings.CHANNEL_TABLE_NAME,
            "ssh_keys": settings.SSH_KEY_TABLE_NAME
        }
        
        table_name = table_map.get(resource_type)
        if not table_name:
            return 0
        
        # Query the database (this is a simplified version)
        # In production, you might want to use a count query or maintain counters
        result = await dynamodb.scan_items(
            table_name=table_name,
            filter_expression="tenant_id = :tenant_id",
            expression_values={":tenant_id": tenant_id}
        )
        
        return len(result.get("items", []))


# Singleton instance
limits_service = LimitsService()