from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator

from .base import BaseSchema


class SubscriptionRole(str):
    """Subscription role enum"""
    SUBSCRIBER = "subscriber"
    PUBLISHER = "publisher"
    ADMIN = "admin"
    OWNER = "owner"


class ChannelSubscriptionBase(BaseModel):
    """Base channel subscription model"""
    agent_id: str
    channel_id: str
    role: str = SubscriptionRole.SUBSCRIBER
    permissions: Dict[str, bool] = Field(default_factory=lambda: {
        "read": True,
        "write": False,
        "publish": False,
        "subscribe": True,
        "manage": False
    })
    
    @validator('role')
    def validate_role(cls, v):
        """Validate subscription role"""
        allowed_roles = [SubscriptionRole.SUBSCRIBER, SubscriptionRole.PUBLISHER,
                        SubscriptionRole.ADMIN, SubscriptionRole.OWNER]
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {', '.join(allowed_roles)}")
        return v


class ChannelSubscriptionCreate(ChannelSubscriptionBase):
    """Channel subscription creation model"""
    metadata: Optional[Dict] = None


class ChannelSubscription(ChannelSubscriptionBase, BaseSchema):
    """Channel subscription model"""
    subscription_id: str = Field(..., alias="id")
    tenant_id: str
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    status: str = "active"
    metadata: Optional[Dict] = None
    
    # Connection details
    connection_id: Optional[str] = None  # WebSocket connection ID if connected
    connected_at: Optional[datetime] = None
    
    # Usage tracking
    messages_sent: int = 0
    messages_received: int = 0
    
    class Config:
        allow_population_by_field_name = True


class ChannelSubscriptionUpdate(BaseModel):
    """Channel subscription update model"""
    role: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    status: Optional[str] = None
    metadata: Optional[Dict] = None


class ChannelSubscriptionResponse(BaseModel):
    """Channel subscription response model"""
    subscription: ChannelSubscription
    success: bool = True


class ChannelSubscriptionsResponse(BaseModel):
    """Channel subscriptions list response model"""
    subscriptions: List[ChannelSubscription]
    next_token: Optional[str] = None