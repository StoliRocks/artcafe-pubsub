#!/bin/bash

# Create a script that contains our Python fix
cat << 'EOF' > /tmp/fix_commands.sh
cd /opt/artcafe/artcafe-pubsub && sudo tee fix_dynamodb_format.py << 'PYEOF'
#!/usr/bin/env python3
import re
import os
import shutil
from datetime import datetime

def fix_dynamodb_file():
    file_path = "/opt/artcafe/artcafe-pubsub/api/db/dynamodb.py"
    
    # Backup the original file
    backup_path = file_path + ".bak"
    shutil.copy(file_path, backup_path)
    print(f"Backed up to {backup_path}")
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Add the format_value method
    format_method = '''
    def _format_value(self, value):
        """Format a value for DynamoDB."""
        if value is None:
            return {"NULL": True}
        elif isinstance(value, bool):
            return {"BOOL": value}
        elif isinstance(value, (int, float)):
            return {"N": str(value)}
        elif isinstance(value, str):
            return {"S": value}
        elif isinstance(value, list):
            return {"L": [self._format_value(v) for v in value]}
        elif isinstance(value, dict):
            return {"M": {k: self._format_value(v) for k, v in value.items()}}
        else:
            return {"S": str(value)}
'''
    
    # Check if method already exists
    if '_format_value' not in content:
        # Find the class definition and insert the method
        lines = content.split('\n')
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            if line.strip().startswith('class DynamoDBService:'):
                # Insert the method after the class definition
                new_lines.append(format_method)
        content = '\n'.join(new_lines)
        print("Added _format_value method")
    
    # Fix the update_item method
    lines = content.split('\n')
    new_lines = []
    in_update_method = False
    
    for i, line in enumerate(lines):
        if 'def update_item' in line:
            in_update_method = True
        
        if in_update_method and 'ExpressionAttributeValues={' in line and '":api_calls":' in line:
            # Replace the entire ExpressionAttributeValues section
            indent = line[:line.find('E')]
            new_lines.append(f'{indent}ExpressionAttributeValues={{')
            new_lines.append(f'{indent}    ":api_calls": self._format_value(api_calls),')
            new_lines.append(f'{indent}    ":messages_sent": self._format_value(messages_sent),')
            new_lines.append(f'{indent}    ":messages_received": self._format_value(messages_received),')
            new_lines.append(f'{indent}    ":requests_made": self._format_value(requests_made),')
            new_lines.append(f'{indent}    ":bandwidth_bytes": self._format_value(bandwidth_bytes),')
            new_lines.append(f'{indent}    ":updated_at": self._format_value(datetime.utcnow().isoformat()),')
            new_lines.append(f'{indent}}}')
            # Skip the original lines until we find the closing brace
            while i < len(lines) and not lines[i].strip().endswith('}'):
                i += 1
            continue
        
        new_lines.append(line)
        
        if in_update_method and line.strip() == '}':
            in_update_method = False
    
    content = '\n'.join(new_lines)
    
    # Write the updated file
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Fixed DynamoDB formatting in update_item method")
    print("DynamoDB file has been updated successfully")

if __name__ == "__main__":
    fix_dynamodb_file()
PYEOF

sudo python3 fix_dynamodb_format.py
sudo systemctl restart artcafe-pubsub
echo "DynamoDB fix applied and service restarted"
EOF

# Use SSM to run the script
aws ssm send-command \
  --instance-ids "i-0cd295d6b239ca775" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"$(cat /tmp/fix_commands.sh)\"]" \
  --output json