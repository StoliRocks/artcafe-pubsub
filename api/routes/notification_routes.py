from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

from auth.dependencies import get_current_user
from api.services.notification_service import notification_service
from models.notification import (
    Notification, NotificationCreate, NotificationUpdate,
    NotificationType, NotificationStatus, NotificationPriority,
    NotificationPreferences
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=List[Notification])
async def get_notifications(
    user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[NotificationStatus] = Query(None),
    notification_type: Optional[NotificationType] = Query(None),
    days: int = Query(7, ge=1, le=90)
):
    """
    Get notifications for the current user
    
    Args:
        limit: Maximum number of notifications (1-200)
        status: Filter by status
        notification_type: Filter by type
        days: Number of days to look back (1-90)
        
    Returns:
        List of notifications
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        notifications = await notification_service.get_notifications(
            user_id=user_id,
            limit=limit,
            status=status,
            notification_type=notification_type,
            start_date=start_date
        )
        
        return notifications
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching notifications: {str(e)}"
        )


@router.get("/unread-count", response_model=Dict[str, int])
async def get_unread_count(
    user: dict = Depends(get_current_user)
):
    """
    Get count of unread notifications
    
    Returns:
        Dictionary with unread_count
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        count = await notification_service.get_unread_count(user_id)
        
        return {"unread_count": count}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting unread count: {str(e)}"
        )


@router.put("/{notification_id}/read", response_model=Notification)
async def mark_as_read(
    notification_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Mark a notification as read
    
    Args:
        notification_id: Notification ID
        
    Returns:
        Updated notification
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        notification = await notification_service.mark_as_read(
            user_id=user_id,
            notification_id=notification_id
        )
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return notification
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error marking notification as read: {str(e)}"
        )


@router.put("/mark-all-read", response_model=Dict[str, int])
async def mark_all_as_read(
    user: dict = Depends(get_current_user)
):
    """
    Mark all notifications as read
    
    Returns:
        Dictionary with count of notifications marked
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        count = await notification_service.mark_all_as_read(user_id)
        
        return {"marked_count": count}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error marking all as read: {str(e)}"
        )


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Delete a notification
    
    Args:
        notification_id: Notification ID
        
    Returns:
        Success status
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        success = await notification_service.delete_notification(
            user_id=user_id,
            notification_id=notification_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting notification: {str(e)}"
        )


@router.get("/preferences", response_model=NotificationPreferences)
async def get_preferences(
    user: dict = Depends(get_current_user)
):
    """
    Get notification preferences
    
    Returns:
        User's notification preferences
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        preferences = await notification_service.get_user_preferences(user_id)
        
        return preferences
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting preferences: {str(e)}"
        )


@router.put("/preferences", response_model=NotificationPreferences)
async def update_preferences(
    preferences: Dict[str, Any],
    user: dict = Depends(get_current_user)
):
    """
    Update notification preferences
    
    Args:
        preferences: Preference updates
        
    Returns:
        Updated preferences
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        updated = await notification_service.update_user_preferences(
            user_id=user_id,
            preferences=preferences
        )
        
        return updated
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating preferences: {str(e)}"
        )


@router.get("/types", response_model=List[str])
async def get_notification_types():
    """Get all notification types"""
    return [nt.value for nt in NotificationType]


@router.get("/priorities", response_model=List[str])
async def get_notification_priorities():
    """Get all notification priorities"""
    return [np.value for np in NotificationPriority]


# Internal endpoint for creating notifications (not exposed to users directly)
@router.post("/internal/create", response_model=Notification, include_in_schema=False)
async def create_notification_internal(
    notification_data: NotificationCreate,
    api_key: str = Depends(get_api_key)  # Special internal API key
):
    """
    Internal endpoint for services to create notifications
    
    This is called by other services when events occur
    """
    try:
        notification = await notification_service.create_notification(notification_data)
        return notification
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating notification: {str(e)}"
        )