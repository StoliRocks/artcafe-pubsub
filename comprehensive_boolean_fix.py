"""
Comprehensive fix for boolean values in DynamoDB
"""

def fix_all_booleans_in_dict(data):
    """
    Recursively convert all boolean values to integers in a dictionary
    """
    if isinstance(data, dict):
        fixed_dict = {}
        for key, value in data.items():
            if isinstance(value, bool):
                fixed_dict[key] = 1 if value else 0
            elif isinstance(value, dict):
                fixed_dict[key] = fix_all_booleans_in_dict(value)
            elif isinstance(value, list):
                fixed_dict[key] = [fix_all_booleans_in_dict(item) if isinstance(item, dict) else item for item in value]
            else:
                fixed_dict[key] = value
        return fixed_dict
    else:
        return data


# Patch for DynamoDBService._convert_to_dynamodb_item
def patched_convert_to_dynamodb_item(self, item):
    """Convert Python dict to DynamoDB item format with boolean fix"""
    # First fix all booleans in the item
    fixed_item = fix_all_booleans_in_dict(item)
    
    result = {}
    for key, value in fixed_item.items():
        if isinstance(value, str):
            result[key] = {"S": value}
        elif isinstance(value, (int, float)):
            result[key] = {"N": str(value)}
        elif isinstance(value, bool):
            # This should never happen after fix_all_booleans_in_dict
            result[key] = {"N": "1" if value else "0"}
        elif isinstance(value, (list, tuple)):
            if not value:
                result[key] = {"L": []}
            elif all(isinstance(v, str) for v in value):
                result[key] = {"SS": list(value)}
            elif all(isinstance(v, (int, float)) for v in value):
                result[key] = {"NS": [str(v) for v in value]}
            else:
                result[key] = {"L": [self._convert_value(v) for v in value]}
        elif isinstance(value, dict):
            result[key] = {"M": self._convert_to_dynamodb_item(value)}
        elif value is None:
            result[key] = {"NULL": True}
        elif isinstance(value, (datetime, date)):
            result[key] = {"S": value.isoformat()}
        else:
            # Default to string conversion  
            result[key] = {"S": str(value)}
    return result