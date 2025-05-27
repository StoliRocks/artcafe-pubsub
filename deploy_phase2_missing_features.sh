#!/bin/bash

# Deploy Phase 2: Missing Features (Profile, SSH Keys, Notifications)

INSTANCE_ID="i-0cd295d6b239ca775"
S3_BUCKET="artcafe-deployment"

echo "=== Deploying Phase 2: Missing Features ==="

# Step 1: Create notification preferences table
echo "Step 1: Creating notification preferences table..."
aws dynamodb create-table \
    --table-name artcafe-notification-preferences \
    --attribute-definitions \
        AttributeName=user_id,AttributeType=S \
    --key-schema \
        AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table may already exist"

# Step 2: Create SNS topic for notifications
echo "Step 2: Setting up SNS for email notifications..."
SNS_TOPIC_ARN=$(aws sns create-topic --name artcafe-notifications --region us-east-1 --query 'TopicArn' --output text)
echo "SNS Topic ARN: $SNS_TOPIC_ARN"

# Step 3: Package the new code
echo "Step 3: Creating deployment package..."
zip -r phase2-missing-features.zip \
    models/notification.py \
    models/agent_metrics.py \
    api/services/notification_service.py \
    api/services/metrics_service.py \
    api/routes/notification_routes.py

# Step 4: Upload to S3
echo "Step 4: Uploading to S3..."
aws s3 cp phase2-missing-features.zip s3://${S3_BUCKET}/phase2-missing-features.zip

# Step 5: Deploy to EC2
echo "Step 5: Deploying to EC2..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Backing up current code...\"",
        "sudo cp -r api api.backup.phase2.$(date +%Y%m%d_%H%M%S)",
        "sudo cp -r models models.backup.phase2.$(date +%Y%m%d_%H%M%S)",
        "echo \"Downloading update package...\"",
        "sudo aws s3 cp s3://artcafe-deployment/phase2-missing-features.zip .",
        "echo \"Extracting updates...\"",
        "sudo unzip -o phase2-missing-features.zip",
        "echo \"Updating routes __init__.py...\"",
        "sudo sed -i '\''s/from .activity_routes import router as activity_router/from .activity_routes import router as activity_router\\nfrom .notification_routes import router as notification_router/'\'' api/routes/__init__.py",
        "sudo sed -i '\''s/router.include_router(activity_router)/router.include_router(activity_router)\\nrouter.include_router(notification_router)/'\'' api/routes/__init__.py",
        "echo \"Adding metrics endpoints to agent routes...\"",
        "sudo tee -a api/routes/agent_routes.py > /dev/null <<'\''METRICS_ENDPOINTS'\''",
        "",
        "# Metrics endpoints",
        "@router.post(\"/{agent_id}/metrics\", response_model=Dict[str, Any])",
        "async def record_agent_metrics(",
        "    agent_id: str,",
        "    metrics_data: AgentMetricsCreate,",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.metrics_service import metrics_service",
        "    metrics = await metrics_service.record_metrics(tenant_id, metrics_data)",
        "    return {\"success\": True, \"timestamp\": metrics.timestamp}",
        "",
        "@router.get(\"/{agent_id}/metrics\", response_model=AgentMetricsSummary)",
        "async def get_agent_metrics(",
        "    agent_id: str,",
        "    hours: int = Query(1, ge=1, le=168),",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.metrics_service import metrics_service",
        "    summary = await metrics_service.get_agent_metrics_summary(tenant_id, agent_id, hours)",
        "    return summary",
        "",
        "@router.get(\"/{agent_id}/metrics/history\", response_model=List[AgentMetrics])",
        "async def get_agent_metrics_history(",
        "    agent_id: str,",
        "    hours: int = Query(1, ge=1, le=24),",
        "    limit: int = Query(100, ge=1, le=1000),",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.metrics_service import metrics_service",
        "    metrics = await metrics_service.get_agent_metrics(tenant_id, agent_id, hours, limit)",
        "    return metrics",
        "METRICS_ENDPOINTS",
        "echo \"Updating environment variables...\"",
        "echo \"SNS_NOTIFICATION_TOPIC_ARN='$SNS_TOPIC_ARN'\" | sudo tee -a /etc/environment",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub | head -20",
        "echo \"Cleaning up...\"",
        "sudo rm phase2-missing-features.zip"
    ]' \
    --output text

echo "Phase 2 deployment initiated. Monitor EC2 for completion."

# Clean up local file
rm -f phase2-missing-features.zip

echo ""
echo "=== Frontend Updates Required ==="
echo "1. Create /dashboard/profile page"
echo "2. Create /dashboard/ssh-keys page"
echo "3. Create /dashboard/notifications page"
echo "4. Update navbar notification bell to show unread count"
echo "5. Add WebSocket subscriptions for notifications"
echo ""
echo "Test endpoints:"
echo "- GET /api/v1/notifications"
echo "- GET /api/v1/notifications/unread-count"
echo "- PUT /api/v1/notifications/{id}/read"
echo "- GET /api/v1/agents/{id}/metrics"
echo "- POST /api/v1/agents/{id}/metrics"