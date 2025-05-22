import json
import logging
import uuid
import asyncio
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable, AsyncIterator
from datetime import datetime

from nats.msg import Msg
from nats.errors import AuthError
from core.nats_client import NATSClient
from core.nats_auth import nats_auth
from models.agent_message import (
    AgentMessage, MessageType, AgentIdentity, 
    MessageContext, MessagePayload, MessageRouting,
    StreamMetadata, AgentCapability, AgentAnnouncement
)

logger = logging.getLogger(__name__)

class MessagingService:
    """
    Service for agent-to-agent messaging using NATS.
    """
    
    def __init__(self, nats_client: NATSClient):
        """
        Initialize messaging service.
        
        Args:
            nats_client: NATS client
        """
        self.nats_client = nats_client
        self.service_id = nats_client.client_id
        
        # Track message handlers by subject
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        
        # Subscription IDs by subject
        self._subscriptions: Dict[str, int] = {}
    
    async def send_message(
        self,
        subject: str,
        message: Dict[str, Any],
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """
        Send a message to a subject.
        
        Args:
            subject: Subject to send message to
            message: Message payload
            reply_to: Optional reply subject
            headers: Optional message headers
            tenant_id: Optional tenant ID for authorization check
            
        Returns:
            Message ID
            
        Raises:
            AuthError: If tenant is not authorized to publish to the subject
        """
        # Validate tenant authorization if tenant_id is provided
        if tenant_id:
            nats_auth.validate_publish(tenant_id, subject)
            
            # Add tenant ID to headers if not already present
            if headers is None:
                headers = {}
            if "tenant_id" not in headers:
                headers["tenant_id"] = tenant_id
        
        # Extract tenant_id from subject if not explicitly provided
        elif subject.startswith("tenants."):
            # Parse tenant ID from subject (format: tenants.{tenant_id}.*)
            parts = subject.split(".")
            if len(parts) >= 2:
                extracted_tenant_id = parts[1]
                # Add to headers
                if headers is None:
                    headers = {}
                if "tenant_id" not in headers:
                    headers["tenant_id"] = extracted_tenant_id
        
        # Add message metadata
        message_id = str(uuid.uuid4())
        enriched_message = {
            **message,
            "meta": {
                "sender_id": self.service_id,
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        # Publish message
        await self.nats_client.publish(subject, enriched_message, reply_to=reply_to, headers=headers)
        
        return message_id
    
    async def subscribe(
        self,
        subject: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        queue_group: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Subscribe to a subject and register a callback function.
        
        Args:
            subject: Subject to subscribe to
            callback: Function to call when a message is received
            queue_group: Optional queue group for load balancing
            tenant_id: Optional tenant ID for authorization check
            
        Raises:
            AuthError: If tenant is not authorized to subscribe to the subject
        """
        # Validate tenant authorization if tenant_id is provided
        if tenant_id:
            nats_auth.validate_subscribe(tenant_id, subject)
        
        # Extract tenant_id from subject if not explicitly provided
        elif subject.startswith("tenants."):
            # Parse tenant ID from subject (format: tenants.{tenant_id}.*)
            parts = subject.split(".")
            if len(parts) >= 2:
                extracted_tenant_id = parts[1]
                # Register tenant with NATS auth
                nats_auth.register_tenant(extracted_tenant_id)
        
        # Register message handler
        if subject not in self._handlers:
            self._handlers[subject] = []
        
        self._handlers[subject].append(callback)
        
        # Create NATS message handler
        async def message_handler(msg: Msg) -> None:
            try:
                # Parse JSON payload
                payload = json.loads(msg.data.decode("utf-8"))
                
                # Extract tenant ID from headers if available
                msg_tenant_id = None
                if msg.headers and "tenant_id" in msg.headers:
                    msg_tenant_id = msg.headers["tenant_id"]
                
                # If tenant ID is provided, validate that message is from the same tenant
                if tenant_id and msg_tenant_id and tenant_id != msg_tenant_id:
                    logger.warning(f"Tenant mismatch: expected {tenant_id}, got {msg_tenant_id}")
                    return
                
                # Call all registered handlers
                handlers = []
                
                # Find handlers for this subject and wildcard subjects
                for sub_pattern, sub_handlers in self._handlers.items():
                    if self._subject_matches(sub_pattern, msg.subject):
                        handlers.extend(sub_handlers)
                
                # Execute all handlers
                for handler in handlers:
                    await handler(payload)
            
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON message: {msg.data}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
        
        # Subscribe to subject
        sub_id = await self.nats_client.subscribe(subject, queue_group, message_handler)
        self._subscriptions[subject] = sub_id
    
    async def unsubscribe(self, subject: str) -> None:
        """
        Unsubscribe from a subject.
        
        Args:
            subject: Subject to unsubscribe from
        """
        # Get subscription ID
        sub_id = self._subscriptions.get(subject)
        if sub_id is None:
            logger.warning(f"No subscription found for subject: {subject}")
            return
        
        # Unsubscribe
        await self.nats_client.unsubscribe(sub_id)
        
        # Remove subscription and handlers
        del self._subscriptions[subject]
        if subject in self._handlers:
            del self._handlers[subject]
    
    async def request(
        self,
        subject: str,
        request: Dict[str, Any],
        timeout: float = 2.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a request and wait for a response.
        
        Args:
            subject: Subject to send request to
            request: Request payload
            timeout: Timeout in seconds
            headers: Optional message headers
            
        Returns:
            Response payload
        """
        # Add message metadata
        message_id = str(uuid.uuid4())
        enriched_request = {
            **request,
            "meta": {
                "sender_id": self.service_id,
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        # Send request
        response = await self.nats_client.request(subject, enriched_request, timeout, headers)
        
        return response
    
    def create_channel_subject(self, tenant_id: str, channel_id: str) -> str:
        """
        Create a subject for a specific channel.
        
        Args:
            tenant_id: Tenant identifier
            channel_id: Channel identifier
            
        Returns:
            Full subject name
        """
        return f"tenants.{tenant_id}.channels.{channel_id}"
    
    def create_agent_subject(self, tenant_id: str, agent_id: str) -> str:
        """
        Create a subject for a specific agent.
        
        Args:
            tenant_id: Tenant identifier
            agent_id: Agent identifier
            
        Returns:
            Full subject name
        """
        return f"tenants.{tenant_id}.agents.{agent_id}"
    
    def create_tenant_subject(self, tenant_id: str) -> str:
        """
        Create a subject for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Full subject name
        """
        return f"tenants.{tenant_id}"
    
    async def send_to_channel(
        self,
        tenant_id: str,
        channel_id: str,
        message: Dict[str, Any],
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Send a message to a specific channel.
        
        Args:
            tenant_id: Tenant identifier
            channel_id: Channel identifier
            message: Message payload
            reply_to: Optional reply subject
            headers: Optional message headers
            
        Returns:
            Message ID
        """
        subject = self.create_channel_subject(tenant_id, channel_id)
        return await self.send_message(subject, message, reply_to, headers, tenant_id)
    
    async def send_to_agent(
        self,
        tenant_id: str,
        agent_id: str,
        message: Dict[str, Any],
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Send a message to a specific agent.
        
        Args:
            tenant_id: Tenant identifier
            agent_id: Agent identifier
            message: Message payload
            reply_to: Optional reply subject
            headers: Optional message headers
            
        Returns:
            Message ID
        """
        subject = self.create_agent_subject(tenant_id, agent_id)
        return await self.send_message(subject, message, reply_to, headers, tenant_id)
    
    async def subscribe_to_channel(
        self,
        tenant_id: str,
        channel_id: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        queue_group: Optional[str] = None
    ) -> None:
        """
        Subscribe to messages for a specific channel.
        
        Args:
            tenant_id: Tenant identifier
            channel_id: Channel identifier
            callback: Function to call when a message is received
            queue_group: Optional queue group for load balancing
        """
        subject = self.create_channel_subject(tenant_id, channel_id)
        await self.subscribe(subject, callback, queue_group, tenant_id)
    
    async def subscribe_to_agent(
        self,
        tenant_id: str,
        agent_id: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        queue_group: Optional[str] = None
    ) -> None:
        """
        Subscribe to messages for a specific agent.
        
        Args:
            tenant_id: Tenant identifier
            agent_id: Agent identifier
            callback: Function to call when a message is received
            queue_group: Optional queue group for load balancing
        """
        subject = self.create_agent_subject(tenant_id, agent_id)
        await self.subscribe(subject, callback, queue_group, tenant_id)
    
    async def subscribe_to_tenant(
        self,
        tenant_id: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        queue_group: Optional[str] = None
    ) -> None:
        """
        Subscribe to all messages for a specific tenant.
        
        Args:
            tenant_id: Tenant identifier
            callback: Function to call when a message is received
            queue_group: Optional queue group for load balancing
        """
        subject = f"tenants.{tenant_id}.>"
        await self.subscribe(subject, callback, queue_group, tenant_id)
    
    def _subject_matches(self, pattern: str, subject: str) -> bool:
        """
        Check if a subject matches a pattern.
        
        Args:
            pattern: Subject pattern with wildcards
            subject: Actual subject to check
            
        Returns:
            True if the subject matches the pattern, False otherwise
        """
        if pattern == subject:
            return True
        
        # Split pattern and subject into parts
        pattern_parts = pattern.split('.')
        subject_parts = subject.split('.')
        
        # Process pattern parts
        for i, pattern_part in enumerate(pattern_parts):
            # > wildcard matches the rest of the subject
            if pattern_part == '>':
                return True
            
            # * wildcard matches exactly one part
            if pattern_part == '*':
                if i >= len(subject_parts):
                    return False
                continue
            
            # Exact match required
            if i >= len(subject_parts) or pattern_part != subject_parts[i]:
                return False
        
        # If pattern has same number of parts as subject, it's a match
        return len(pattern_parts) == len(subject_parts)
    
    # New methods for AgentMessage protocol
    
    async def send_agent_message(
        self,
        message: AgentMessage,
        subject: Optional[str] = None
    ) -> str:
        """
        Send an agent message using the standardized protocol.
        
        Args:
            message: AgentMessage instance
            subject: Optional subject override. If not provided, will be generated from message
            
        Returns:
            Message ID
        """
        # Determine subject based on message
        if not subject:
            subject = message.to_subject(message.source.tenant_id)
        
        # Validate tenant permissions
        tenant_id = message.source.tenant_id
        nats_auth.validate_publish(tenant_id, subject)
        
        # Prepare headers
        headers = {
            "tenant_id": tenant_id,
            "message_type": message.type.value,
            "source_agent": message.source.id
        }
        
        if message.correlation_id:
            headers["correlation_id"] = message.correlation_id
        
        # Convert to dict for transmission
        message_dict = message.dict()
        
        # Publish message
        await self.nats_client.publish(
            subject,
            message_dict,
            reply_to=message.reply_to,
            headers=headers
        )
        
        logger.info(f"Sent {message.type.value} message {message.id} to {subject}")
        
        return message.id
    
    async def subscribe_agent_message(
        self,
        subject: str,
        callback: Callable[[AgentMessage], Awaitable[None]],
        tenant_id: str,
        queue_group: Optional[str] = None
    ) -> None:
        """
        Subscribe to agent messages with automatic deserialization.
        
        Args:
            subject: Subject pattern to subscribe to
            callback: Function to call with AgentMessage instances
            tenant_id: Tenant ID for authorization
            queue_group: Optional queue group for load balancing
        """
        # Validate permissions
        nats_auth.validate_subscribe(tenant_id, subject)
        
        # Create wrapper to deserialize messages
        async def agent_message_handler(msg: Msg) -> None:
            try:
                # Parse JSON payload
                payload_str = msg.data.decode("utf-8")
                payload_dict = json.loads(payload_str)
                
                # Create AgentMessage instance
                agent_msg = AgentMessage(**payload_dict)
                
                # Verify tenant ID matches
                if agent_msg.source.tenant_id != tenant_id:
                    logger.warning(f"Tenant mismatch: expected {tenant_id}, got {agent_msg.source.tenant_id}")
                    return
                
                # Call user callback
                await callback(agent_msg)
                
            except Exception as e:
                logger.error(f"Error processing agent message: {e}")
        
        # Subscribe with wrapper
        sub_id = await self.nats_client.subscribe(subject, queue_group, agent_message_handler)
        self._subscriptions[subject] = sub_id
        
        logger.info(f"Subscribed to {subject} for tenant {tenant_id}")
    
    async def request_agent_message(
        self,
        message: AgentMessage,
        timeout: float = 5.0
    ) -> AgentMessage:
        """
        Send an agent message and wait for a response.
        
        Args:
            message: AgentMessage to send
            timeout: Timeout in seconds
            
        Returns:
            Response AgentMessage
        """
        # Generate subject
        subject = message.to_subject(message.source.tenant_id)
        
        # Validate permissions
        nats_auth.validate_publish(message.source.tenant_id, subject)
        
        # Convert to dict
        message_dict = message.dict()
        
        # Send request
        headers = {"tenant_id": message.source.tenant_id}
        response_dict = await self.nats_client.request(
            subject, 
            message_dict, 
            timeout, 
            headers
        )
        
        # Parse response
        response = AgentMessage(**response_dict)
        
        return response
    
    async def broadcast_capability_announcement(
        self,
        tenant_id: str,
        agent_id: str,
        capabilities: List[AgentCapability],
        status: str = "online"
    ) -> str:
        """
        Broadcast agent capabilities for discovery.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            capabilities: List of agent capabilities
            status: Agent status
            
        Returns:
            Message ID
        """
        announcement = AgentAnnouncement(
            agent_id=agent_id,
            tenant_id=tenant_id,
            capabilities=capabilities,
            status=status,
            metadata={
                "hostname": self.service_id,
                "version": "1.0"
            }
        )
        
        message = AgentMessage(
            type=MessageType.EVENT,
            source=AgentIdentity(
                id=agent_id,
                tenant_id=tenant_id,
                capabilities=[cap.name for cap in capabilities]
            ),
            context=MessageContext(
                conversation_id="system",
                metadata={"event_type": "capability_announcement"}
            ),
            payload=MessagePayload(
                content={
                    "event": "agent_online",
                    "announcement": announcement.dict()
                }
            ),
            routing=MessageRouting(priority=7)
        )
        
        # Publish to discovery topic
        return await self.send_agent_message(
            message,
            f"agents.{tenant_id}.event.status.online"
        )
    
    async def discover_agents_by_capability(
        self,
        tenant_id: str,
        required_capabilities: List[str],
        timeout: float = 2.0
    ) -> List[AgentAnnouncement]:
        """
        Discover agents with specific capabilities.
        
        Args:
            tenant_id: Tenant ID
            required_capabilities: List of required capability names
            timeout: Discovery timeout in seconds
            
        Returns:
            List of agent announcements
        """
        discovery_id = str(uuid.uuid4())
        responses = []
        
        # Create discovery request
        message = AgentMessage(
            type=MessageType.QUERY,
            source=AgentIdentity(
                id="system",
                type="system",
                tenant_id=tenant_id
            ),
            reply_to=f"agents.{tenant_id}.discovery.responses.{discovery_id}",
            context=MessageContext(
                conversation_id=discovery_id,
                metadata={"query_type": "capability_discovery"}
            ),
            payload=MessagePayload(
                content={
                    "query": "discover_agents",
                    "required_capabilities": required_capabilities
                }
            ),
            routing=MessageRouting(
                priority=8,
                timeout=int(timeout * 1000)
            )
        )
        
        # Subscribe to responses
        response_subject = f"agents.{tenant_id}.discovery.responses.{discovery_id}"
        
        async def collect_response(msg: AgentMessage) -> None:
            if msg.type == MessageType.RESULT and msg.correlation_id == message.id:
                announcement_data = msg.payload.content.get("announcement")
                if announcement_data:
                    responses.append(AgentAnnouncement(**announcement_data))
        
        # Temporary subscription
        await self.subscribe_agent_message(
            response_subject,
            collect_response,
            tenant_id
        )
        
        # Send discovery request
        await self.send_agent_message(
            message,
            f"agents.{tenant_id}.discovery.requests"
        )
        
        # Wait for responses
        await asyncio.sleep(timeout)
        
        # Cleanup subscription
        await self.unsubscribe(response_subject)
        
        # Filter agents that have all required capabilities
        filtered_responses = []
        for announcement in responses:
            agent_caps = [cap.name for cap in announcement.capabilities]
            if all(req_cap in agent_caps for req_cap in required_capabilities):
                filtered_responses.append(announcement)
        
        return filtered_responses
    
    async def stream_response(
        self,
        original_message: AgentMessage,
        content_generator: AsyncIterator[Any],
        source: AgentIdentity
    ) -> None:
        """
        Stream a response in chunks.
        
        Args:
            original_message: The message being responded to
            content_generator: Async generator yielding content chunks
            source: Identity of the responding agent
        """
        sequence = 0
        stream_id = str(uuid.uuid4())
        
        async for chunk in content_generator:
            stream_msg = AgentMessage(
                type=MessageType.STREAM,
                source=source,
                correlation_id=original_message.id,
                context=original_message.context,
                payload=MessagePayload(content=chunk),
                routing=MessageRouting(priority=original_message.routing.priority),
                stream_metadata=StreamMetadata(
                    sequence_number=sequence,
                    is_first=(sequence == 0),
                    is_final=False
                )
            )
            
            await self.send_agent_message(
                stream_msg,
                f"agents.{source.tenant_id}.stream.response.{stream_id}"
            )
            sequence += 1
        
        # Send final message
        final_msg = AgentMessage(
            type=MessageType.STREAM,
            source=source,
            correlation_id=original_message.id,
            context=original_message.context,
            payload=MessagePayload(content={"status": "completed"}),
            routing=MessageRouting(priority=original_message.routing.priority),
            stream_metadata=StreamMetadata(
                sequence_number=sequence,
                is_first=False,
                is_final=True,
                total_expected=sequence + 1
            )
        )
        
        await self.send_agent_message(
            final_msg,
            f"agents.{source.tenant_id}.stream.response.{stream_id}"
        )