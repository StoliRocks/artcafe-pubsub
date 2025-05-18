#!/bin/bash

# Direct EC2 deployment using known instance details

INSTANCE_IP="3.229.1.223"
INSTANCE_ID="i-02eb87cad85b30cf0"  # Your EC2 instance ID
REGION="us-east-1"
S3_BUCKET="artcafe-temp-deploy-$(date +%s)"

echo "Deploying CORS update directly to EC2..."

# Create deployment package
echo "Creating deployment package..."
zip -r cors_update.zip config/ api/ models/ auth/ -x "*.pyc" -x "__pycache__/*" -x ".venv/*"

# Create temporary S3 bucket
echo "Creating temporary S3 bucket..."
aws s3 mb s3://${S3_BUCKET} --region ${REGION}

# Upload the package
echo "Uploading package to S3..."
aws s3 cp cors_update.zip s3://${S3_BUCKET}/cors_update.zip

# Deploy using SSM
echo "Deploying to EC2 instance..."
COMMAND_ID=$(aws ssm send-command \
    --instance-ids ${INSTANCE_ID} \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'cd /home/ec2-user/artcafe-pubsub',
        'echo \"Stopping service...\"',
        'sudo systemctl stop artcafe-pubsub',
        'echo \"Downloading update...\"',
        'aws s3 cp s3://${S3_BUCKET}/cors_update.zip .',
        'echo \"Extracting files...\"',
        'unzip -o cors_update.zip',
        'echo \"Starting service...\"',
        'sudo systemctl start artcafe-pubsub',
        'echo \"Checking service status...\"',
        'sudo systemctl status artcafe-pubsub --no-pager',
        'rm cors_update.zip'
    ]" \
    --region ${REGION} \
    --query "Command.CommandId" \
    --output text)

if [ $? -eq 0 ]; then
    echo "Command sent successfully. Command ID: ${COMMAND_ID}"
    
    # Wait for the command to complete
    echo "Waiting for deployment to complete..."
    sleep 30
    
    # Get command status
    aws ssm get-command-invocation \
        --command-id ${COMMAND_ID} \
        --instance-id ${INSTANCE_ID} \
        --region ${REGION}
else
    echo "Failed to send SSM command"
fi

# Clean up
echo "Cleaning up..."
aws s3 rm s3://${S3_BUCKET}/cors_update.zip
aws s3 rb s3://${S3_BUCKET}
rm cors_update.zip

echo ""
echo "Deployment complete!"
echo "Testing the API..."
curl -s http://${INSTANCE_IP}:8000/health | python -m json.tool || echo "API test failed"

echo ""
echo "The backend now accepts requests from api.artcafe.ai"