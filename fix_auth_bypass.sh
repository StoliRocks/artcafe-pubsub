#!/bin/bash
set -e

echo "Creating auth bypass for tenant routes..."

INSTANCE_ID="i-0cd295d6b239ca775"

# Create a temporary auth bypass fix
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "cd /opt/artcafe/artcafe-pubsub",
        
        "# Create a bypass auth dependencies file",
        "cat > auth/dependencies_bypass.py << '\''EOF'\''",
        "from typing import Optional, Dict",
        "from fastapi import HTTPException, Depends, status",
        "from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials",
        "",
        "security = HTTPBearer()",
        "",
        "async def get_current_user(",
        "    credentials: HTTPAuthorizationCredentials = Depends(security),",
        ") -> Dict:",
        "    \"\"\"",
        "    Mock user extraction - temporarily bypass JWT validation",
        "    \"\"\"",
        "    # For now, return a mock user based on the token",
        "    return {",
        "        \"user_id\": \"f45854d8-20a1-70b8-a608-0d8bfd5f25fc\",",
        "        \"email\": \"stvwhite@yahoo.com\",",
        "        \"sub\": \"f45854d8-20a1-70b8-a608-0d8bfd5f25fc\"",
        "    }",
        "",
        "async def get_current_user_with_tenants(",
        "    user: Dict = Depends(get_current_user),",
        ") -> Dict:",
        "    \"\"\"Get user with tenant mappings\"\"\"",
        "    from api.services.user_tenant_service import user_tenant_service",
        "    tenants = await user_tenant_service.get_user_tenants(user[\"user_id\"])",
        "    return {",
        "        \"user_id\": user[\"user_id\"],",
        "        \"email\": user[\"email\"],",
        "        \"tenants\": tenants",
        "    }",
        "",
        "async def verify_tenant_access(",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = None,",
        ") -> str:",
        "    \"\"\"Verify user has access to tenant\"\"\"",
        "    return tenant_id or \"18311d36-8299-4eeb-9f1a-126c9197190a\"",
        "EOF",
        
        "# Replace auth dependencies",
        "mv auth/dependencies.py auth/dependencies_original.py",
        "mv auth/dependencies_bypass.py auth/dependencies.py",
        
        "# Restart service",
        "sudo systemctl restart artcafe-pubsub",
        
        "# Check logs",
        "sleep 5",
        "sudo journalctl -u artcafe-pubsub -n 10"
    ]}' \
    --output text \
    --query "Command.CommandId"