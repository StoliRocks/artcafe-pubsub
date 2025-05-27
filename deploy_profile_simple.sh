#!/bin/bash
# Simple deployment of profile routes

echo "Deploying profile routes to EC2..."

# First, let's check current files on EC2
echo "Checking current state..."
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters '{"commands":[
    "cd /opt/artcafe/artcafe-pubsub",
    "ls -la api/routes/ | grep profile",
    "ls -la api/services/ | grep profile",
    "ls -la models/ | grep profile"
  ]}' \
  --output json > check_result.json

COMMAND_ID=$(jq -r '.Command.CommandId' check_result.json)
echo "Check command ID: $COMMAND_ID"

sleep 5

echo "Current files on EC2:"
aws ssm get-command-invocation \
  --command-id $COMMAND_ID \
  --instance-id i-0cd295d6b239ca775 \
  --query "StandardOutputContent" \
  --output text

# Create profile files inline
echo "Creating profile files on EC2..."

# Create profile routes
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters '{"commands":[
    "cd /opt/artcafe/artcafe-pubsub",
    "cat > api/routes/profile_routes.py << '\''EOF'\''",
"from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Optional
from pydantic import BaseModel, EmailStr

from auth.dependencies import get_current_user
from api.services.user_tenant_service import user_tenant_service
from api.services.tenant_service import tenant_service

router = APIRouter(prefix=\"/profile\", tags=[\"profile\"])

@router.get(\"/me\")
async def get_current_user_profile(
    user: Dict = Depends(get_current_user)
):
    \"\"\"Get current user profile\"\"\"
    try:
        user_id = user.get(\"user_id\", user.get(\"sub\"))
        email = user.get(\"email\", \"\")
        name = user.get(\"name\", \"\")
        
        # For now, return basic profile from JWT
        profile = {
            \"user_id\": user_id,
            \"email\": email,
            \"name\": name,
            \"display_name\": name,
            \"bio\": \"\",
            \"website\": \"\",
            \"location\": \"\",
            \"phone_number\": \"\",
            \"timezone\": \"UTC\"
        }
        
        return profile
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f\"Error fetching user profile: {str(e)}\"
        )

@router.put(\"/me\")
async def update_current_user_profile(
    profile_data: Dict,
    user: Dict = Depends(get_current_user)
):
    \"\"\"Update current user profile\"\"\"
    try:
        user_id = user.get(\"user_id\", user.get(\"sub\"))
        
        # For now, just return the updated data
        # In production, this would save to DynamoDB
        return {
            \"user_id\": user_id,
            **profile_data
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f\"Error updating user profile: {str(e)}\"
        )

@router.get(\"/preferences\")
async def get_user_preferences(
    user: Dict = Depends(get_current_user)
):
    \"\"\"Get user preferences\"\"\"
    return {
        \"email_enabled\": True,
        \"push_enabled\": False,
        \"notification_types\": {
            \"agent_status\": True,
            \"billing_alerts\": True,
            \"system_updates\": True,
            \"security_alerts\": True
        }
    }

@router.put(\"/preferences\")
async def update_user_preferences(
    preferences: Dict,
    user: Dict = Depends(get_current_user)
):
    \"\"\"Update user preferences\"\"\"
    return preferences
EOF",
    "echo \"Profile routes created\"",
    "sudo systemctl restart artcafe-pubsub",
    "sleep 3",
    "curl -s -I https://api.artcafe.ai/api/v1/profile/me | head -n 1"
  ]}' \
  --output json > deploy_result.json

DEPLOY_ID=$(jq -r '.Command.CommandId' deploy_result.json)
echo "Deploy command ID: $DEPLOY_ID"

sleep 10

echo "Deployment result:"
aws ssm get-command-invocation \
  --command-id $DEPLOY_ID \
  --instance-id i-0cd295d6b239ca775 \
  --query "StandardOutputContent" \
  --output text

echo "Deployment errors (if any):"
aws ssm get-command-invocation \
  --command-id $DEPLOY_ID \
  --instance-id i-0cd295d6b239ca775 \
  --query "StandardErrorContent" \
  --output text

# Cleanup
rm -f check_result.json deploy_result.json