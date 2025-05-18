#!/bin/bash

# Deploy via S3 for manual EC2 update

S3_BUCKET="artcafe-public-8473"  # Using a known bucket
REGION="us-east-1"

echo "Uploading deployment package to S3..."

# Create the bucket if it doesn't exist
aws s3 mb s3://${S3_BUCKET} --region ${REGION} 2>/dev/null || true

# Upload the deployment package with public read access
aws s3 cp artcafe_pubsub_cors_update.zip s3://${S3_BUCKET}/updates/cors_update.zip \
    --acl public-read \
    --region ${REGION}

# Generate presigned URL for 1 hour
DOWNLOAD_URL=$(aws s3 presign s3://${S3_BUCKET}/updates/cors_update.zip --expires-in 3600)

echo ""
echo "Deployment package uploaded successfully!"
echo ""
echo "To deploy on your EC2 instance:"
echo "1. SSH to your EC2 instance"
echo "2. Run these commands:"
echo ""
echo "cd /home/ec2-user/artcafe-pubsub"
echo "sudo systemctl stop artcafe-pubsub"
echo "wget -O cors_update.zip '${DOWNLOAD_URL}'"
echo "unzip -o cors_update.zip"
echo "sudo systemctl start artcafe-pubsub"
echo ""
echo "Or download directly from:"
echo "https://${S3_BUCKET}.s3.amazonaws.com/updates/cors_update.zip"
echo ""
echo "The backend will then accept requests from api.artcafe.ai"