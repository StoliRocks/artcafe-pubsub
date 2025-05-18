#!/bin/bash

# Deploy CORS fix to EC2

echo "Deploying CORS fix to ArtCafe PubSub Service..."

# EC2 instance details
EC2_HOST="3.229.1.223"
EC2_USER="ec2-user"
SERVICE_DIR="/home/ec2-user/artcafe-pubsub"

# Step 1: Copy updated files to EC2
echo "Step 1: Copying updated files to EC2..."
scp config/settings.py api/middleware.py ${EC2_USER}@${EC2_HOST}:${SERVICE_DIR}/
scp -r config api ${EC2_USER}@${EC2_HOST}:${SERVICE_DIR}/

# Step 2: Restart the service
echo "Step 2: Restarting the service..."
ssh ${EC2_USER}@${EC2_HOST} "cd ${SERVICE_DIR} && sudo systemctl restart artcafe-pubsub"

# Step 3: Check status
echo "Step 3: Checking service status..."
ssh ${EC2_USER}@${EC2_HOST} "sudo systemctl status artcafe-pubsub --no-pager"

# Step 4: Test the health endpoint
echo "Step 4: Testing health endpoint..."
sleep 2
if curl -s http://${EC2_HOST}:8000/health | grep -q "ok"; then
    echo "✅ Service is healthy!"
else
    echo "❌ Service health check failed!"
fi

echo ""
echo "CORS fix deployed!"
echo "Allowed origins now include:"
echo "  - http://localhost:3000"
echo "  - https://www.artcafe.ai"
echo "  - https://artcafe.ai"
echo "  - https://d1isgvgjiqe68i.cloudfront.net"
echo ""