"""
Updated usage routes that query the NATS instance tracking service
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta

from auth.dependencies import get_current_tenant_id
from api.services.remote_tracking_client import tracking_client

router = APIRouter(prefix="/usage", tags=["usage"])

@router.get("/current")
async def get_current_usage(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get current usage statistics for the tenant"""
    
    # Get stats from tracking service
    current = await tracking_client.get_current_usage(tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "current_period": {
            "start": datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "usage": {
            "messages": current.get('messages', 0),
            "bytes": current.get('bytes', 0),
            "active_agents": current.get('active_agents', 0),
            "active_channels": current.get('active_channels', 0)
        }
    }

@router.get("/history")
async def get_usage_history(
    tenant_id: str = Depends(get_current_tenant_id),
    days: int = Query(default=30, ge=1, le=90, description="Number of days of history")
):
    """Get historical usage data"""
    
    # Get stats from tracking service
    result = await tracking_client.get_tenant_stats(tenant_id, days=days)
    
    return {
        "tenant_id": tenant_id,
        "period": {
            "days": days,
            "start": (datetime.utcnow() - timedelta(days=days)).isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "daily_stats": result.get('stats', [])
    }

@router.get("/summary")
async def get_usage_summary(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get usage summary for different time periods"""
    
    # Get stats for different periods
    today = await tracking_client.get_current_usage(tenant_id)
    week = await tracking_client.get_tenant_stats(tenant_id, days=7)
    month = await tracking_client.get_tenant_stats(tenant_id, days=30)
    
    # Calculate totals
    week_total = sum(day.get('messages', 0) for day in week.get('stats', []))
    month_total = sum(day.get('messages', 0) for day in month.get('stats', []))
    
    return {
        "tenant_id": tenant_id,
        "summary": {
            "today": {
                "messages": today.get('messages', 0),
                "active_agents": today.get('active_agents', 0),
                "active_channels": today.get('active_channels', 0)
            },
            "last_7_days": {
                "messages": week_total,
                "daily_average": week_total // 7 if week_total > 0 else 0
            },
            "last_30_days": {
                "messages": month_total,
                "daily_average": month_total // 30 if month_total > 0 else 0
            }
        }
    }