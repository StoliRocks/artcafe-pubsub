#!/bin/bash
set -e
echo "Fixing case sensitivity issue in user_tenant_service.py..."
cd /opt/artcafe/artcafe-pubsub

# Create backup
cp api/services/user_tenant_service.py api/services/user_tenant_service.py.bak.items_fix

# Fix the case sensitivity issue
sed -i 's/response\.get("Items", \[\])/response.get("items", [])/g' api/services/user_tenant_service.py
sed -i 's/items = response\.get("Items", \[\])/items = response.get("items", [])/g' api/services/user_tenant_service.py

# Verify the changes
echo "Verifying changes..."
grep -n 'response.get("items"' api/services/user_tenant_service.py || echo "No lowercase items found"
grep -n 'response.get("Items"' api/services/user_tenant_service.py || echo "No uppercase Items found"

# Restart service
echo "Restarting service..."
sudo systemctl restart artcafe-pubsub
sleep 2
sudo journalctl -u artcafe-pubsub -n 5

echo "Fix applied successfully!"