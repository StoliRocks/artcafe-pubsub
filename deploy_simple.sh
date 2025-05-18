#!/bin/bash

# Simple direct deployment script
set -e

EC2_IP="3.229.1.223"
EC2_USER="ubuntu"
KEY_PATH="~/.ssh/artcafe-ec2.pem"

echo "Deploying fixes to EC2 instance at ${EC2_IP}..."

# Check if SSH key exists
if [ ! -f "${KEY_PATH}" ]; then
    echo "SSH key not found at ${KEY_PATH}"
    echo "Checking for AWS SSM access..."
    
    # Try using AWS Systems Manager Session Manager
    INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=ip-address,Values=${EC2_IP}" \
        --query "Reservations[0].Instances[0].InstanceId" \
        --output text \
        --region us-east-1)
    
    if [ "$INSTANCE_ID" != "None" ] && [ ! -z "$INSTANCE_ID" ]; then
        echo "Found instance ID: ${INSTANCE_ID}"
        
        # Create update script locally
        cat > /tmp/update_artcafe.sh << 'EOF'
#!/bin/bash
set -e

echo "Starting ArtCafe backend update..."

# Navigate to the project directory
cd /opt/artcafe/artcafe-pubsub

# Backup current files
sudo cp api/services/tenant_service.py api/services/tenant_service.py.backup
sudo cp models/tenant_limits.py models/tenant_limits.py.backup
sudo cp models/tenant.py models/tenant.py.backup

# Download the fixed files from GitHub or S3
# For now, we'll use direct file creation with the fixes

# Fix tenant_service.py
sudo tee api/services/tenant_service.py > /dev/null << 'PYEOF'
# File content will be inserted here by the script
PYEOF

# Fix tenant_limits.py  
sudo tee models/tenant_limits.py > /dev/null << 'PYEOF'
# File content will be inserted here by the script
PYEOF

# Fix tenant.py
sudo tee models/tenant.py > /dev/null << 'PYEOF'
# File content will be inserted here by the script
PYEOF

# Restart the service
echo "Restarting artcafe-pubsub service..."
sudo systemctl restart artcafe-pubsub
sleep 5

# Check service status
echo "Checking service status..."
sudo systemctl status artcafe-pubsub --no-pager

echo "Update completed!"
EOF

        # Use AWS SSM to execute the update
        aws ssm start-session --target $INSTANCE_ID --region us-east-1 \
            --document-name AWS-StartInteractiveCommand \
            --parameters "command=[\"bash /tmp/update_artcafe.sh\"]"
    else
        echo "Cannot connect to EC2 instance. Please check:"
        echo "1. SSH key location: ${KEY_PATH}"
        echo "2. EC2 instance IP: ${EC2_IP}"
        echo "3. AWS credentials and permissions"
        exit 1
    fi
else
    # Use direct SSH/SCP
    echo "Using SSH to deploy..."
    
    # Create a temporary directory
    TEMP_DIR=$(mktemp -d)
    
    # Copy the fixed files
    cp api/services/tenant_service.py ${TEMP_DIR}/
    cp models/tenant_limits.py ${TEMP_DIR}/
    cp models/tenant.py ${TEMP_DIR}/
    
    # Create update script
    cat > ${TEMP_DIR}/update.sh << 'EOF'
#!/bin/bash
set -e

echo "Updating ArtCafe backend files..."

# Backup and update files
sudo cp /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py.backup
sudo cp tenant_service.py /opt/artcafe/artcafe-pubsub/api/services/

sudo cp /opt/artcafe/artcafe-pubsub/models/tenant_limits.py /opt/artcafe/artcafe-pubsub/models/tenant_limits.py.backup
sudo cp tenant_limits.py /opt/artcafe/artcafe-pubsub/models/

sudo cp /opt/artcafe/artcafe-pubsub/models/tenant.py /opt/artcafe/artcafe-pubsub/models/tenant.py.backup
sudo cp tenant.py /opt/artcafe/artcafe-pubsub/models/

# Set correct ownership
sudo chown ubuntu:ubuntu /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py
sudo chown ubuntu:ubuntu /opt/artcafe/artcafe-pubsub/models/tenant_limits.py
sudo chown ubuntu:ubuntu /opt/artcafe/artcafe-pubsub/models/tenant.py

# Restart service
echo "Restarting service..."
sudo systemctl restart artcafe-pubsub

# Check status
echo "Service status:"
sudo systemctl status artcafe-pubsub --no-pager

echo "Update completed!"
EOF

    chmod +x ${TEMP_DIR}/update.sh
    
    # Upload files
    echo "Uploading files to EC2..."
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i ${KEY_PATH} \
        ${TEMP_DIR}/* ${EC2_USER}@${EC2_IP}:/tmp/
    
    # Execute update
    echo "Executing update script..."
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i ${KEY_PATH} \
        ${EC2_USER}@${EC2_IP} "cd /tmp && bash update.sh"
    
    # Cleanup
    rm -rf ${TEMP_DIR}
fi

echo "Deployment completed!"