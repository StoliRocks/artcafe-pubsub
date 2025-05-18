#!/bin/bash

# Quick monitoring setup for ArtCafe PubSub API

echo "🚀 Setting up quick monitoring for ArtCafe PubSub API"

# Variables
EMAIL="${1:-}"
API_ENDPOINT="http://3.229.1.223:8000"
REGION="us-east-1"

if [ -z "$EMAIL" ]; then
    echo "Usage: $0 <your-email>"
    echo "Example: $0 user@example.com"
    exit 1
fi

# Create SNS topic for alerts
echo "Creating SNS topic..."
TOPIC_ARN=$(aws sns create-topic --name artcafe-pubsub-alerts --region $REGION --query 'TopicArn' --output text)
aws sns subscribe --topic-arn $TOPIC_ARN --protocol email --notification-endpoint $EMAIL --region $REGION

# Create simple health check alarm
echo "Creating health check alarm..."
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-api-down" \
    --alarm-description "ArtCafe API is not responding" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --evaluation-periods 2 \
    --datapoints-to-alarm 2 \
    --threshold 1 \
    --comparison-operator LessThanThreshold \
    --treat-missing-data notBreaching \
    --region $REGION \
    --metric-name HealthCheck \
    --namespace "ArtCafePubSub/Monitoring" \
    --statistic Average \
    --period 300

# Create monitoring script
cat > /tmp/monitor_artcafe.sh << 'EOF'
#!/bin/bash
API_ENDPOINT="http://3.229.1.223:8000"
REGION="us-east-1"

while true; do
    # Check health
    if curl -s -f "$API_ENDPOINT/health" > /dev/null; then
        VALUE=1
        echo "$(date): API is healthy"
    else
        VALUE=0
        echo "$(date): API is DOWN!"
    fi
    
    # Send metric
    aws cloudwatch put-metric-data \
        --region $REGION \
        --namespace "ArtCafePubSub/Monitoring" \
        --metric-name HealthCheck \
        --value $VALUE
    
    sleep 60
done
EOF

chmod +x /tmp/monitor_artcafe.sh

echo "
✅ Quick monitoring setup complete!

1. You'll receive an email to confirm your alert subscription
2. Click the confirmation link in the email

To start monitoring in background:
    nohup /tmp/monitor_artcafe.sh > /tmp/artcafe_monitor.log 2>&1 &

To check status:
    tail -f /tmp/artcafe_monitor.log

To stop monitoring:
    pkill -f monitor_artcafe.sh

CloudWatch Dashboard:
    https://console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards

The monitoring will alert you if the API is down for 2 consecutive checks (10 minutes).
"