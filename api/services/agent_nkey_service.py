"""
Agent service for managing clients (formerly agents)
"""

import boto3
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

from models.agent_nkey import Agent
from config.settings import settings

class AgentService:
    """Service for managing clients"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
        self.table = self.dynamodb.Table('artcafe-agents-nkey')
        self.connections_table = self.dynamodb.Table('artcafe-websocket-connections')
    
    async def create_agent(self, agent: Agent) -> Agent:
        """Create a new client"""
        item = agent.to_dynamodb_item()
        self.table.put_item(Item=item)
        return agent
    
    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get client by ID (which is the NKey public key)"""
        response = self.table.get_item(Key={'agent_id': agent_id})
        
        if 'Item' in response:
            return Agent.from_dynamodb_item(response['Item'])
        return None
    
    async def list_agents(self, tenant_id: str, status: Optional[str] = None, limit: int = 100) -> List[Agent]:
        """List clients for a tenant"""
        response = self.table.query(
            IndexName='TenantIndex',
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            Limit=limit
        )
        
        agents = []
        for item in response.get('Items', []):
            agent = Agent.from_dynamodb_item(item)
            if not status or client.status == status:
                agents.append(agent)
        
        return agents
    
    async def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[Agent]:
        """Update client"""
        # Build update expression
        update_expr = "SET "
        expr_values = {}
        expr_names = {}
        
        for key, value in updates.items():
            update_expr += f"#{key} = :{key}, "
            expr_values[f":{key}"] = value
            expr_names[f"#{key}"] = key
        
        # Add updated_at
        update_expr += "#updated_at = :updated_at"
        expr_values[":updated_at"] = datetime.now(timezone.utc).isoformat()
        expr_names["#updated_at"] = "updated_at"
        
        try:
            response = self.table.update_item(
                Key={'agent_id': agent_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names,
                ReturnValues='ALL_NEW'
            )
            
            return Agent.from_dynamodb_item(response['Attributes'])
        except Exception as e:
            print(f"Error updating agent: {e}")
            return None
    
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete client"""
        try:
            self.table.delete_item(Key={'agent_id': agent_id})
            return True
        except Exception as e:
            print(f"Error deleting agent: {e}")
            return False
    
    async def get_agent_connection(self, agent_id: str) -> Optional[dict]:
        """Get active connection info for a client"""
        try:
            response = self.connections_table.query(
                IndexName='AgentIdIndex',
                KeyConditionExpression=Key('agent_id').eq(agent_id)
            )
            
            if response['Items']:
                # Return the most recent connection
                return response['Items'][0]
            return None
        except Exception as e:
            print(f"Error getting client connection: {e}")
            return None
# Global instance
agent_nkey_service = AgentService()
