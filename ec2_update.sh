#!/bin/bash

# Update EC2 instance to use production tables
API_IP="3.229.1.223"

echo "Creating environment configuration..."
cat > /tmp/artcafe.conf <<'EOL'
[Service]
Environment="AGENT_TABLE_NAME=artcafe-agents"
Environment="SSH_KEY_TABLE_NAME=artcafe-ssh-keys"
Environment="CHANNEL_TABLE_NAME=artcafe-channels"
Environment="TENANT_TABLE_NAME=artcafe-tenants"
Environment="USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics"
Environment="CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions"
Environment="USER_TENANT_TABLE_NAME=artcafe-user-tenants"
EOL

echo "Updating EC2 instance at $API_IP..."

# Transfer configuration
scp -o StrictHostKeyChecking=no /tmp/artcafe.conf ubuntu@$API_IP:/tmp/

# Update EC2 instance
ssh -o StrictHostKeyChecking=no ubuntu@$API_IP << 'ENDSSH'
    sudo su -
    
    # Create systemd override directory if it doesn't exist
    mkdir -p /etc/systemd/system/artcafe-pubsub.service.d/
    
    # Copy configuration
    cp /tmp/artcafe.conf /etc/systemd/system/artcafe-pubsub.service.d/override.conf
    
    # Reload systemd and restart service
    systemctl daemon-reload
    systemctl restart artcafe-pubsub
    
    # Check service status
    systemctl status artcafe-pubsub
ENDSSH

echo "EC2 instance updated"