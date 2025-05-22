from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class AgentMetadata(BaseModel):
    """Agent metadata model"""
    description: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    custom: Optional[Dict] = None


class AgentCapabilityDefinition(BaseModel):
    """Agent capability definition"""
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    models: List[str] = Field(default_factory=list)  # Supported LLM models
    max_concurrent: int = 1
    average_duration_ms: Optional[int] = None


class AgentBase(BaseModel):
    """Base agent model"""
    name: str
    capabilities: List[str] = Field(default_factory=list)  # List of capability names
    capability_definitions: Optional[List[AgentCapabilityDefinition]] = None  # Full capability definitions
    metadata: Optional[AgentMetadata] = Field(default_factory=AgentMetadata)


class AgentCreate(AgentBase):
    """Agent creation model"""
    type: str  # Required field for now  
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
    key_fingerprint: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    
    # Subscription tracking
    channel_subscriptions: Set[str] = Field(default_factory=set)
    active_connections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    
    # Performance tracking
    average_response_time_ms: Optional[float] = None
    success_rate: Optional[float] = None  # Percentage of successful task completions
    
    # Resource limits
    max_concurrent_tasks: int = 5
    max_memory_mb: Optional[int] = None
    max_cpu_percent: Optional[int] = None
    
    class Config:
        allow_population_by_field_name = True


class AgentResponse(BaseModel):
    """Agent response model"""
    agent: Agent
    success: bool = True


class AgentCreateResponse(BaseModel):
    """Agent creation response model with optional private key"""
    agent: Agent
    private_key: Optional[str] = None
    success: bool = True


class AgentsResponse(BaseModel):
    """Agents list response model"""
    agents: List[Agent]
    next_token: Optional[str] = None