"""
Channel subscription models for tracking agent-channel relationships.
"""
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field

from .base import BaseSchema


class SubscriptionRole(str, Enum):
    """Subscription role types"""
    PUBLISHER = "publisher"
    SUBSCRIBER = "subscriber"
    BOTH = "both"


class ChannelSubscriptionBase(BaseModel):
    """Base channel subscription model"""
    channel_id: str = Field(..., description="Channel ID")
    agent_id: str = Field(..., description="Agent ID")
    role: SubscriptionRole = Field(default=SubscriptionRole.BOTH, description="Subscription role")


class ChannelSubscriptionCreate(ChannelSubscriptionBase):
    """Channel subscription creation model"""
    pass


class ChannelSubscriptionUpdate(BaseModel):
    """Channel subscription update model"""
    role: Optional[SubscriptionRole] = Field(None, description="Updated role")


class ChannelSubscription(ChannelSubscriptionBase, BaseSchema):
    """Complete channel subscription model"""
    subscription_id: str = Field(..., alias="id")
    tenant_id: str = Field(..., description="Tenant ID")
    state: str = Field(default="offline", description="Connection state: online/offline")
    websocket_id: Optional[str] = Field(None, description="WebSocket connection ID")
    server_id: Optional[str] = Field(None, description="Server ID for multi-server support")
    connected_at: Optional[datetime] = Field(None, description="Connection timestamp")
    disconnected_at: Optional[datetime] = Field(None, description="Disconnection timestamp")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow(), description="Creation timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class ChannelSubscriptionResponse(ChannelSubscription):
    """Channel subscription response model"""
    pass


class ChannelSubscriptionsResponse(BaseModel):
    """Multiple channel subscriptions response"""
    subscriptions: List[ChannelSubscriptionResponse]
    total: int