from typing import Dict, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class AgentMetadata(BaseModel):
    """Agent metadata model"""
    description: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    custom: Optional[Dict] = None


class AgentBase(BaseModel):
    """Base agent model"""
    name: str
    metadata: Optional[AgentMetadata] = Field(default_factory=AgentMetadata)


class AgentCreate(AgentBase):
    """Agent creation model"""
    public_key: Optional[str] = None


class AgentUpdate(BaseModel):
    """Agent update model"""
    name: Optional[str] = None
    metadata: Optional[AgentMetadata] = None


class Agent(AgentBase, BaseSchema):
    """Agent model"""
    agent_id: str = Field(..., alias="id")
    status: str  # Status is determined by connection state, not user-set
    tenant_id: str
    public_key: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    
    # Subscription tracking
    channel_subscriptions: Set[str] = Field(default_factory=set)
    active_connections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    
    class Config:
        allow_population_by_field_name = True


class AgentResponse(BaseModel):
    """Agent response model"""
    agent: Agent
    success: bool = True


class AgentsResponse(BaseModel):
    """Agents list response model"""
    agents: List[Agent]
    next_token: Optional[str] = None