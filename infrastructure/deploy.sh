#!/bin/bash

# ArtCafe.ai PubSub Deployment Script

# Default values
ENV="dev"
REGION="us-east-1"
STACK_NAME="artcafe-pubsub"
KEY_NAME=""
NATS_INSTANCE_TYPE="t3.small"
API_INSTANCE_TYPE="t3.small"
CODE_PACKAGE="lambda.zip"
SKIP_PACKAGE=false

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --env)
            ENV="$2"
            shift
            shift
            ;;
        --region)
            REGION="$2"
            shift
            shift
            ;;
        --stack-name)
            STACK_NAME="$2"
            shift
            shift
            ;;
        --key-name)
            KEY_NAME="$2"
            shift
            shift
            ;;
        --nats-instance-type)
            NATS_INSTANCE_TYPE="$2"
            shift
            shift
            ;;
        --api-instance-type)
            API_INSTANCE_TYPE="$2"
            shift
            shift
            ;;
        --code-package)
            CODE_PACKAGE="$2"
            shift
            shift
            ;;
        --skip-package)
            SKIP_PACKAGE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set stack name based on environment
STACK_NAME="${STACK_NAME}-${ENV}"

# Check if key name is provided
if [ -z "$KEY_NAME" ]; then
    echo "Error: EC2 key pair name must be provided with --key-name"
    exit 1
fi

echo "Deploying ArtCafe.ai PubSub Service..."
echo "Environment: $ENV"
echo "Region: $REGION"
echo "Stack Name: $STACK_NAME"
echo "EC2 Key Name: $KEY_NAME"
echo "Code Package: $CODE_PACKAGE"

# Package the application code if not skipped
if [ "$SKIP_PACKAGE" = false ]; then
    echo "Packaging application code..."

    # Go to the project root directory
    cd $(dirname "$0")/..

    # Create a zip file with the application code
    zip -r $CODE_PACKAGE . -x "*.git*" -x "*__pycache__*" -x "*.pytest_cache*" -x "*.env*" -x "*.zip"

    echo "Application code packaged to $CODE_PACKAGE"

    # Return to the infrastructure directory
    cd $(dirname "$0")
fi

# Create or update CloudFormation stack
aws cloudformation deploy \
    --template-file cloudformation.yml \
    --stack-name $STACK_NAME \
    --region $REGION \
    --parameter-overrides \
        Environment=$ENV \
        KeyName=$KEY_NAME \
        NATSInstanceType=$NATS_INSTANCE_TYPE \
        APIInstanceType=$API_INSTANCE_TYPE \
    --capabilities CAPABILITY_IAM

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo "Deployment successful!"

    # Get stack outputs
    echo "Fetching deployment details..."
    OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs')

    # Extract API URL and IP
    API_URL=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="APIServerURL") | .OutputValue')
    API_IP=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="APIServerIP") | .OutputValue')

    # Transfer application code to EC2 instance if not skipped
    if [ "$SKIP_PACKAGE" = false ]; then
        echo "Transferring application code to EC2 instance..."

        # Go to the project root directory
        cd $(dirname "$0")/..

        # Wait a bit for instance to be ready
        echo "Waiting for instance to be ready..."
        sleep 30

        # Transfer the zip file to the EC2 instance
        scp -i ~/.ssh/"$KEY_NAME".pem -o StrictHostKeyChecking=no $CODE_PACKAGE ec2-user@$API_IP:/tmp/

        # SSH into the instance to unzip and set up the code
        ssh -i ~/.ssh/"$KEY_NAME".pem -o StrictHostKeyChecking=no ec2-user@$API_IP <<EOF
            sudo su -
            cd /opt/artcafe/artcafe-pubsub
            unzip -o /tmp/$CODE_PACKAGE
            chown -R ec2-user:ec2-user /opt/artcafe
            systemctl restart artcafe-pubsub
            exit
EOF

        echo "Application code deployed to EC2 instance"

        # Return to the infrastructure directory
        cd $(dirname "$0")
    fi

    echo ""
    echo "ArtCafe.ai PubSub Service is now available at: $API_URL"
    echo "API Endpoints:"
    echo "- $API_URL/api/v1/agents"
    echo "- $API_URL/api/v1/ssh-keys"
    echo "- $API_URL/api/v1/channels"
    echo "- $API_URL/api/v1/tenants"
    echo "- $API_URL/api/v1/usage-metrics"
    echo ""
    echo "Check the API documentation at: $API_URL/docs"
else
    echo "Deployment failed. Please check the AWS CloudFormation console for details."
    exit 1
fi