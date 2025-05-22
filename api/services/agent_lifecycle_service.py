"""
Agent lifecycle service for managing agent state transitions, announcements, and discovery.

This service handles:
- Agent online/offline announcements
- Capability discovery
- Heartbeat management
- Agent state transitions
"""

import logging
import asyncio
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from models.agent_message import (
    AgentMessage, MessageType, AgentIdentity,
    MessageContext, MessagePayload, MessageRouting,
    AgentCapability, AgentAnnouncement
)
from models.agent import Agent, AgentCapabilityDefinition
from core.messaging_service import MessagingService
from api.services.agent_service import agent_service
from nats_client import subjects

logger = logging.getLogger(__name__)


class AgentLifecycleService:
    """Service for managing agent lifecycle events and discovery"""
    
    def __init__(self, messaging_service: MessagingService):
        """
        Initialize agent lifecycle service.
        
        Args:
            messaging_service: Messaging service instance
        """
        self.messaging_service = messaging_service
        self._discovery_handlers = {}
        self._heartbeat_tasks = {}
        
    async def announce_agent_online(
        self,
        tenant_id: str,
        agent_id: str,
        capabilities: List[str],
        capability_definitions: Optional[List[AgentCapabilityDefinition]] = None
    ) -> str:
        """
        Announce agent coming online with capabilities.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            capabilities: List of capability names
            capability_definitions: Optional full capability definitions
            
        Returns:
            Message ID
        """
        # Convert capability definitions if provided
        cap_defs = []
        if capability_definitions:
            cap_defs = [
                AgentCapability(
                    name=cap.name,
                    version=cap.version,
                    description=cap.description,
                    parameters=cap.parameters,
                    models=cap.models,
                    max_concurrent=cap.max_concurrent,
                    average_duration_ms=cap.average_duration_ms
                )
                for cap in capability_definitions
            ]
        else:
            # Create basic capabilities from names
            cap_defs = [
                AgentCapability(name=cap_name)
                for cap_name in capabilities
            ]
        
        # Create announcement
        announcement = AgentAnnouncement(
            agent_id=agent_id,
            tenant_id=tenant_id,
            capabilities=cap_defs,
            status="online",
            metadata={
                "service_id": self.messaging_service.service_id,
                "version": "1.0",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Create message
        message = AgentMessage(
            type=MessageType.EVENT,
            source=AgentIdentity(
                id=agent_id,
                tenant_id=tenant_id,
                capabilities=capabilities
            ),
            context=MessageContext(
                conversation_id="system",
                metadata={"event_type": "agent_online"}
            ),
            payload=MessagePayload(
                content={
                    "event": "agent_online",
                    "announcement": announcement.dict()
                }
            ),
            routing=MessageRouting(priority=7)
        )
        
        # Update agent status in database
        await agent_service.update_agent_status(tenant_id, agent_id, "online")
        
        # Publish announcement
        subject = subjects.get_agent_event_subject(tenant_id, "status", "online")
        message_id = await self.messaging_service.send_agent_message(message, subject)
        
        logger.info(f"Agent {agent_id} announced online with capabilities: {capabilities}")
        
        return message_id
    
    async def announce_agent_offline(
        self,
        tenant_id: str,
        agent_id: str
    ) -> str:
        """
        Announce agent going offline.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            
        Returns:
            Message ID
        """
        # Get agent details
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            logger.warning(f"Agent {agent_id} not found for offline announcement")
            capabilities = []
        else:
            capabilities = agent.capabilities or []
        
        # Create message
        message = AgentMessage(
            type=MessageType.EVENT,
            source=AgentIdentity(
                id=agent_id,
                tenant_id=tenant_id,
                capabilities=capabilities
            ),
            context=MessageContext(
                conversation_id="system",
                metadata={"event_type": "agent_offline"}
            ),
            payload=MessagePayload(
                content={
                    "event": "agent_offline",
                    "timestamp": datetime.utcnow().isoformat()
                }
            ),
            routing=MessageRouting(priority=7)
        )
        
        # Update agent status in database
        await agent_service.update_agent_status(tenant_id, agent_id, "offline")
        
        # Cancel heartbeat task if exists
        if agent_id in self._heartbeat_tasks:
            self._heartbeat_tasks[agent_id].cancel()
            del self._heartbeat_tasks[agent_id]
        
        # Publish announcement
        subject = subjects.get_agent_event_subject(tenant_id, "status", "offline")
        message_id = await self.messaging_service.send_agent_message(message, subject)
        
        logger.info(f"Agent {agent_id} announced offline")
        
        return message_id
    
    async def handle_agent_heartbeat(
        self,
        tenant_id: str,
        agent_id: str,
        heartbeat_data: Dict[str, Any]
    ) -> None:
        """
        Handle agent heartbeat.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            heartbeat_data: Heartbeat data including status, metrics, etc.
        """
        # Update last seen timestamp
        await agent_service.update_agent_status(
            tenant_id, 
            agent_id, 
            heartbeat_data.get("status", "online")
        )
        
        # Update performance metrics if provided
        if "metrics" in heartbeat_data:
            metrics = heartbeat_data["metrics"]
            # TODO: Update agent performance metrics in database
            
        logger.debug(f"Heartbeat received from agent {agent_id}")
    
    async def discover_agents(
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
            reply_to=subjects.get_agent_discovery_response_subject(tenant_id, discovery_id),
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
        response_subject = subjects.get_agent_discovery_response_subject(tenant_id, discovery_id)
        
        async def collect_response(msg: AgentMessage) -> None:
            if msg.type == MessageType.RESULT and msg.correlation_id == message.id:
                announcement_data = msg.payload.content.get("announcement")
                if announcement_data:
                    responses.append(AgentAnnouncement(**announcement_data))
        
        # Temporary subscription
        await self.messaging_service.subscribe_agent_message(
            response_subject,
            collect_response,
            tenant_id
        )
        
        # Send discovery request
        request_subject = subjects.get_agent_discovery_request_subject(tenant_id)
        await self.messaging_service.send_agent_message(message, request_subject)
        
        # Wait for responses
        await asyncio.sleep(timeout)
        
        # Cleanup subscription
        await self.messaging_service.unsubscribe(response_subject)
        
        # Filter agents that have all required capabilities
        filtered_responses = []
        for announcement in responses:
            agent_caps = [cap.name for cap in announcement.capabilities]
            if all(req_cap in agent_caps for req_cap in required_capabilities):
                filtered_responses.append(announcement)
        
        logger.info(f"Discovered {len(filtered_responses)} agents with capabilities: {required_capabilities}")
        
        return filtered_responses
    
    async def setup_discovery_handler(
        self,
        tenant_id: str,
        agent_id: str,
        agent: Agent
    ) -> None:
        """
        Setup discovery request handler for an agent.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            agent: Agent instance
        """
        async def handle_discovery_request(msg: AgentMessage) -> None:
            """Handle incoming discovery requests"""
            if msg.type != MessageType.QUERY:
                return
                
            query_content = msg.payload.content
            if query_content.get("query") != "discover_agents":
                return
                
            required_capabilities = query_content.get("required_capabilities", [])
            agent_capabilities = agent.capabilities or []
            
            # Check if agent has all required capabilities
            if all(cap in agent_capabilities for cap in required_capabilities):
                # Create announcement
                cap_defs = []
                if agent.capability_definitions:
                    cap_defs = [
                        AgentCapability(
                            name=cap.name,
                            version=cap.version,
                            description=cap.description,
                            parameters=cap.parameters,
                            models=cap.models,
                            max_concurrent=cap.max_concurrent,
                            average_duration_ms=cap.average_duration_ms
                        )
                        for cap in agent.capability_definitions
                    ]
                else:
                    cap_defs = [
                        AgentCapability(name=cap_name)
                        for cap_name in agent_capabilities
                    ]
                
                announcement = AgentAnnouncement(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    capabilities=cap_defs,
                    status=agent.status,
                    metadata={
                        "last_seen": agent.last_seen.isoformat(),
                        "success_rate": agent.success_rate,
                        "average_response_time_ms": agent.average_response_time_ms
                    }
                )
                
                # Create response
                response = msg.create_response(
                    content={"announcement": announcement.dict()},
                    success=True,
                    source=AgentIdentity(
                        id=agent_id,
                        tenant_id=tenant_id,
                        capabilities=agent_capabilities
                    )
                )
                
                # Send response to reply_to if specified
                if msg.reply_to:
                    await self.messaging_service.send_agent_message(response, msg.reply_to)
        
        # Subscribe to discovery requests
        discovery_subject = subjects.get_agent_discovery_request_subject(tenant_id)
        await self.messaging_service.subscribe_agent_message(
            discovery_subject,
            handle_discovery_request,
            tenant_id
        )
        
        # Store handler reference
        self._discovery_handlers[agent_id] = handle_discovery_request
        
        logger.info(f"Setup discovery handler for agent {agent_id}")
    
    async def cleanup_discovery_handler(
        self,
        tenant_id: str,
        agent_id: str
    ) -> None:
        """
        Cleanup discovery handler for an agent.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
        """
        if agent_id in self._discovery_handlers:
            discovery_subject = subjects.get_agent_discovery_request_subject(tenant_id)
            await self.messaging_service.unsubscribe(discovery_subject)
            del self._discovery_handlers[agent_id]
            logger.info(f"Cleaned up discovery handler for agent {agent_id}")
    
    async def start_heartbeat_monitor(
        self,
        tenant_id: str,
        agent_id: str,
        timeout: int = 60
    ) -> None:
        """
        Start monitoring heartbeats for an agent.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            timeout: Heartbeat timeout in seconds
        """
        async def monitor_heartbeat():
            """Monitor agent heartbeat and mark offline if timeout"""
            while True:
                try:
                    await asyncio.sleep(timeout)
                    
                    # Check last seen time
                    agent = await agent_service.get_agent(tenant_id, agent_id)
                    if agent:
                        time_since_last_seen = datetime.utcnow() - agent.last_seen
                        if time_since_last_seen > timedelta(seconds=timeout):
                            logger.warning(f"Agent {agent_id} heartbeat timeout")
                            await self.announce_agent_offline(tenant_id, agent_id)
                            break
                            
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error monitoring heartbeat for agent {agent_id}: {e}")
                    break
        
        # Cancel existing task if any
        if agent_id in self._heartbeat_tasks:
            self._heartbeat_tasks[agent_id].cancel()
        
        # Start new monitoring task
        task = asyncio.create_task(monitor_heartbeat())
        self._heartbeat_tasks[agent_id] = task
        
        logger.info(f"Started heartbeat monitor for agent {agent_id}")


# Global instance
agent_lifecycle_service = None

def get_agent_lifecycle_service(messaging_service: MessagingService) -> AgentLifecycleService:
    """Get or create agent lifecycle service instance"""
    global agent_lifecycle_service
    if agent_lifecycle_service is None:
        agent_lifecycle_service = AgentLifecycleService(messaging_service)
    return agent_lifecycle_service