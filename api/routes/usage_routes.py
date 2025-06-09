"""
Routes for usage metrics.

This module provides API routes for usage metrics and billing information.
"""

from typing import Optional, Dict, List, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from datetime import datetime, date, timedelta

from auth.tenant_auth import get_tenant_id, validate_tenant
from models.usage import UsageMetricsResponse, UsageLimits
from api.services.usage_service import usage_service
from api.services.tenant_service import tenant_service
from api.services.simple_wildcard_tracker import wildcard_tracker
import logging

logger = logging.getLogger(__name__)

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
    
    # Get current usage for the month
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    metrics = await usage_service.get_usage_metrics(
        tenant_id=tenant_id,
        start_date=start_of_month.isoformat(),
        end_date=today.isoformat()
    )
    
    totals = await usage_service.get_usage_totals(
        tenant_id=tenant_id,
        start_date=start_of_month.isoformat(),
        end_date=today.isoformat()
    )

    # Get current storage usage from metrics
    storage_gb = 0
    if metrics and len(metrics) > 0:
        storage_gb = metrics[0].storage_used_bytes / (1024 * 1024 * 1024)  # Convert bytes to GB
        
    # Get billing info from tenant
    return {
        "tenant_id": tenant_id,
        "plan": tenant.subscription_tier,
        "billing_cycle": "monthly",
        "next_billing_date": tenant.subscription_expires_at.isoformat() if tenant.subscription_expires_at else None,
        "amount": 49.99 if tenant.subscription_tier == "basic" else 0.00,
        "currency": "USD",
        "payment_method": "credit_card" if tenant.subscription_tier != "free" else "none",
        "status": tenant.payment_status,
        "current_usage": {
            "agents": totals.agents_total if totals else 0,
            "channels": totals.channels_total if totals else 0,
            "messages": totals.messages_in_total if totals else 0,
            "api_calls": totals.api_calls_count if hasattr(totals, 'api_calls_count') else 0,
            "storage_gb": round(storage_gb, 2)  # Round to 2 decimal places
        },
        "limits": {
            "agents": tenant.max_agents,
            "channels": tenant.max_channels,
            "messages_per_day": tenant.max_messages_per_day,
            "api_calls_per_day": tenant.max_messages_per_day // 5,
            "storage_gb": 10  # Default 10GB storage limit
        },
        "success": True
    }
    
    
@router.get("/historical", tags=["Usage"])
async def get_historical_metrics(
    tenant_id: str = Depends(get_tenant_id),
    timeframe: str = Query("7d", description="Time period (24h, 7d, 30d)"),
    metric: str = Query("messages", description="Metric to retrieve (messages, agents, api_calls)")
):
    """
    Get historical usage metrics by timeframe and metric.
    
    Note: This is a placeholder that returns empty data, as historical metrics are not
    currently tracked. Real implementation will be added in a future update.
    
    Args:
        tenant_id: Tenant ID
        timeframe: Time period (24h, 7d, 30d)
        metric: Metric to retrieve (messages, agents, api_calls)
        
    Returns:
        Empty historical metrics in the expected format
    """
    # Validate tenant
    tenant = await validate_tenant(tenant_id)
    
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Calculate start and end dates based on timeframe
    today = date.today()
    end_date = today
    
    if timeframe == "24h":
        start_date = today - timedelta(days=1)
        # For hourly data
        empty_data = []
        for hour in range(24):
            hour_str = f"{hour:02d}:00"
            empty_data.append({
                "hour": hour_str,
                "date": today.isoformat(),
                metric: 0,
                "timestamp": f"{today.isoformat()}T{hour_str}:00Z"
            })
        return {
            "hourly_data": empty_data,
            "daily_data": [],
            "metric": metric,
            "timeframe": timeframe,
            "success": True,
            "message": "Historical data not available yet. Coming soon!",
            "tenant_id": tenant_id
        }
    elif timeframe == "7d":
        start_date = today - timedelta(days=6)
    elif timeframe == "30d":
        start_date = today - timedelta(days=29)
    else:
        start_date = today - timedelta(days=6)  # Default to 7d
    
    # Generate empty daily data for the date range
    empty_data = []
    current_date = start_date
    while current_date <= end_date:
        empty_data.append({
            "date": current_date.isoformat(),
            metric: 0,
            "timestamp": f"{current_date.isoformat()}T00:00:00Z"
        })
        current_date += timedelta(days=1)
    
    # Return empty data with appropriate message
    return {
        "daily_data": empty_data,
        "hourly_data": [],
        "metric": metric,
        "timeframe": timeframe,
        "success": True,
        "message": "Historical data not available yet. Coming soon!",
        "tenant_id": tenant_id
    }


@router.get("/wildcard-stats")
async def get_wildcard_tracker_stats(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get wildcard tracker statistics for debugging and monitoring.
    
    This shows ALL subjects being used in the system, helping identify
    any messages that might be bypassing normal tracking.
    """
    # Validate tenant (admin only in production)
    await validate_tenant(tenant_id)
    
    stats = wildcard_tracker.get_stats()
    
    return {
        "tracker_stats": stats,
        "description": "These stats show ALL messages flowing through NATS",
        "note": "If messages appear here but not in regular tracking, they may be using non-standard subjects"
    }