#!/bin/bash

# Create simple API Gateway proxy

REGION="us-east-1"
BACKEND_URL="http://3.229.1.223:8000"

echo "Creating API Gateway..."

# Create the API
API_ID=$(aws apigatewayv2 create-api \
    --name artcafe-proxy-api \
    --protocol-type HTTP \
    --cors-configuration AllowOrigins='*',AllowMethods='*',AllowHeaders='*',AllowCredentials=true \
    --region ${REGION} \
    --output text \
    --query 'ApiId')

echo "Created API: ${API_ID}"

# Create integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --integration-type HTTP_PROXY \
    --integration-uri ${BACKEND_URL} \
    --integration-method ANY \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --output text \
    --query 'IntegrationId')

echo "Created integration: ${INTEGRATION_ID}"

# Create route
ROUTE_ID=$(aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key '$default' \
    --target integrations/${INTEGRATION_ID} \
    --region ${REGION} \
    --output text \
    --query 'RouteId')

echo "Created route: ${ROUTE_ID}"

# Create deployment
DEPLOYMENT_ID=$(aws apigatewayv2 create-deployment \
    --api-id ${API_ID} \
    --region ${REGION} \
    --output text \
    --query 'DeploymentId')

echo "Created deployment: ${DEPLOYMENT_ID}"

# Create stage
aws apigatewayv2 create-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION} \
    --output json > /dev/null

# Get endpoint
ENDPOINT=$(aws apigatewayv2 get-api \
    --api-id ${API_ID} \
    --region ${REGION} \
    --output text \
    --query 'ApiEndpoint')

echo ""
echo "✅ API Gateway created successfully!"
echo ""
echo "API Endpoint: ${ENDPOINT}"
echo ""
echo "Testing the endpoint:"
curl -s ${ENDPOINT}/health

echo ""
echo ""
echo "Next steps:"
echo "1. Update frontend to use: ${ENDPOINT}"
echo "2. Or set up custom domain for api.artcafe.ai"