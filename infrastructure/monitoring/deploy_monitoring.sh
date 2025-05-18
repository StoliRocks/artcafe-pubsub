#!/bin/bash

# Deploy ArtCafe PubSub Monitoring

set -e

# Variables
EMAIL="${1}"
PHONE="${2:-}"
STACK_NAME="artcafe-pubsub-monitoring"
REGION="us-east-1"
API_ENDPOINT="http://3.229.1.223:8000"

# Check parameters
if [ -z "$EMAIL" ]; then
    echo "Usage: $0 <notification-email> [phone-number]"
    echo "Example: $0 user@example.com +1234567890"
    exit 1
fi

echo "Deploying monitoring stack..."

# Package canary code
echo "Packaging canary code..."
cd "$(dirname "$0")"
mkdir -p canary-package
cp artcafe_health_check.py canary-package/canary.py
cd canary-package
zip -r ../health-check-canary.zip canary.py
cd ..
rm -rf canary-package

# Upload canary code to S3
echo "Uploading canary code to S3..."
CANARY_BUCKET="artcafe-canary-$(aws sts get-caller-identity --query Account --output text)"
aws s3 mb s3://$CANARY_BUCKET --region $REGION 2>/dev/null || true
aws s3 cp health-check-canary.zip s3://$CANARY_BUCKET/health-check-canary.zip

# Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file monitoring-stack.yml \
    --stack-name $STACK_NAME \
    --parameter-overrides \
        APIEndpoint=$API_ENDPOINT \
        NotificationEmail=$EMAIL \
        NotificationPhone="$PHONE" \
    --capabilities CAPABILITY_IAM \
    --region $REGION

# Get stack outputs
echo "Getting stack outputs..."
DASHBOARD_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='DashboardURL'].OutputValue" \
    --output text \
    --region $REGION)

TOPIC_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='AlertTopicArn'].OutputValue" \
    --output text \
    --region $REGION)

# Deploy monitor service on EC2
echo "Deploying monitor service on EC2..."
INSTANCE_ID="i-0cd295d6b239ca775"

# Copy monitor files to EC2
aws s3 cp monitor.sh s3://artcafe-deployments/monitoring/monitor.sh
aws s3 cp artcafe-pubsub-monitor.service s3://artcafe-deployments/monitoring/artcafe-pubsub-monitor.service

# Install monitor on EC2
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "sudo aws s3 cp s3://artcafe-deployments/monitoring/monitor.sh /opt/artcafe/artcafe-pubsub/monitor.sh",
        "sudo chmod +x /opt/artcafe/artcafe-pubsub/monitor.sh",
        "sudo aws s3 cp s3://artcafe-deployments/monitoring/artcafe-pubsub-monitor.service /etc/systemd/system/",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable artcafe-pubsub-monitor",
        "sudo systemctl start artcafe-pubsub-monitor"
    ]' \
    --region $REGION

# Create additional alarms
echo "Creating additional alarms..."

# Memory usage alarm
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-pubsub-high-memory" \
    --alarm-description "High memory usage" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --metric-name MemoryUsagePercent \
    --namespace ArtCafePubSub \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --region $REGION

# CPU usage alarm
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-pubsub-high-cpu" \
    --alarm-description "High CPU usage" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --metric-name CPUUsagePercent \
    --namespace ArtCafePubSub \
    --statistic Average \
    --period 300 \
    --threshold 70 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --region $REGION

# Service restart alarm
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-pubsub-frequent-restarts" \
    --alarm-description "Service restarting frequently" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --metric-name ServiceRestart \
    --namespace ArtCafePubSub \
    --statistic Sum \
    --period 300 \
    --threshold 3 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 1 \
    --region $REGION

echo
echo "✅ Monitoring deployed successfully!"
echo
echo "Dashboard URL: $DASHBOARD_URL"
echo "Alert Topic: $TOPIC_ARN"
echo
echo "You will receive an email to confirm your subscription to alerts."
echo "Please click the confirmation link in the email."
echo
echo "To test the monitoring:"
echo "1. Stop the service: aws ssm send-command --instance-ids $INSTANCE_ID --document-name 'AWS-RunShellScript' --parameters 'commands=[\"sudo systemctl stop artcafe-pubsub\"]'"
echo "2. Wait 1-2 minutes for alerts"
echo "3. Check CloudWatch dashboard"
echo