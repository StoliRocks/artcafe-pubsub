#!/bin/bash
# Cleanup script to remove outdated deployment scripts and temporary files
# Run this from the artcafe-pubsub directory

echo "This script will remove outdated deployment scripts and temporary files."
echo "It will NOT remove:"
echo "  - Core application code"
echo "  - Configuration files currently in use"
echo "  - Documentation"
echo "  - The artcafe-pubsub.service file (still needed)"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

# Create backup directory with timestamp
backup_dir="cleanup_backup_$(date +%Y%m%d_%H%M%S)"
echo "Creating backup directory: $backup_dir"
mkdir -p "$backup_dir"

# Function to move file to backup
move_to_backup() {
    if [ -e "$1" ]; then
        echo "Moving $1 to backup..."
        mv "$1" "$backup_dir/"
    fi
}

echo ""
echo "Starting cleanup..."

# Remove shell scripts (except the ones we want to keep)
for file in *.sh; do
    if [ "$file" != "cleanup_outdated_files.sh" ]; then
        move_to_backup "$file"
    fi
done

# Remove Python fix scripts
for file in *fix*.py complete_boolean_fix.py comprehensive_boolean_fix.py debug_patch.py runtime_bool_fix.py safe_boolean_fix.py tenant_boolean_fix.py usage_service_fixed.py user_tenant_service_complete.py; do
    move_to_backup "$file"
done

# Remove zip archives
for file in *.zip; do
    move_to_backup "$file"
done

# Remove JSON files (except legal_versions.py if it exists)
for file in *.json; do
    if [[ "$file" != "package.json" && "$file" != "tsconfig.json" ]]; then
        move_to_backup "$file"
    fi
done

# Remove backup and fixed files
move_to_backup "api/db/dynamodb_fixed.py"
move_to_backup "api/routes/dashboard_websocket_routes.py.bak"
move_to_backup "api/routes/tenant_routes.py.bak.20250517_082422"
move_to_backup "api/routes/websocket_routes_debug.py"
move_to_backup "api/routes/websocket_routes_fixed.py"
move_to_backup "api/services/ssh_key_service.py.fixed"
move_to_backup "api/services/usage_service_fixed.py"
move_to_backup "api/services/user_tenant_service_debug.py"
move_to_backup "auth/ssh_auth.py.fixed"
move_to_backup "auth/ssh_auth_agent_fixed.py"
move_to_backup "config/settings.py.fixed"
move_to_backup "models/usage.py.fixed"
move_to_backup "nats_client/__init__.py.new"
move_to_backup "nats_client/connection.py.fixed"
move_to_backup "nats_client/connection.py.new"

# Remove temporary files
move_to_backup "server.log"
move_to_backup "server.pid"

# Remove temporary directories (if they exist)
if [ -d "lambda-venv" ]; then
    echo "Moving lambda-venv to backup..."
    mv lambda-venv "$backup_dir/"
fi

if [ -d "s3-bucket-check" ]; then
    echo "Moving s3-bucket-check to backup..."
    mv s3-bucket-check "$backup_dir/"
fi

# Note: keeping venv as it might be actively used

echo ""
echo "Cleanup complete!"
echo "Backed up files are in: $backup_dir"
echo ""
echo "You can review the backup and delete it later with:"
echo "  rm -rf $backup_dir"
echo ""
echo "If you need to restore any file:"
echo "  mv $backup_dir/filename ."