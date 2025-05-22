#!/usr/bin/env python3
"""
Migration script to add capability-related fields to existing agents in DynamoDB.

This script:
1. Scans all agents in the agents table
2. Adds missing capability-related fields with default values
3. Updates the table schema if needed
"""

import os
import sys
import json
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_dynamodb_client():
    """Get DynamoDB client"""
    return boto3.client(
        'dynamodb',
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )


def get_dynamodb_resource():
    """Get DynamoDB resource"""
    return boto3.resource(
        'dynamodb',
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )


def migrate_agents_table():
    """Migrate agents table to add new capability fields"""
    dynamodb = get_dynamodb_resource()
    table_name = settings.AGENT_TABLE_NAME
    
    try:
        table = dynamodb.Table(table_name)
        logger.info(f"Starting migration for table: {table_name}")
        
        # Fields to add with default values
        default_fields = {
            'capabilities': [],
            'capability_definitions': None,
            'average_response_time_ms': None,
            'success_rate': None,
            'max_concurrent_tasks': 5,
            'max_memory_mb': None,
            'max_cpu_percent': None
        }
        
        # Scan all items
        scan_kwargs = {}
        updated_count = 0
        scanned_count = 0
        
        while True:
            response = table.scan(**scan_kwargs)
            items = response.get('Items', [])
            scanned_count += len(items)
            
            # Process each item
            for item in items:
                agent_id = item.get('id')
                tenant_id = item.get('tenant_id')
                
                if not agent_id or not tenant_id:
                    logger.warning(f"Skipping item without id or tenant_id: {item}")
                    continue
                
                # Check which fields need to be added
                updates = {}
                for field, default_value in default_fields.items():
                    if field not in item:
                        updates[field] = default_value
                
                # Update item if needed
                if updates:
                    try:
                        # Build update expression
                        update_parts = []
                        expression_values = {}
                        
                        for i, (field, value) in enumerate(updates.items()):
                            placeholder = f":val{i}"
                            update_parts.append(f"{field} = {placeholder}")
                            expression_values[placeholder] = value
                        
                        update_expression = "SET " + ", ".join(update_parts)
                        
                        # Update item
                        table.update_item(
                            Key={
                                'tenant_id': tenant_id,
                                'id': agent_id
                            },
                            UpdateExpression=update_expression,
                            ExpressionAttributeValues=expression_values
                        )
                        
                        updated_count += 1
                        logger.info(f"Updated agent {agent_id} in tenant {tenant_id}")
                        
                    except ClientError as e:
                        logger.error(f"Error updating agent {agent_id}: {e}")
            
            # Check if there are more items
            if 'LastEvaluatedKey' not in response:
                break
                
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        
        logger.info(f"Migration completed. Scanned: {scanned_count}, Updated: {updated_count}")
        
    except ClientError as e:
        logger.error(f"Error accessing table {table_name}: {e}")
        raise


def verify_migration():
    """Verify that migration was successful"""
    dynamodb = get_dynamodb_resource()
    table_name = settings.AGENT_TABLE_NAME
    
    try:
        table = dynamodb.Table(table_name)
        
        # Sample a few items to verify
        response = table.scan(Limit=5)
        items = response.get('Items', [])
        
        logger.info("\nVerification - Sample agents after migration:")
        for item in items:
            agent_id = item.get('id', 'unknown')
            capabilities = item.get('capabilities', 'MISSING')
            max_tasks = item.get('max_concurrent_tasks', 'MISSING')
            
            logger.info(f"Agent {agent_id}: capabilities={capabilities}, max_concurrent_tasks={max_tasks}")
        
    except ClientError as e:
        logger.error(f"Error verifying migration: {e}")


def main():
    """Main migration function"""
    logger.info("Starting agent capabilities migration...")
    
    # Check if table exists
    dynamodb_client = get_dynamodb_client()
    try:
        response = dynamodb_client.describe_table(TableName=settings.AGENT_TABLE_NAME)
        logger.info(f"Table {settings.AGENT_TABLE_NAME} exists with {response['Table']['ItemCount']} items")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.error(f"Table {settings.AGENT_TABLE_NAME} not found!")
            return
        else:
            raise
    
    # Run migration
    migrate_agents_table()
    
    # Verify migration
    verify_migration()
    
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    main()