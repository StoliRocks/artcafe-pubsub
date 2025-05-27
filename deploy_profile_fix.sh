#!/bin/bash
# Deploy profile routes fix to EC2

echo "Creating deployment package..."

# Create temp directory
TEMP_DIR=$(mktemp -d)
DEPLOY_ZIP="profile_fix_deploy.zip"

# Copy necessary files
echo "Copying files..."
cp -r api/routes/profile_routes.py $TEMP_DIR/
cp -r api/services/profile_service.py $TEMP_DIR/
cp -r models/user_profile.py $TEMP_DIR/
cp -r api/router.py $TEMP_DIR/

# Create zip
cd $TEMP_DIR
zip -r $DEPLOY_ZIP *
mv $DEPLOY_ZIP ~/

# Cleanup
cd ~
rm -rf $TEMP_DIR

echo "Deployment package created: ~/$DEPLOY_ZIP"

# Upload to S3
echo "Uploading to S3..."
aws s3 cp ~/$DEPLOY_ZIP s3://artcafe-deployment-bucket/$DEPLOY_ZIP

# Deploy to EC2
echo "Deploying to EC2..."
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters '{"commands":[
    "cd /opt/artcafe/artcafe-pubsub",
    "aws s3 cp s3://artcafe-deployment-bucket/profile_fix_deploy.zip .",
    "unzip -o profile_fix_deploy.zip",
    "mkdir -p api/routes api/services models",
    "mv profile_routes.py api/routes/",
    "mv profile_service.py api/services/",
    "mv user_profile.py models/",
    "mv router.py api/",
    "sudo systemctl restart artcafe-pubsub",
    "sleep 5",
    "sudo systemctl status artcafe-pubsub"
  ]}' \
  --output json

echo "Deployment initiated. Check AWS SSM console for status."