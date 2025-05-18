#!/bin/bash
# Deploy script for ArtCafe PubSub with NATS enabled
# This script captures the current server configuration

set -e

# Configuration
INSTANCE_ID="i-0cd295d6b239ca775"
INSTANCE_IP="3.229.1.223"
KEY_PATH="~/.ssh/agent-pubsub-key.pem"
SERVICE_PATH="/opt/artcafe/artcafe-pubsub"

echo "=== Deploying ArtCafe PubSub with NATS ==="

# Step 1: Deploy application files
echo "1. Deploying application files..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'venv' \
    -e "ssh -i $KEY_PATH" \
    . ubuntu@$INSTANCE_IP:$SERVICE_PATH/

# Step 2: Install Python dependencies
echo "2. Installing Python dependencies..."
ssh -i $KEY_PATH ubuntu@$INSTANCE_IP << 'EOF'
cd /opt/artcafe/artcafe-pubsub
source venv/bin/activate
pip install -r requirements.txt
EOF

# Step 3: Ensure NATS is installed and running
echo "3. Checking NATS installation..."
ssh -i $KEY_PATH ubuntu@$INSTANCE_IP << 'EOF'
# Check if NATS is installed
if ! command -v /usr/local/bin/nats-server &> /dev/null; then
    echo "Installing NATS server..."
    # Get the correct architecture
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ]; then
        NATS_ARCH="arm64"
    else
        NATS_ARCH="amd64"
    fi
    
    # Download and install NATS
    curl -L https://github.com/nats-io/nats-server/releases/download/v2.10.18/nats-server-v2.10.18-linux-${NATS_ARCH}.zip -o /tmp/nats-server.zip
    cd /tmp && unzip -o nats-server.zip
    sudo mv /tmp/nats-server-v2.10.18-linux-${NATS_ARCH}/nats-server /usr/local/bin/
    sudo chmod +x /usr/local/bin/nats-server
    
    # Create systemd service
    sudo tee /etc/systemd/system/nats.service > /dev/null <<'NATS_SERVICE'
[Unit]
Description=NATS Server
After=network.target

[Service]
Type=exec
User=ubuntu
ExecStart=/usr/local/bin/nats-server -p 4222
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
NATS_SERVICE
    
    sudo systemctl daemon-reload
    sudo systemctl enable nats
    sudo systemctl start nats
fi

# Check if NATS is running
sudo systemctl status nats --no-pager | head -10
EOF

# Step 4: Update service configuration to enable NATS
echo "4. Updating service configuration..."
ssh -i $KEY_PATH ubuntu@$INSTANCE_IP << 'EOF'
# Create or update the override configuration
sudo mkdir -p /etc/systemd/system/artcafe-pubsub.service.d
sudo tee /etc/systemd/system/artcafe-pubsub.service.d/override.conf > /dev/null <<'SERVICE_OVERRIDE'
[Service]
Environment="AGENT_TABLE_NAME=artcafe-agents"
Environment="SSH_KEY_TABLE_NAME=artcafe-ssh-keys"
Environment="CHANNEL_TABLE_NAME=artcafe-channels"
Environment="TENANT_TABLE_NAME=artcafe-tenants"
Environment="USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics"
Environment="CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions"
Environment="USER_TENANT_TABLE_NAME=artcafe-user-tenants"
Environment="USER_TENANT_INDEX_TABLE_NAME=artcafe-user-tenant-index"
Environment="NATS_ENABLED=true"
SERVICE_OVERRIDE

sudo systemctl daemon-reload
EOF

# Step 5: Restart the service
echo "5. Restarting ArtCafe PubSub service..."
ssh -i $KEY_PATH ubuntu@$INSTANCE_IP << 'EOF'
sudo systemctl restart artcafe-pubsub
sleep 5
sudo systemctl status artcafe-pubsub --no-pager | head -10
EOF

# Step 6: Verify deployment
echo "6. Verifying deployment..."
ssh -i $KEY_PATH ubuntu@$INSTANCE_IP << 'EOF'
# Check health endpoint
echo "Health check:"
curl -s http://localhost:8000/health | jq .

# Check NATS connection in logs
echo -e "\nNATS connection logs:"
sudo journalctl -u artcafe-pubsub -n 50 --no-pager | grep -i nats | tail -5
EOF

echo "=== Deployment complete ==="