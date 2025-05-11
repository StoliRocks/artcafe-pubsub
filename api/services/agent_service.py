import logging
import ulid
from typing import Dict, List, Optional
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models import Agent, AgentCreate, AgentUpdate
from nats import nats_manager, subjects

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent management"""
    
    async def list_agents(self, tenant_id: str, 
                        status: Optional[str] = None, 
                        agent_type: Optional[str] = None,
                        limit: int = 50, 
                        next_token: Optional[str] = None) -> Dict:
        """
        List agents for a tenant
        
        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            agent_type: Optional agent type filter
            limit: Maximum number of results
            next_token: Pagination token
            
        Returns:
            Dictionary with agents and pagination token
        """
        try:
            # Query agents from DynamoDB
            filter_expression = None
            expression_values = {":tenant_id": tenant_id}
            
            # Add optional filters
            if status or agent_type:
                filter_parts = []
                
                if status:
                    filter_parts.append("status = :status")
                    expression_values[":status"] = status
                    
                if agent_type:
                    filter_parts.append("#type = :type")
                    expression_values[':type'] = agent_type
                    
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
            
    async def create_agent(self, tenant_id: str, agent_data: AgentCreate) -> Agent:
        """
        Create a new agent
        
        Args:
            tenant_id: Tenant ID
            agent_data: Agent data
            
        Returns:
            Created agent
        """
        try:
            # Generate agent ID
            agent_id = str(ulid.new())
            
            # Prepare agent data
            agent_dict = agent_data.dict()
            agent_dict["id"] = agent_id
            agent_dict["tenant_id"] = tenant_id
            agent_dict["last_seen"] = datetime.utcnow().isoformat()
            
            # Store in DynamoDB
            item = await dynamodb.put_item(
                table_name=settings.AGENT_TABLE_NAME,
                item=agent_dict
            )
            
            # Convert to Agent model
            agent = Agent(**item)
            
            # Publish event to NATS
            await self._publish_agent_create_event(tenant_id, agent)
            
            return agent
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
            
    async def update_agent_status(self, tenant_id: str, agent_id: str, status: str) -> Optional[Agent]:
        """
        Update agent status
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            status: New status
            
        Returns:
            Updated agent or None if not found
        """
        return await self.update_agent(
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_data=AgentUpdate(status=status)
        )
        
    async def delete_agent(self, tenant_id: str, agent_id: str) -> bool:
        """
        Delete an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            
        Returns:
            True if agent was deleted
        """
        try:
            # Check if agent exists
            existing_agent = await self.get_agent(tenant_id, agent_id)
            if not existing_agent:
                return False
                
            # Delete agent from DynamoDB
            result = await dynamodb.delete_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id}
            )
            
            # Publish event to NATS
            if result:
                await self._publish_agent_delete_event(tenant_id, agent_id)
                
            return result
        except Exception as e:
            logger.error(f"Error deleting agent {agent_id} for tenant {tenant_id}: {e}")
            raise
            
    # NATS event publishing methods
    
    async def _publish_agent_list_event(self, tenant_id: str, count: int) -> None:
        """Publish agent list event to NATS"""
        try:
            subject = subjects.get_agents_subject(tenant_id)
            payload = {
                "event": "list_agents",
                "tenant_id": tenant_id,
                "count": count,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing agent list event: {e}")
    
    async def _publish_agent_get_event(self, tenant_id: str, agent_id: str) -> None:
        """Publish agent get event to NATS"""
        try:
            subject = subjects.get_agent_subject(tenant_id, agent_id)
            payload = {
                "event": "get_agent",
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing agent get event: {e}")
            
    async def _publish_agent_create_event(self, tenant_id: str, agent: Agent) -> None:
        """Publish agent create event to NATS"""
        try:
            subject = subjects.get_agent_subject(tenant_id, agent.agent_id)
            payload = {
                "event": "create_agent",
                "tenant_id": tenant_id,
                "agent_id": agent.agent_id,
                "agent": agent.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing agent create event: {e}")
            
    async def _publish_agent_update_event(self, tenant_id: str, agent: Agent) -> None:
        """Publish agent update event to NATS"""
        try:
            subject = subjects.get_agent_subject(tenant_id, agent.agent_id)
            payload = {
                "event": "update_agent",
                "tenant_id": tenant_id,
                "agent_id": agent.agent_id,
                "agent": agent.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing agent update event: {e}")
            
    async def _publish_agent_delete_event(self, tenant_id: str, agent_id: str) -> None:
        """Publish agent delete event to NATS"""
        try:
            subject = subjects.get_agent_subject(tenant_id, agent_id)
            payload = {
                "event": "delete_agent",
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing agent delete event: {e}")


# Singleton instance
agent_service = AgentService()