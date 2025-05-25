from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
import logging

from auth.dependencies import get_current_tenant_id, get_current_user
from models.subscription import SubscriptionCreate, SubscriptionResponse
from api.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["billing"])


@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(
    tenant_id: str = Depends(get_current_tenant_id),
    user_data: dict = Depends(get_current_user)
) -> SubscriptionResponse:
    """Get the current active subscription for the authenticated user"""
    user_id = user_data["user_id"]
    logger.info(f"Getting current subscription for user {user_id} in tenant {tenant_id}")
    
    subscription = await SubscriptionService.get_current_subscription(tenant_id, user_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found"
        )
    
    return subscription


@router.post("/", response_model=SubscriptionResponse)
async def create_subscription(
    subscription_data: SubscriptionCreate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_data: dict = Depends(get_current_user)
) -> SubscriptionResponse:
    """Create a new subscription for the authenticated user"""
    user_id = user_data["user_id"]
    logger.info(f"Creating subscription for user {user_id} in tenant {tenant_id}")
    
    try:
        subscription = await SubscriptionService.create_subscription(
            tenant_id, user_id, subscription_data
        )
        return subscription
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.post("/{subscription_id}/cancel", response_model=dict)
async def cancel_subscription(
    subscription_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_data: dict = Depends(get_current_user)
) -> dict:
    """Cancel a subscription"""
    user_id = user_data["user_id"]
    logger.info(f"Cancelling subscription {subscription_id} for user {user_id}")
    
    try:
        success = await SubscriptionService.cancel_subscription(tenant_id, subscription_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )
        return {"status": "success", "message": "Subscription cancelled"}
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


@router.get("/organizations/{organization_id}/subscriptions", response_model=List[SubscriptionResponse])
async def get_organization_subscriptions(
    organization_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_data: dict = Depends(get_current_user)
) -> List[SubscriptionResponse]:
    """Get all subscriptions for an organization"""
    # Note: In this context, organization_id is the same as tenant_id
    # This endpoint is kept for compatibility with the frontend
    
    if organization_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization"
        )
    
    subscriptions = await SubscriptionService.get_organization_subscriptions(tenant_id)
    return subscriptions