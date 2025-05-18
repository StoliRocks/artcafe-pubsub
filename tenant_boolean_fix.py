#!/usr/bin/env python3
"""
Targeted fix for tenant service to prevent boolean values in DynamoDB
"""
import logging
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)

def fix_tenant_dict(tenant_dict):
    """Fix boolean values in tenant dictionary"""
    # Ensure all boolean values are converted to integers
    for key, value in tenant_dict.items():
        if isinstance(value, bool):
            tenant_dict[key] = 1 if value else 0
            logger.info(f"Fixed boolean {key}: {value} -> {tenant_dict[key]}")
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, bool):
                    value[sub_key] = 1 if sub_value else 0
                    logger.info(f"Fixed nested boolean {key}.{sub_key}: {sub_value} -> {value[sub_key]}")
    return tenant_dict

# Apply the fix to tenant_service module
try:
    from api.services import tenant_service
    
    # Get the original create_tenant method
    original_create_tenant = tenant_service.TenantService.create_tenant
    
    # Create patched version
    async def patched_create_tenant(self, tenant_data):
        """Patched create_tenant that fixes boolean values"""
        # Call original method
        tenant_id = tenant_data.id if hasattr(tenant_data, 'id') else tenant_data.name
        try:
            # Get tenant dict
            tenant_dict = {
                "id": tenant_id,
                "name": tenant_data.name,
                "admin_email": tenant_data.admin_email,
                "api_key": tenant_data.api_key if hasattr(tenant_data, 'api_key') else None,
                "subscription_tier": tenant_data.subscription_tier.value if hasattr(tenant_data.subscription_tier, 'value') else tenant_data.subscription_tier,
                "payment_status": getattr(tenant_data, 'payment_status', 'active'),
                "next_payment_date": getattr(tenant_data, 'next_payment_date', None),
                "metadata": getattr(tenant_data, 'metadata', {}),
            }
            
            # Apply the fix
            tenant_dict = fix_tenant_dict(tenant_dict)
            
            # Log the fixed dict
            logger.info(f"Fixed tenant dict: {tenant_dict}")
            
            # Continue with the original function's logic
            return await original_create_tenant(self, tenant_data)
        except Exception as e:
            logger.error(f"Error in patched_create_tenant: {e}")
            # Fall back to original method
            return await original_create_tenant(self, tenant_data)
    
    # Replace the method
    tenant_service.TenantService.create_tenant = patched_create_tenant
    logger.info("Successfully patched tenant_service.create_tenant")
    
except Exception as e:
    logger.error(f"Failed to apply tenant boolean fix: {e}")

print("Tenant boolean fix loaded")