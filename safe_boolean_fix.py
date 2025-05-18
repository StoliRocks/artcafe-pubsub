#!/usr/bin/env python3
"""
Safe boolean fix for DynamoDB
"""

FIXED_CONVERT_METHOD = '''
    def _convert_to_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Convert Python dict to DynamoDB format with boolean fix"""
        # Fix boolean values before conversion
        def fix_booleans(obj):
            if isinstance(obj, dict):
                return {k: fix_booleans(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [fix_booleans(v) for v in obj]
            elif isinstance(obj, bool):
                return int(obj)
            else:
                return obj
        
        item = fix_booleans(item)
        
        # Original conversion logic
        if not item:
            return {}
            
        def convert_value(value):
            """Convert a single value to DynamoDB format"""
            if value is None:
                return {"NULL": True}
            elif isinstance(value, bool):
                # Should already be fixed, but just in case
                return {"N": str(int(value))}
            elif isinstance(value, (int, float)):
                return {"N": str(value)}
            elif isinstance(value, str):
                if value:
                    return {"S": value}
                else:
                    return {"S": " "}  # DynamoDB doesn't accept empty strings
            elif isinstance(value, bytes):
                return {"B": base64.b64encode(value).decode("utf-8")}
            elif isinstance(value, list):
                if not value:
                    return {"L": []}
                # Check if all items are strings
                if all(isinstance(x, str) for x in value):
                    return {"SS": value}
                # Check if all items are numbers
                elif all(isinstance(x, (int, float)) for x in value):
                    return {"NS": [str(x) for x in value]}
                else:
                    # Mixed list
                    return {"L": [self._convert_to_dynamodb_item({"value": x})["value"] for x in value]}
            elif isinstance(value, dict):
                return {"M": self._convert_to_dynamodb_item(value)}
            elif isinstance(value, (datetime, date)):
                return {"S": value.isoformat()}
            elif value is None:
                return {"NULL": True}
            else:
                # Try to JSON serialize
                try:
                    return {"S": json.dumps(value)}
                except:
                    logger.warning(f"Failed to serialize value for key {key}: {value}")
                    return {"S": str(value)}
        
        result = {}
        for key, value in item.items():
            result[key] = convert_value(value)
            
        return result
'''

if __name__ == "__main__":
    # Save the fixed method
    with open("/tmp/fixed_convert_method.py", "w") as f:
        f.write(FIXED_CONVERT_METHOD)
    print("Fixed convert method saved to /tmp/fixed_convert_method.py")