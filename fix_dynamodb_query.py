#!/usr/bin/env python3
import re

# Read the file
with open('api/services/user_tenant_service.py', 'r') as f:
    content = f.read()

# Replace key_condition_expression with key_condition
content = re.sub(r'key_condition_expression=', 'key_condition=', content)

# Replace expression_attribute_values with expression_values
content = re.sub(r'expression_attribute_values=', 'expression_values=', content)

# Write back the fixed content
with open('api/services/user_tenant_service.py', 'w') as f:
    f.write(content)

print("Fixed parameter names in user_tenant_service.py")