#!/bin/bash

# Cleanup orphaned SSH keys from deleted agents
# This script finds SSH keys that belong to agents that no longer exist

echo "🔍 Scanning for orphaned SSH keys..."

# Get all SSH keys with agent_id
echo "📋 Getting all SSH keys with agent associations..."
aws dynamodb scan \
  --table-name artcafe-ssh-keys \
  --filter-expression "attribute_exists(agent_id) AND key_type = :kt" \
  --expression-attribute-values '{":kt":{"S":"agent"}}' \
  --projection-expression "id,tenant_id,agent_id,#n" \
  --expression-attribute-names '{"#n":"name"}' \
  --output json > /tmp/ssh_keys.json

# Extract unique tenant/agent pairs
echo "🔎 Extracting agent references..."
jq -r '.Items[] | "\(.tenant_id.S)|\(.agent_id.S)|\(.id.S)|\(.["name"].S // "unnamed")"' /tmp/ssh_keys.json > /tmp/agent_keys.txt

# Check each agent exists
echo "✅ Checking which agents still exist..."
> /tmp/orphaned_keys.txt

while IFS='|' read -r tenant_id agent_id key_id key_name; do
  # Check if agent exists
  agent_exists=$(aws dynamodb get-item \
    --table-name artcafe-agents \
    --key "{\"tenant_id\":{\"S\":\"$tenant_id\"},\"id\":{\"S\":\"$agent_id\"}}" \
    --output json 2>/dev/null | jq -r '.Item')
  
  if [ "$agent_exists" == "null" ] || [ -z "$agent_exists" ]; then
    echo "❌ Orphaned key found: $key_name (ID: $key_id) for deleted agent: $agent_id"
    echo "$tenant_id|$key_id" >> /tmp/orphaned_keys.txt
  fi
done < /tmp/agent_keys.txt

# Count orphaned keys
orphaned_count=$(wc -l < /tmp/orphaned_keys.txt)
echo ""
echo "📊 Found $orphaned_count orphaned SSH keys"

if [ "$orphaned_count" -eq 0 ]; then
  echo "✨ No orphaned keys found. Database is clean!"
  exit 0
fi

# Ask for confirmation
echo ""
echo "⚠️  Found $orphaned_count orphaned SSH keys to delete"
read -p "Do you want to delete these keys? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "❌ Cleanup cancelled"
  exit 0
fi

# Delete orphaned keys
echo ""
echo "🗑️  Deleting orphaned keys..."
deleted=0

while IFS='|' read -r tenant_id key_id; do
  aws dynamodb delete-item \
    --table-name artcafe-ssh-keys \
    --key "{\"tenant_id\":{\"S\":\"$tenant_id\"},\"id\":{\"S\":\"$key_id\"}}" \
    2>/dev/null
  
  if [ $? -eq 0 ]; then
    ((deleted++))
    echo "✅ Deleted key: $key_id"
  else
    echo "❌ Failed to delete key: $key_id"
  fi
done < /tmp/orphaned_keys.txt

echo ""
echo "🎉 Cleanup complete! Deleted $deleted orphaned SSH keys"

# Cleanup temp files
rm -f /tmp/ssh_keys.json /tmp/agent_keys.txt /tmp/orphaned_keys.txt