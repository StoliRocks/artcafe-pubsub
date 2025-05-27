#!/bin/bash

# Master deployment script for all phases

echo "=== ArtCafe.ai Production Deployment ==="
echo "This will deploy all 5 phases to make the dashboard production-ready"
echo ""

# Check if running with confirmation
if [ "$1" != "--confirm" ]; then
    echo "Usage: ./deploy_all_phases.sh --confirm"
    echo ""
    echo "This will deploy:"
    echo "  Phase 1: Activity Tracking & Agent Metrics"
    echo "  Phase 2: Profile, SSH Keys, Notifications"
    echo "  Phase 3: Search & Analytics"
    echo "  Phase 4: Billing & Payments"
    echo "  Phase 5: Production Hardening"
    echo ""
    echo "WARNING: This will modify your production environment!"
    exit 1
fi

# Function to check deployment status
check_deployment() {
    local phase=$1
    echo ""
    echo "=== Phase $phase Deployment Status ==="
    echo "Checking deployment..."
    sleep 10
    
    # Check service status
    aws ssm send-command \
        --instance-ids i-0cd295d6b239ca775 \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["sudo systemctl status artcafe-pubsub | head -5"]' \
        --output text
    
    echo "Phase $phase deployment check complete"
    echo ""
}

# Phase 1: Activity Tracking
echo "=== Phase 1: Activity Tracking & Metrics ==="
read -p "Deploy Phase 1? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./deploy_phase1_activity_system.sh
    check_deployment 1
else
    echo "Skipping Phase 1"
fi

# Phase 2: Missing Features
echo "=== Phase 2: Missing Features ==="
read -p "Deploy Phase 2? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./deploy_phase2_missing_features.sh
    check_deployment 2
else
    echo "Skipping Phase 2"
fi

# Phase 3: Search & Analytics
echo "=== Phase 3: Search & Analytics ==="
read -p "Deploy Phase 3? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./deploy_phase3_search_analytics.sh
    check_deployment 3
else
    echo "Skipping Phase 3"
fi

# Phase 4: Billing
echo "=== Phase 4: Billing & Payments ==="
echo "Note: Requires STRIPE_SECRET_KEY environment variable"
read -p "Deploy Phase 4? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -z "$STRIPE_SECRET_KEY" ]; then
        echo "WARNING: STRIPE_SECRET_KEY not set. Using test key."
        export STRIPE_SECRET_KEY="sk_test_placeholder"
    fi
    ./deploy_phase4_billing.sh
    check_deployment 4
else
    echo "Skipping Phase 4"
fi

# Phase 5: Production Hardening
echo "=== Phase 5: Production Hardening ==="
read -p "Deploy Phase 5? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ./deploy_phase5_production_hardening.sh
    check_deployment 5
else
    echo "Skipping Phase 5"
fi

echo ""
echo "=== Deployment Summary ==="
echo "All selected phases have been deployed!"
echo ""
echo "=== Next Steps ==="
echo "1. Update frontend components to use new APIs"
echo "2. Test all endpoints thoroughly"
echo "3. Monitor CloudWatch for any errors"
echo "4. Configure production environment variables:"
echo "   - STRIPE_SECRET_KEY"
echo "   - SNS_NOTIFICATION_TOPIC_ARN"
echo "   - REDIS_URL (if using ElastiCache)"
echo ""
echo "=== Frontend Updates Required ==="
echo "1. Replace ActivityFeed mock data"
echo "2. Update agent metrics to use real data"
echo "3. Create profile, SSH keys, and notifications pages"
echo "4. Implement search functionality"
echo "5. Update billing page with real data"
echo ""
echo "=== Testing Checklist ==="
echo "□ Activity logs are being recorded"
echo "□ Agent metrics are being collected"
echo "□ Notifications are delivered"
echo "□ Search returns relevant results"
echo "□ Billing invoices are generated"
echo "□ Rate limiting is working"
echo "□ Caching improves performance"
echo "□ Monitoring alerts are triggered"
echo ""
echo "Deployment complete!"