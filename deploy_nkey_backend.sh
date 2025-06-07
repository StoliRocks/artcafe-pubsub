#!/bin/bash
# Deploy complete NKey backend update to EC2

echo "🚀 Starting NKey backend deployment..."

# Configuration
EC2_IP="3.229.1.223"
INSTANCE_ID="i-0cd295d6b239ca775"
DEPLOY_DIR="/opt/artcafe/artcafe-pubsub"

# Create deployment package
echo "📦 Creating deployment package..."
tar -czf nkey_backend.tar.gz \
    models/account.py \
    models/client.py \
    models/subject.py \
    api/routes/account_routes.py \
    api/routes/client_routes.py \
    api/routes/__init__.py \
    api/services/account_service.py \
    api/services/client_service.py \
    infrastructure/create_tables_fixed.py \
    infrastructure/dynamodb_new_schema.json \
    requirements_nkey.txt

# Create requirements file for nkeys
cat > requirements_nkey.txt << EOF
nkeys>=0.1.0
EOF

# Copy to EC2
echo "📤 Copying to EC2..."
scp -o StrictHostKeyChecking=no nkey_backend.tar.gz ubuntu@${EC2_IP}:/tmp/

# Deploy via SSM
echo "🔧 Deploying via SSM..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids ${INSTANCE_ID} \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "echo \"📦 Extracting update package...\"",
        "cd /opt/artcafe/artcafe-pubsub",
        "tar -xzf /tmp/nkey_backend.tar.gz",
        "echo \"📚 Installing NKey dependencies...\"",
        "source venv/bin/activate",
        "pip install nkeys",
        "echo \"🗄️ Creating new DynamoDB tables...\"",
        "cd infrastructure && python3 create_tables_fixed.py",
        "cd ..",
        "echo \"🔄 Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "echo \"✅ Checking service status...\"",
        "sudo systemctl status artcafe-pubsub --no-pager",
        "echo \"🏥 Testing health endpoint...\"",
        "curl -s https://api.artcafe.ai/health | jq ."
    ]' \
    --output-s3-bucket-name artcafe-deployments \
    --output-s3-key-prefix "nkey-migration" \
    --query 'Command.CommandId' \
    --output text)

echo "📋 Command ID: ${COMMAND_ID}"

# Wait for command to complete
echo "⏳ Waiting for deployment to complete..."
aws ssm wait command-executed \
    --command-id ${COMMAND_ID} \
    --instance-id ${INSTANCE_ID}

# Get command output
echo "📄 Deployment output:"
aws ssm get-command-invocation \
    --command-id ${COMMAND_ID} \
    --instance-id ${INSTANCE_ID} \
    --query 'StandardOutputContent' \
    --output text

# Check if deployment was successful
STATUS=$(aws ssm get-command-invocation \
    --command-id ${COMMAND_ID} \
    --instance-id ${INSTANCE_ID} \
    --query 'Status' \
    --output text)

if [ "$STATUS" = "Success" ]; then
    echo "✅ Deployment successful!"
    echo "🔍 Testing new endpoints..."
    
    # Test new account endpoint
    echo "Testing /api/v1/accounts endpoint:"
    curl -s https://api.artcafe.ai/api/v1/accounts | jq .
    
else
    echo "❌ Deployment failed with status: $STATUS"
    echo "📋 Error output:"
    aws ssm get-command-invocation \
        --command-id ${COMMAND_ID} \
        --instance-id ${INSTANCE_ID} \
        --query 'StandardErrorContent' \
        --output text
fi

# Cleanup
rm -f nkey_backend.tar.gz requirements_nkey.txt

echo "🎉 NKey backend deployment complete!"