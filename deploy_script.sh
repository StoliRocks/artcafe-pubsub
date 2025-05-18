#!/bin/bash

# Deploy script for artcafe-pubsub API

# Create deployment package
cd /home/stvwhite/projects/artcafe/artcafe-pubsub

# Create a zip file with the application code
zip -r deploy_package.zip . -x "*.git*" -x "*__pycache__*" -x "*.pytest_cache*" -x "*.env*" -x "*.zip"

# Upload the deployment package to S3
aws s3 cp deploy_package.zip s3://artcafe-deployments/deploy_package.zip

# Create user data script for EC2 instance update
cat > update_script.sh << 'EOL'
#!/bin/bash

# Download deployment package from S3
aws s3 cp s3://artcafe-deployments/deploy_package.zip /tmp/deploy_package.zip

# Deploy to the EC2 instance
sudo su -
cd /opt/artcafe/artcafe-pubsub
unzip -o /tmp/deploy_package.zip
chown -R ec2-user:ec2-user /opt/artcafe
systemctl restart artcafe-pubsub
EOL

# Make script executable
chmod +x update_script.sh

# Create an SSM document to execute the update
cat > ssm_document.json << 'EOL'
{
  "schemaVersion": "1.2",
  "description": "Update artcafe-pubsub API service",
  "parameters": {},
  "runtimeConfig": {
    "aws:runShellScript": {
      "properties": [
        {
          "id": "0.aws:runShellScript",
          "runCommand": [
            "#!/bin/bash",
            "aws s3 cp s3://artcafe-deployments/deploy_package.zip /tmp/deploy_package.zip",
            "sudo su -",
            "cd /opt/artcafe/artcafe-pubsub",
            "unzip -o /tmp/deploy_package.zip",
            "chown -R ec2-user:ec2-user /opt/artcafe",
            "systemctl restart artcafe-pubsub"
          ]
        }
      ]
    }
  }
}
EOL

# Create the SSM document
aws ssm create-document \
  --name "UpdateArtCafePubSub" \
  --content file://ssm_document.json \
  --document-type "Command"

# Execute the SSM document on the instance
aws ssm send-command \
  --document-name "UpdateArtCafePubSub" \
  --targets "Key=instanceids,Values=i-0cd295d6b239ca775" \
  --comment "Update artcafe-pubsub API service"

echo "Deployment initiated. Check the AWS SSM console for command status."
