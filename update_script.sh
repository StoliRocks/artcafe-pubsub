#!/bin/bash

# Download deployment package from S3
aws s3 cp s3://artcafe-deployments/deploy_package.zip /tmp/deploy_package.zip

# Deploy to the EC2 instance
sudo su -
cd /opt/artcafe/artcafe-pubsub
unzip -o /tmp/deploy_package.zip
chown -R ec2-user:ec2-user /opt/artcafe
systemctl restart artcafe-pubsub
