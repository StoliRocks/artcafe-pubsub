#!/bin/bash
set -e

echo "=== Deploying NATS Message Flow Fix ==="
echo ""
echo "Changes:"
echo "1. Fixed nats_manager.publish() call - now passes dict instead of bytes"
echo "2. Removed direct WebSocket broadcast workaround"
echo "3. Added detailed logging to trace NATS message flow"
echo ""

# Get the EC2 instance ID from CLAUDE.md
INSTANCE_ID="i-0cd295d6b239ca775"

echo "Restarting service on EC2 instance ${INSTANCE_ID}..."

# Use AWS SSM to restart the service
aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["cd /opt/artcafe/artcafe-pubsub && sudo git pull && sudo systemctl restart artcafe-pubsub && sudo journalctl -u artcafe-pubsub -n 50"]' \
    --output text

echo ""
echo "Deployment command sent. The service will restart and pull latest changes."
echo ""
echo "To monitor logs:"
echo "aws ssm get-command-invocation --command-id <command-id> --instance-id ${INSTANCE_ID}"
echo ""
echo "Expected behavior after fix:"
echo "- Agents publish to NATS topics"
echo "- NATS delivers to ALL subscribers (agents + dashboards)"
echo "- Dashboard receives messages via NATS subscription"
echo "- No more direct WebSocket broadcast"