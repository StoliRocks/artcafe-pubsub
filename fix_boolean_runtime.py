#!/usr/bin/env python3
"""
Runtime fix for boolean values in DynamoDB operations.
This script patches the DynamoDB service to automatically convert boolean values.
"""

import sys
import os

# The patched version of the _convert_to_dynamodb_item method
PATCHED_CONVERT_METHOD = '''
    def _convert_to_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python dictionary to DynamoDB item format with boolean fix"""
        # First fix booleans recursively
        fixed_item = self._fix_booleans_for_dynamodb(item)
        
        # Original conversion code
        if not item:
            return {}
        
        dynamodb_item = {}
        for key, value in fixed_item.items():
            if value is None:
                dynamodb_item[key] = {"NULL": True}
            elif isinstance(value, bool):
                # This should already be fixed to int, but just in case
                dynamodb_item[key] = {"N": str(int(value))}
            elif isinstance(value, (int, float)):
                dynamodb_item[key] = {"N": str(value)}
            elif isinstance(value, str):
                dynamodb_item[key] = {"S": value}
            elif isinstance(value, dict):
                dynamodb_item[key] = {"M": self._convert_to_dynamodb_item(value)}
            elif isinstance(value, list):
                dynamodb_item[key] = {"L": [self._convert_to_dynamodb_item({"value": v})["value"] for v in value]}
            else:
                # Convert to string as fallback
                dynamodb_item[key] = {"S": str(value)}
        
        logger.debug(f"[BOOLEAN_FIX] Converted item: {dynamodb_item}")
        return dynamodb_item
'''

# Helper method to fix booleans
FIX_BOOLEANS_METHOD = '''
    def _fix_booleans_for_dynamodb(self, data: Any) -> Any:
        """Recursively convert all boolean values to numbers for DynamoDB"""
        if isinstance(data, dict):
            fixed = {}
            for key, value in data.items():
                logger.debug(f"[BOOLEAN_FIX] Processing key={key}, value={value}, type={type(value)}")
                fixed[key] = self._fix_booleans_for_dynamodb(value)
            return fixed
        elif isinstance(data, list):
            return [self._fix_booleans_for_dynamodb(item) for item in data]
        elif isinstance(data, bool):
            logger.info(f"[BOOLEAN_FIX] Converting boolean {data} to {int(data)}")
            return int(data)
        else:
            return data
'''

def apply_runtime_patch():
    """Apply the runtime patch to DynamoDB service"""
    # Import the module
    from api.db import dynamodb
    import types
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Apply the fix_booleans method
    exec(FIX_BOOLEANS_METHOD.replace('logger', 'logging.getLogger(__name__)'))
    dynamodb.dynamodb._fix_booleans_for_dynamodb = types.MethodType(
        locals()['_fix_booleans_for_dynamodb'], 
        dynamodb.dynamodb
    )
    
    # Apply the patched convert method
    exec(PATCHED_CONVERT_METHOD.replace('logger', 'logging.getLogger(__name__)'))
    dynamodb.dynamodb._convert_to_dynamodb_item = types.MethodType(
        locals()['_convert_to_dynamodb_item'], 
        dynamodb.dynamodb
    )
    
    print("Runtime patch applied successfully!")

if __name__ == "__main__":
    apply_runtime_patch()