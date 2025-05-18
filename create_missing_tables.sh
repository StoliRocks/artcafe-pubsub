#!/bin/bash

# Create artcafe-user-tenants table
echo "Creating artcafe-user-tenants table..."
aws dynamodb create-table \
    --table-name artcafe-user-tenants \
    --attribute-definitions \
        AttributeName=id,AttributeType=S \
    --key-schema \
        AttributeName=id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --tags \
        Key=env,Value=dev \
        Key=application,Value=artcafe

# Wait for table to be created
echo "Waiting for artcafe-user-tenants table to be active..."
aws dynamodb wait table-exists --table-name artcafe-user-tenants

# Create artcafe-channel-subscriptions table
echo "Creating artcafe-channel-subscriptions table..."
aws dynamodb create-table \
    --table-name artcafe-channel-subscriptions \
    --attribute-definitions \
        AttributeName=id,AttributeType=S \
    --key-schema \
        AttributeName=id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --tags \
        Key=env,Value=dev \
        Key=application,Value=artcafe

# Wait for table to be created
echo "Waiting for artcafe-channel-subscriptions table to be active..."
aws dynamodb wait table-exists --table-name artcafe-channel-subscriptions

# Create artcafe-user-tenants-index table (for the new user-tenant mapping)
echo "Creating artcafe-user-tenants-index table..."
aws dynamodb create-table \
    --table-name artcafe-user-tenants-index \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --tags \
        Key=env,Value=dev \
        Key=application,Value=artcafe

# Wait for table to be created
echo "Waiting for artcafe-user-tenants-index table to be active..."
aws dynamodb wait table-exists --table-name artcafe-user-tenants-index

echo "All tables created successfully!"