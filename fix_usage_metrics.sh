#!/bin/bash
set -e

echo "Fixing usage metrics issues..."

INSTANCE_ID="i-0cd295d6b239ca775"

# Deploy fixes for usage metrics
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "cd /opt/artcafe/artcafe-pubsub",
        
        "# Fix 1: Update usage routes to use tenant.limits instead of direct attributes",
        "cp api/routes/usage_routes.py api/routes/usage_routes.py.bak",
        "sed -i '\''s/tenant\\.max_agents/tenant.limits.max_agents/g'\'' api/routes/usage_routes.py",
        "sed -i '\''s/tenant\\.max_channels/tenant.limits.max_channels/g'\'' api/routes/usage_routes.py",
        "sed -i '\''s/tenant\\.max_messages_per_day/tenant.limits.max_messages_per_day/g'\'' api/routes/usage_routes.py",
        
        "# Fix 2: Fix DynamoDB expression attribute values format",
        "cp api/db/dynamodb.py api/db/dynamodb.py.bak.metrics",
        "cat > /tmp/fix_dynamodb_update.py << '\''EOF'\''",
        "import sys",
        "import re",
        "with open(sys.argv[1], '\''r'\'') as f:",
        "    content = f.read()",
        "",
        "# Find the update_item method and fix the expression attribute values",
        "# Add proper DynamoDB type formatting",
        "pattern = r\"(expression_values\\[key\\] = value)\"",
        "replacement = \"\"\"if isinstance(value, str):",
        "            expression_values[key] = {'S': value}",
        "        elif isinstance(value, (int, float)):",
        "            expression_values[key] = {'N': str(value)}",
        "        elif isinstance(value, bool):",
        "            expression_values[key] = {'BOOL': value}",
        "        else:",
        "            expression_values[key] = value\"\"\"",
        "",
        "# Replace the simple assignment with type checking",
        "content = re.sub(pattern, replacement, content)",
        "",
        "with open(sys.argv[1], '\''w'\'') as f:",
        "    f.write(content)",
        "EOF",
        "python3 /tmp/fix_dynamodb_update.py api/db/dynamodb.py",
        
        "# Fix 3: Add missing query method to DynamoDB service",
        "grep -q \"def query\" api/db/dynamodb.py || cat >> api/db/dynamodb.py << '\''EOF'\''",
        "",
        "    async def query(self, table_name: str, partition_key: str, sort_key: Optional[str] = None) -> List[Dict[str, Any]]:",
        "        \"\"\"Query items by partition key\"\"\"",
        "        return await self.query_items(",
        "            table_name=table_name,",
        "            key_condition_expression=\"pk = :pk\",",
        "            expression_attribute_values={\":pk\": partition_key}",
        "        )",
        "EOF",
        
        "# Restart service",
        "sudo systemctl restart artcafe-pubsub",
        
        "# Check service status",
        "sleep 5",
        "sudo systemctl status artcafe-pubsub --no-pager",
        "sudo journalctl -u artcafe-pubsub -n 20"
    ]}' \
    --output text \
    --query "Command.CommandId"