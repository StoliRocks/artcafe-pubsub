#!/bin/bash

# Create production DynamoDB tables for ArtCafe.ai

echo "Creating production DynamoDB tables..."

# 1. Activity Logs Table
echo "Creating artcafe-activity-logs table..."
aws dynamodb create-table \
    --table-name artcafe-activity-logs \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=timestamp_activity_id,AttributeType=S \
        AttributeName=activity_type,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=timestamp_activity_id,KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "activity-type-index",
            "Keys": [
                {"AttributeName": "activity_type", "KeyType": "HASH"},
                {"AttributeName": "timestamp_activity_id", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

# 2. Agent Metrics Table
echo "Creating artcafe-agent-metrics table..."
aws dynamodb create-table \
    --table-name artcafe-agent-metrics \
    --attribute-definitions \
        AttributeName=tenant_agent_id,AttributeType=S \
        AttributeName=timestamp,AttributeType=N \
    --key-schema \
        AttributeName=tenant_agent_id,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

# 3. Notifications Table
echo "Creating artcafe-notifications table..."
aws dynamodb create-table \
    --table-name artcafe-notifications \
    --attribute-definitions \
        AttributeName=user_id,AttributeType=S \
        AttributeName=timestamp_notification_id,AttributeType=S \
        AttributeName=read_status,AttributeType=S \
    --key-schema \
        AttributeName=user_id,KeyType=HASH \
        AttributeName=timestamp_notification_id,KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "read-status-index",
            "Keys": [
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "read_status", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

# 4. Billing History Table
echo "Creating artcafe-billing-history table..."
aws dynamodb create-table \
    --table-name artcafe-billing-history \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=invoice_id,AttributeType=S \
        AttributeName=invoice_date,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=invoice_id,KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "date-index",
            "Keys": [
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "invoice_date", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

# 5. Search Index Table (for basic search without OpenSearch)
echo "Creating artcafe-search-index table..."
aws dynamodb create-table \
    --table-name artcafe-search-index \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=search_key,AttributeType=S \
        AttributeName=resource_type,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=search_key,KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "resource-type-index",
            "Keys": [
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "resource_type", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

echo "Waiting for tables to become active..."
for table in artcafe-activity-logs artcafe-agent-metrics artcafe-notifications artcafe-billing-history artcafe-search-index; do
    echo "Waiting for $table..."
    aws dynamodb wait table-exists --table-name $table --region us-east-1
done

echo "All tables created successfully!"

# Set up TTL for tables that need it
echo "Configuring TTL..."

# Activity logs - 30 days
aws dynamodb update-time-to-live \
    --table-name artcafe-activity-logs \
    --time-to-live-specification "Enabled=true,AttributeName=ttl" \
    --region us-east-1

# Agent metrics - 7 days
aws dynamodb update-time-to-live \
    --table-name artcafe-agent-metrics \
    --time-to-live-specification "Enabled=true,AttributeName=ttl" \
    --region us-east-1

# Notifications - 90 days
aws dynamodb update-time-to-live \
    --table-name artcafe-notifications \
    --time-to-live-specification "Enabled=true,AttributeName=ttl" \
    --region us-east-1

echo "TTL configuration complete!"
echo "Production tables setup complete!"