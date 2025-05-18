#!/bin/bash
set -e

echo "Applying simple DynamoDB fix..."

INSTANCE_ID="i-0cd295d6b239ca775"

# Deploy simple DynamoDB fix
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "cd /opt/artcafe/artcafe-pubsub",
        
        "# First check the current update_item method",
        "echo \"Current update_item method:\"",
        "grep -n -A 20 \"async def update_item\" api/db/dynamodb.py",
        
        "# Simple fix - just modify the line that sets expression values",
        "cp api/db/dynamodb.py api/db/dynamodb.py.bak.simple",
        
        "# Find the line with expression_values[key] = value and fix it",
        "sed -i '\''s/expression_values\\[key\\] = value/expression_values[key] = self._format_value(value)/g'\'' api/db/dynamodb.py",
        
        "# Add the format_value method if it doesn'\''t exist",
        "grep -q \"_format_value\" api/db/dynamodb.py || echo '\''",
    def _format_value(self, value):",
        \"\"\"Format value for DynamoDB\"\"\"",
        if isinstance(value, str):",
            return {\"S\": value}",
        elif isinstance(value, (int, float)):",
            return {\"N\": str(value)}",
        elif isinstance(value, bool):",
            return {\"BOOL\": value}",
        elif value is None:",
            return {\"NULL\": True}",
        else:",
            return value'\'' >> api/db/dynamodb.py",
        
        "# Verify the changes",
        "echo \"\"",
        "echo \"After fix:\"",
        "grep -A 15 \"_format_value\" api/db/dynamodb.py",
        
        "# Restart service",
        "sudo systemctl restart artcafe-pubsub",
        
        "# Check status",
        "sleep 5",
        "sudo systemctl status artcafe-pubsub --no-pager"
    ]}' \
    --output text \
    --query "Command.CommandId"