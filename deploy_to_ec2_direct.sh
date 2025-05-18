#!/bin/bash

# Direct deployment to EC2 instance using AWS Systems Manager

INSTANCE_ID="i-02eb87cad85b30cf0"  # Your EC2 instance ID
REGION="us-east-1"

echo "Deploying updated CORS configuration to EC2..."

# Create deployment package
echo "Creating deployment package..."
zip -r /tmp/api_update.zip config/ api/ models/ auth/ infrastructure/ *.py -x "*.pyc" -x "__pycache__/*" -x ".venv/*" -x "lambda-venv/*"

# Upload to S3
BUCKET_NAME="artcafe-deployment-temp-$(date +%s)"
echo "Creating S3 bucket..."
aws s3 mb s3://${BUCKET_NAME} --region ${REGION}

echo "Uploading deployment package..."
aws s3 cp /tmp/api_update.zip s3://${BUCKET_NAME}/api_update.zip

# Create SSM command to update the service
echo "Deploying to EC2 instance..."
aws ssm send-command \
    --instance-ids ${INSTANCE_ID} \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /home/ec2-user/artcafe-pubsub",
        "sudo systemctl stop artcafe-pubsub",
        "aws s3 cp s3://'${BUCKET_NAME}'/api_update.zip .",
        "unzip -o api_update.zip",
        "sudo systemctl start artcafe-pubsub",
        "rm api_update.zip"
    ]' \
    --region ${REGION}

# Wait a moment for the command to process
sleep 10

# Clean up S3 bucket
echo "Cleaning up..."
aws s3 rm s3://${BUCKET_NAME}/api_update.zip
aws s3 rb s3://${BUCKET_NAME}

echo "Deployment complete!"
echo "The backend should now accept requests from api.artcafe.ai"