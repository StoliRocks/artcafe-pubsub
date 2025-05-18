"""
Script to fix boolean values in model dictionaries before DynamoDB storage
"""
import sys

# Add this to the user_tenant_service.py file at the top
def fix_boolean_for_dynamodb(data: dict) -> dict:
    """Convert boolean values to numeric for DynamoDB"""
    if 'active' in data and isinstance(data['active'], bool):
        data['active'] = 1 if data['active'] else 0
    return data


# Patch for the create_user_tenant_mapping function
# Replace this part in user_tenant_service.py:
"""
# Store in DynamoDB
await dynamodb.put_item(
    table_name=settings.USER_TENANT_TABLE_NAME,
    item=mapping_dict
)
"""

# With this:
"""
# Fix boolean values for DynamoDB
mapping_dict = fix_boolean_for_dynamodb(mapping_dict)

# Store in DynamoDB
await dynamodb.put_item(
    table_name=settings.USER_TENANT_TABLE_NAME,
    item=mapping_dict
)
"""