#!/bin/bash

# Enable CORS for WebSocket routes in API Gateway
API_ID="m9lm7i9ed7"
AWS_REGION="us-east-1"

echo "Configuring CORS for WebSocket routes..."

# Update CORS configuration to include WebSocket routes
aws apigatewayv2 update-api \
  --api-id $API_ID \
  --cors-configuration AllowOrigins="*",AllowMethods="*",AllowHeaders="*",AllowCredentials=true \
  --region $AWS_REGION

echo "CORS configuration updated for WebSocket routes"