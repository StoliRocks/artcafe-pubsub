#!/bin/bash

# Simple deployment script for CORS update

echo "Deploying CORS update to ArtCafe API..."

# Create deployment package
echo "Creating deployment package..."
cd /home/stvwhite/projects/artcafe/artcafe-pubsub

# Create a minimal deployment with just the updated files
mkdir -p deploy_temp
cp -r config api models auth deploy_temp/
cd deploy_temp
zip -r ../cors_update.zip . -x "*.pyc" -x "__pycache__/*"
cd ..
rm -rf deploy_temp

# Get the S3 bucket name from CloudFormation
STACK_NAME="artcafe-pubsub"
REGION="us-east-1"

echo "Getting S3 bucket name..."
S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query "Stacks[0].Outputs[?OutputKey=='CodeBucketName'].OutputValue" \
    --output text)

if [ -z "$S3_BUCKET" ]; then
    echo "Error: Could not find S3 bucket from CloudFormation stack"
    exit 1
fi

echo "Uploading to S3 bucket: ${S3_BUCKET}"
aws s3 cp cors_update.zip s3://${S3_BUCKET}/cors_update.zip

# Update the Lambda function if it exists
FUNCTION_NAME="artcafe-api"
echo "Checking for Lambda function..."
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} 2>/dev/null; then
    echo "Updating Lambda function..."
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --s3-bucket ${S3_BUCKET} \
        --s3-key cors_update.zip \
        --region ${REGION}
else
    echo "Lambda function not found, skipping Lambda update"
fi

# Find EC2 instance
echo "Finding EC2 instance..."
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:aws:cloudformation:stack-name,Values=${STACK_NAME}" \
              "Name=instance-state-name,Values=running" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text \
    --region ${REGION})

if [ "$INSTANCE_ID" != "None" ]; then
    echo "Updating EC2 instance: ${INSTANCE_ID}"
    
    # Create SSM command
    COMMAND_ID=$(aws ssm send-command \
        --instance-ids ${INSTANCE_ID} \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[
            'cd /home/ec2-user/artcafe-pubsub',
            'sudo systemctl stop artcafe-pubsub',
            'aws s3 cp s3://${S3_BUCKET}/cors_update.zip .',
            'unzip -o cors_update.zip',
            'sudo systemctl start artcafe-pubsub',
            'rm cors_update.zip'
        ]" \
        --region ${REGION} \
        --query "Command.CommandId" \
        --output text)
    
    echo "Waiting for deployment to complete..."
    aws ssm wait command-executed \
        --command-id ${COMMAND_ID} \
        --instance-id ${INSTANCE_ID} \
        --region ${REGION}
    
    echo "EC2 deployment complete!"
else
    echo "No EC2 instance found"
fi

echo "CORS update deployed successfully!"
echo "The API now accepts requests from api.artcafe.ai"

# Cleanup
rm -f cors_update.zip