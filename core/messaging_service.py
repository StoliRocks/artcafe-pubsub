import json
import logging
import uuid
import asyncio
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable
from datetime import datetime

from nats.msg import Msg
from nats.errors import AuthError
from core.nats_client import NATSClient
from core.nats_auth import nats_auth

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