from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .base import BaseSchema


class ChannelBase(BaseModel):
    """Base channel model"""
    name: str
    description: Optional[str] = None


class ChannelCreate(ChannelBase):
    """Channel creation model"""
    metadata: Optional[Dict] = None


class Channel(ChannelBase, BaseSchema):
    """Channel model"""
    channel_id: str = Field(..., alias="id")
    tenant_id: str
    status: str = "active"
    metadata: Optional[Dict] = None
    
    class Config:
        allow_population_by_field_name = True


class ChannelResponse(BaseModel):
    """Channel response model"""
    channel: Channel
    success: bool = True


class ChannelsResponse(BaseModel):
    """Channels list response model"""
    channels: List[Channel]
    next_token: Optional[str] = None