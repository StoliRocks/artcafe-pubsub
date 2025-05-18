#!/bin/bash

# Fix WebSocket authentication handling
AWS_REGION="us-east-1"

echo "Fixing WebSocket authentication handling..."

# Update the dashboard WebSocket route to handle base64 encoded auth
cat << 'EOF' > /tmp/fix_websocket_auth.py
import os
import base64
import json

# Fix the WebSocket authentication in dashboard routes
route_file = "/opt/artcafe/artcafe-pubsub/api/routes/dashboard_websocket_routes.py"

with open(route_file, 'r') as f:
    content = f.read()

# Replace the auth handling section
new_auth_section = '''@router.websocket("/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    auth: Optional[str] = None,
    x_tenant_id: Optional[str] = None
):
    """
    WebSocket endpoint for dashboard real-time updates
    
    Clients should connect with authentication headers:
    - Authorization: Bearer <token>
    - x-tenant-id: <tenant_id>
    """
    # Extract auth from query params
    token = None
    tenant_id = x_tenant_id
    
    if auth:
        try:
            # Decode base64 auth info
            auth_json = base64.b64decode(auth).decode('utf-8')
            auth_info = json.loads(auth_json)
            token = auth_info.get('token')
            tenant_id = auth_info.get('tenantId') or x_tenant_id
        except Exception as e:
            logger.error(f"Failed to decode auth: {e}")
    
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    if not tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return'''

# Find and replace the websocket endpoint definition
content = content.replace(
    '@router.websocket("/dashboard")\nasync def dashboard_websocket(\n    websocket: WebSocket,\n    token: Optional[str] = None,\n    x_tenant_id: Optional[str] = None\n):',
    new_auth_section
)

# Also add necessary imports at the top
if 'import base64' not in content:
    content = 'import base64\n' + content

with open(route_file, 'w') as f:
    f.write(content)

print("Fixed WebSocket authentication handling")
EOF

# Apply the fix on the EC2 instance
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=['cd /opt/artcafe/artcafe-pubsub && python3 /tmp/fix_websocket_auth.py']" \
  --document-version '$DEFAULT' \
  --timeout-seconds 600 \
  --service-role-arn "arn:aws:iam::767397979228:role/MySSMExecutionRole" \
  --region $AWS_REGION

echo "WebSocket auth fix applied to EC2 instance"