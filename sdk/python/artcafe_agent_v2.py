#!/usr/bin/env python3
"""
ArtCafe.ai Agent SDK v2.0 - Support for AgentMessage Protocol

This SDK provides an updated client implementation for ArtCafe.ai agents
that uses the new standardized AgentMessage protocol for communication.

Key features:
- AgentMessage protocol support
- Capability-based task routing
- Discovery and announcements
- Streaming response support
- Improved error handling and reconnection
"""

import asyncio
import json
import uuid
import time
import logging
import base64
import socket
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Awaitable, Union, AsyncIterator
from enum import Enum
from dataclasses import dataclass, field

import jwt
import websockets
import httpx
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

__version__ = "2.0.0"


# Message Type Enum
class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    EVENT = "event"
    QUERY = "query"
    STREAM = "stream"
    COMMAND = "command"
    HEARTBEAT = "heartbeat"
    NEGOTIATION = "negotiation"


@dataclass
class AgentIdentity:
    """Agent identity information"""
    id: str
    type: str = "agent"
    tenant_id: str = ""
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageContext:
    """Message context information"""
    conversation_id: str
    parent_message_id: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    max_history: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessagePayload:
    """Message payload"""
    content: Any
    model: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None


@dataclass
class MessageRouting:
    """Message routing information"""
    priority: int = 5
    capabilities: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    queue_group: Optional[str] = None


@dataclass
class StreamMetadata:
    """Streaming metadata"""
    sequence_number: int
    is_first: bool = False
    is_final: bool = False
    total_expected: Optional[int] = None


@dataclass
class AgentMessage:
    """Standardized agent message format"""
    type: MessageType
    source: AgentIdentity
    context: MessageContext
    payload: MessagePayload
    routing: MessageRouting
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    version: str = "1.0"
    target: Optional[str] = None
    reply_to: Optional[str] = None
    correlation_id: Optional[str] = None
    stream_metadata: Optional[StreamMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "id": self.id,
            "timestamp": self.timestamp,
            "version": self.version,
            "type": self.type.value,
            "source": {
                "id": self.source.id,
                "type": self.source.type,
                "tenant_id": self.source.tenant_id,
                "capabilities": self.source.capabilities,
                "metadata": self.source.metadata
            },
            "context": {
                "conversation_id": self.context.conversation_id,
                "parent_message_id": self.context.parent_message_id,
                "history": self.context.history,
                "max_history": self.context.max_history,
                "metadata": self.context.metadata
            },
            "payload": {
                "content": self.payload.content,
                "model": self.payload.model,
                "parameters": self.payload.parameters,
                "constraints": self.payload.constraints
            },
            "routing": {
                "priority": self.routing.priority,
                "capabilities": self.routing.capabilities,
                "exclusions": self.routing.exclusions,
                "timeout": self.routing.timeout,
                "queue_group": self.routing.queue_group
            }
        }
        
        if self.target:
            result["target"] = self.target
        if self.reply_to:
            result["reply_to"] = self.reply_to
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.stream_metadata:
            result["stream_metadata"] = {
                "sequence_number": self.stream_metadata.sequence_number,
                "is_first": self.stream_metadata.is_first,
                "is_final": self.stream_metadata.is_final,
                "total_expected": self.stream_metadata.total_expected
            }
            
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create from dictionary"""
        # Parse source
        source_data = data["source"]
        source = AgentIdentity(
            id=source_data["id"],
            type=source_data.get("type", "agent"),
            tenant_id=source_data["tenant_id"],
            capabilities=source_data.get("capabilities", []),
            metadata=source_data.get("metadata", {})
        )
        
        # Parse context
        context_data = data["context"]
        context = MessageContext(
            conversation_id=context_data["conversation_id"],
            parent_message_id=context_data.get("parent_message_id"),
            history=context_data.get("history", []),
            max_history=context_data.get("max_history", 10),
            metadata=context_data.get("metadata", {})
        )
        
        # Parse payload
        payload_data = data["payload"]
        payload = MessagePayload(
            content=payload_data["content"],
            model=payload_data.get("model"),
            parameters=payload_data.get("parameters"),
            constraints=payload_data.get("constraints")
        )
        
        # Parse routing
        routing_data = data["routing"]
        routing = MessageRouting(
            priority=routing_data.get("priority", 5),
            capabilities=routing_data.get("capabilities", []),
            exclusions=routing_data.get("exclusions", []),
            timeout=routing_data.get("timeout"),
            queue_group=routing_data.get("queue_group")
        )
        
        # Parse stream metadata if present
        stream_metadata = None
        if "stream_metadata" in data and data["stream_metadata"]:
            sm_data = data["stream_metadata"]
            stream_metadata = StreamMetadata(
                sequence_number=sm_data["sequence_number"],
                is_first=sm_data.get("is_first", False),
                is_final=sm_data.get("is_final", False),
                total_expected=sm_data.get("total_expected")
            )
        
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            version=data.get("version", "1.0"),
            type=MessageType(data["type"]),
            source=source,
            target=data.get("target"),
            reply_to=data.get("reply_to"),
            correlation_id=data.get("correlation_id"),
            context=context,
            payload=payload,
            routing=routing,
            stream_metadata=stream_metadata
        )


@dataclass
class AgentCapability:
    """Agent capability definition"""
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    models: List[str] = field(default_factory=list)
    max_concurrent: int = 1
    average_duration_ms: Optional[int] = None


class ArtCafeAgentError(Exception):
    """Base exception for ArtCafe Agent errors"""
    pass


class AuthenticationError(ArtCafeAgentError):
    """Authentication error"""
    pass


class ConnectionError(ArtCafeAgentError):
    """Connection error"""
    pass


class MessageError(ArtCafeAgentError):
    """Message handling error"""
    pass