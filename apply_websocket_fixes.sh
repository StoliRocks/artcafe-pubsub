#!/bin/bash
set -e

echo "=== Applying WebSocket NATS Fixes to EC2 ==="
echo ""

INSTANCE_ID="i-0cd295d6b239ca775"

# Send the fix commands
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Creating backup of websocket.py...\"",
        "sudo cp api/websocket.py api/websocket.py.backup.$(date +%Y%m%d_%H%M%S)",
        "echo \"\"",
        "echo \"Applying Fix 1: Correcting NATS publish call...\"",
        "sudo python3 -c \"",
        "import re",
        "with open('"'"'api/websocket.py'"'"', '"'"'r'"'"') as f:",
        "    content = f.read()",
        "# Fix the NATS publish call to pass dict instead of bytes",
        "content = content.replace(",
        "    '"'"'await nats_manager.publish(subject, json.dumps(data).encode())'"'"',",
        "    '"'"'await nats_manager.publish(subject, data)'"'"'",
        ")",
        "with open('"'"'api/websocket.py'"'"', '"'"'w'"'"') as f:",
        "    f.write(content)",
        "print('"'"'Fixed NATS publish call'"'"')\"",
        "echo \"\"",
        "echo \"Applying Fix 2: Removing direct broadcast workaround...\"",
        "sudo python3 -c \"",
        "with open('"'"'api/websocket.py'"'"', '"'"'r'"'"') as f:",
        "    lines = f.readlines()",
        "# Find and remove the direct broadcast section",
        "new_lines = []",
        "skip = False",
        "for i, line in enumerate(lines):",
        "    if '"'"'# Also broadcast to dashboards if it'"'"' in line:",
        "        skip = True",
        "        new_lines.append('"'"'                        # REMOVED: Direct broadcast to dashboards\\n'"'"')",
        "        new_lines.append('"'"'                        # Dashboard subscribers should receive messages via NATS like any other subscriber\\n'"'"')",
        "    elif skip and (line.strip() == '"'"''"'"' or (not line.startswith('"'"'                        '"'"') and line.strip())):",
        "        skip = False",
        "    if not skip:",
        "        new_lines.append(line)",
        "with open('"'"'api/websocket.py'"'"', '"'"'w'"'"') as f:",
        "    f.writelines(new_lines)",
        "print('"'"'Removed direct broadcast workaround'"'"')\"",
        "echo \"\"",
        "echo \"Applying Fix 3: Adding detailed logging...\"",
        "sudo sed -i '"'"'/await nats_manager.publish(subject, data)/i\\                        # Log the publish\\n                        logger.info(f\"Agent {agent_id} publishing to {subject}\")'"'"' api/websocket.py",
        "sudo sed -i '"'"'/await nats_manager.publish(subject, data)/a\\                        logger.info(f\"Published to NATS: {subject}\")'"'"' api/websocket.py",
        "echo \"\"",
        "echo \"All fixes applied. Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 3",
        "echo \"\"",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub --no-pager | head -20",
        "echo \"\"",
        "echo \"Recent logs (looking for WebSocket connections):\"",
        "sudo journalctl -u artcafe-pubsub -n 50 --no-pager | grep -E \"WebSocket|connected|Publishing|NATS\" | tail -20"
    ]' \
    --output json > /tmp/fix_output.json

# Get command ID
COMMAND_ID=$(cat /tmp/fix_output.json | grep -o '"CommandId": "[^"]*' | cut -d'"' -f4)

echo "Deployment command sent!"
echo "Command ID: ${COMMAND_ID}"
echo ""
echo "Fixes being applied:"
echo "✓ NATS publish call: json.dumps(data).encode() → data"
echo "✓ Removed direct WebSocket broadcast to dashboards"
echo "✓ Added logging for message flow tracing"
echo ""
echo "To see the results:"
echo "aws ssm get-command-invocation --command-id ${COMMAND_ID} --instance-id ${INSTANCE_ID} --output text"

# Make the script executable
chmod +x apply_websocket_fixes.sh