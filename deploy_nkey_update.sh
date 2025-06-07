#!/bin/bash
# Deploy NKey update to EC2

echo "🚀 Deploying NKey backend update..."

# Create deployment package
echo "📦 Creating deployment package..."
tar -czf nkey_update.tar.gz \
    models/account.py \
    models/client.py \
    models/subject.py \
    infrastructure/create_tables_fixed.py \
    infrastructure/dynamodb_new_schema.json

# Copy to EC2
echo "📤 Copying to EC2..."
scp -i ~/.ssh/artcafe-deploy.pem nkey_update.tar.gz ubuntu@3.229.1.223:/tmp/

# Deploy via SSM
echo "🔧 Deploying via SSM..."
aws ssm send-command \
    --instance-ids i-0cd295d6b239ca775 \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "tar -xzf /tmp/nkey_update.tar.gz",
        "source venv/bin/activate",
        "cd infrastructure && python3 create_tables_fixed.py",
        "cd ..",
        "echo \"✅ Tables created, restarting service...\"",
        "sudo systemctl restart artcafe-pubsub"
    ]' \
    --query 'Command.CommandId' \
    --output text

echo "✅ Deployment initiated"