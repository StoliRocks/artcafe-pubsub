#!/bin/bash

# Deploy Phase 1: Activity Tracking System

INSTANCE_ID="i-0cd295d6b239ca775"
S3_BUCKET="artcafe-deployment"

echo "=== Deploying Phase 1: Activity Tracking System ==="

# Step 1: Create DynamoDB tables
echo "Step 1: Creating DynamoDB tables..."
chmod +x scripts/create_production_tables.sh
./scripts/create_production_tables.sh

# Step 2: Package the new code
echo "Step 2: Creating deployment package..."
zip -r phase1-activity-system.zip \
    models/activity_log.py \
    models/agent_metrics.py \
    api/services/activity_service.py \
    api/routes/activity_routes.py

# Step 3: Upload to S3
echo "Step 3: Uploading to S3..."
aws s3 cp phase1-activity-system.zip s3://${S3_BUCKET}/phase1-activity-system.zip

# Step 4: Deploy to EC2
echo "Step 4: Deploying to EC2..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Backing up current code...\"",
        "sudo cp -r api api.backup.$(date +%Y%m%d_%H%M%S)",
        "sudo cp -r models models.backup.$(date +%Y%m%d_%H%M%S)",
        "echo \"Downloading update package...\"",
        "sudo aws s3 cp s3://artcafe-deployment/phase1-activity-system.zip .",
        "echo \"Extracting updates...\"",
        "sudo unzip -o phase1-activity-system.zip",
        "echo \"Updating routes __init__.py...\"",
        "sudo sed -i '\''s/from .profile_routes import router as profile_router/from .profile_routes import router as profile_router\\nfrom .activity_routes import router as activity_router/'\'' api/routes/__init__.py",
        "sudo sed -i '\''s/router.include_router(profile_router)/router.include_router(profile_router)\\nrouter.include_router(activity_router)/'\'' api/routes/__init__.py",
        "echo \"Updating agent routes to log activities...\"",
        "sudo tee -a api/routes/agent_routes.py > /dev/null <<'\''ACTIVITY_PATCH'\''",
        "",
        "# Import activity service at the top of the file",
        "from api.services.activity_service import activity_service",
        "from models.activity_log import ActivityType, ActivityStatus",
        "ACTIVITY_PATCH",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub | head -20",
        "echo \"Cleaning up...\"",
        "sudo rm phase1-activity-system.zip"
    ]' \
    --output text

echo "Phase 1 deployment initiated. Monitor EC2 for completion."

# Step 5: Update frontend to use activity API
echo ""
echo "=== Next Steps for Frontend ==="
echo "1. Update ActivityFeed.js to use /api/v1/activity/logs endpoint"
echo "2. Add WebSocket subscription for 'activity.new' events"
echo "3. Update agent operations to show activity logs"
echo "4. Add activity filters and search"

# Clean up local file
rm -f phase1-activity-system.zip

echo ""
echo "=== Phase 1 Deployment Complete ==="
echo "Activity tracking system is now deployed!"
echo ""
echo "Test endpoints:"
echo "- GET /api/v1/activity/logs"
echo "- GET /api/v1/activity/summary"
echo "- GET /api/v1/activity/types"
echo "- GET /api/v1/activity/statuses"