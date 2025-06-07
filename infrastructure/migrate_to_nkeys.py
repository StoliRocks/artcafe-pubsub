#!/usr/bin/env python3
"""
Migration script from SSH keys to NKeys
Transforms DynamoDB data to new schema with industry-standard naming
"""

import boto3
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
import nkeys
import base64
from ulid import ULID

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

def generate_nkey_pair():
    """Generate an NKey pair for an account or client"""
    # Generate user NKey (for clients)
    kp = nkeys.from_seed(nkeys.create_user_seed())
    return {
        'seed': kp.seed.decode('utf-8'),
        'public': kp.public_key.decode('utf-8')
    }

def generate_account_nkey():
    """Generate an account NKey pair"""
    # Generate account NKey
    kp = nkeys.from_seed(nkeys.create_account_seed())
    return {
        'seed': kp.seed.decode('utf-8'),
        'public': kp.public_key.decode('utf-8')
    }

def migrate_tenants_to_accounts():
    """Migrate artcafe-tenants to artcafe-accounts"""
    print("🔄 Migrating tenants to accounts...")
    
    old_table = dynamodb.Table('artcafe-tenants')
    new_table = dynamodb.Table('artcafe-accounts')
    
    # Scan all tenants
    response = old_table.scan()
    items = response.get('Items', [])
    
    migrated = 0
    for tenant in items:
        # Generate account NKey
        account_nkey = generate_account_nkey()
        
        # Transform the data
        account = {
            'account_id': tenant['tenant_id'],  # Keep same ID
            'name': tenant.get('organization_name', tenant.get('name', 'Unknown')),
            'nkey_public': account_nkey['public'],
            'issuer_key': account_nkey['seed'],  # In production, store securely!
            'created_at': tenant.get('created_at', datetime.now(timezone.utc).isoformat()),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'status': tenant.get('status', 'active'),
            'metadata': {
                'migrated_from': 'tenant',
                'migration_date': datetime.now(timezone.utc).isoformat(),
                'old_tenant_id': tenant['tenant_id']
            }
        }
        
        # Copy over any additional fields
        if 'subscription_tier' in tenant:
            account['subscription_tier'] = tenant['subscription_tier']
        if 'limits' in tenant:
            account['limits'] = tenant['limits']
        
        # Write to new table
        new_table.put_item(Item=account)
        migrated += 1
        print(f"  ✓ Migrated account: {account['name']} ({account['account_id']})")
    
    print(f"✅ Migrated {migrated} accounts\n")
    return migrated

def migrate_agents_to_clients():
    """Migrate artcafe-agents to artcafe-clients"""
    print("🔄 Migrating agents to clients...")
    
    old_table = dynamodb.Table('artcafe-agents')
    new_table = dynamodb.Table('artcafe-clients')
    
    # Scan all agents
    response = old_table.scan()
    items = response.get('Items', [])
    
    migrated = 0
    for agent in items:
        # Generate client NKey
        client_nkey = generate_nkey_pair()
        
        # Transform capabilities to permissions
        capabilities = agent.get('capabilities', [])
        permissions = {
            'publish': [],
            'subscribe': []
        }
        
        # Map capabilities to subject permissions
        if 'task_creation' in capabilities:
            permissions['publish'].append('*.tasks.*')
        if 'task_execution' in capabilities:
            permissions['subscribe'].append('*.tasks.*')
            permissions['publish'].append('*.events.task.*')
        if 'monitoring' in capabilities:
            permissions['subscribe'].append('*._sys.*')
        
        # Default permissions for all clients
        account_id = agent.get('tenant_id', agent.get('organization_id', 'unknown'))
        permissions['publish'].append(f'{account_id}.clients.{agent["agent_id"]}.evt')
        permissions['subscribe'].append(f'{account_id}.clients.{agent["agent_id"]}.cmd')
        
        # Transform the data
        client = {
            'client_id': agent['agent_id'],  # Keep same ID
            'account_id': account_id,
            'name': agent.get('name', 'Unnamed Client'),
            'nkey_public': client_nkey['public'],
            'permissions': permissions,
            'created_at': agent.get('created_at', datetime.now(timezone.utc).isoformat()),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'status': agent.get('status', 'offline'),
            'last_seen': agent.get('last_seen', None),
            'metadata': {
                'migrated_from': 'agent',
                'migration_date': datetime.now(timezone.utc).isoformat(),
                'old_capabilities': capabilities
            }
        }
        
        # Store the seed temporarily (user must retrieve it)
        seed_item = {
            'seed_id': f"{client['client_id']}_migration",
            'client_id': client['client_id'],
            'nkey_seed': client_nkey['seed'],
            'created_at': datetime.now(timezone.utc).isoformat(),
            'ttl': int(datetime.now(timezone.utc).timestamp()) + 86400  # 24 hours
        }
        
        seed_table = dynamodb.Table('artcafe-nkey-seeds')
        seed_table.put_item(Item=seed_item)
        
        # Write to new table
        new_table.put_item(Item=client)
        migrated += 1
        print(f"  ✓ Migrated client: {client['name']} ({client['client_id']})")
    
    print(f"✅ Migrated {migrated} clients\n")
    return migrated

def migrate_channels_to_subjects():
    """Migrate artcafe-channels to artcafe-subjects"""
    print("🔄 Migrating channels to subjects...")
    
    old_table = dynamodb.Table('artcafe-channels')
    new_table = dynamodb.Table('artcafe-subjects')
    
    # Scan all channels
    response = old_table.scan()
    items = response.get('Items', [])
    
    migrated = 0
    for channel in items:
        account_id = channel.get('tenant_id', channel.get('organization_id', 'unknown'))
        
        # Determine subject pattern based on channel type
        channel_name = channel.get('name', '').lower()
        if 'system' in channel_name:
            pattern = f"{account_id}._sys.*"
            stream = "SYSTEM"
        elif 'notification' in channel_name:
            pattern = f"{account_id}.notifications.*"
            stream = "NOTIFICATIONS"
        else:
            # Generic pattern
            channel_slug = channel.get('channel_id', str(ULID())).split('-')[-1]
            pattern = f"{account_id}.{channel_slug}.*"
            stream = channel_slug.upper()
        
        # Transform the data
        subject = {
            'subject_id': channel['channel_id'],  # Keep same ID
            'account_id': account_id,
            'name': channel.get('name', 'Unnamed Subject'),
            'pattern': pattern,
            'description': channel.get('description', ''),
            'stream': stream,
            'retention': {
                'age': 86400,  # 1 day default
                'messages': 10000,
                'bytes': 1048576  # 1MB
            },
            'created_at': channel.get('created_at', datetime.now(timezone.utc).isoformat()),
            'status': channel.get('status', 'active')
        }
        
        # Write to new table
        new_table.put_item(Item=subject)
        migrated += 1
        print(f"  ✓ Migrated subject: {subject['name']} → {pattern}")
    
    print(f"✅ Migrated {migrated} subjects\n")
    return migrated

def create_tables():
    """Create new DynamoDB tables"""
    print("📦 Creating new tables...")
    
    with open('dynamodb_new_schema.json', 'r') as f:
        schemas = json.load(f)
    
    client = boto3.client('dynamodb', region_name='us-east-1')
    
    for table_name, schema in schemas.items():
        try:
            # Check if table exists
            client.describe_table(TableName=schema['TableName'])
            print(f"  ⚠️  Table {schema['TableName']} already exists")
        except client.exceptions.ResourceNotFoundException:
            # Create table
            params = {
                'TableName': schema['TableName'],
                'KeySchema': schema['KeySchema'],
                'AttributeDefinitions': schema['AttributeDefinitions'],
                'BillingMode': schema['BillingMode']
            }
            
            if 'GlobalSecondaryIndexes' in schema:
                params['GlobalSecondaryIndexes'] = schema['GlobalSecondaryIndexes']
            
            if 'TimeToLiveSpecification' in schema:
                # TTL is set after table creation
                pass
            
            client.create_table(**params)
            print(f"  ✓ Created table: {schema['TableName']}")
            
            # Wait for table to be active
            waiter = client.get_waiter('table_exists')
            waiter.wait(TableName=schema['TableName'])
            
            # Enable TTL if specified
            if 'TimeToLiveSpecification' in schema:
                client.update_time_to_live(
                    TableName=schema['TableName'],
                    TimeToLiveSpecification=schema['TimeToLiveSpecification']
                )
    
    print("✅ All tables created\n")

def verify_migration():
    """Verify the migration was successful"""
    print("🔍 Verifying migration...")
    
    accounts_table = dynamodb.Table('artcafe-accounts')
    clients_table = dynamodb.Table('artcafe-clients')
    subjects_table = dynamodb.Table('artcafe-subjects')
    
    # Count items
    accounts = accounts_table.scan()['Count']
    clients = clients_table.scan()['Count']
    subjects = subjects_table.scan()['Count']
    
    print(f"  📊 Accounts: {accounts}")
    print(f"  📊 Clients: {clients}")
    print(f"  📊 Subjects: {subjects}")
    
    # Sample data
    print("\n  📋 Sample account:")
    sample_account = accounts_table.scan(Limit=1)['Items'][0] if accounts > 0 else None
    if sample_account:
        print(f"    - ID: {sample_account['account_id']}")
        print(f"    - Name: {sample_account['name']}")
        print(f"    - NKey: {sample_account['nkey_public'][:20]}...")
    
    print("\n✅ Migration verified\n")

def main():
    """Run the migration"""
    print("🚀 Starting NKey Migration\n")
    
    try:
        # Check if nkeys module is available
        import nkeys
    except ImportError:
        print("❌ Error: nkeys module not found")
        print("   Run: pip install nkeys")
        sys.exit(1)
    
    # Create new tables
    create_tables()
    
    # Run migrations
    migrate_tenants_to_accounts()
    migrate_agents_to_clients()
    migrate_channels_to_subjects()
    
    # Verify
    verify_migration()
    
    print("🎉 Migration complete!")
    print("\n⚠️  Important:")
    print("  1. Client NKey seeds are stored temporarily in artcafe-nkey-seeds table")
    print("  2. They expire in 24 hours - retrieve them for your clients!")
    print("  3. Update your application code to use new table/field names")
    print("  4. Test thoroughly before deleting old tables")

if __name__ == "__main__":
    main()