import os
import json
import uuid
import boto3
import logging
from botocore.exceptions import ClientError
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Union, TypeVar, Generic, Type
from pydantic import BaseModel

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Type variable for generic functions
T = TypeVar('T', bound=BaseModel)

class DynamoDBService:
    """
    Service for interacting with DynamoDB tables.
    """
    
    def __init__(
        self,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        table_prefix: str = "ArtCafe-PubSub-"
    ):
        """
        Initialize DynamoDB service.
        
        Args:
            region_name: AWS region name
            endpoint_url: Optional endpoint URL for local DynamoDB
            aws_access_key_id: Optional AWS access key ID
            aws_secret_access_key: Optional AWS secret access key
            table_prefix: Prefix for table names
        """
        # Initialize DynamoDB client
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=region_name or os.getenv('AWS_REGION', 'us-east-1'),
            endpoint_url=endpoint_url or os.getenv('DYNAMODB_ENDPOINT'),
            aws_access_key_id=aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        
        # Table names
        self.table_prefix = table_prefix
        self.agent_table_name = f"{table_prefix}Agents"
        self.ssh_key_table_name = f"{table_prefix}SSHKeys"
        self.channel_table_name = f"{table_prefix}Channels"
        self.tenant_table_name = f"{table_prefix}Tenants"
        self.usage_table_name = f"{table_prefix}Usage"
        
        # Table references
        self.agent_table = self.dynamodb.Table(self.agent_table_name)
        self.ssh_key_table = self.dynamodb.Table(self.ssh_key_table_name)
        self.channel_table = self.dynamodb.Table(self.channel_table_name)
        self.tenant_table = self.dynamodb.Table(self.tenant_table_name)
        self.usage_table = self.dynamodb.Table(self.usage_table_name)
    
    # Utility functions
    
    def _serialize_datetime(self, obj: Any) -> Any:
        """Serialize datetime objects to ISO format string."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return obj
    
    def _model_to_item(self, model: BaseModel) -> Dict[str, Any]:
        """Convert a Pydantic model to a DynamoDB item."""
        # Convert to dict and handle datetime serialization
        return json.loads(model.json())
    
    def _item_to_model(self, item: Dict[str, Any], model_class: Type[T]) -> T:
        """Convert a DynamoDB item to a Pydantic model."""
        return model_class(**item)
    
    # Agent methods
    
    async def create_agent(self, agent: T) -> T:
        """
        Create a new agent.
        
        Args:
            agent: Agent model to create
            
        Returns:
            Created agent
        """
        try:
            # Convert model to item
            item = self._model_to_item(agent)
            
            # Write to DynamoDB
            self.agent_table.put_item(Item=item)
            
            logger.info(f"Created agent: {agent.agent_id}")
            return agent
        
        except ClientError as e:
            logger.error(f"Error creating agent: {e}")
            raise
    
    async def get_agent(self, tenant_id: str, agent_id: str, model_class: Type[T]) -> Optional[T]:
        """
        Get an agent by ID.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            model_class: Model class for type conversion
            
        Returns:
            Agent if found, None otherwise
        """
        try:
            # Get from DynamoDB
            response = self.agent_table.get_item(
                Key={
                    'tenant_id': tenant_id,
                    'agent_id': agent_id
                }
            )
            
            # Check if item exists
            if 'Item' not in response:
                logger.info(f"Agent not found: {agent_id}")
                return None
            
            # Convert item to model
            return self._item_to_model(response['Item'], model_class)
        
        except ClientError as e:
            logger.error(f"Error getting agent {agent_id}: {e}")
            raise
    
    async def list_agents(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 50,
        next_token: Optional[str] = None,
        model_class: Type[T] = None
    ) -> Dict[str, Any]:
        """
        List agents with optional filters.
        
        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            agent_type: Optional agent type filter
            limit: Maximum number of items to return
            next_token: Pagination token
            model_class: Model class for type conversion
            
        Returns:
            Dict with agents and next token
        """
        try:
            # Start with base parameters
            params = {
                'TableName': self.agent_table_name,
                'Limit': limit
            }
            
            # Add key condition expression for tenant_id
            params['KeyConditionExpression'] = 'tenant_id = :tid'
            params['ExpressionAttributeValues'] = {
                ':tid': tenant_id
            }
            
            # Add filter expression for status if provided
            if status:
                if 'FilterExpression' not in params:
                    params['FilterExpression'] = 'status = :status'
                else:
                    params['FilterExpression'] += ' AND status = :status'
                params['ExpressionAttributeValues'][':status'] = status
            
            # Add filter expression for agent_type if provided
            if agent_type:
                if 'FilterExpression' not in params:
                    params['FilterExpression'] = '#type = :type'
                else:
                    params['FilterExpression'] += ' AND #type = :type'
                if 'ExpressionAttributeNames' not in params:
                    params['ExpressionAttributeNames'] = {}
                params['ExpressionAttributeNames']['#type'] = 'type'
                params['ExpressionAttributeValues'][':type'] = agent_type
            
            # Add pagination token if provided
            if next_token:
                params['ExclusiveStartKey'] = json.loads(next_token)
            
            # Query DynamoDB
            response = self.agent_table.query(**params)
            
            # Convert items to models
            agents = [self._item_to_model(item, model_class) for item in response.get('Items', [])]
            
            # Get next token if there are more results
            result = {
                'agents': agents,
                'next_token': None
            }
            
            if 'LastEvaluatedKey' in response:
                result['next_token'] = json.dumps(response['LastEvaluatedKey'])
            
            return result
        
        except ClientError as e:
            logger.error(f"Error listing agents: {e}")
            raise
    
    async def update_agent(self, tenant_id: str, agent_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an agent.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            updates: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Build update expression and values
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                if key in ('tenant_id', 'agent_id'):
                    continue  # Skip primary key fields
                
                # Handle reserved keywords
                attr_name = f"#{key.replace('.', '_DOT_')}"
                attr_value = f":{key.replace('.', '_DOT_')}"
                
                expression_names[attr_name] = key
                expression_values[attr_value] = value
                
                update_expression += f"{attr_name} = {attr_value}, "
            
            # Remove trailing comma and space
            update_expression = update_expression.rstrip(", ")
            
            # Update in DynamoDB
            self.agent_table.update_item(
                Key={
                    'tenant_id': tenant_id,
                    'agent_id': agent_id
                },
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            
            logger.info(f"Updated agent: {agent_id}")
            return True
        
        except ClientError as e:
            logger.error(f"Error updating agent {agent_id}: {e}")
            raise
    
    async def update_agent_status(self, tenant_id: str, agent_id: str, status: str) -> bool:
        """
        Update agent status.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            status: New status
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update in DynamoDB
            self.agent_table.update_item(
                Key={
                    'tenant_id': tenant_id,
                    'agent_id': agent_id
                },
                UpdateExpression="SET #status = :status, last_seen = :last_seen",
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': status,
                    ':last_seen': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Updated agent status: {agent_id} -> {status}")
            return True
        
        except ClientError as e:
            logger.error(f"Error updating agent status {agent_id}: {e}")
            raise
    
    async def delete_agent(self, tenant_id: str, agent_id: str) -> bool:
        """
        Delete an agent.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete from DynamoDB
            self.agent_table.delete_item(
                Key={
                    'tenant_id': tenant_id,
                    'agent_id': agent_id
                }
            )
            
            logger.info(f"Deleted agent: {agent_id}")
            return True
        
        except ClientError as e:
            logger.error(f"Error deleting agent {agent_id}: {e}")
            raise
    
    # SSH key methods
    
    async def create_ssh_key(self, ssh_key: T) -> T:
        """
        Create a new SSH key.
        
        Args:
            ssh_key: SSH key model to create
            
        Returns:
            Created SSH key
        """
        try:
            # Convert model to item
            item = self._model_to_item(ssh_key)
            
            # Write to DynamoDB
            self.ssh_key_table.put_item(Item=item)
            
            logger.info(f"Created SSH key: {ssh_key.key_id}")
            return ssh_key
        
        except ClientError as e:
            logger.error(f"Error creating SSH key: {e}")
            raise
    
    async def list_ssh_keys(
        self,
        tenant_id: str,
        agent_id: Optional[str] = None,
        limit: int = 50,
        next_token: Optional[str] = None,
        model_class: Type[T] = None
    ) -> Dict[str, Any]:
        """
        List SSH keys with optional filters.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Optional agent ID filter
            limit: Maximum number of items to return
            next_token: Pagination token
            model_class: Model class for type conversion
            
        Returns:
            Dict with SSH keys and next token
        """
        try:
            # Start with base parameters
            params = {
                'TableName': self.ssh_key_table_name,
                'Limit': limit
            }
            
            # Add key condition expression for tenant_id
            params['KeyConditionExpression'] = 'tenant_id = :tid'
            params['ExpressionAttributeValues'] = {
                ':tid': tenant_id
            }
            
            # Add filter expression for agent_id if provided
            if agent_id:
                params['FilterExpression'] = 'agent_id = :aid'
                params['ExpressionAttributeValues'][':aid'] = agent_id
            
            # Add pagination token if provided
            if next_token:
                params['ExclusiveStartKey'] = json.loads(next_token)
            
            # Query DynamoDB
            response = self.ssh_key_table.query(**params)
            
            # Convert items to models
            ssh_keys = [self._item_to_model(item, model_class) for item in response.get('Items', [])]
            
            # Get next token if there are more results
            result = {
                'ssh_keys': ssh_keys,
                'next_token': None
            }
            
            if 'LastEvaluatedKey' in response:
                result['next_token'] = json.dumps(response['LastEvaluatedKey'])
            
            return result
        
        except ClientError as e:
            logger.error(f"Error listing SSH keys: {e}")
            raise
    
    async def delete_ssh_key(self, tenant_id: str, key_id: str) -> bool:
        """
        Delete an SSH key.
        
        Args:
            tenant_id: Tenant ID
            key_id: Key ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # We need to query first to get the agent_id (part of the composite key)
            params = {
                'TableName': self.ssh_key_table_name,
                'IndexName': 'KeyIdIndex',
                'KeyConditionExpression': 'key_id = :kid',
                'ExpressionAttributeValues': {
                    ':kid': key_id
                }
            }
            
            # Query DynamoDB
            response = self.ssh_key_table.query(**params)
            
            # Check if key exists
            if 'Items' not in response or len(response['Items']) == 0:
                logger.info(f"SSH key not found: {key_id}")
                return False
            
            # Get the first matching key
            key_item = response['Items'][0]
            
            # Delete from DynamoDB
            self.ssh_key_table.delete_item(
                Key={
                    'tenant_id': tenant_id,
                    'key_id': key_id
                }
            )
            
            logger.info(f"Deleted SSH key: {key_id}")
            return True
        
        except ClientError as e:
            logger.error(f"Error deleting SSH key {key_id}: {e}")
            raise
    
    # Channel methods
    
    async def create_channel(self, channel: T) -> T:
        """
        Create a new channel.
        
        Args:
            channel: Channel model to create
            
        Returns:
            Created channel
        """
        try:
            # Convert model to item
            item = self._model_to_item(channel)
            
            # Write to DynamoDB
            self.channel_table.put_item(Item=item)
            
            logger.info(f"Created channel: {channel.id}")
            return channel
        
        except ClientError as e:
            logger.error(f"Error creating channel: {e}")
            raise
    
    async def get_channel(self, tenant_id: str, channel_id: str, model_class: Type[T]) -> Optional[T]:
        """
        Get a channel by ID.
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            model_class: Model class for type conversion
            
        Returns:
            Channel if found, None otherwise
        """
        try:
            # Get from DynamoDB
            response = self.channel_table.get_item(
                Key={
                    'tenant_id': tenant_id,
                    'id': channel_id
                }
            )
            
            # Check if item exists
            if 'Item' not in response:
                logger.info(f"Channel not found: {channel_id}")
                return None
            
            # Convert item to model
            return self._item_to_model(response['Item'], model_class)
        
        except ClientError as e:
            logger.error(f"Error getting channel {channel_id}: {e}")
            raise
    
    async def list_channels(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        channel_type: Optional[str] = None,
        limit: int = 50,
        next_token: Optional[str] = None,
        model_class: Type[T] = None
    ) -> Dict[str, Any]:
        """
        List channels with optional filters.
        
        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            channel_type: Optional channel type filter
            limit: Maximum number of items to return
            next_token: Pagination token
            model_class: Model class for type conversion
            
        Returns:
            Dict with channels and next token
        """
        try:
            # Start with base parameters
            params = {
                'TableName': self.channel_table_name,
                'Limit': limit
            }
            
            # Add key condition expression for tenant_id
            params['KeyConditionExpression'] = 'tenant_id = :tid'
            params['ExpressionAttributeValues'] = {
                ':tid': tenant_id
            }
            
            # Add filter expression for status if provided
            if status:
                if 'FilterExpression' not in params:
                    params['FilterExpression'] = 'status = :status'
                else:
                    params['FilterExpression'] += ' AND status = :status'
                params['ExpressionAttributeValues'][':status'] = status
            
            # Add filter expression for channel_type if provided
            if channel_type:
                if 'FilterExpression' not in params:
                    params['FilterExpression'] = '#type = :type'
                else:
                    params['FilterExpression'] += ' AND #type = :type'
                if 'ExpressionAttributeNames' not in params:
                    params['ExpressionAttributeNames'] = {}
                params['ExpressionAttributeNames']['#type'] = 'type'
                params['ExpressionAttributeValues'][':type'] = channel_type
            
            # Add pagination token if provided
            if next_token:
                params['ExclusiveStartKey'] = json.loads(next_token)
            
            # Query DynamoDB
            response = self.channel_table.query(**params)
            
            # Convert items to models
            channels = [self._item_to_model(item, model_class) for item in response.get('Items', [])]
            
            # Get next token if there are more results
            result = {
                'channels': channels,
                'next_token': None
            }
            
            if 'LastEvaluatedKey' in response:
                result['next_token'] = json.dumps(response['LastEvaluatedKey'])
            
            return result
        
        except ClientError as e:
            logger.error(f"Error listing channels: {e}")
            raise
    
    # Tenant methods
    
    async def create_tenant(self, tenant: T) -> T:
        """
        Create a new tenant.
        
        Args:
            tenant: Tenant model to create
            
        Returns:
            Created tenant
        """
        try:
            # Convert model to item
            item = self._model_to_item(tenant)
            
            # Write to DynamoDB
            self.tenant_table.put_item(Item=item)
            
            logger.info(f"Created tenant: {tenant.tenant_id}")
            return tenant
        
        except ClientError as e:
            logger.error(f"Error creating tenant: {e}")
            raise
    
    async def get_tenant(self, tenant_id: str, model_class: Type[T]) -> Optional[T]:
        """
        Get a tenant by ID.
        
        Args:
            tenant_id: Tenant ID
            model_class: Model class for type conversion
            
        Returns:
            Tenant if found, None otherwise
        """
        try:
            # Get from DynamoDB
            response = self.tenant_table.get_item(
                Key={
                    'tenant_id': tenant_id
                }
            )
            
            # Check if item exists
            if 'Item' not in response:
                logger.info(f"Tenant not found: {tenant_id}")
                return None
            
            # Convert item to model
            return self._item_to_model(response['Item'], model_class)
        
        except ClientError as e:
            logger.error(f"Error getting tenant {tenant_id}: {e}")
            raise
    
    # Usage methods
    
    async def record_usage(self, usage_metrics: T) -> T:
        """
        Record usage metrics.
        
        Args:
            usage_metrics: Usage metrics to record
            
        Returns:
            Recorded usage metrics
        """
        try:
            # Convert model to item
            item = self._model_to_item(usage_metrics)
            
            # Write to DynamoDB
            self.usage_table.put_item(Item=item)
            
            logger.info(f"Recorded usage for tenant: {usage_metrics.tenant_id}, date: {usage_metrics.timestamp_date}")
            return usage_metrics
        
        except ClientError as e:
            logger.error(f"Error recording usage: {e}")
            raise
    
    async def get_usage_metrics(
        self,
        tenant_id: str,
        start_date: str,
        end_date: str,
        model_class: Type[T] = None
    ) -> Dict[str, Any]:
        """
        Get usage metrics for a date range.
        
        Args:
            tenant_id: Tenant ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            model_class: Model class for type conversion
            
        Returns:
            Dict with usage metrics
        """
        try:
            # Start with base parameters
            params = {
                'TableName': self.usage_table_name,
                'KeyConditionExpression': 'tenant_id = :tid AND timestamp_date BETWEEN :start AND :end',
                'ExpressionAttributeValues': {
                    ':tid': tenant_id,
                    ':start': start_date,
                    ':end': end_date
                }
            }
            
            # Query DynamoDB
            response = self.usage_table.query(**params)
            
            # Convert items to models if model_class is provided
            daily_metrics = []
            for item in response.get('Items', []):
                if model_class:
                    daily_metrics.append(self._item_to_model(item, model_class))
                else:
                    daily_metrics.append(item)
            
            # Calculate totals
            totals = {
                'messages': sum(item.get('messages', 0) for item in response.get('Items', [])),
                'api_calls': sum(item.get('api_calls', 0) for item in response.get('Items', [])),
                'storage_mb': sum(item.get('storage_mb', 0) for item in response.get('Items', []))
            }
            
            # Subscription tier limits
            # In a real implementation, these would be fetched from the tenant's subscription tier
            limits = {
                'max_messages_per_day': 50000,
                'max_api_calls_per_day': 10000,
                'max_storage_mb': 1000,
                'max_agents': 20,
                'max_channels': 50
            }
            
            return {
                'totals': totals,
                'limits': limits,
                'daily': [
                    {
                        'date': metric.get('timestamp_date'),
                        'messages': metric.get('messages', 0),
                        'api_calls': metric.get('api_calls', 0),
                        'storage_mb': metric.get('storage_mb', 0)
                    } for metric in daily_metrics
                ]
            }
        
        except ClientError as e:
            logger.error(f"Error getting usage metrics: {e}")
            raise