#!/bin/bash

# Simple monitoring deployment for ArtCafe PubSub

EMAIL="steve@oldbluechair.com"
REGION="us-east-1"
API_ENDPOINT="http://3.229.1.223:8000"

echo "Setting up monitoring for ArtCafe PubSub API..."

# 1. Create SNS topic if it doesn't exist
echo "Creating SNS topic..."
TOPIC_ARN=$(aws sns create-topic --name artcafe-pubsub-alerts --region $REGION --query 'TopicArn' --output text)

# 2. Subscribe email
echo "Adding email subscription..."
aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol email \
    --notification-endpoint $EMAIL \
    --region $REGION

# 3. Create CloudWatch Log Group
echo "Creating log group..."
aws logs create-log-group \
    --log-group-name /aws/ec2/artcafe-pubsub \
    --region $REGION 2>/dev/null || true

# 4. Create monitoring metrics namespace
echo "Creating custom metrics..."

# 5. Create health check alarm
echo "Creating health check alarm..."
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-api-health-check" \
    --alarm-description "API health check failure" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --evaluation-periods 2 \
    --datapoints-to-alarm 2 \
    --threshold 1 \
    --comparison-operator LessThanThreshold \
    --treat-missing-data breaching \
    --region $REGION \
    --metric-name HealthCheckSuccess \
    --namespace "ArtCafePubSub" \
    --statistic Average \
    --period 60

# 6. Create high error rate alarm
echo "Creating error rate alarm..."
aws cloudwatch put-metric-alarm \
    --alarm-name "artcafe-api-high-errors" \
    --alarm-description "High error rate detected" \
    --actions-enabled \
    --alarm-actions $TOPIC_ARN \
    --evaluation-periods 1 \
    --threshold 10 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --region $REGION \
    --metric-name ErrorCount \
    --namespace "ArtCafePubSub" \
    --statistic Sum \
    --period 300

# 7. Deploy monitoring script to EC2
echo "Deploying monitoring script to EC2..."
aws s3 cp monitor.sh s3://artcafe-deployments/monitoring/monitor.sh
aws s3 cp send_service_notification.sh s3://artcafe-deployments/monitoring/send_service_notification.sh

INSTANCE_ID="i-0cd295d6b239ca775"
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "sudo aws s3 cp s3://artcafe-deployments/monitoring/monitor.sh /opt/artcafe/artcafe-pubsub/monitor.sh",
        "sudo chmod +x /opt/artcafe/artcafe-pubsub/monitor.sh",
        "sudo aws s3 cp s3://artcafe-deployments/monitoring/send_service_notification.sh /usr/local/bin/",
        "sudo chmod +x /usr/local/bin/send_service_notification.sh",
        "sudo mkdir -p /var/log/artcafe",
        "echo \"*/1 * * * * /opt/artcafe/artcafe-pubsub/monitor.sh > /var/log/artcafe/monitor.log 2>&1\" | sudo crontab -"
    ]' \
    --region $REGION \
    --output json > /tmp/ssm_command.json

COMMAND_ID=$(cat /tmp/ssm_command.json | jq -r '.Command.CommandId')

# 8. Create CloudWatch dashboard
echo "Creating CloudWatch dashboard..."
cat > /tmp/dashboard.json << EOF
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["ArtCafePubSub", "HealthCheckSuccess", { "stat": "Average" }],
          [".", "ErrorCount", { "stat": "Sum" }]
        ],
        "period": 300,
        "stat": "Average",
        "region": "$REGION",
        "title": "API Health Status"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["ArtCafePubSub", "ResponseTime", { "stat": "Average" }]
        ],
        "period": 300,
        "stat": "Average",
        "region": "$REGION",
        "title": "Response Time"
      }
    }
  ]
}
EOF

aws cloudwatch put-dashboard \
    --dashboard-name artcafe-pubsub-monitoring \
    --dashboard-body file:///tmp/dashboard.json \
    --region $REGION

echo
echo "✅ Monitoring setup complete!"
echo
echo "SNS Topic: $TOPIC_ARN"
echo "Dashboard: https://console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards:name=artcafe-pubsub-monitoring"
echo
echo "Please check your email (steve@oldbluechair.com) for the SNS subscription confirmation."
echo
echo "To send a test metric:"
echo "aws cloudwatch put-metric-data --namespace ArtCafePubSub --metric-name HealthCheckSuccess --value 0"
echo