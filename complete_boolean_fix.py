#!/usr/bin/env python3
"""
Complete boolean fix for DynamoDB - patches all models and services
"""

import importlib
import sys
from types import MethodType

def patch_all_models():
    """Patch all Pydantic models to convert boolean to int in dict() method"""
    modules_to_patch = [
        'models.tenant',
        'models.tenant_limits',
        'models.user_tenant',
        'models.channel_subscription',
        'models.terms_acceptance',
        'models.ssh_key',
        'models.usage',
        'models.channel',
        'models.agent'
    ]
    
    for module_name in modules_to_patch:
        try:
            module = importlib.import_module(module_name)
            for name in dir(module):
                obj = getattr(module, name)
                if hasattr(obj, '__mro__') and any('BaseModel' in str(base) for base in obj.__mro__):
                    # This is a Pydantic model, patch its dict method
                    original_dict = obj.dict
                    
                    def patched_dict(self, **kwargs):
                        result = original_dict(self, **kwargs)
                        return fix_booleans(result)
                    
                    obj.dict = patched_dict
                    print(f"Patched {module_name}.{name}.dict()")
        except Exception as e:
            print(f"Could not patch {module_name}: {e}")

def fix_booleans(data):
    """Recursively convert boolean values to integers"""
    if isinstance(data, dict):
        return {k: fix_booleans(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [fix_booleans(item) for item in data]
    elif isinstance(data, bool):
        return int(data)
    else:
        return data

def patch_dynamodb_service():
    """Apply patches to DynamoDB service"""
    from api.db import dynamodb
    
    # Patch put_item
    original_put = dynamodb.dynamodb.put_item
    
    async def patched_put(self, table_name, item, **kwargs):
        fixed_item = fix_booleans(item)
        print(f"[BOOLEAN_FIX] Putting item to {table_name} after boolean fix")
        return await original_put(self, table_name, fixed_item, **kwargs)
    
    dynamodb.dynamodb.put_item = MethodType(patched_put, dynamodb.dynamodb)
    
    # Patch update_item
    original_update = dynamodb.dynamodb.update_item
    
    async def patched_update(self, table_name, key, updates, **kwargs):
        fixed_key = fix_booleans(key)
        fixed_updates = fix_booleans(updates)
        print(f"[BOOLEAN_FIX] Updating item in {table_name} after boolean fix")
        return await original_update(self, table_name, fixed_key, fixed_updates, **kwargs)
    
    dynamodb.dynamodb.update_item = MethodType(patched_update, dynamodb.dynamodb)
    
    # Patch _convert_to_dynamodb_item
    original_convert = dynamodb.dynamodb._convert_to_dynamodb_item
    
    def patched_convert(self, item):
        fixed_item = fix_booleans(item)
        return original_convert(self, fixed_item)
    
    dynamodb.dynamodb._convert_to_dynamodb_item = MethodType(patched_convert, dynamodb.dynamodb)
    
    print("DynamoDB service patched successfully!")

# Apply all patches when module is imported
print("Applying complete boolean fix...")
patch_all_models()
patch_dynamodb_service()
print("Complete boolean fix applied successfully!")