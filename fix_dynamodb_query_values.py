#!/usr/bin/env python3
import re

# Read the DynamoDB service file
with open('api/db/dynamodb.py', 'r') as f:
    content = f.read()

# Find the query_items method and fix the expression values conversion
# The current code tries to convert to DynamoDB format but doesn't do it correctly

# Replace the problematic conversion logic
old_pattern = r'''            # Convert expression values to DynamoDB format
            dynamo_values = self._convert_to_dynamodb_item\(
                \{k\[1:\]: v for k, v in expression_values\.items\(\)\}
            \)
            dynamo_expression_values = \{
                k: list\(v\.values\(\)\)\[0\] for k, v in zip\(
                    expression_values\.keys\(\), 
                    dynamo_values\.values\(\)
                \)
            \}'''

new_pattern = '''            # Convert expression values to DynamoDB format
            dynamo_expression_values = {}
            for k, v in expression_values.items():
                if isinstance(v, str):
                    dynamo_expression_values[k] = {"S": v}
                elif isinstance(v, (int, float)):
                    dynamo_expression_values[k] = {"N": str(v)}
                elif isinstance(v, bool):
                    dynamo_expression_values[k] = {"BOOL": v}
                else:
                    # For complex types, use the conversion method
                    converted = self._convert_to_dynamodb_item({k: v})
                    dynamo_expression_values[k] = converted[k]'''

# Apply the fix
content = re.sub(old_pattern, new_pattern, content, flags=re.DOTALL)

# Write the fixed content back
with open('api/db/dynamodb.py', 'w') as f:
    f.write(content)

print("Fixed DynamoDB expression value conversion")