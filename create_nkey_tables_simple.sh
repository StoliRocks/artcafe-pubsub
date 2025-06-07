#!/bin/bash
# Simple script to create NKey tables on EC2

echo "🚀 Creating NKey tables on production..."

# Run commands directly via SSM
aws ssm send-command \
    --instance-ids i-0cd295d6b239ca775 \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "echo \"Creating artcafe-accounts table...\"",
        "aws dynamodb create-table --table-name artcafe-accounts --attribute-definitions AttributeName=account_id,AttributeType=S AttributeName=nkey_public,AttributeType=S --key-schema AttributeName=account_id,KeyType=HASH --global-secondary-indexes \"[{\\\"IndexName\\\":\\\"NKeyIndex\\\",\\\"KeySchema\\\":[{\\\"AttributeName\\\":\\\"nkey_public\\\",\\\"KeyType\\\":\\\"HASH\\\"}],\\\"Projection\\\":{\\\"ProjectionType\\\":\\\"ALL\\\"}}]\" --billing-mode PAY_PER_REQUEST --region us-east-1 || echo \"Table exists\"",
        "echo \"Creating artcafe-clients table...\"",
        "aws dynamodb create-table --table-name artcafe-clients --attribute-definitions AttributeName=client_id,AttributeType=S AttributeName=account_id,AttributeType=S AttributeName=nkey_public,AttributeType=S --key-schema AttributeName=client_id,KeyType=HASH --global-secondary-indexes \"[{\\\"IndexName\\\":\\\"AccountIndex\\\",\\\"KeySchema\\\":[{\\\"AttributeName\\\":\\\"account_id\\\",\\\"KeyType\\\":\\\"HASH\\\"}],\\\"Projection\\\":{\\\"ProjectionType\\\":\\\"ALL\\\"}},{\\\"IndexName\\\":\\\"NKeyIndex\\\",\\\"KeySchema\\\":[{\\\"AttributeName\\\":\\\"nkey_public\\\",\\\"KeyType\\\":\\\"HASH\\\"}],\\\"Projection\\\":{\\\"ProjectionType\\\":\\\"ALL\\\"}}]\" --billing-mode PAY_PER_REQUEST --region us-east-1 || echo \"Table exists\"",
        "echo \"Creating artcafe-subjects table...\"",
        "aws dynamodb create-table --table-name artcafe-subjects --attribute-definitions AttributeName=subject_id,AttributeType=S AttributeName=account_id,AttributeType=S --key-schema AttributeName=subject_id,KeyType=HASH --global-secondary-indexes \"[{\\\"IndexName\\\":\\\"AccountIndex\\\",\\\"KeySchema\\\":[{\\\"AttributeName\\\":\\\"account_id\\\",\\\"KeyType\\\":\\\"HASH\\\"}],\\\"Projection\\\":{\\\"ProjectionType\\\":\\\"ALL\\\"}}]\" --billing-mode PAY_PER_REQUEST --region us-east-1 || echo \"Table exists\"",
        "echo \"Creating artcafe-nkey-seeds table...\"",
        "aws dynamodb create-table --table-name artcafe-nkey-seeds --attribute-definitions AttributeName=seed_id,AttributeType=S --key-schema AttributeName=seed_id,KeyType=HASH --billing-mode PAY_PER_REQUEST --region us-east-1 || echo \"Table exists\"",
        "echo \"Enabling TTL on seeds table...\"",
        "aws dynamodb update-time-to-live --table-name artcafe-nkey-seeds --time-to-live-specification Enabled=true,AttributeName=ttl --region us-east-1 || echo \"TTL already enabled\"",
        "echo \"✅ Done! Listing new tables...\"",
        "aws dynamodb list-tables --region us-east-1 | grep -E \\\"(artcafe-accounts|artcafe-clients|artcafe-subjects|artcafe-nkey)\\\" | sort"
    ]' \
    --output text \
    --query 'Command.CommandId'

echo "✅ Command sent to create tables"