#!/bin/bash

# Fix the API Gateway integration

API_ID="m9lm7i9ed7"
INTEGRATION_ID="d81prob"
REGION="us-east-1"
BACKEND_URL="http://3.229.1.223:8000"

echo "Fixing API Gateway integration..."

# Delete the problematic integration
aws apigatewayv2 delete-integration \
    --api-id ${API_ID} \
    --integration-id ${INTEGRATION_ID} \
    --region ${REGION} 2>/dev/null || true

# Create new integration with simpler path
NEW_INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --integration-type HTTP_PROXY \
    --integration-uri ${BACKEND_URL} \
    --integration-method ANY \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --output text \
    --query 'IntegrationId')

echo "Created new integration: ${NEW_INTEGRATION_ID}"

# Create route
aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key '$default' \
    --target "integrations/${NEW_INTEGRATION_ID}" \
    --region ${REGION} > /dev/null

echo "Created route"

# Deploy changes
DEPLOYMENT_ID=$(aws apigatewayv2 create-deployment \
    --api-id ${API_ID} \
    --region ${REGION} \
    --output text \
    --query 'DeploymentId')

aws apigatewayv2 update-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION} > /dev/null

echo "Deployed changes"

# Test the endpoint
ENDPOINT="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"

echo ""
echo "Testing endpoints:"
echo "Health check:"
curl -s ${ENDPOINT}/health | jq .

echo ""
echo "API info:"
curl -s ${ENDPOINT}/ | jq .

echo ""
echo "CORS test:"
curl -I -X OPTIONS ${ENDPOINT}/api/v1/agents \
    -H "Origin: https://www.artcafe.ai" \
    -H "Access-Control-Request-Method: POST" \
    2>/dev/null | grep -i access-control

echo ""
echo "Your API Gateway is ready at: ${ENDPOINT}"