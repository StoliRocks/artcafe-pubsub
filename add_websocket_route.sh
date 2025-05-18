#!/bin/bash

# Add WebSocket route to existing API Gateway
API_ID="m9lm7i9ed7"
BACKEND_URL="http://3.229.1.223:8000"
AWS_REGION="us-east-1"

echo "Adding WebSocket route to existing API..."

# Create integration for WebSocket endpoint
INTEGRATION_RESPONSE=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/dashboard" \
  --integration-method ANY \
  --payload-format-version "1.0" \
  --region $AWS_REGION)

INTEGRATION_ID=$(echo $INTEGRATION_RESPONSE | jq -r '.IntegrationId')
echo "Created integration: $INTEGRATION_ID"

# Create route for WebSocket path
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "ANY /ws/dashboard" \
  --target "integrations/$INTEGRATION_ID" \
  --region $AWS_REGION

# Also create a generic ws route
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "ANY /ws/{proxy+}" \
  --target "integrations/$INTEGRATION_ID" \
  --region $AWS_REGION

echo "WebSocket routes added successfully!"