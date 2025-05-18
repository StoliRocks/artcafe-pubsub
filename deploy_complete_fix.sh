#!/bin/bash
set -e

echo "Deploying complete fix for artcafe-pubsub service..."

# EC2 instance details
INSTANCE_ID="i-0cd295d6b239ca775"
SERVICE_DIR="/opt/artcafe/artcafe-pubsub"

# Cognito configuration from the frontend token
COGNITO_USER_POOL_ID="us-east-1_PStcs21bo"
COGNITO_CLIENT_ID="nhu1bm1gi24coii7kk1u481k6"

# Create deploy package
cd /home/stvwhite/projects/artcafe/artcafe-pubsub

# Update service file with environment variables
cat > artcafe-pubsub.service << 'EOF'
[Unit]
Description=ArtCafe PubSub API Service
After=network.target

[Service]
Type=exec
User=ubuntu
WorkingDirectory=/opt/artcafe/artcafe-pubsub
ExecStart=/opt/artcafe/artcafe-pubsub/venv/bin/python -m api.app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PATH=/opt/artcafe/artcafe-pubsub/venv/bin:/usr/bin:/usr/local/bin
Environment=PYTHONUNBUFFERED=1
Environment=COGNITO_USER_POOL_ID=us-east-1_PStcs21bo
Environment=COGNITO_CLIENT_ID=nhu1bm1gi24coii7kk1u481k6
Environment=COGNITO_REGION=us-east-1
Environment=AWS_REGION=us-east-1
Environment=NATS_SERVER_URL=localhost:4222
Environment=FRONTEND_URL=https://artcafe.ai

[Install]
WantedBy=multi-user.target
EOF

# Deploy the fix using SSM
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "cd /opt/artcafe/artcafe-pubsub",
        
        "# Backup current service file",
        "sudo cp /etc/systemd/system/artcafe-pubsub.service /etc/systemd/system/artcafe-pubsub.service.bak",
        
        "# Update service with environment variables",
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
        "Environment=COGNITO_USER_POOL_ID=us-east-1_PStcs21bo",
        "Environment=COGNITO_CLIENT_ID=nhu1bm1gi24coii7kk1u481k6",
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
        
        "# Verify service is running",
        "sleep 5",
        "sudo systemctl status artcafe-pubsub",
        "sudo journalctl -u artcafe-pubsub -n 10"
    ]}' \
    --output text \
    --query "Command.CommandId"

echo "Deployment initiated. Monitor the command execution..."