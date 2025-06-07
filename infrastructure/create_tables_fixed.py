#!/usr/bin/env python3
"""Create new DynamoDB tables for NKey-based system"""

import boto3
import json
from time import sleep

dynamodb = boto3.client('dynamodb', region_name='us-east-1')

def create_table_if_not_exists(table_config):
    """Create a table if it doesn't exist"""
    table_name = table_config['TableName']
    
    try:
        # Check if table exists
        dynamodb.describe_table(TableName=table_name)
        print(f"⚠️  Table {table_name} already exists")
        return False
    except dynamodb.exceptions.ResourceNotFoundException:
        # Create table
        print(f"📦 Creating table {table_name}...")
        
        # Basic parameters
        params = {
            'TableName': table_name,
            'KeySchema': table_config['KeySchema'],
            'AttributeDefinitions': table_config['AttributeDefinitions'],
            'BillingMode': table_config['BillingMode']
        }
        
        # Add GSIs if present
        if 'GlobalSecondaryIndexes' in table_config:
            # Fix the Keys -> KeySchema issue
            gsis = []
            for gsi in table_config['GlobalSecondaryIndexes']:
                fixed_gsi = {
                    'IndexName': gsi['IndexName'],
                    'KeySchema': gsi['Keys'],  # Rename Keys to KeySchema
                    'Projection': gsi['Projection']
                }
                # Remove provisioned throughput for PAY_PER_REQUEST mode
                gsis.append(fixed_gsi)
            params['GlobalSecondaryIndexes'] = gsis
        
        dynamodb.create_table(**params)
        print(f"✅ Created table {table_name}")
        
        # Wait for table to be active
        waiter = dynamodb.get_waiter('table_exists')
        waiter.wait(TableName=table_name)
        
        # Enable TTL if specified
        if 'TimeToLiveSpecification' in table_config:
            dynamodb.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification=table_config['TimeToLiveSpecification']
            )
            print(f"⏰ Enabled TTL on {table_name}")
        
        return True

def main():
    """Create all tables"""
    print("🔧 Creating DynamoDB tables for NKey system...")
    
    # Load schema
    with open('dynamodb_new_schema.json', 'r') as f:
        schemas = json.load(f)
    
    created_count = 0
    for table_type, config in schemas.items():
        if create_table_if_not_exists(config):
            created_count += 1
    
    print(f"\n✅ Created {created_count} new tables")
    
    # List all artcafe tables
    print("\n📋 Current ArtCafe tables:")
    response = dynamodb.list_tables()
    artcafe_tables = [t for t in response['TableNames'] if t.startswith('artcafe-')]
    for table in sorted(artcafe_tables):
        print(f"  - {table}")

if __name__ == "__main__":
    main()