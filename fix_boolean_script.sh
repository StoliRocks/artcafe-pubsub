#!/bin/bash

echo "Fixing boolean values in user_tenant_service.py..."

# Find all True/False values and replace with 1/0
sed -i 's/"active": True/"active": 1/g' api/services/user_tenant_service.py
sed -i 's/":active": True/":active": 1/g' api/services/user_tenant_service.py
sed -i 's/"active": False/"active": 0/g' api/services/user_tenant_service.py
sed -i 's/":active": False/":active": 0/g' api/services/user_tenant_service.py

# Also replace ULID with UUID
sed -i 's/import ulid/import uuid/g' api/services/user_tenant_service.py
sed -i 's/str(ulid\.ULID())/str(uuid.uuid4())/g' api/services/user_tenant_service.py

echo "Fixes applied."
echo "Checking for remaining boolean values..."
grep -n "True\|False" api/services/user_tenant_service.py | grep -v "#" | grep -v "is_" | grep -v "return" | head -10

echo "Restarting service..."
sudo systemctl restart artcafe-pubsub.service
sleep 2
sudo systemctl status artcafe-pubsub.service