#!/bin/bash

# Update Lambda functions to use production tables
echo "Updating Lambda functions to use production tables..."

# Update artcafe-tenant-lambda-dev
aws lambda update-function-configuration \
    --function-name artcafe-tenant-lambda-dev \
    --environment '{"Variables":{
        "TABLE_NAME":"artcafe-tenants",
        "AGENT_TABLE_NAME":"artcafe-agents",
        "SSH_KEY_TABLE_NAME":"artcafe-ssh-keys",
        "CHANNEL_TABLE_NAME":"artcafe-channels",
        "USAGE_METRICS_TABLE_NAME":"artcafe-usage-metrics",
        "CHANNEL_SUBSCRIPTIONS_TABLE_NAME":"artcafe-channel-subscriptions",
        "USER_TENANT_TABLE_NAME":"artcafe-user-tenants"
    }}'

# Update artcafe-agent-lambda-dev
aws lambda update-function-configuration \
    --function-name artcafe-agent-lambda-dev \
    --environment '{"Variables":{
        "TABLE_NAME":"artcafe-agents",
        "TENANT_TABLE_NAME":"artcafe-tenants"
    }}'

# Update artcafe-auth-lambda-dev  
aws lambda update-function-configuration \
    --function-name artcafe-auth-lambda-dev \
    --environment '{"Variables":{
        "API_KEY_TABLE_NAME":"artcafe-api-keys",
        "TENANT_TABLE_NAME":"artcafe-tenants"
    }}'

echo "Lambda functions updated"

# Create environment file for EC2 instance
echo "Creating environment configuration for EC2..."
cat > /tmp/artcafe_env <<EOF
AGENT_TABLE_NAME=artcafe-agents
SSH_KEY_TABLE_NAME=artcafe-ssh-keys
CHANNEL_TABLE_NAME=artcafe-channels
TENANT_TABLE_NAME=artcafe-tenants
USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics
CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions
USER_TENANT_TABLE_NAME=artcafe-user-tenants
EOF

# Get the API server IP from CloudFormation
STACK_NAME="artcafe-pubsub"
API_IP=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`APIServerIP`].OutputValue' --output text)

if [ -z "$API_IP" ]; then
    echo "Could not find API server IP. Please update manually."
    exit 1
fi

echo "Found API server at $API_IP"

# Update EC2 instance environment
echo "Updating EC2 instance configuration..."
scp -o StrictHostKeyChecking=no /tmp/artcafe_env ec2-user@$API_IP:/tmp/

ssh -o StrictHostKeyChecking=no ec2-user@$API_IP << 'ENDSSH'
    sudo su -
    
    # Update systemd service with environment variables
    cat > /etc/systemd/system/artcafe-pubsub.service.d/override.conf <<EOF
[Service]
Environment="AGENT_TABLE_NAME=artcafe-agents"
Environment="SSH_KEY_TABLE_NAME=artcafe-ssh-keys"
Environment="CHANNEL_TABLE_NAME=artcafe-channels"
Environment="TENANT_TABLE_NAME=artcafe-tenants"
Environment="USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics"
Environment="CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions"
Environment="USER_TENANT_TABLE_NAME=artcafe-user-tenants"
EOF
    
    # Reload systemd and restart service
    systemctl daemon-reload
    systemctl restart artcafe-pubsub
    
    # Check service status
    systemctl status artcafe-pubsub
ENDSSH

echo "EC2 instance updated and service restarted"
echo "All components now using production tables"