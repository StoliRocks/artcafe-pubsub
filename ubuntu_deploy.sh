#!/bin/bash

# Ubuntu EC2 deployment script for artcafe-pubsub

# Set variables
INSTANCE_ID="i-0cd295d6b239ca775"
SSH_KEY="agent-pubsub-key.pem"  # Assumes the key is in ~/.ssh/
IP_ADDRESS="3.229.1.223"
DEPLOY_PACKAGE="deploy_package.zip"
REMOTE_USER="ubuntu"  # Ubuntu instances use 'ubuntu' as the default user
SERVICE_NAME="artcafe-pubsub"
APP_DIR="/opt/artcafe/artcafe-pubsub"

# Make sure we're in the right directory
cd "$(dirname "$0")" || exit 1

echo "Creating deployment package..."
# Create a zip package with app code, excluding unnecessary files
zip -r $DEPLOY_PACKAGE . -x "*.git*" -x "*__pycache__*" -x "*.pytest_cache*" -x "*.env*" -x "*.zip"

echo "Checking if we can connect to the instance..."
# Check SSH connectivity
if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i ~/.ssh/$SSH_KEY $REMOTE_USER@$IP_ADDRESS "echo Connected successfully"; then
    echo "Cannot connect to the instance. Please check that the SSH key exists and the instance is reachable."
    exit 1
fi

echo "Transferring deployment package..."
# Copy zip package to the instance
scp -i ~/.ssh/$SSH_KEY $DEPLOY_PACKAGE $REMOTE_USER@$IP_ADDRESS:/tmp/

echo "Deploying application..."
# Execute remote commands to deploy the application
ssh -i ~/.ssh/$SSH_KEY $REMOTE_USER@$IP_ADDRESS << EOF
    echo "Checking app directory..."
    if [ ! -d "$APP_DIR" ]; then
        echo "Creating application directory..."
        sudo mkdir -p $APP_DIR
    fi

    echo "Extracting deployment package..."
    cd /tmp
    sudo unzip -o $DEPLOY_PACKAGE -d /tmp/app_extract

    echo "Copying files to application directory..."
    sudo cp -R /tmp/app_extract/* $APP_DIR/
    sudo chown -R $(whoami):$(whoami) $APP_DIR

    echo "Restarting service..."
    if systemctl list-units --type=service | grep -q "$SERVICE_NAME"; then
        sudo systemctl restart $SERVICE_NAME
    else
        echo "Warning: Service $SERVICE_NAME not found"
        
        # Check running processes
        echo "Checking for running processes..."
        ps aux | grep "artcafe"
        
        # Check existing services
        echo "Available services:"
        sudo systemctl list-units --type=service | grep -E "artcafe|pubsub"
    fi

    # Clean up
    echo "Cleaning up temporary files..."
    sudo rm -rf /tmp/app_extract
    sudo rm -f /tmp/$DEPLOY_PACKAGE
EOF

echo "Deployment completed!"