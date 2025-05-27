#!/bin/bash

# Deploy profile update to EC2

echo "Deploying profile updates to EC2..."

# Create the DynamoDB table first
echo "Creating user profiles table..."
./create_user_profiles_table.sh

# Deploy to EC2
INSTANCE_ID="i-0cd295d6b239ca775"

echo "Deploying updated backend code..."

# Create deployment package
echo "Creating deployment package..."
zip -r profile-update.zip \
    api/routes/profile_routes.py \
    api/services/profile_service.py \
    models/user_profile.py \
    api/routes/__init__.py

# Upload to S3
echo "Uploading to S3..."
aws s3 cp profile-update.zip s3://artcafe-deployment/profile-update.zip

# Deploy via SSM
echo "Deploying via SSM..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "sudo aws s3 cp s3://artcafe-deployment/profile-update.zip .",
        "sudo unzip -o profile-update.zip",
        "sudo rm profile-update.zip",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "sudo systemctl status artcafe-pubsub"
    ]' \
    --output json > deploy-command.json

# Get command ID
COMMAND_ID=$(jq -r '.Command.CommandId' deploy-command.json)
echo "Command ID: $COMMAND_ID"

# Wait for completion
echo "Waiting for deployment to complete..."
sleep 10

# Check status
aws ssm get-command-invocation \
    --command-id $COMMAND_ID \
    --instance-id $INSTANCE_ID \
    --query '[Status,StandardOutputContent]' \
    --output text

# Clean up
rm -f profile-update.zip deploy-command.json

echo "Deployment complete!"