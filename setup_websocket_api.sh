#!/bin/bash

# Create WebSocket API
echo "Creating WebSocket API..."
AWS_REGION="us-east-1"
BACKEND_URL="http://3.229.1.223:8000"

# Create the WebSocket API
API_RESPONSE=$(aws apigatewayv2 create-api \
  --name "artcafe-websocket" \
  --protocol-type WEBSOCKET \
  --route-selection-expression '$request.body.action' \
  --region $AWS_REGION)

API_ID=$(echo $API_RESPONSE | jq -r '.ApiId')
echo "Created WebSocket API: $API_ID"

# Create routes for WebSocket connections
echo "Creating routes..."

# $connect route
CONNECT_INTEGRATION=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/dashboard" \
  --integration-method POST \
  --region $AWS_REGION)

CONNECT_INTEGRATION_ID=$(echo $CONNECT_INTEGRATION | jq -r '.IntegrationId')

aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key '$connect' \
  --integration-id $CONNECT_INTEGRATION_ID \
  --region $AWS_REGION

# $disconnect route
DISCONNECT_INTEGRATION=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/dashboard" \
  --integration-method POST \
  --region $AWS_REGION)

DISCONNECT_INTEGRATION_ID=$(echo $DISCONNECT_INTEGRATION | jq -r '.IntegrationId')

aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key '$disconnect' \
  --integration-id $DISCONNECT_INTEGRATION_ID \
  --region $AWS_REGION

# $default route
DEFAULT_INTEGRATION=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type HTTP_PROXY \
  --integration-uri "$BACKEND_URL/ws/dashboard" \
  --integration-method POST \
  --region $AWS_REGION)

DEFAULT_INTEGRATION_ID=$(echo $DEFAULT_INTEGRATION | jq -r '.IntegrationId')

aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key '$default' \
  --integration-id $DEFAULT_INTEGRATION_ID \
  --region $AWS_REGION

# Deploy the WebSocket API
echo "Deploying WebSocket API..."
DEPLOYMENT=$(aws apigatewayv2 create-deployment \
  --api-id $API_ID \
  --stage-name prod \
  --region $AWS_REGION)

# Get the WebSocket URL
API_ENDPOINT=$(aws apigatewayv2 get-api \
  --api-id $API_ID \
  --region $AWS_REGION | jq -r '.ApiEndpoint')

echo "WebSocket API deployed successfully!"
echo "WebSocket URL: $API_ENDPOINT"
echo "API ID: $API_ID"