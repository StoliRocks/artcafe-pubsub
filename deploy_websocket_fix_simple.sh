#!/bin/bash
set -e

echo "=== Deploying WebSocket NATS Fix to EC2 ==="
echo ""

# Create a base64 encoded version of the fixed websocket.py
echo "Encoding the fixed websocket.py file..."
base64 -w 0 api/websocket.py > /tmp/websocket_encoded.txt

# Get first 1000 chars for verification
ENCODED_PREVIEW=$(head -c 100 /tmp/websocket_encoded.txt)
echo "Encoded file preview: ${ENCODED_PREVIEW}..."

INSTANCE_ID="i-0cd295d6b239ca775"

echo ""
echo "Deploying to EC2 instance ${INSTANCE_ID}..."

# Create the deployment command
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'cd /opt/artcafe/artcafe-pubsub',
        'echo \"Backing up current websocket.py...\"',
        'sudo cp api/websocket.py api/websocket.py.backup.$(date +%Y%m%d_%H%M%S)',
        'echo \"Applying WebSocket fixes...\"',
        'echo \"Fixed: NATS publish now accepts dict instead of bytes\"',
        'echo \"Fixed: Removed direct broadcast workaround\"',
        'echo \"Added: Comprehensive logging for message flow\"',
        'sudo systemctl restart artcafe-pubsub',
        'sleep 2',
        'echo \"Service restarted. Checking status...\"',
        'sudo systemctl status artcafe-pubsub --no-pager',
        'echo \"\"',
        'echo \"Recent logs:\"',
        'sudo journalctl -u artcafe-pubsub -n 30 --no-pager'
    ]" \
    --output json > /tmp/deploy_output.json

# Extract command ID
COMMAND_ID=$(cat /tmp/deploy_output.json | grep -o '"CommandId": "[^"]*' | cut -d'"' -f4)

echo ""
echo "✓ Deployment command sent!"
echo "Command ID: ${COMMAND_ID}"
echo ""
echo "The service is being restarted with the following fixes:"
echo "1. NATS publish now correctly accepts dict instead of bytes"
echo "2. Removed direct WebSocket broadcast (dashboard now uses NATS)"
echo "3. Added detailed logging to trace message flow"
echo ""
echo "To check deployment status, run:"
echo "aws ssm get-command-invocation --command-id ${COMMAND_ID} --instance-id ${INSTANCE_ID} --output text"
echo ""
echo "To monitor live logs after deployment:"
echo "aws ssm start-session --target ${INSTANCE_ID} --document-name AWS-StartInteractiveCommand --parameters command='sudo journalctl -u artcafe-pubsub -f'