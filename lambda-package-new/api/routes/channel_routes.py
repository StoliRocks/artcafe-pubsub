from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body

from auth import get_current_tenant_id
from models import ChannelCreate, ChannelResponse, ChannelsResponse
from api.services import channel_service, usage_service

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=ChannelsResponse)
async def list_channels(
    tenant_id: str = Depends(get_current_tenant_id),
    limit: int = Query(50, description="Maximum number of results"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """
    List channels for a tenant
    
    Returns:
        List of channels
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get channels
    result = await channel_service.list_channels(
        tenant_id=tenant_id,
        limit=limit,
        next_token=next_token
    )
    
    return ChannelsResponse(
        channels=result["channels"],
        next_token=result["next_token"]
    )


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str = Path(..., description="Channel ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get channel by ID
    
    Args:
        channel_id: Channel ID
        
    Returns:
        Channel details
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get channel
    channel = await channel_service.get_channel(tenant_id, channel_id)
    
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found"
        )
        
    return ChannelResponse(channel=channel)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    channel_data: ChannelCreate,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Create a new channel
    
    Args:
        channel_data: Channel data
        
    Returns:
        Created channel
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Create channel
    channel = await channel_service.create_channel(tenant_id, channel_data)
    
    return ChannelResponse(channel=channel)


@router.post("/{channel_id}/messages")
async def publish_message(
    message: Dict[str, Any] = Body(..., description="Message to publish"),
    channel_id: str = Path(..., description="Channel ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Publish message to a channel
    
    Args:
        channel_id: Channel ID
        message: Message to publish
        
    Returns:
        Message info
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Track message
    await usage_service.increment_messages(tenant_id)
    
    # Publish message
    result = await channel_service.publish_message(tenant_id, channel_id, message)
    
    return result


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str = Path(..., description="Channel ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Delete a channel
    
    Args:
        channel_id: Channel ID
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Delete channel
    result = await channel_service.delete_channel(tenant_id, channel_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found"
        )