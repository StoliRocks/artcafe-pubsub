"""
Routes for usage metrics.

This module provides API routes for usage metrics and billing information.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from datetime import datetime, date, timedelta

from auth.tenant_auth import get_tenant_id, validate_tenant
from models.usage import UsageMetricsResponse, UsageLimits
from api.services.usage_service import usage_service
from api.services.tenant_service import tenant_service

router = APIRouter(prefix="/usage-metrics", tags=["Usage"])


@router.get("", response_model=UsageMetricsResponse)
async def get_usage_metrics(
    tenant_id: str = Depends(get_tenant_id),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)")
):
    """
    Get usage metrics for a tenant.

    This endpoint returns usage metrics for the authenticated tenant within the
    specified date range. If no date range is specified, it defaults to the last 7 days.

    Args:
        tenant_id: Tenant ID
        start_date: Optional start date (ISO format)
        end_date: Optional end date (ISO format)

    Returns:
        Usage metrics response
    """
    # Validate tenant
    tenant = await validate_tenant(tenant_id)

    # Track API call
    await usage_service.increment_api_calls(tenant_id)

    # Set default date range if not provided
    if not end_date:
        end_date = date.today().isoformat()
    if not start_date:
        start_date = (date.today() - timedelta(days=6)).isoformat()  # Last 7 days

    # Get usage metrics
    metrics = await usage_service.get_usage_metrics(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date
    )

    # Get usage totals
    totals = await usage_service.get_usage_totals(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date
    )

    # Get usage limits based on tenant's subscription tier
    limits = UsageLimits(
        max_agents=tenant.max_agents,
        max_channels=tenant.max_channels,
        max_messages_per_day=tenant.max_messages_per_day,
        max_api_calls_per_day=tenant.max_messages_per_day // 5,  # Default ratio
        max_storage_bytes=1073741824,  # 1GB default
        concurrent_connections=tenant.max_agents * 5
    )

    # Return response
    return UsageMetricsResponse(
        metrics=metrics,
        totals=totals,
        limits=limits,
        success=True
    )


@router.get("/billing", tags=["Usage"])
async def get_billing_info(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get billing information for a tenant.

    This endpoint returns billing information for the authenticated tenant,
    including subscription plan, billing cycle, and payment status.

    Args:
        tenant_id: Tenant ID

    Returns:
        Billing information
    """
    # Validate tenant
    tenant = await validate_tenant(tenant_id)

    # Track API call
    await usage_service.increment_api_calls(tenant_id)

    # Get billing info from tenant
    return {
        "tenant_id": tenant_id,
        "plan": tenant.subscription_tier,
        "billing_cycle": "monthly",  # Default
        "next_billing_date": tenant.subscription_expires_at.isoformat() if tenant.subscription_expires_at else None,
        "amount": 49.99,  # Default for basic tier
        "currency": "USD",
        "payment_method": "credit_card",
        "status": tenant.payment_status,
        "success": True
    }