#!/usr/bin/env python3
"""
Minimal boolean fix - just patches the DynamoDB conversion
"""

# Create a small patch file for the _convert_to_dynamodb_item method
PATCH_CODE = '''
# Insert this after line 70 in dynamodb.py
def _convert_to_dynamodb_item_fixed(self, item):
    """Convert Python objects to DynamoDB format with boolean fix"""
    if not item:
        return {}
        
    # First, recursively fix all boolean values to integers
    def fix_booleans(obj):
        if isinstance(obj, dict):
            return {k: fix_booleans(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [fix_booleans(v) for v in obj]
        elif isinstance(obj, bool):
            return int(obj)
        else:
            return obj
    
    fixed_item = fix_booleans(item)
    
    # Original conversion logic
    if not fixed_item:
        return {}
    
    dynamodb_item = {}
    for key, value in fixed_item.items():
        if value is None:
            dynamodb_item[key] = {"NULL": True}
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
    
    return dynamodb_item

# Replace the original method
DynamoDBService._convert_to_dynamodb_item = _convert_to_dynamodb_item_fixed
'''

if __name__ == "__main__":
    # Write the patch code to a file
    with open('/tmp/dynamodb_boolean_patch.py', 'w') as f:
        f.write(PATCH_CODE)
    print("Patch code written to /tmp/dynamodb_boolean_patch.py")