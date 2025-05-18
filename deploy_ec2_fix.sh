#!/bin/bash

# Deploy script to fix backend on EC2 instance
set -e

EC2_IP="3.229.1.223"
EC2_USER="ubuntu"
REMOTE_PATH="/opt/artcafe/artcafe-pubsub"

echo "Deploying fixes to EC2 instance at ${EC2_IP}..."

# Files to upload
FILES=(
    "api/services/tenant_service.py"
    "models/tenant_limits.py"
    "models/tenant.py"
)

# Create a temporary directory for the update
TEMP_DIR=$(mktemp -d)
echo "Creating temporary package in ${TEMP_DIR}"

# Copy the files preserving directory structure
for file in "${FILES[@]}"; do
    mkdir -p "${TEMP_DIR}/$(dirname $file)"
    cp "$file" "${TEMP_DIR}/$file"
done

# Create update script
cat > "${TEMP_DIR}/update.sh" << 'EOF'
#!/bin/bash
set -e

# Backup current files
echo "Backing up current files..."
sudo cp /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py.backup
sudo cp /opt/artcafe/artcafe-pubsub/models/tenant_limits.py /opt/artcafe/artcafe-pubsub/models/tenant_limits.py.backup
sudo cp /opt/artcafe/artcafe-pubsub/models/tenant.py /opt/artcafe/artcafe-pubsub/models/tenant.py.backup

# Copy new files
echo "Copying updated files..."
sudo cp api/services/tenant_service.py /opt/artcafe/artcafe-pubsub/api/services/
sudo cp models/tenant_limits.py /opt/artcafe/artcafe-pubsub/models/
sudo cp models/tenant.py /opt/artcafe/artcafe-pubsub/models/

# Restart the service
echo "Restarting artcafe-pubsub service..."
sudo systemctl restart artcafe-pubsub

# Check service status
echo "Checking service status..."
sudo systemctl status artcafe-pubsub --no-pager

echo "Update completed!"
EOF

chmod +x "${TEMP_DIR}/update.sh"

# Use AWS SSM to upload and execute the update
echo "Uploading files to EC2..."

# Get instance ID from IP
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=${EC2_IP}" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text \
    --region us-east-1)

if [ "$INSTANCE_ID" == "None" ] || [ -z "$INSTANCE_ID" ]; then
    echo "Could not find instance ID for IP ${EC2_IP}"
    echo "Attempting direct SSH deployment..."
    
    # Upload files via SSH
    tar -czf "${TEMP_DIR}/update.tar.gz" -C "${TEMP_DIR}" .
    scp -o StrictHostKeyChecking=no -i ~/.ssh/artcafe-ec2.pem "${TEMP_DIR}/update.tar.gz" ${EC2_USER}@${EC2_IP}:/tmp/
    
    # Extract and run update
    ssh -o StrictHostKeyChecking=no -i ~/.ssh/artcafe-ec2.pem ${EC2_USER}@${EC2_IP} << 'ENDSSH'
cd /tmp
tar -xzf update.tar.gz
./update.sh
rm -rf update.tar.gz update.sh api models
ENDSSH
    
else
    echo "Found instance ID: ${INSTANCE_ID}"
    echo "Using SSM for deployment..."
    
    # Use SSM to run commands
    aws ssm send-command \
        --instance-ids "${INSTANCE_ID}" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[
            'cd /tmp',
            'mkdir -p fix_update',
            'cd fix_update',
            'cat > update.sh << '\''EOF'\''
#!/bin/bash
set -e

# Backup current files
echo \"Backing up current files...\"
sudo cp /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py.backup
sudo cp /opt/artcafe/artcafe-pubsub/models/tenant_limits.py /opt/artcafe/artcafe-pubsub/models/tenant_limits.py.backup
sudo cp /opt/artcafe/artcafe-pubsub/models/tenant.py /opt/artcafe/artcafe-pubsub/models/tenant.py.backup

# Download updated files from S3 or curl from GitHub
# For now, we will create the files directly with the fixes

# Update tenant_service.py - fix boolean values
cat > /opt/artcafe/artcafe-pubsub/api/services/tenant_service.py << '\''PYEOF'\''
$(cat api/services/tenant_service.py)
PYEOF

# Update tenant_limits.py - add basic tier
cat > /opt/artcafe/artcafe-pubsub/models/tenant_limits.py << '\''PYEOF'\''
$(cat models/tenant_limits.py)
PYEOF

# Update tenant.py - fix subscription tiers
cat > /opt/artcafe/artcafe-pubsub/models/tenant.py << '\''PYEOF'\''
$(cat models/tenant.py)
PYEOF

# Restart the service
echo \"Restarting artcafe-pubsub service...\"
sudo systemctl restart artcafe-pubsub

# Check service status
echo \"Checking service status...\"
sudo systemctl status artcafe-pubsub --no-pager

echo \"Update completed!\"
EOF',
            'chmod +x update.sh',
            './update.sh'
        ]" \
        --region us-east-1
fi

# Clean up
rm -rf "${TEMP_DIR}"

echo "Deployment initiated. Check EC2 instance logs for status."
echo "Service should be restarted automatically after file updates."