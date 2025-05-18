#!/bin/bash

# Deploy via S3 without ACL

S3_BUCKET="artcafe-public-8473"
REGION="us-east-1"

echo "Uploading deployment package to S3..."

# Upload without ACL
aws s3 cp artcafe_pubsub_cors_update.zip s3://${S3_BUCKET}/updates/cors_update.zip \
    --region ${REGION}

# Generate presigned URL for 24 hours
DOWNLOAD_URL=$(aws s3 presign s3://${S3_BUCKET}/updates/cors_update.zip --expires-in 86400)

echo ""
echo "Deployment package uploaded successfully!"
echo ""
echo "To deploy on your EC2 instance:"
echo "1. SSH to your EC2 instance"
echo "2. Run these commands:"
echo ""
echo "cd /home/ec2-user/artcafe-pubsub"
echo "sudo systemctl stop artcafe-pubsub"
echo "curl -o cors_update.zip '${DOWNLOAD_URL}'"
echo "unzip -o cors_update.zip"
echo "sudo systemctl start artcafe-pubsub"
echo ""
echo "The presigned URL is valid for 24 hours."
echo ""
echo "After deployment, the backend will accept requests from api.artcafe.ai"