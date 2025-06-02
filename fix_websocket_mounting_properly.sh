#!/bin/bash
set -e

echo "=== Fixing WebSocket Route Mounting (Properly) ==="
echo ""

INSTANCE_ID="i-0cd295d6b239ca775"

# Fix the mounting
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Current mounting in app.py:\"",
        "grep -n \"include_router.*router\" api/app.py | grep -E \"agent|dashboard\"",
        "echo \"\"",
        "echo \"Fixing the mounting...\"",
        "sudo sed -i '"'"'s/app.include_router(agent_router, prefix=\"\/api\/v1\")/app.include_router(agent_router)  # No prefix for WebSocket routes/'"'"' api/app.py",
        "sudo sed -i '"'"'s/app.include_router(dashboard_router, prefix=\"\/api\/v1\")/app.include_router(dashboard_router)  # No prefix for WebSocket routes/'"'"' api/app.py",
        "echo \"\"",
        "echo \"After fix:\"",
        "grep -n \"include_router.*router\" api/app.py | grep -E \"agent|dashboard\"",
        "echo \"\"",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 3",
        "echo \"\"",
        "echo \"Service status:\"",
        "sudo systemctl is-active artcafe-pubsub",
        "echo \"\"",
        "echo \"Verifying routes are now accessible:\"",
        "curl -s -o /dev/null -w \"Status: %{http_code}\" -H \"Upgrade: websocket\" http://localhost:8000/ws/agent/test",
        "echo \" for /ws/agent/test\"",
        "curl -s -o /dev/null -w \"Status: %{http_code}\" -H \"Upgrade: websocket\" http://localhost:8000/ws/dashboard",
        "echo \" for /ws/dashboard\"",
        "echo \"\"",
        "echo \"WebSocket routes should now be accessible at:\"",
        "echo \"  - /ws/agent/{agent_id}\"",
        "echo \"  - /ws/dashboard\""
    ]' \
    --output json > /tmp/fix_mounting.json

COMMAND_ID=$(cat /tmp/fix_mounting.json | grep -o '"CommandId": "[^"]*' | cut -d'"' -f4)

echo "Deployment started. Command ID: ${COMMAND_ID}"
echo ""
echo "To check status:"
echo "aws ssm get-command-invocation --command-id ${COMMAND_ID} --instance-id ${INSTANCE_ID} --output text"