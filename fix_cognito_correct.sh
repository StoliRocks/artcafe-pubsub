#!/bin/bash
set -e

echo "Fixing Cognito configuration with correct pool ID..."

INSTANCE_ID="i-0cd295d6b239ca775"

# Deploy the fix using SSM with correct Cognito pool
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "# Create new service file with correct Cognito config",
        "cat > /tmp/artcafe-pubsub.service << '\''EOF'\''",
        "[Unit]",
        "Description=ArtCafe PubSub API Service",
        "After=network.target",
        "",
        "[Service]",
        "Type=exec",
        "User=ubuntu",
        "WorkingDirectory=/opt/artcafe/artcafe-pubsub",
        "ExecStart=/opt/artcafe/artcafe-pubsub/venv/bin/python -m api.app",
        "Restart=always",
        "RestartSec=5",
        "StandardOutput=journal",
        "StandardError=journal",
        "Environment=PATH=/opt/artcafe/artcafe-pubsub/venv/bin:/usr/bin:/usr/local/bin",
        "Environment=PYTHONUNBUFFERED=1",
        "Environment=COGNITO_USER_POOL_ID=us-east-1_YUMQS3O2J",
        "Environment=COGNITO_CLIENT_ID=34srilubaou3u1hu626tmioodi",
        "Environment=COGNITO_REGION=us-east-1",
        "Environment=AWS_REGION=us-east-1",
        "Environment=NATS_SERVER_URL=localhost:4222",
        "Environment=FRONTEND_URL=https://artcafe.ai",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "EOF",
        
        "# Install new service file",
        "sudo mv /tmp/artcafe-pubsub.service /etc/systemd/system/artcafe-pubsub.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl restart artcafe-pubsub",
        
        "# Test token fetch",
        "sleep 5",
        "curl -s https://cognito-idp.us-east-1.amazonaws.com/us-east-1_YUMQS3O2J/.well-known/jwks.json | jq '.keys[0].kid'",
        
        "# Verify service",
        "sudo systemctl status artcafe-pubsub"
    ]}' \
    --output text \
    --query "Command.CommandId"