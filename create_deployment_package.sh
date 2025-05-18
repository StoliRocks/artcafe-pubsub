#!/bin/bash

# Create a deployment package for manual upload

echo "Creating deployment package with CORS updates..."

# Create clean directory
rm -rf deployment_package
mkdir -p deployment_package

# Copy only necessary files
cp -r config api models auth deployment_package/
cp requirements.txt deployment_package/

# Remove unnecessary files
find deployment_package -name "*.pyc" -delete
find deployment_package -name "__pycache__" -type d -exec rm -rf {} +
find deployment_package -name "*.fixed" -delete
find deployment_package -name "*.bak" -delete

# Create the zip file
cd deployment_package
zip -r ../artcafe_pubsub_cors_update.zip .
cd ..

# Clean up
rm -rf deployment_package

echo ""
echo "Deployment package created: artcafe_pubsub_cors_update.zip"
echo ""
echo "To deploy this package:"
echo "1. Upload to your EC2 instance:"
echo "   scp artcafe_pubsub_cors_update.zip ec2-user@3.229.1.223:~/"
echo ""
echo "2. SSH to your instance and run:"
echo "   cd /home/ec2-user/artcafe-pubsub"
echo "   sudo systemctl stop artcafe-pubsub"
echo "   unzip -o ~/artcafe_pubsub_cors_update.zip"
echo "   sudo systemctl start artcafe-pubsub"
echo ""
echo "The backend will then accept requests from api.artcafe.ai"