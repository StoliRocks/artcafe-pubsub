#!/bin/bash

# Create the override directory
sudo mkdir -p /etc/systemd/system/artcafe-pubsub.service.d/

# Create the override file
cat <<'EOF' | sudo tee /etc/systemd/system/artcafe-pubsub.service.d/override.conf
[Service]
Environment="AGENT_TABLE_NAME=artcafe-agents"
Environment="SSH_KEY_TABLE_NAME=artcafe-ssh-keys"
Environment="CHANNEL_TABLE_NAME=artcafe-channels"
Environment="TENANT_TABLE_NAME=artcafe-tenants"
Environment="USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics"
Environment="CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions"
Environment="USER_TENANT_TABLE_NAME=artcafe-user-tenants"
Environment="USER_TENANT_INDEX_TABLE_NAME=artcafe-user-tenant-index"
EOF

# Reload systemd
sudo systemctl daemon-reload

# Restart the service
sudo systemctl restart artcafe-pubsub

# Check status
sudo systemctl status artcafe-pubsub

# Verify environment variables
echo "Environment variables:"
sudo systemctl show artcafe-pubsub | grep Environment