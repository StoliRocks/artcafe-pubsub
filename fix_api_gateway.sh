#!/bin/bash

# Fix API Gateway routes

API_ID="tpj6ehjr1i"
INTEGRATION_ID="1h22ou9"
REGION="us-east-1"
BACKEND_URL="http://3.229.1.223:8000"

echo "Fixing API Gateway routes..."

# Delete the existing integration
echo "Deleting existing integration..."
aws apigatewayv2 delete-integration \
    --api-id ${API_ID} \
    --integration-id ${INTEGRATION_ID} \
    --region ${REGION} 2>/dev/null || true

# Create new integration without proxy in URI
echo "Creating new integration..."
NEW_INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --integration-type HTTP_PROXY \
    --integration-uri ${BACKEND_URL}/\${request.path} \
    --integration-method ANY \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --query 'IntegrationId' \
    --output text)

echo "New integration created with ID: ${NEW_INTEGRATION_ID}"

# Create catch-all route
echo "Creating catch-all route..."
ROUTE_ID=$(aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key '\$default' \
    --target integrations/${NEW_INTEGRATION_ID} \
    --region ${REGION} \
    --query 'RouteId' \
    --output text)

echo "Route created with ID: ${ROUTE_ID}"

# Create new deployment
echo "Creating new deployment..."
DEPLOYMENT_ID=$(aws apigatewayv2 create-deployment \
    --api-id ${API_ID} \
    --region ${REGION} \
    --query 'DeploymentId' \
    --output text)

# Update stage with new deployment
echo "Updating stage..."
aws apigatewayv2 update-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION}

echo ""
echo "API Gateway fixed!"
echo "Testing the API..."
curl -s https://tpj6ehjr1i.execute-api.us-east-1.amazonaws.com/health | jq .

echo ""
echo "Your API is now available at:"
echo "https://tpj6ehjr1i.execute-api.us-east-1.amazonaws.com"