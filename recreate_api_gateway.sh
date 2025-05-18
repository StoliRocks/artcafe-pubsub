#!/bin/bash

# Recreate API Gateway with simple proxy configuration

REGION="us-east-1"
API_NAME="artcafe-api-v2"
BACKEND_URL="http://3.229.1.223:8000"

echo "Creating new API Gateway..."

# Delete the old API first
echo "Cleaning up old API..."
aws apigatewayv2 delete-api --api-id tpj6ehjr1i --region ${REGION} 2>/dev/null || true

# Create new HTTP API with simple configuration
echo "Creating HTTP API..."
API_RESPONSE=$(aws apigatewayv2 create-api \
    --name ${API_NAME} \
    --protocol-type HTTP \
    --version "1.0" \
    --route-selection-expression "\$request.method \$request.path" \
    --cors-configuration \
        AllowOrigins=https://www.artcafe.ai,https://artcafe.ai,http://localhost:3000 \
        AllowMethods=GET,POST,PUT,DELETE,OPTIONS,PATCH \
        AllowHeaders=Authorization,Content-Type,X-Tenant-Id \
        AllowCredentials=true \
        MaxAge=600 \
    --region ${REGION})

API_ID=$(echo $API_RESPONSE | jq -r '.ApiId')
echo "API created with ID: ${API_ID}"

# Create the integration
echo "Creating integration..."
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --connection-type INTERNET \
    --integration-method ANY \
    --integration-type HTTP_PROXY \
    --integration-uri ${BACKEND_URL}/\'{proxy}\' \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --query 'IntegrationId' \
    --output text)

echo "Integration created: ${INTEGRATION_ID}"

# Create routes
echo "Creating routes..."

# Create default route
DEFAULT_ROUTE=$(aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key '\$default' \
    --target integrations/${INTEGRATION_ID} \
    --region ${REGION} \
    --query 'RouteId' \
    --output text)

echo "Default route created: ${DEFAULT_ROUTE}"

# Create deployment
echo "Creating deployment..."
DEPLOYMENT_ID=$(aws apigatewayv2 create-deployment \
    --api-id ${API_ID} \
    --description "Initial deployment" \
    --region ${REGION} \
    --query 'DeploymentId' \
    --output text)

# Create or update stage
echo "Creating stage..."
aws apigatewayv2 create-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION} || \
aws apigatewayv2 update-stage \
    --api-id ${API_ID} \
    --stage-name prod \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION}

# Get the endpoint
ENDPOINT=$(aws apigatewayv2 get-api \
    --api-id ${API_ID} \
    --region ${REGION} \
    --query 'ApiEndpoint' \
    --output text)

echo ""
echo "API Gateway created successfully!"
echo "API ID: ${API_ID}"
echo "Endpoint: ${ENDPOINT}"
echo ""
echo "Testing health endpoint..."
curl -s ${ENDPOINT}/health | jq .

echo ""
echo "Update your frontend to use: ${ENDPOINT}"