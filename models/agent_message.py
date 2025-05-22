"""
Agent message protocol models for NATS-based multi-agent communication.

This module defines the standardized message format for agent-to-agent
and agent-to-system communication in the ArtCafe.ai platform.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid


class MessageType(str, Enum):
    """Types of messages in the agent communication protocol"""
    TASK = "task"
    RESULT = "result"
    EVENT = "event"
    QUERY = "query"
    STREAM = "stream"
    COMMAND = "command"
    HEARTBEAT = "heartbeat"
    NEGOTIATION = "negotiation"


class AgentIdentity(BaseModel):
    """Identity information for message source/target"""
    id: str
    type: str = "agent"  # agent, system, user
    tenant_id: str
    capabilities: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class MessageContext(BaseModel):
    """Context information for message processing and history"""
    conversation_id: str
    parent_message_id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    max_history: int = 10
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessagePayload(BaseModel):
    """Payload containing the actual message content"""
    content: Any
    model: Optional[str] = None  # LLM model preference
    parameters: Optional[Dict[str, Any]] = None  # LLM parameters (temperature, max_tokens, etc.)
    constraints: Optional[Dict[str, Any]] = None  # Time limits, cost limits, etc.


class MessageRouting(BaseModel):
    """Routing hints and requirements for message delivery"""
    priority: int = Field(default=5, ge=0, le=9)  # 0-9, higher = more urgent
    capabilities: List[str] = Field(default_factory=list)  # Required agent capabilities
    exclusions: List[str] = Field(default_factory=list)  # Agents to exclude
    timeout: Optional[int] = None  # Message expiry in milliseconds
    queue_group: Optional[str] = None  # For load balancing


class StreamMetadata(BaseModel):
    """Metadata for streaming responses"""
    sequence_number: int
    is_first: bool = False
    is_final: bool = False
    total_expected: Optional[int] = None


class AgentMessage(BaseModel):
    """
    Standardized message format for agent communication.
    
    This message format supports:
    - Async communication patterns
    - Message correlation and threading
    - Capability-based routing
    - LLM-specific parameters
    - Streaming responses
    - Multi-tenant isolation
    """
    # Message Metadata
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: datetime.utcnow().timestamp())
    version: str = "1.0"
    
    # Message Type and Routing
    type: MessageType
    source: AgentIdentity
    target: Optional[str] = None  # Specific agent ID or None for broadcast
    reply_to: Optional[str] = None  # Topic for responses
    correlation_id: Optional[str] = None  # Links related messages
    
    # Context and Content
    context: MessageContext
    payload: MessagePayload
    routing: MessageRouting
    
    # Optional streaming metadata
    stream_metadata: Optional[StreamMetadata] = None
    
    class Config:
        """Pydantic configuration"""
        allow_population_by_field_name = True
        schema_extra = {
            "example": {
                "id": "msg-123e4567-e89b-12d3-a456-426614174000",
                "timestamp": 1234567890.123,
                "version": "1.0",
                "type": "task",
                "source": {
                    "id": "agent-001",
                    "type": "agent",
                    "tenant_id": "tenant-123",
                    "capabilities": ["analysis", "code_generation"]
                },
                "context": {
                    "conversation_id": "conv-123",
                    "metadata": {"user": "user-456"}
                },
                "payload": {
                    "content": {
                        "instruction": "Analyze this code for security vulnerabilities",
                        "code": "def process_user_input(data): exec(data)"
                    },
                    "model": "claude-3-opus",
                    "parameters": {"temperature": 0.7, "max_tokens": 2000}
                },
                "routing": {
                    "priority": 7,
                    "capabilities": ["security_analysis"],
                    "timeout": 30000
                }
            }
        }
    
    def to_subject(self, tenant_id: str) -> str:
        """Generate NATS subject based on message type and routing"""
        base = f"agents.{tenant_id}"
        
        if self.type == MessageType.TASK:
            if self.routing.capabilities:
                capability = self.routing.capabilities[0]
                return f"{base}.task.{capability}.general"
            return f"{base}.task.general"
            
        elif self.type == MessageType.RESULT:
            agent_id = self.source.id
            task_type = self.payload.content.get("task_type", "general")
            return f"{base}.result.{agent_id}.{task_type}"
            
        elif self.type == MessageType.EVENT:
            event_type = self.payload.content.get("event", "general")
            return f"{base}.event.{event_type}"
            
        elif self.type == MessageType.STREAM:
            stream_id = self.correlation_id or self.id
            return f"{base}.stream.response.{stream_id}"
            
        elif self.type == MessageType.HEARTBEAT:
            return f"{base}.heartbeat"
            
        elif self.type == MessageType.COMMAND:
            if self.target:
                return f"{base}.command.{self.target}"
            return f"{base}.command.broadcast"
            
        else:
            return f"{base}.{self.type.value}.general"
    
    def create_response(
        self,
        content: Any,
        success: bool = True,
        **kwargs
    ) -> "AgentMessage":
        """Create a response message to this message"""
        return AgentMessage(
            type=MessageType.RESULT,
            source=kwargs.get("source", self.source),
            correlation_id=self.id,
            context=self.context,
            payload=MessagePayload(
                content={
                    "success": success,
                    "data": content,
                    "original_task": self.id
                }
            ),
            routing=MessageRouting(
                priority=self.routing.priority
            ),
            reply_to=self.reply_to
        )


class AgentCapability(BaseModel):
    """Definition of an agent capability"""
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    models: List[str] = Field(default_factory=list)  # Supported LLM models
    max_concurrent: int = 1
    average_duration_ms: Optional[int] = None


class AgentAnnouncement(BaseModel):
    """Agent announcement message for discovery"""
    agent_id: str
    tenant_id: str
    capabilities: List[AgentCapability]
    status: str  # online, busy, offline
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)