#!/bin/bash
set -e

echo "=== Final WebSocket Fix ==="
echo ""

INSTANCE_ID="i-0cd295d6b239ca775"

# Create a patch to ensure WebSocket routes work
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Creating a test to verify WebSocket routes...\"",
        "cat > test_ws_routes.py << '"'"'EOF'"'"'",
        "#!/usr/bin/env python3",
        "import sys",
        "sys.path.insert(0, '"'"'.'"'"')",
        "",
        "print(\"Testing WebSocket route registration...\")",
        "print()",
        "",
        "# Import the routers",
        "from api.websocket import agent_router, dashboard_router",
        "print(f\"Agent router has {len(agent_router.routes)} routes\")",
        "print(f\"Dashboard router has {len(dashboard_router.routes)} routes\")",
        "",
        "# Import the app",
        "from api.app import app",
        "print(f\"\\nApp has {len(app.routes)} total routes\")",
        "",
        "# Find WebSocket routes",
        "ws_routes = []",
        "for route in app.routes:",
        "    if hasattr(route, '"'"'path'"'"'):",
        "        path = str(route.path)",
        "        if '"'"'/ws/'"'"' in path:",
        "            ws_routes.append(path)",
        "            print(f\"Found WebSocket route: {path}\")",
        "",
        "print(f\"\\nTotal WebSocket routes in app: {len(ws_routes)}\")",
        "",
        "# Check if the routes are properly mounted",
        "if '"'"'/ws/agent/{agent_id}'"'"' in ws_routes:",
        "    print(\"✓ Agent WebSocket route is registered\")",
        "else:",
        "    print(\"✗ Agent WebSocket route is NOT registered\")",
        "",
        "if '"'"'/ws/dashboard'"'"' in ws_routes:",
        "    print(\"✓ Dashboard WebSocket route is registered\")",
        "else:",
        "    print(\"✗ Dashboard WebSocket route is NOT registered\")",
        "EOF",
        "echo \"\"",
        "echo \"Running test...\"",
        "python3 test_ws_routes.py",
        "echo \"\"",
        "echo \"If routes are not registered, we need to check the import order...\"",
        "echo \"\"",
        "echo \"Current app.py WebSocket imports:\"",
        "grep -n \"websocket\" api/app.py"
    ]' \
    --output json > /tmp/final_fix.json

COMMAND_ID=$(cat /tmp/final_fix.json | grep -o '"CommandId": "[^"]*' | cut -d'"' -f4)

echo "Command sent. ID: ${COMMAND_ID}"
echo "Waiting for results..."
sleep 4

# Get the output
aws ssm get-command-invocation --command-id "${COMMAND_ID}" --instance-id "${INSTANCE_ID}" --output text --query StandardOutputContent