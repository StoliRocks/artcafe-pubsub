import logging
import ulid
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models import Agent, AgentCreate, AgentUpdate
from nats_client import nats_manager, subjects
from .limits_service import limits_service
from utils.ssh_key_generator import ssh_key_generator

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent management"""
    
    async def list_agents(self, tenant_id: str, 
                        status: Optional[str] = None, 
                        limit: int = 50, 
                        next_token: Optional[str] = None) -> Dict:
        """
        List agents for a tenant
        
        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            limit: Maximum number of results
            next_token: Pagination token
            
        Returns:
            Dictionary with agents and pagination token
        """
        try:
            # Query agents from DynamoDB
            filter_parts = ["tenant_id = :tenant_id"]
            expression_values = {":tenant_id": tenant_id}
            
            # Add optional filters
            if status:
                filter_parts.append("status = :status")
                expression_values[":status"] = status
                
            filter_expression = " AND ".join(filter_parts)
            
            # Query DynamoDB
            result = await dynamodb.scan_items(
                table_name=settings.AGENT_TABLE_NAME,
                filter_expression=filter_expression,
                expression_values=expression_values,
                limit=limit,
                next_token=next_token
            )
            
            # Convert to Agent models
            agents = [Agent(**item) for item in result["items"]]
            
            # Publish event to NATS
            await self._publish_agent_list_event(tenant_id, len(agents))
            
            return {
                "agents": agents,
                "next_token": result["next_token"]
            }
        except Exception as e:
            logger.error(f"Error listing agents for tenant {tenant_id}: {e}")
            raise
    
    async def get_agent(self, tenant_id: str, agent_id: str) -> Optional[Agent]:
        """
        Get agent by ID
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            
        Returns:
            Agent or None if not found
        """
        try:
            # Get agent from DynamoDB
            item = await dynamodb.get_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id}
            )
            
            if not item:
                return None
                
            # Convert to Agent model
            agent = Agent(**item)
            
            # Publish event to NATS
            await self._publish_agent_get_event(tenant_id, agent_id)
            
            return agent
        except Exception as e:
            logger.error(f"Error getting agent {agent_id} for tenant {tenant_id}: {e}")
            raise
            
    async def create_agent(self, tenant_id: str, agent_data: AgentCreate) -> Tuple[Agent, Optional[str]]:
        """
        Create a new agent with SSH keypair
        
        Args:
            tenant_id: Tenant ID
            agent_data: Agent data
            
        Returns:
            Tuple of (Created agent, private key) - private key is None if not generated
        """
        logger.error(f"DEBUG: create_agent called for tenant {tenant_id}")
        try:
            # Check usage limits
            current_count = len((await self.list_agents(tenant_id))["agents"])
            await limits_service.enforce_limit(tenant_id, "agents", current_count)
            
            # Generate agent ID
            agent_id = str(ulid.ULID())
            
            # Prepare agent data
            agent_dict = agent_data.dict()
            agent_dict["id"] = agent_id
            agent_dict["tenant_id"] = tenant_id
            agent_dict["status"] = "offline"  # Initial status is always offline
            agent_dict["last_seen"] = datetime.utcnow().isoformat()
            
            # Initialize capabilities if not provided
            if "capabilities" not in agent_dict:
                agent_dict["capabilities"] = []
            
            # Initialize performance metrics
            agent_dict["average_response_time_ms"] = None
            agent_dict["success_rate"] = None
            agent_dict["max_concurrent_tasks"] = 5
            
            # Generate SSH keypair if no public key was provided
            private_key = None
            logger.error(f"DEBUG: Starting SSH key generation check for agent {agent_id}")
            logger.error(f"DEBUG: Public key value: {agent_dict.get('public_key')}")
            if not agent_dict.get("public_key"):
                logger.error(f"DEBUG: No public key provided, will generate SSH keypair for agent {agent_id}")
                try:
                    private_key, public_key = ssh_key_generator.generate_agent_keypair(
                        agent_data.name,
                        tenant_id
                    )
                    logger.info(f"Generated keypair for agent {agent_id}")
                    agent_dict["public_key"] = public_key
                    
                    # Generate fingerprint for the public key
                    key_bytes = public_key.encode('utf-8')
                    fingerprint = hashlib.sha256(key_bytes).hexdigest()
                    agent_dict["key_fingerprint"] = fingerprint
                    logger.info(f"SSH keypair generated successfully for agent {agent_id}")
                except Exception as e:
                    logger.error(f"Error generating SSH keypair for agent {agent_id}: {e}")
                    # Continue without SSH key
            else:
                logger.info(f"Public key already provided for agent {agent_id}")
            
            # Store in DynamoDB
            item = await dynamodb.put_item(
                table_name=settings.AGENT_TABLE_NAME,
                item=agent_dict
            )
            
            # Convert to Agent model
            agent = Agent(**item)
            
            # Update usage metrics
            await limits_service.track_usage(tenant_id, "agent_count", 1)
            
            # Publish event to NATS
            await self._publish_agent_create_event(tenant_id, agent)
            
            return agent, private_key
        except Exception as e:
            logger.error(f"Error creating agent for tenant {tenant_id}: {e}")
            raise
            
    async def update_agent(self, tenant_id: str, agent_id: str, 
                         agent_data: AgentUpdate) -> Optional[Agent]:
        """
        Update an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            agent_data: Agent update data
            
        Returns:
            Updated agent or None if not found
        """
        try:
            # Check if agent exists
            existing_agent = await self.get_agent(tenant_id, agent_id)
            if not existing_agent:
                return None
                
            # Prepare update data
            update_data = {k: v for k, v in agent_data.dict().items() if v is not None}
            update_data["last_seen"] = datetime.utcnow().isoformat()
            
            # Update agent in DynamoDB
            updated_item = await dynamodb.update_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id},
                updates=update_data
            )
            
            # Convert to Agent model
            updated_agent = Agent(**updated_item)
            
            # Publish event to NATS
            await self._publish_agent_update_event(tenant_id, updated_agent)
            
            return updated_agent
        except Exception as e:
            logger.error(f"Error updating agent {agent_id} for tenant {tenant_id}: {e}")
            raise
            
    async def delete_agent(self, tenant_id: str, agent_id: str) -> bool:
        """
        Delete an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Check if agent exists
            existing_agent = await self.get_agent(tenant_id, agent_id)
            if not existing_agent:
                return False
                
            # Delete associated SSH keys
            await self._delete_agent_ssh_keys(tenant_id, agent_id)
                
            # Delete from DynamoDB
            await dynamodb.delete_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id}
            )
            
            # Update usage metrics
            await limits_service.track_usage(tenant_id, "agent_count", -1)
            
            # Publish event to NATS
            await self._publish_agent_delete_event(tenant_id, agent_id)
            
            return True
        except Exception as e:
            logger.error(f"Error deleting agent {agent_id} for tenant {tenant_id}: {e}")
            raise
    
    async def update_agent_capabilities(
        self, 
        tenant_id: str, 
        agent_id: str, 
        capabilities: List[str],
        capability_definitions: Optional[List[Dict]] = None
    ) -> Optional[Agent]:
        """
        Update agent capabilities
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            capabilities: List of capability names
            capability_definitions: Optional full capability definitions
            
        Returns:
            Updated agent or None if not found
        """
        try:
            # Check if agent exists
            existing_agent = await self.get_agent(tenant_id, agent_id)
            if not existing_agent:
                return None
            
            # Prepare update data
            update_data = {
                "capabilities": capabilities,
                "last_seen": datetime.utcnow().isoformat()
            }
            
            if capability_definitions:
                update_data["capability_definitions"] = capability_definitions
            
            # Update agent in DynamoDB
            updated_item = await dynamodb.update_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id},
                updates=update_data
            )
            
            # Convert to Agent model
            updated_agent = Agent(**updated_item)
            
            # Publish capability update event
            await self._publish_agent_capability_update_event(tenant_id, agent_id, capabilities)
            
            return updated_agent
            
        except Exception as e:
            logger.error(f"Error updating capabilities for agent {agent_id}: {e}")
            raise
    
    async def get_agents_by_capability(
        self, 
        tenant_id: str, 
        capability: str,
        status: Optional[str] = "online"
    ) -> List[Agent]:
        """
        Get agents with a specific capability
        
        Args:
            tenant_id: Tenant ID
            capability: Capability name
            status: Optional status filter (default: online)
            
        Returns:
            List of agents with the capability
        """
        try:
            # Query agents
            filter_parts = ["tenant_id = :tenant_id", "contains(capabilities, :capability)"]
            expression_values = {
                ":tenant_id": tenant_id,
                ":capability": capability
            }
            
            if status:
                filter_parts.append("status = :status")
                expression_values[":status"] = status
            
            filter_expression = " AND ".join(filter_parts)
            
            # Query DynamoDB
            result = await dynamodb.scan_items(
                table_name=settings.AGENT_TABLE_NAME,
                filter_expression=filter_expression,
                expression_values=expression_values
            )
            
            # Convert to Agent models
            agents = [Agent(**item) for item in result["items"]]
            
            return agents
            
        except Exception as e:
            logger.error(f"Error getting agents by capability {capability}: {e}")
            raise
    
    async def update_agent_performance_metrics(
        self,
        tenant_id: str,
        agent_id: str,
        response_time_ms: float,
        success: bool
    ) -> None:
        """
        Update agent performance metrics
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            response_time_ms: Response time in milliseconds
            success: Whether the task was successful
        """
        try:
            # Get current agent
            agent = await self.get_agent(tenant_id, agent_id)
            if not agent:
                return
            
            # Calculate new metrics
            current_avg = agent.average_response_time_ms or response_time_ms
            current_success_rate = agent.success_rate or (100.0 if success else 0.0)
            
            # Simple moving average (last 10 samples)
            new_avg = (current_avg * 0.9) + (response_time_ms * 0.1)
            new_success_rate = (current_success_rate * 0.9) + ((100.0 if success else 0.0) * 0.1)
            
            # Update metrics
            await dynamodb.update_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id},
                updates={
                    "average_response_time_ms": new_avg,
                    "success_rate": new_success_rate,
                    "total_messages_sent": (agent.total_messages_sent or 0) + 1
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating performance metrics for agent {agent_id}: {e}")
            # Don't raise - metrics are not critical
    
    async def _publish_agent_capability_update_event(
        self, 
        tenant_id: str, 
        agent_id: str, 
        capabilities: List[str]
    ) -> None:
        """Publish agent capability update event to NATS"""
        try:
            event = {
                "event": "agent_capability_update",
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "capabilities": capabilities,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            subject = subjects.get_agent_event_subject(tenant_id, "capability", "update")
            await nats_manager.publish(subject, event)
            
        except Exception as e:
            logger.error(f"Error publishing capability update event: {e}")
            
    async def update_agent_status(self, tenant_id: str, agent_id: str, 
                                status: str) -> Optional[Agent]:
        """
        Update agent status (automatically done by connection state)
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            status: Agent status (online, offline, error)
            
        Returns:
            Updated agent or None if not found
        """
        try:
            # Check if agent exists
            existing_agent = await self.get_agent(tenant_id, agent_id)
            if not existing_agent:
                return None
                
            # Update status in DynamoDB
            updated_item = await dynamodb.update_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id},
                updates={
                    "status": status,
                    "last_seen": datetime.utcnow().isoformat()
                }
            )
            
            # Convert to Agent model
            updated_agent = Agent(**updated_item)
            
            # Publish event to NATS
            await self._publish_agent_status_event(tenant_id, agent_id, status)
            
            return updated_agent
        except Exception as e:
            logger.error(f"Error updating agent status for {agent_id}: {e}")
            raise
    
    async def _delete_agent_ssh_keys(self, tenant_id: str, agent_id: str) -> None:
        """
        Delete all SSH keys associated with an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
        """
        try:
            # Query SSH keys for this agent
            filter_expression = "tenant_id = :tenant_id AND agent_id = :agent_id"
            expression_values = {
                ":tenant_id": tenant_id,
                ":agent_id": agent_id
            }
            
            # Scan for all SSH keys belonging to this agent
            result = await dynamodb.scan_items(
                table_name=settings.SSH_KEY_TABLE_NAME,
                filter_expression=filter_expression,
                expression_values=expression_values
            )
            
            # Delete each SSH key
            for key_item in result.get("items", []):
                key_id = key_item.get("id")
                if key_id:
                    await dynamodb.delete_item(
                        table_name=settings.SSH_KEY_TABLE_NAME,
                        key={"tenant_id": tenant_id, "id": key_id}
                    )
                    logger.info(f"Deleted SSH key {key_id} for agent {agent_id}")
                    
            logger.info(f"Deleted {len(result.get('items', []))} SSH keys for agent {agent_id}")
            
        except Exception as e:
            logger.error(f"Error deleting SSH keys for agent {agent_id}: {e}")
            # Don't raise - we still want to delete the agent even if SSH key cleanup fails
            
    # NATS event publishing methods
    async def _publish_agent_create_event(self, tenant_id: str, agent: Agent):
        """Publish agent create event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_CREATE),
                data={
                    "event": "agent.created",
                    "tenant_id": tenant_id,
                    "agent_id": agent.agent_id,
                    "data": agent.dict()
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent create event: {e}")
            
    async def _publish_agent_update_event(self, tenant_id: str, agent: Agent):
        """Publish agent update event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_UPDATE),
                data={
                    "event": "agent.updated",
                    "tenant_id": tenant_id,
                    "agent_id": agent.agent_id,
                    "data": agent.dict()
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent update event: {e}")
            
    async def _publish_agent_delete_event(self, tenant_id: str, agent_id: str):
        """Publish agent delete event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_DELETE),
                data={
                    "event": "agent.deleted",
                    "tenant_id": tenant_id,
                    "agent_id": agent_id
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent delete event: {e}")
            
    async def _publish_agent_status_event(self, tenant_id: str, agent_id: str, status: str):
        """Publish agent status event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_STATUS),
                data={
                    "event": "agent.status_changed",
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "status": status
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent status event: {e}")
            
    async def _publish_agent_list_event(self, tenant_id: str, count: int):
        """Publish agent list event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_LIST),
                data={
                    "event": "agent.list",
                    "tenant_id": tenant_id,
                    "count": count
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent list event: {e}")
            
    async def _publish_agent_get_event(self, tenant_id: str, agent_id: str):
        """Publish agent get event to NATS"""
        try:
            await nats_manager.publish(
                subject=subjects.get_tenant_subject(tenant_id, subjects.AGENTS_EVENTS_GET),
                data={
                    "event": "agent.get",
                    "tenant_id": tenant_id,
                    "agent_id": agent_id
                }
            )
        except Exception as e:
            logger.error(f"Error publishing agent get event: {e}")


# Create a singleton instance
agent_service = AgentService()