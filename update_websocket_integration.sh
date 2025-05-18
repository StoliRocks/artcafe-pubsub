#!/bin/bash

# Update WebSocket integration to pass headers
API_ID="m9lm7i9ed7"
INTEGRATION_ID="ayhyuca"
AWS_REGION="us-east-1"

echo "Updating WebSocket integration to pass headers..."

# Update the integration to pass WebSocket headers
aws apigatewayv2 update-integration \
  --api-id $API_ID \
  --integration-id $INTEGRATION_ID \
  --request-parameters '{
    "append:header.Connection": "Upgrade",
    "append:header.Upgrade": "websocket",
    "overwrite:path": "$request.path"
  }' \
  --region $AWS_REGION

echo "Integration updated to pass WebSocket headers"