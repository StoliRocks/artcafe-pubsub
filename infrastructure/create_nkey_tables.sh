#!/bin/bash
# Create new DynamoDB tables for NKey-based system

echo "🔧 Creating DynamoDB tables for NKey migration..."

# Create accounts table (formerly tenants)
aws dynamodb create-table \
    --table-name artcafe-accounts \
    --attribute-definitions \
        AttributeName=account_id,AttributeType=S \
        AttributeName=nkey_public,AttributeType=S \
    --key-schema \
        AttributeName=account_id,KeyType=HASH \
    --global-secondary-indexes \
        "IndexName=NKeyIndex,Keys=[{AttributeName=nkey_public,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5}" \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table artcafe-accounts already exists"

# Create clients table (formerly agents)
aws dynamodb create-table \
    --table-name artcafe-clients \
    --attribute-definitions \
        AttributeName=client_id,AttributeType=S \
        AttributeName=account_id,AttributeType=S \
        AttributeName=nkey_public,AttributeType=S \
    --key-schema \
        AttributeName=client_id,KeyType=HASH \
    --global-secondary-indexes \
        "IndexName=AccountIndex,Keys=[{AttributeName=account_id,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5}" \
        "IndexName=NKeyIndex,Keys=[{AttributeName=nkey_public,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5}" \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table artcafe-clients already exists"

# Create subjects table (formerly channels)
aws dynamodb create-table \
    --table-name artcafe-subjects \
    --attribute-definitions \
        AttributeName=subject_id,AttributeType=S \
        AttributeName=account_id,AttributeType=S \
    --key-schema \
        AttributeName=subject_id,KeyType=HASH \
    --global-secondary-indexes \
        "IndexName=AccountIndex,Keys=[{AttributeName=account_id,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5}" \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table artcafe-subjects already exists"

# Create temporary NKey seeds table (with TTL)
aws dynamodb create-table \
    --table-name artcafe-nkey-seeds \
    --attribute-definitions \
        AttributeName=seed_id,AttributeType=S \
    --key-schema \
        AttributeName=seed_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table artcafe-nkey-seeds already exists"

# Wait for tables to be created
echo "⏳ Waiting for tables to be active..."
aws dynamodb wait table-exists --table-name artcafe-accounts
aws dynamodb wait table-exists --table-name artcafe-clients
aws dynamodb wait table-exists --table-name artcafe-subjects
aws dynamodb wait table-exists --table-name artcafe-nkey-seeds

# Enable TTL on seeds table
echo "⏰ Enabling TTL on seeds table..."
aws dynamodb update-time-to-live \
    --table-name artcafe-nkey-seeds \
    --time-to-live-specification Enabled=true,AttributeName=ttl \
    --region us-east-1

echo "✅ All tables created successfully!"

# List tables
echo -e "\n📋 New tables:"
aws dynamodb list-tables --region us-east-1 | grep -E "(artcafe-accounts|artcafe-clients|artcafe-subjects|artcafe-nkey-seeds)"