#!/usr/bin/env python3
"""
Migration script to add tenant limits and usage tracking to existing tenants.
"""

import asyncio
import logging
from datetime import datetime

from infrastructure.dynamodb_service import dynamodb
from config.settings import settings
from models.tenant_limits import SUBSCRIPTION_PLANS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_tenants():
    """Add limits and usage tracking to existing tenants"""
    
    try:
        # Scan all tenants
        result = await dynamodb.scan_items(
            table_name=settings.TENANT_TABLE_NAME
        )
        
        tenants = result.get("items", [])
        logger.info(f"Found {len(tenants)} tenants to migrate")
        
        for tenant in tenants:
            tenant_id = tenant.get("id")
            current_plan = tenant.get("subscription_plan", "free")
            
            # Get plan limits
            plan = SUBSCRIPTION_PLANS.get(current_plan, SUBSCRIPTION_PLANS["free"])
            
            # Prepare update
            updates = {
                "subscription_plan": current_plan,
                "limits": plan.limits.dict(),
                "usage": {
                    "agent_count": 0,
                    "messages_today": 0,
                    "storage_used_gb": 0.0,
                    "concurrent_connections": 0,
                    "api_calls_this_minute": 0,
                    "channel_count": 0,
                    "ssh_key_count": 0,
                    "last_reset": datetime.utcnow().isoformat(),
                    "last_api_call": datetime.utcnow().isoformat()
                }
            }
            
            # Count current resources
            try:
                # Count agents
                agents_result = await dynamodb.scan_items(
                    table_name=settings.AGENT_TABLE_NAME,
                    filter_expression="tenant_id = :tenant_id",
                    expression_values={":tenant_id": tenant_id}
                )
                updates["usage"]["agent_count"] = len(agents_result.get("items", []))
                
                # Count channels
                channels_result = await dynamodb.scan_items(
                    table_name=settings.CHANNEL_TABLE_NAME,
                    filter_expression="tenant_id = :tenant_id",
                    expression_values={":tenant_id": tenant_id}
                )
                updates["usage"]["channel_count"] = len(channels_result.get("items", []))
                
                # Count SSH keys
                keys_result = await dynamodb.scan_items(
                    table_name=settings.SSH_KEY_TABLE_NAME,
                    filter_expression="tenant_id = :tenant_id",
                    expression_values={":tenant_id": tenant_id}
                )
                updates["usage"]["ssh_key_count"] = len(keys_result.get("items", []))
                
            except Exception as e:
                logger.warning(f"Error counting resources for tenant {tenant_id}: {e}")
            
            # Update tenant
            await dynamodb.update_item(
                table_name=settings.TENANT_TABLE_NAME,
                key={"id": tenant_id},
                updates=updates
            )
            
            logger.info(f"Migrated tenant {tenant_id} to {current_plan} plan with limits")
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(migrate_tenants())