#!/bin/bash

# Deploy via SSM

INSTANCE_ID="i-0cd295d6b239ca775"
REGION="us-east-1"
S3_BUCKET="artcafe-public-8473"
PRESIGNED_URL="https://artcafe-public-8473.s3.us-east-1.amazonaws.com/updates/cors_update.zip?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIA5A2HAFH76BSFAGGM%2F20250518%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250518T131829Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=host&X-Amz-Signature=c4299b63587d71889bd06de7e74e6ff7565c61713a3a9b58693435a7f9c06f84"

echo "Deploying CORS update via SSM to instance ${INSTANCE_ID}..."

# Send deployment commands
COMMAND_ID=$(aws ssm send-command \
    --instance-ids ${INSTANCE_ID} \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'echo \"Starting deployment...\"',
        'cd /home/ec2-user/artcafe-pubsub',
        'echo \"Backing up current configuration...\"',
        'cp -r config config.backup.$(date +%Y%m%d_%H%M%S)',
        'echo \"Stopping service...\"',
        'sudo systemctl stop artcafe-pubsub',
        'echo \"Downloading update...\"',
        'curl -o cors_update.zip \"${PRESIGNED_URL}\"',
        'echo \"Extracting files...\"',
        'unzip -o cors_update.zip',
        'echo \"Starting service...\"',
        'sudo systemctl start artcafe-pubsub',
        'sleep 5',
        'echo \"Checking service status...\"',
        'sudo systemctl status artcafe-pubsub --no-pager',
        'echo \"Testing API health...\"',
        'curl -s http://localhost:8000/health',
        'rm cors_update.zip',
        'echo \"Deployment complete!\"'
    ]" \
    --region ${REGION} \
    --output json | jq -r '.Command.CommandId')

echo "Command ID: ${COMMAND_ID}"
echo "Waiting for deployment to complete..."

# Wait for command to complete
aws ssm wait command-executed \
    --command-id ${COMMAND_ID} \
    --instance-id ${INSTANCE_ID} \
    --region ${REGION}

# Get command output
echo ""
echo "Deployment output:"
aws ssm get-command-invocation \
    --command-id ${COMMAND_ID} \
    --instance-id ${INSTANCE_ID} \
    --region ${REGION} \
    --query '[StandardOutputContent,StandardErrorContent]' \
    --output text

echo ""
echo "CORS update deployed successfully!"
echo "The backend now accepts requests from api.artcafe.ai"