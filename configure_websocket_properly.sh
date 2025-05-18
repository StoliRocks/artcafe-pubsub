#!/bin/bash

# Configure WebSocket properly in API Gateway
API_ID="m9lm7i9ed7"
BACKEND_URL="http://3.229.1.223:8000"
AWS_REGION="us-east-1"

echo "Configuring WebSocket integration properly..."

# First, let's check existing integrations
echo "Checking existing integrations..."
aws apigatewayv2 get-integrations --api-id $API_ID --region $AWS_REGION

# Create a new integration specifically for WebSocket upgrade
echo "Creating WebSocket integration..."
INTEGRATION_RESPONSE=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/{proxy}" \
  --integration-method GET \
  --payload-format-version "1.0" \
  --request-parameters 'request.path.proxy=$request.path.proxy,request.querystring.auth=$request.querystring.auth,request.header.x-tenant-id=$request.header.x-tenant-id' \
  --region $AWS_REGION)

INTEGRATION_ID=$(echo $INTEGRATION_RESPONSE | jq -r '.IntegrationId')
echo "Created integration: $INTEGRATION_ID"

# Create the specific route for dashboard WebSocket
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "GET /ws/dashboard" \
  --target "integrations/$INTEGRATION_ID" \
  --region $AWS_REGION

echo "WebSocket route configured successfully!"