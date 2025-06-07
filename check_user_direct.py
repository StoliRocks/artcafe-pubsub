import boto3
import os

# Set AWS credentials from environment or use defaults
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

dynamodb = boto3.client('dynamodb')

def check_user_tenants(user_id):
    """Check user tenant associations directly in DynamoDB."""
    try:
        # Query the user-tenant index table
        response = dynamodb.query(
            TableName='artcafe-user-tenant-index',
            KeyConditionExpression='pk = :pk',
            ExpressionAttributeValues={
                ':pk': {'S': f'USER#{user_id}'}
            }
        )
        
        items = response.get('Items', [])
        print(f"Found {len(items)} tenant associations for user {user_id}")
        
        for item in items:
            tenant_id = item.get('sk', {}).get('S', '').replace('TENANT#', '')
            mapping_id = item.get('mapping_id', {}).get('S', '')
            print(f"  - Tenant ID: {tenant_id}")
            print(f"    Mapping ID: {mapping_id}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # The user ID from the JWT token
    user_id = "f45854d8-20a1-70b8-a608-0d8bfd5f2cfc"
    check_user_tenants(user_id)
