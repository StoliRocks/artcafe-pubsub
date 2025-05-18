#!/bin/bash
set -e

echo "Fixing DynamoDB value formatting..."

INSTANCE_ID="i-0cd295d6b239ca775"

# Deploy DynamoDB value fixes
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters '{"commands":[
        "cd /opt/artcafe/artcafe-pubsub",
        
        "# Create a proper fix for DynamoDB expression values",
        "cat > /tmp/fix_dynamodb_values.py << '\''EOF'\''",
        "import re",
        "import sys",
        "",
        "# Read the file",
        "with open('\''api/db/dynamodb.py'\'', '\''r'\'') as f:",
        "    content = f.read()",
        "",
        "# Find the update_item method and fix expression values formatting",
        "# This fixes the part where we build expression_values",
        "def fix_update_item():",
        "    global content",
        "    ",
        "    # Find the update_item method",
        "    update_pattern = r\"(async def update_item.*?)(\n\\s*async def)\"",
        "    match = re.search(update_pattern, content, re.DOTALL)",
        "    ",
        "    if match:",
        "        method_content = match.group(1)",
        "        ",
        "        # Fix the expression values assignment",
        "        old_assignment = \"expression_values[key] = value\"",
        "        new_assignment = \"\"\"# Format value for DynamoDB",
        "                if isinstance(value, str):",
        "                    expression_values[key] = {\\'S\\': value}",
        "                elif isinstance(value, (int, float)):",
        "                    expression_values[key] = {\\'N\\': str(value)}",
        "                elif isinstance(value, bool):",
        "                    expression_values[key] = {\\'BOOL\\': value}",
        "                elif value is None:",
        "                    expression_values[key] = {\\'NULL\\': True}",
        "                else:",
        "                    expression_values[key] = value\"\"\"",
        "        ",
        "        if old_assignment in method_content:",
        "            fixed_method = method_content.replace(old_assignment, new_assignment)",
        "            content = content.replace(method_content, fixed_method)",
        "            print(\"Fixed update_item expression values\")",
        "        else:",
        "            print(\"Expression values assignment not found\")",
        "",
        "fix_update_item()",
        "",
        "# Write the fixed content",
        "with open('\''api/db/dynamodb.py'\'', '\''w'\'') as f:",
        "    f.write(content)",
        "",
        "print(\"DynamoDB fixes applied\")",
        "EOF",
        "",
        "# Run the fix",
        "python3 /tmp/fix_dynamodb_values.py",
        "",
        "# Check the update_item method",
        "echo \"Checking update_item method:\"",
        "grep -A 30 \"async def update_item\" api/db/dynamodb.py | grep -A 10 \"Format value\"",
        "",
        "# Restart service",
        "sudo systemctl restart artcafe-pubsub",
        "",
        "# Wait and check logs",
        "sleep 5",
        "sudo journalctl -u artcafe-pubsub -n 10"
    ]}' \
    --output text \
    --query "Command.CommandId"