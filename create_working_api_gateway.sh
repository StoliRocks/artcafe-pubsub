#!/bin/bash

# Create API Gateway with proper CORS

REGION="us-east-1"
BACKEND_URL="http://3.229.1.223:8000"

echo "Creating API Gateway with proper CORS..."

# Create API without CORS first
API_ID=$(aws apigatewayv2 create-api \
    --name artcafe-api-proxy \
    --protocol-type HTTP \
    --region ${REGION} \
    --output text \
    --query 'ApiId')

if [ -z "$API_ID" ]; then
    echo "Failed to create API"
    exit 1
fi

echo "Created API: ${API_ID}"

# Now update CORS configuration
aws apigatewayv2 update-api \
    --api-id ${API_ID} \
    --cors-configuration \
        AllowOrigins=https://www.artcafe.ai,https://artcafe.ai,http://localhost:3000 \
        AllowMethods=GET,POST,PUT,DELETE,OPTIONS,PATCH \
        AllowHeaders=Authorization,Content-Type,X-Tenant-Id \
        AllowCredentials=true \
        MaxAge=600 \
    --region ${REGION} > /dev/null

echo "Updated CORS configuration"

# Create integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --integration-type HTTP_PROXY \
    --integration-uri "${BACKEND_URL}/\${request.path}" \
    --integration-method ANY \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --output text \
    --query 'IntegrationId')

echo "Created integration: ${INTEGRATION_ID}"

# Create default route
aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key '$default' \
    --target "integrations/${INTEGRATION_ID}" \
    --region ${REGION} > /dev/null

echo "Created default route"

# Create stage
aws apigatewayv2 create-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --auto-deploy \
    --region ${REGION} > /dev/null

echo "Created prod stage"

# Get the endpoint
ENDPOINT="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"

echo ""
echo "✅ API Gateway created successfully!"
echo ""
echo "API ID: ${API_ID}"
echo "Endpoint: ${ENDPOINT}"
echo ""
echo "Testing health endpoint:"
curl -s ${ENDPOINT}/health | jq . || echo "Failed to parse JSON"

echo ""
echo "Testing CORS headers:"
curl -I -X OPTIONS ${ENDPOINT}/api/v1/agents \
    -H "Origin: https://www.artcafe.ai" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Content-Type" \
    | grep -i "access-control"

echo ""
echo "To update your frontend, use: ${ENDPOINT}"