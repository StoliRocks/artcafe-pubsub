import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, status

from api.middleware import verify_jwt_token, require_tenant_id
from api.services.channel_subscription_service import channel_subscription_service
from models.channel_subscription import (
    ChannelSubscriptionCreate,
    ChannelSubscriptionUpdate,
    ChannelSubscriptionResponse,
    ChannelSubscriptionsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("/", response_model=ChannelSubscriptionResponse)
async def create_subscription(
    subscription_data: ChannelSubscriptionCreate,
    tenant_id: str = Depends(require_tenant_id),
    _: dict = Depends(verify_jwt_token)
):
    """Create a new channel subscription"""
    try:
        subscription = await channel_subscription_service.create_subscription(
            tenant_id=tenant_id,
            subscription_data=subscription_data
        )
        return ChannelSubscriptionResponse(subscription=subscription)
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{channel_id}/{agent_id}", response_model=ChannelSubscriptionResponse)
async def get_subscription(
    channel_id: str,
    agent_id: str,
    _: dict = Depends(verify_jwt_token)
):
    """Get a specific subscription"""
    try:
        subscription = await channel_subscription_service.get_subscription(
            channel_id=channel_id,
            agent_id=agent_id
        )
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return ChannelSubscriptionResponse(subscription=subscription)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{channel_id}/{agent_id}", response_model=ChannelSubscriptionResponse)
async def update_subscription(
    channel_id: str,
    agent_id: str,
    update_data: ChannelSubscriptionUpdate,
    _: dict = Depends(verify_jwt_token)
):
    """Update a subscription"""
    try:
        subscription = await channel_subscription_service.update_subscription(
            channel_id=channel_id,
            agent_id=agent_id,
            update_data=update_data
        )
        return ChannelSubscriptionResponse(subscription=subscription)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{channel_id}/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    channel_id: str,
    agent_id: str,
    tenant_id: str = Depends(require_tenant_id),
    _: dict = Depends(verify_jwt_token)
):
    """Delete a subscription"""
    try:
        success = await channel_subscription_service.delete_subscription(
            tenant_id=tenant_id,
            channel_id=channel_id,
            agent_id=agent_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Subscription not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channel/{channel_id}", response_model=ChannelSubscriptionsResponse)
async def list_channel_subscriptions(
    channel_id: str,
    limit: int = Query(100, le=1000),
    next_token: Optional[str] = None,
    _: dict = Depends(verify_jwt_token)
):
    """List all subscriptions for a channel"""
    try:
        result = await channel_subscription_service.list_channel_subscriptions(
            channel_id=channel_id,
            limit=limit,
            next_token=next_token
        )
        return ChannelSubscriptionsResponse(**result)
    except Exception as e:
        logger.error(f"Error listing channel subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/{agent_id}", response_model=ChannelSubscriptionsResponse)
async def list_agent_subscriptions(
    agent_id: str,
    limit: int = Query(100, le=1000),
    next_token: Optional[str] = None,
    _: dict = Depends(verify_jwt_token)
):
    """List all subscriptions for an agent"""
    try:
        result = await channel_subscription_service.list_agent_subscriptions(
            agent_id=agent_id,
            limit=limit,
            next_token=next_token
        )
        return ChannelSubscriptionsResponse(**result)
    except Exception as e:
        logger.error(f"Error listing agent subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tenant/{tenant_id}", response_model=ChannelSubscriptionsResponse)
async def list_tenant_subscriptions(
    tenant_id: str,
    limit: int = Query(100, le=1000),
    next_token: Optional[str] = None,
    _: dict = Depends(verify_jwt_token)
):
    """List all subscriptions for a tenant"""
    try:
        result = await channel_subscription_service.list_tenant_subscriptions(
            tenant_id=tenant_id,
            limit=limit,
            next_token=next_token
        )
        return ChannelSubscriptionsResponse(**result)
    except Exception as e:
        logger.error(f"Error listing tenant subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{channel_id}/{agent_id}/activity")
async def update_subscription_activity(
    channel_id: str,
    agent_id: str,
    activity_type: str = Query("message", description="Type of activity"),
    _: dict = Depends(verify_jwt_token)
):
    """Update subscription activity (for tracking last activity)"""
    try:
        await channel_subscription_service.update_last_activity(
            channel_id=channel_id,
            agent_id=agent_id,
            activity_type=activity_type
        )
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error updating activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{channel_id}/{agent_id}/connection")
async def update_subscription_connection(
    channel_id: str,
    agent_id: str,
    connected: bool = Query(..., description="Connection status"),
    connection_id: Optional[str] = Query(None, description="WebSocket connection ID"),
    _: dict = Depends(verify_jwt_token)
):
    """Update subscription connection status"""
    try:
        await channel_subscription_service.update_connection_status(
            channel_id=channel_id,
            agent_id=agent_id,
            connected=connected,
            connection_id=connection_id
        )
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error updating connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))