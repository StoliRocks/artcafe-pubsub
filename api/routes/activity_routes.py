from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import List, Optional
from datetime import datetime, timedelta

from auth.dependencies import get_current_user, verify_tenant_access
from api.services.activity_service import activity_service
from models.activity_log import (
    ActivityLog, ActivityType, ActivityStatus, ActivitySummary
)

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/logs", response_model=List[ActivityLog])
async def get_activity_logs(
    request: Request,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(50, ge=1, le=200),
    hours: int = Query(24, ge=1, le=168),  # Max 7 days
    activity_type: Optional[ActivityType] = Query(None),
    status: Optional[ActivityStatus] = Query(None)
):
    """
    Get activity logs for the tenant
    
    Args:
        limit: Maximum number of logs to return (1-200)
        hours: Number of hours to look back (1-168)
        activity_type: Filter by activity type
        status: Filter by status
        
    Returns:
        List of activity logs
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(hours=hours)
        
        # Get activities
        activities = await activity_service.get_activities(
            tenant_id=tenant_id,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            activity_type=activity_type,
            status=status
        )
        
        return activities
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching activity logs: {str(e)}"
        )


@router.get("/summary", response_model=ActivitySummary)
async def get_activity_summary(
    request: Request,
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(verify_tenant_access),
    hours: int = Query(24, ge=1, le=168)
):
    """
    Get activity summary for dashboard
    
    Args:
        hours: Number of hours to analyze (1-168)
        
    Returns:
        Activity summary with counts and recent activities
    """
    try:
        summary = await activity_service.get_activity_summary(
            tenant_id=tenant_id,
            hours=hours
        )
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching activity summary: {str(e)}"
        )


@router.get("/types", response_model=List[str])
async def get_activity_types(
    user: dict = Depends(get_current_user)
):
    """
    Get all available activity types
    
    Returns:
        List of activity type values
    """
    return [activity_type.value for activity_type in ActivityType]


@router.get("/statuses", response_model=List[str])
async def get_activity_statuses(
    user: dict = Depends(get_current_user)
):
    """
    Get all available activity statuses
    
    Returns:
        List of activity status values
    """
    return [status.value for status in ActivityStatus]


# WebSocket endpoint for real-time activity updates would be in websocket module
# Clients can subscribe to "activity.new" events for their tenant