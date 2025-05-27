#!/bin/bash

# Create DynamoDB table for user profiles

echo "Creating artcafe-user-profiles table..."

aws dynamodb create-table \
    --table-name artcafe-user-profiles \
    --attribute-definitions \
        AttributeName=user_id,AttributeType=S \
    --key-schema \
        AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1

if [ $? -eq 0 ]; then
    echo "✓ Table created successfully"
else
    echo "✗ Failed to create table (may already exist)"
fi

# Wait for table to be active
echo "Waiting for table to become active..."
aws dynamodb wait table-exists --table-name artcafe-user-profiles --region us-east-1

# Check table status
echo "Checking table status..."
aws dynamodb describe-table --table-name artcafe-user-profiles --region us-east-1 --query 'Table.TableStatus' --output text

echo "Done!"