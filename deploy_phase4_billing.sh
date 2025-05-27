#!/bin/bash

# Deploy Phase 4: Billing & Payments

INSTANCE_ID="i-0cd295d6b239ca775"
S3_BUCKET="artcafe-deployment"

echo "=== Deploying Phase 4: Billing & Payments ==="

# Step 1: Create payment tables
echo "Step 1: Creating payment tables..."
aws dynamodb create-table \
    --table-name artcafe-payments \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=payment_id,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=payment_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table may already exist"

aws dynamodb create-table \
    --table-name artcafe-payment-methods \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=method_id,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=method_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table may already exist"

aws dynamodb create-table \
    --table-name artcafe-usage-records \
    --attribute-definitions \
        AttributeName=tenant_id,AttributeType=S \
        AttributeName=usage_id,AttributeType=S \
    --key-schema \
        AttributeName=tenant_id,KeyType=HASH \
        AttributeName=usage_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1 || echo "Table may already exist"

# Step 2: Install Stripe SDK
echo "Step 2: Installing Stripe SDK..."
aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "sudo pip install stripe"
    ]' \
    --output text

# Step 3: Package the new code
echo "Step 3: Creating deployment package..."
zip -r phase4-billing.zip \
    models/billing.py \
    api/services/billing_service.py

# Step 4: Upload to S3
echo "Step 4: Uploading to S3..."
aws s3 cp phase4-billing.zip s3://${S3_BUCKET}/phase4-billing.zip

# Step 5: Deploy to EC2
echo "Step 5: Deploying to EC2..."
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-sk_test_placeholder}"

aws ssm send-command \
    --instance-ids $INSTANCE_ID \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "echo \"Downloading update package...\"",
        "sudo aws s3 cp s3://artcafe-deployment/phase4-billing.zip .",
        "echo \"Extracting updates...\"",
        "sudo unzip -o phase4-billing.zip",
        "echo \"Setting environment variables...\"",
        "echo \"STRIPE_SECRET_KEY='$STRIPE_SECRET_KEY'\" | sudo tee -a /etc/environment",
        "echo \"Adding billing routes...\"",
        "sudo tee -a api/routes/billing_routes.py > /dev/null <<'\''BILLING_ROUTES'\''",
        "",
        "# Enhanced billing routes",
        "@router.get(\"/invoices\", response_model=List[Invoice])",
        "async def get_invoices(",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access),",
        "    status: Optional[InvoiceStatus] = Query(None),",
        "    limit: int = Query(50, ge=1, le=200)",
        "):",
        "    from api.services.billing_service import billing_service",
        "    invoices = await billing_service.get_invoices(tenant_id, status, limit)",
        "    return invoices",
        "",
        "@router.get(\"/history\", response_model=BillingHistory)",
        "async def get_billing_history(",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.billing_service import billing_service",
        "    history = await billing_service.get_billing_history(tenant_id)",
        "    return history",
        "",
        "@router.post(\"/payment-methods\", response_model=PaymentMethodInfo)",
        "async def add_payment_method(",
        "    method_data: Dict[str, Any],",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.billing_service import billing_service",
        "    method = await billing_service.add_payment_method(",
        "        tenant_id=tenant_id,",
        "        method_type=method_data[\"type\"],",
        "        processor_method_id=method_data[\"processor_method_id\"],",
        "        details=method_data.get(\"details\", {}),",
        "        set_as_default=method_data.get(\"set_as_default\", True)",
        "    )",
        "    return method",
        "",
        "@router.get(\"/payment-methods\", response_model=List[PaymentMethodInfo])",
        "async def get_payment_methods(",
        "    user: Dict = Depends(get_current_user),",
        "    tenant_id: str = Depends(verify_tenant_access)",
        "):",
        "    from api.services.billing_service import billing_service",
        "    methods = await billing_service.get_payment_methods(tenant_id)",
        "    return methods",
        "BILLING_ROUTES",
        "echo \"Restarting service...\"",
        "sudo systemctl restart artcafe-pubsub",
        "sleep 5",
        "echo \"Service status:\"",
        "sudo systemctl status artcafe-pubsub | head -20",
        "echo \"Cleaning up...\"",
        "sudo rm phase4-billing.zip"
    ]' \
    --output text

echo "Phase 4 deployment initiated."

# Clean up local file
rm -f phase4-billing.zip

echo ""
echo "=== Next Steps ==="
echo "1. Set up Stripe webhook endpoints"
echo "2. Configure Stripe API keys in production"
echo "3. Test payment processing in sandbox mode"
echo ""
echo "Test endpoints:"
echo "- GET /api/v1/billing/invoices"
echo "- GET /api/v1/billing/history"
echo "- GET /api/v1/billing/payment-methods"