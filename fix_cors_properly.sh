#!/bin/bash

# Fix CORS configuration for API Gateway
API_ID="m9lm7i9ed7"
AWS_REGION="us-east-1"

echo "Fixing CORS configuration..."

# Update CORS configuration with specific origins
aws apigatewayv2 update-api \
  --api-id $API_ID \
  --cors-configuration \
    AllowOrigins='"https://www.artcafe.ai","https://artcafe.ai","http://localhost:3000"',\
AllowMethods='"GET","POST","PUT","DELETE","OPTIONS","PATCH"',\
AllowHeaders='"Authorization","Content-Type","X-Tenant-Id"',\
AllowCredentials=true,\
MaxAge=600 \
  --region $AWS_REGION

echo "CORS configuration updated"