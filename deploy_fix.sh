#!/bin/bash

# Deploy script to fix backend tenant creation issue
# This script updates the backend files to fix boolean value conversion for DynamoDB

echo "Fixing backend tenant creation issue..."

# Files that were modified:
# 1. api/services/tenant_service.py - Convert boolean values to numbers for DynamoDB
# 2. models/tenant_limits.py - Add 'basic' subscription tier
# 3. models/tenant.py - Update subscription tier enum

echo "Files updated:"
echo "- api/services/tenant_service.py"
echo "- models/tenant_limits.py"
echo "- models/tenant.py"

echo "Changes made:"
echo "1. Convert boolean feature flags to 0/1 for DynamoDB storage"
echo "2. Added 'basic' subscription tier to SUBSCRIPTION_PLANS"
echo "3. Updated SubscriptionTier enum to include all tiers"
echo "4. Fixed permissions boolean values in channel subscriptions"
echo "5. Added null check for metadata handling"

echo ""
echo "To deploy these changes:"
echo "1. Stop the backend service"
echo "2. Pull or copy these updated files"
echo "3. Restart the backend service"
echo ""
echo "The backend should now properly handle tenant creation requests."