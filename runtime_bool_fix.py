#!/usr/bin/env python3
"""
Runtime boolean fix for DynamoDB operations.
This patches the DynamoDB service to automatically convert booleans to integers.
"""

import logging

logger = logging.getLogger(__name__)

def patch_dynamodb_service():
    """Apply runtime patch to fix boolean values in DynamoDB operations"""
    from api.db import dynamodb
    
    # Store original methods
    original_convert = dynamodb.dynamodb._convert_to_dynamodb_item
    original_update = dynamodb.dynamodb.update_item
    original_put = dynamodb.dynamodb.put_item
    
    def fix_booleans(data):
        """Recursively convert boolean values to integers"""
        if isinstance(data, dict):
            return {k: fix_booleans(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [fix_booleans(item) for item in data]
        elif isinstance(data, bool):
            logger.info(f"[RUNTIME_FIX] Converting boolean {data} to {int(data)}")
            return int(data)
        else:
            return data
    
    # Patch _convert_to_dynamodb_item
    def patched_convert(self, item):
        fixed_item = fix_booleans(item)
        logger.debug(f"[RUNTIME_FIX] Fixed item before conversion: {fixed_item}")
        return original_convert(self, fixed_item)
    
    # Patch put_item
    async def patched_put(self, table_name, item, **kwargs):
        fixed_item = fix_booleans(item)
        logger.info(f"[RUNTIME_FIX] Putting item to {table_name} after boolean fix")
        logger.debug(f"[RUNTIME_FIX] Fixed item: {fixed_item}")
        return await original_put(self, table_name, fixed_item, **kwargs)
    
    # Patch update_item
    async def patched_update(self, table_name, key, updates, **kwargs):
        fixed_key = fix_booleans(key)
        fixed_updates = fix_booleans(updates)
        logger.info(f"[RUNTIME_FIX] Updating item in {table_name} after boolean fix")
        return await original_update(self, table_name, fixed_key, fixed_updates, **kwargs)
    
    # Apply patches
    dynamodb.dynamodb._convert_to_dynamodb_item = patched_convert
    dynamodb.dynamodb.put_item = patched_put
    dynamodb.dynamodb.update_item = patched_update
    
    logger.info("[RUNTIME_FIX] Boolean fix patches applied successfully!")
    print("[RUNTIME_FIX] Boolean fix patches applied successfully!")

# Apply patch when module is imported
patch_dynamodb_service()