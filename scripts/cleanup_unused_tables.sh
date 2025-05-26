#!/bin/bash

# Script to backup and delete unused DynamoDB tables
# Run with --delete flag to actually delete (otherwise just shows what would be deleted)

DELETE_MODE=false
if [ "$1" == "--delete" ]; then
    DELETE_MODE=true
fi

# List of tables that appear to be unused
UNUSED_TABLES=(
    "artcafe-ssh-keys"
    "artcafe-subscribers"
    "artcafe-subscriptions"
    "artcafe-Challenges"
    "artcafe-organizations"
    "artcafe-users"
    "artcafe-user-tenants-index"
)

# Also include dev tables that mirror unused prod tables
UNUSED_DEV_TABLES=(
    "artcafe-ssh-keys-dev"
)

ALL_UNUSED_TABLES=("${UNUSED_TABLES[@]}" "${UNUSED_DEV_TABLES[@]}")

echo "🔍 Checking unused DynamoDB tables..."
echo ""

# Create backup directory
BACKUP_DIR="dynamodb-backups-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

for table in "${ALL_UNUSED_TABLES[@]}"; do
    echo "📊 Checking table: $table"
    
    # Check if table exists
    table_exists=$(aws dynamodb describe-table --table-name "$table" 2>/dev/null)
    
    if [ -z "$table_exists" ]; then
        echo "   ⚠️  Table does not exist, skipping..."
        continue
    fi
    
    # Get item count
    count=$(aws dynamodb scan --table-name "$table" --select COUNT --output json 2>/dev/null | jq -r '.Count // 0')
    echo "   📈 Items in table: $count"
    
    # Backup table data if it has items
    if [ "$count" -gt 0 ]; then
        echo "   💾 Backing up $count items to $BACKUP_DIR/$table.json"
        aws dynamodb scan --table-name "$table" --output json > "$BACKUP_DIR/$table.json"
    fi
    
    if [ "$DELETE_MODE" == "true" ]; then
        echo "   🗑️  Deleting table $table..."
        aws dynamodb delete-table --table-name "$table" --output json > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "   ✅ Table deleted successfully"
        else
            echo "   ❌ Failed to delete table"
        fi
    else
        echo "   🔸 Would delete table $table (run with --delete to actually delete)"
    fi
    
    echo ""
done

echo "📋 Summary:"
echo "- Checked ${#ALL_UNUSED_TABLES[@]} tables"
if [ "$DELETE_MODE" == "true" ]; then
    echo "- Deletion complete"
    echo "- Backups saved to: $BACKUP_DIR"
else
    echo "- This was a dry run. Use --delete flag to actually delete tables"
fi

# Show estimated monthly savings
echo ""
echo "💰 Estimated monthly savings:"
echo "- Each empty table costs ~$0.25/month for on-demand billing"
echo "- Total savings: ~\$$(echo "${#ALL_UNUSED_TABLES[@]} * 0.25" | bc -l | xargs printf "%.2f")/month"