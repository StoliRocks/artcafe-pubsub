#!/bin/bash

# Simple WebSocket fix for API Gateway
API_ID="m9lm7i9ed7"
BACKEND_URL="http://3.229.1.223:8000"
AWS_REGION="us-east-1"

echo "Creating simple WebSocket route..."

# Create a direct route for the dashboard WebSocket
INTEGRATION_RESPONSE=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/dashboard" \
  --integration-method GET \
  --payload-format-version "1.0" \
  --region $AWS_REGION)

INTEGRATION_ID=$(echo $INTEGRATION_RESPONSE | jq -r '.IntegrationId')
echo "Created integration: $INTEGRATION_ID"

if [ "$INTEGRATION_ID" != "null" ]; then
  # Create the route
  aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key "GET /ws/dashboard" \
    --target "integrations/$INTEGRATION_ID" \
    --region $AWS_REGION
    
  echo "Route created successfully!"
else
  echo "Failed to create integration"
fi