from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class AgentMetadata(BaseModel):
    """Agent metadata model"""
    description: Optional[str] = None
    owner: Optional[str] = None
    roles: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    custom: Optional[Dict] = None


class AgentBase(BaseModel):
    """Base agent model"""
    name: str
    type: str = Field(..., description="Agent type (worker, supervisor, specialist)")
    metadata: Optional[AgentMetadata] = Field(default_factory=AgentMetadata)


class AgentCreate(AgentBase):
    """Agent creation model"""
    public_key: Optional[str] = None
    status: str = Field(default="offline", description="Agent status (online, offline, error)")


class AgentUpdate(BaseModel):
    """Agent update model"""
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[AgentMetadata] = None


class Agent(AgentBase, BaseSchema):
    """Agent model"""
    agent_id: str = Field(..., alias="id")
    status: str
    tenant_id: str
    public_key: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    
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