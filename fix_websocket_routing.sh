#!/bin/bash
set -e

echo "=== Quick Fix for WebSocket Routing ==="
echo ""
echo "This script implements Option 2: Change FastAPI mounting"
echo "This is the quickest fix that doesn't require nginx changes"
echo ""

INSTANCE_ID="i-0cd295d6b239ca775"

# Deploy the routing fix
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Backing up app.py...\"",
        "sudo cp api/app.py api/app.py.backup.$(date +%Y%m%d_%H%M%S)",
        "echo \"\"",
        "echo \"Fixing WebSocket routing by mounting routers without /api/v1 prefix...\"",
        "sudo python3 -c \"",
        "with open('"'"'api/app.py'"'"', '"'"'r'"'"') as f:",
        "    content = f.read()",
        "",
        "# Change how WebSocket routers are mounted",
        "# From: app.include_router(agent_router, prefix='"'"'/api/v1'"'"')",
        "# To: app.include_router(agent_router)  # No prefix for WebSocket",
        "",
        "lines = content.splitlines()",
        "new_lines = []",
        "for line in lines:",
        "    if '"'"'app.include_router(agent_router, prefix=\"/api/v1\")'"'"' in line:",
        "        new_lines.append('"'"'# Mount WebSocket routers without prefix for clean URLs'"'"')",
        "        new_lines.append('"'"'app.include_router(agent_router)  # /ws/agent/{agent_id}'"'"')",
        "    elif '"'"'app.include_router(dashboard_router, prefix=\"/api/v1\")'"'"' in line:",
        "        new_lines.append('"'"'app.include_router(dashboard_router)  # /ws/dashboard'"'"')",
        "    else:",
        "        new_lines.append(line)",
        "",
        "with open('"'"'api/app.py'"'"', '"'"'w'"'"') as f:",
        "    f.write('"'"'\\n'"'"'.join(new_lines))",
        "print('"'"'Fixed WebSocket router mounting'"'"')\"",
        "echo \"\"",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 3",
        "echo \"\"",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub --no-pager | head -10",
        "echo \"\"",
        "echo \"Testing WebSocket endpoint accessibility:\"",
        "curl -s -o /dev/null -w \"%{http_code}\" http://localhost:8000/ws/agent/test || echo \"\"",
        "echo \" - WebSocket agent endpoint\"",
        "curl -s -o /dev/null -w \"%{http_code}\" http://localhost:8000/ws/dashboard || echo \"\"", 
        "echo \" - WebSocket dashboard endpoint\"",
        "echo \"\"",
        "echo \"Fix complete! WebSocket routes now available at:\"",
        "echo \"  - wss://ws.artcafe.ai/ws/agent/{agent_id}\"",
        "echo \"  - wss://ws.artcafe.ai/ws/dashboard\""
    ]' \
    --output json > /tmp/routing_fix.json

COMMAND_ID=$(cat /tmp/routing_fix.json | grep -o '"CommandId": "[^"]*' | cut -d'"' -f4)

echo "Deployment started. Command ID: ${COMMAND_ID}"
echo ""
echo "This fix:"
echo "✓ Mounts WebSocket routers at root level (no /api/v1 prefix)"
echo "✓ Maintains clean URLs: /ws/agent/{id} and /ws/dashboard"
echo "✓ Works with existing nginx configuration"
echo ""
echo "To check status:"
echo "aws ssm get-command-invocation --command-id ${COMMAND_ID} --instance-id ${INSTANCE_ID} --output text"
echo ""
echo "Next steps:"
echo "1. Test agents and dashboard - messages should now flow!"
echo "2. Plan migration to scalable architecture (see WEBSOCKET_SCALING_ARCHITECTURE.md)"