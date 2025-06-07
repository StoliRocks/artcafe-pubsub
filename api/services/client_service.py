"""
Client service for managing clients (formerly agents)
"""

import boto3
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

from models.client import Client
from config.settings import settings

class ClientService:
    """Service for managing clients"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
        self.table = self.dynamodb.Table('artcafe-clients')
        self.connections_table = self.dynamodb.Table('artcafe-websocket-connections')
    
    async def create_client(self, client: Client) -> Client:
        """Create a new client"""
        item = client.to_dynamodb_item()
        self.table.put_item(Item=item)
        return client
    
    async def get_client(self, client_id: str) -> Optional[Client]:
        """Get client by ID (which is the NKey public key)"""
        response = self.table.get_item(Key={'client_id': client_id})
        
        if 'Item' in response:
            return Client.from_dynamodb_item(response['Item'])
        return None
    
    async def list_clients(self, tenant_id: str, status: Optional[str] = None, limit: int = 100) -> List[Client]:
        """List clients for a tenant"""
        response = self.table.query(
            IndexName='TenantIndex',
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            Limit=limit
        )
        
        clients = []
        for item in response.get('Items', []):
            client = Client.from_dynamodb_item(item)
            if not status or client.status == status:
                clients.append(client)
        
        return clients
    
    async def update_client(self, client_id: str, updates: Dict[str, Any]) -> Optional[Client]:
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
                Key={'client_id': client_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ExpressionAttributeNames=expr_names,
                ReturnValues='ALL_NEW'
            )
            
            return Client.from_dynamodb_item(response['Attributes'])
        except Exception as e:
            print(f"Error updating client: {e}")
            return None
    
    async def delete_client(self, client_id: str) -> bool:
        """Delete client"""
        try:
            self.table.delete_item(Key={'client_id': client_id})
            return True
        except Exception as e:
            print(f"Error deleting client: {e}")
            return False
    
    async def get_client_connection(self, client_id: str) -> Optional[dict]:
        """Get active connection info for a client"""
        try:
            response = self.connections_table.query(
                IndexName='AgentIdIndex',
                KeyConditionExpression=Key('agent_id').eq(client_id)
            )
            
            if response['Items']:
                # Return the most recent connection
                return response['Items'][0]
            return None
        except Exception as e:
            print(f"Error getting client connection: {e}")
            return None