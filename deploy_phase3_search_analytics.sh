#!/bin/bash

# Deploy Phase 3: Search & Analytics

INSTANCE_ID="i-0cd295d6b239ca775"
S3_BUCKET="artcafe-deployment"

echo "=== Deploying Phase 3: Search & Analytics ==="

# Step 1: Install required Python packages
echo "Step 1: Installing search dependencies..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "sudo pip install fuzzywuzzy python-Levenshtein"
    ]' \
    --output text

# Step 2: Package the new code
echo "Step 2: Creating deployment package..."
zip -r phase3-search-analytics.zip \
    api/services/search_service.py \
    api/routes/search_routes.py

# Step 3: Upload to S3
echo "Step 3: Uploading to S3..."
aws s3 cp phase3-search-analytics.zip s3://${S3_BUCKET}/phase3-search-analytics.zip

# Step 4: Deploy to EC2
echo "Step 4: Deploying to EC2..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Downloading update package...\"",
        "sudo aws s3 cp s3://artcafe-deployment/phase3-search-analytics.zip .",
        "echo \"Extracting updates...\"",
        "sudo unzip -o phase3-search-analytics.zip",
        "echo \"Updating routes __init__.py...\"",
        "sudo sed -i '\''s/from .notification_routes import router as notification_router/from .notification_routes import router as notification_router\\nfrom .search_routes import router as search_router/'\'' api/routes/__init__.py",
        "sudo sed -i '\''s/router.include_router(notification_router)/router.include_router(notification_router)\\nrouter.include_router(search_router)/'\'' api/routes/__init__.py",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub | head -20",
        "echo \"Cleaning up...\"",
        "sudo rm phase3-search-analytics.zip"
    ]' \
    --output text

echo "Phase 3 deployment initiated."

# Clean up local file
rm -f phase3-search-analytics.zip

echo ""
echo "=== Test Endpoints ==="
echo "- GET /api/v1/search?q=agent"
echo "- GET /api/v1/search/suggestions?prefix=cha"
echo "- GET /api/v1/search/popular"