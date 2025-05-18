#!/bin/bash

# Send service notification to CloudWatch

STATUS="${1:-unknown}"
SERVICE_NAME="artcafe-pubsub"
NAMESPACE="ArtCafePubSub"
REGION="us-east-1"

# Send metric
aws cloudwatch put-metric-data \
    --metric-name "ServiceStatus" \
    --namespace "$NAMESPACE" \
    --value 0 \
    --unit None \
    --dimensions Service=$SERVICE_NAME,Status=$STATUS \
    --region $REGION

# Log event
aws logs put-log-events \
    --log-group-name "/aws/ec2/artcafe-pubsub" \
    --log-stream-name "systemd" \
    --log-events "timestamp=$(date +%s000),message=[ERROR] Service $SERVICE_NAME $STATUS" \
    --region $REGION || true