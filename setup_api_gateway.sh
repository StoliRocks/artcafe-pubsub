#!/bin/bash

# Setup AWS API Gateway for ArtCafe API

REGION="us-east-1"
API_NAME="artcafe-api"
BACKEND_URL="http://3.229.1.223:8000"
STAGE_NAME="prod"

echo "Setting up AWS API Gateway for ArtCafe API..."

# Create HTTP API
echo "Creating HTTP API..."
API_ID=$(aws apigatewayv2 create-api \
    --name ${API_NAME} \
    --protocol-type HTTP \
    --cors-configuration '{
        "AllowOrigins": ["https://www.artcafe.ai", "https://artcafe.ai", "http://localhost:3000"],
        "AllowMethods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "AllowHeaders": ["*"],
        "AllowCredentials": true,
        "MaxAge": 600
    }' \
    --region ${REGION} \
    --query 'ApiId' \
    --output text)

echo "API created with ID: ${API_ID}"

# Create integration to backend
echo "Creating backend integration..."
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id ${API_ID} \
    --integration-type HTTP_PROXY \
    --integration-uri ${BACKEND_URL}/\$\{proxy\} \
    --integration-method ANY \
    --payload-format-version 1.0 \
    --region ${REGION} \
    --query 'IntegrationId' \
    --output text)

echo "Integration created with ID: ${INTEGRATION_ID}"

# Create route for all paths
echo "Creating routes..."
ROUTE_ID=$(aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key 'ANY /{proxy+}' \
    --target integrations/${INTEGRATION_ID} \
    --region ${REGION} \
    --query 'RouteId' \
    --output text)

# Also create root route
ROOT_ROUTE_ID=$(aws apigatewayv2 create-route \
    --api-id ${API_ID} \
    --route-key 'ANY /' \
    --target integrations/${INTEGRATION_ID} \
    --region ${REGION} \
    --query 'RouteId' \
    --output text)

echo "Routes created"

# Create deployment and stage
echo "Creating deployment..."
DEPLOYMENT_ID=$(aws apigatewayv2 create-deployment \
    --api-id ${API_ID} \
    --region ${REGION} \
    --query 'DeploymentId' \
    --output text)

echo "Creating stage..."
aws apigatewayv2 create-stage \
    --api-id ${API_ID} \
    --stage-name ${STAGE_NAME} \
    --deployment-id ${DEPLOYMENT_ID} \
    --region ${REGION}

# Get the API endpoint
API_ENDPOINT=$(aws apigatewayv2 get-api \
    --api-id ${API_ID} \
    --region ${REGION} \
    --query 'ApiEndpoint' \
    --output text)

echo ""
echo "API Gateway setup complete!"
echo "API ID: ${API_ID}"
echo "API Endpoint: ${API_ENDPOINT}"
echo ""
echo "Next steps:"
echo "1. Update your frontend to use: ${API_ENDPOINT}/api/v1"
echo "2. Set up custom domain api.artcafe.ai to point to this API Gateway"
echo "3. Update DNS CNAME record for api.artcafe.ai"
echo ""

# Create custom domain (optional)
echo "To set up custom domain, run:"
echo "aws apigatewayv2 create-domain-name --domain-name api.artcafe.ai --domain-name-configurations CertificateArn=<YOUR_ACM_CERT_ARN>"