"""
Usage routes using local Valkey/Redis tracking
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta

from auth.dependencies import get_current_tenant_id
from api.services.local_message_tracker import message_tracker

router = APIRouter(prefix="/usage", tags=["usage"])

@router.get("/current")
async def get_current_usage(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get current usage statistics for the tenant"""
    
    # Get stats from local tracker
    stats = await message_tracker.get_current_stats(tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "current_period": {
            "start": datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "usage": stats
    }

@router.get("/history")
async def get_usage_history(
    tenant_id: str = Depends(get_current_tenant_id),
    days: int = Query(default=7, ge=1, le=30, description="Number of days of history")
):
    """Get historical usage data"""
    
    # Get stats from local tracker
    history = await message_tracker.get_usage_history(tenant_id, days=days)
    
    return {
        "tenant_id": tenant_id,
        "period": {
            "days": days,
            "start": (datetime.utcnow() - timedelta(days=days)).isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "daily_stats": history
    }

@router.get("/summary")
async def get_usage_summary(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get usage summary for different time periods"""
    
    # Get current stats
    current = await message_tracker.get_current_stats(tenant_id)
    
    # Get history for calculations
    week_history = await message_tracker.get_usage_history(tenant_id, days=7)
    month_history = await message_tracker.get_usage_history(tenant_id, days=30)
    
    # Calculate totals
    week_total = sum(day.get('messages', 0) for day in week_history)
    month_total = sum(day.get('messages', 0) for day in month_history)
    
    return {
        "tenant_id": tenant_id,
        "summary": {
            "today": {
                "messages": current.get('messages', 0),
                "bytes": current.get('bytes', 0),
                "api_calls": current.get('api_calls', 0),
                "active_agents": current.get('active_agents', 0),
                "active_channels": current.get('active_channels', 0)
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