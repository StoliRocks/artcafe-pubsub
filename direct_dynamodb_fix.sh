#!/bin/bash

# Create inline fix
aws ssm send-command \
  --instance-ids "i-0cd295d6b239ca775" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/artcafe/artcafe-pubsub",
    "sudo cp api/db/dynamodb.py api/db/dynamodb.py.bak",
    "sudo python3 -c \"import re; content = open('"'"'api/db/dynamodb.py'"'"', '"'"'r'"'"').read(); new_content = content.replace('"'"'\":api_calls\": api_calls,'"'"', '"'"'\":api_calls\": {\"N\": str(api_calls)},'"'"'); new_content = new_content.replace('"'"'\":messages_sent\": messages_sent,'"'"', '"'"'\":messages_sent\": {\"N\": str(messages_sent)},'"'"'); new_content = new_content.replace('"'"'\":messages_received\": messages_received,'"'"', '"'"'\":messages_received\": {\"N\": str(messages_received)},'"'"'); new_content = new_content.replace('"'"'\":requests_made\": requests_made,'"'"', '"'"'\":requests_made\": {\"N\": str(requests_made)},'"'"'); new_content = new_content.replace('"'"'\":bandwidth_bytes\": bandwidth_bytes,'"'"', '"'"'\":bandwidth_bytes\": {\"N\": str(bandwidth_bytes)},'"'"'); new_content = new_content.replace('"'"'\":updated_at\": datetime.utcnow().isoformat()'"'"', '"'"'\":updated_at\": {\"S\": datetime.utcnow().isoformat()}'"'"'); open('"'"'api/db/dynamodb.py'"'"', '"'"'w'"'"').write(new_content)\"",
    "sudo systemctl restart artcafe-pubsub",
    "echo \"DynamoDB fix applied\""
  ]' \
  --output json