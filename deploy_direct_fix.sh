#!/bin/bash

# Create a backup of the tenant service
cd /opt/artcafe/artcafe-pubsub
sudo cp api/services/tenant_service.py api/services/tenant_service.py.bak.$(date +%Y%m%d_%H%M%S)

# Apply the boolean fixes directly in the file
echo "Applying boolean fixes to tenant_service.py..."

# Fix permissions dict booleans
sudo sed -i 's/"read": True/"read": 1/g' api/services/tenant_service.py
sudo sed -i 's/"write": True/"write": 1/g' api/services/tenant_service.py
sudo sed -i 's/"publish": True/"publish": 1/g' api/services/tenant_service.py
sudo sed -i 's/"subscribe": True/"subscribe": 1/g' api/services/tenant_service.py
sudo sed -i 's/"manage": True/"manage": 1/g' api/services/tenant_service.py

sudo sed -i 's/"read": False/"read": 0/g' api/services/tenant_service.py
sudo sed -i 's/"write": False/"write": 0/g' api/services/tenant_service.py
sudo sed -i 's/"publish": False/"publish": 0/g' api/services/tenant_service.py
sudo sed -i 's/"subscribe": False/"subscribe": 0/g' api/services/tenant_service.py
sudo sed -i 's/"manage": False/"manage": 0/g' api/services/tenant_service.py

# Fix other boolean values
sudo sed -i 's/ True,/ 1,/g' api/services/tenant_service.py
sudo sed -i 's/ False,/ 0,/g' api/services/tenant_service.py
sudo sed -i 's/:True,/:1,/g' api/services/tenant_service.py
sudo sed -i 's/:False,/:0,/g' api/services/tenant_service.py
sudo sed -i 's/: True,/: 1,/g' api/services/tenant_service.py
sudo sed -i 's/: False,/: 0,/g' api/services/tenant_service.py
sudo sed -i 's/ True}/ 1}/g' api/services/tenant_service.py
sudo sed -i 's/ False}/ 0}/g' api/services/tenant_service.py
sudo sed -i 's/:True}/:1}/g' api/services/tenant_service.py
sudo sed -i 's/:False}/:0}/g' api/services/tenant_service.py
sudo sed -i 's/: True}/: 1}/g' api/services/tenant_service.py
sudo sed -i 's/: False}/: 0}/g' api/services/tenant_service.py

# Fix feature flags
sudo sed -i 's/custom_domains_enabled else True/custom_domains_enabled else 1/g' api/services/tenant_service.py
sudo sed -i 's/custom_domains_enabled else False/custom_domains_enabled else 0/g' api/services/tenant_service.py
sudo sed -i 's/advanced_analytics_enabled else True/advanced_analytics_enabled else 1/g' api/services/tenant_service.py
sudo sed -i 's/advanced_analytics_enabled else False/advanced_analytics_enabled else 0/g' api/services/tenant_service.py
sudo sed -i 's/priority_support else True/priority_support else 1/g' api/services/tenant_service.py
sudo sed -i 's/priority_support else False/priority_support else 0/g' api/services/tenant_service.py

# Restart the service
echo "Restarting artcafe-pubsub service..."
sudo systemctl restart artcafe-pubsub

# Check status
echo "Service status:"
sudo systemctl status artcafe-pubsub --no-pager

echo "Boolean fix applied successfully!"