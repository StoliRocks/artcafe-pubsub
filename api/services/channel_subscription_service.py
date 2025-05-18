import logging
import ulid
from typing import Dict, List, Optional
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models.channel_subscription import (
    ChannelSubscription,
    ChannelSubscriptionCreate,
    ChannelSubscriptionUpdate,
    SubscriptionRole
)

logger = logging.getLogger(__name__)


class ChannelSubscriptionService:
    """Service for managing channel subscriptions"""
    
    async def get_subscription(
        self,
        channel_id: str,
        agent_id: str
    ) -> Optional[ChannelSubscription]:
        """
        Get subscription by channel and agent IDs
        
        Args:
            channel_id: Channel ID
            agent_id: Agent ID
            
        Returns:
            Subscription or None if not found
        """
        try:
            # Get subscription from DynamoDB
            item = await dynamodb.get_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                key={"channel_id": channel_id, "agent_id": agent_id}
            )
            
            if not item:
                return None
                
            # Convert to model
            return ChannelSubscription(**item)
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            raise
            
    async def create_subscription(
        self,
        tenant_id: str,
        subscription_data: ChannelSubscriptionCreate
    ) -> ChannelSubscription:
        """
        Create a new channel subscription
        
        Args:
            tenant_id: Tenant ID
            subscription_data: Subscription data
            
        Returns:
            Created subscription
        """
        try:
            # Generate subscription ID
            subscription_id = f"sub-{ulid.ULID().str.lower()}"
            
            # Create subscription
            subscription = ChannelSubscription(
                id=subscription_id,
                tenant_id=tenant_id,
                **subscription_data.dict(),
                subscribed_at=datetime.utcnow()
            )
            
            # Convert to dict for DynamoDB
            subscription_dict = subscription.dict(by_alias=True)
            
            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                item=subscription_dict
            )
            
            # Update channel subscriber count
            await self._update_channel_stats(
                tenant_id, 
                subscription_data.channel_id, 
                increment=True
            )
            
            # Update agent subscription list
            await self._update_agent_subscriptions(
                tenant_id,
                subscription_data.agent_id,
                subscription_data.channel_id,
                add=True
            )
            
            return subscription
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            raise
            
    async def update_subscription(
        self,
        channel_id: str,
        agent_id: str,
        update_data: ChannelSubscriptionUpdate
    ) -> ChannelSubscription:
        """
        Update a channel subscription
        
        Args:
            channel_id: Channel ID
            agent_id: Agent ID
            update_data: Update data
            
        Returns:
            Updated subscription
        """
        try:
            # Get existing subscription
            subscription = await self.get_subscription(channel_id, agent_id)
            if not subscription:
                raise ValueError("Subscription not found")
                
            # Update fields
            update_dict = update_data.dict(exclude_unset=True)
            if update_dict:
                # Create update expression for DynamoDB
                update_expr = "SET "
                expr_names = {}
                expr_values = {}
                
                for i, (key, value) in enumerate(update_dict.items()):
                    attr_name = f"#{key}"
                    attr_value = f":val{i}"
                    update_expr += f"{attr_name} = {attr_value}, "
                    expr_names[attr_name] = key
                    expr_values[attr_value] = value
                    
                # Add updated_at
                update_expr += "#updated_at = :updated_at"
                expr_names["#updated_at"] = "updated_at"
                expr_values[":updated_at"] = datetime.utcnow().isoformat()
                
                # Update item
                await dynamodb.update_item(
                    table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                    key={"channel_id": channel_id, "agent_id": agent_id},
                    update_expression=update_expr,
                    expression_attribute_names=expr_names,
                    expression_attribute_values=expr_values
                )
                
                # Get updated subscription
                subscription = await self.get_subscription(channel_id, agent_id)
                
            return subscription
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            raise
            
    async def delete_subscription(
        self,
        tenant_id: str,
        channel_id: str,
        agent_id: str
    ) -> bool:
        """
        Delete a channel subscription
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            agent_id: Agent ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Check if subscription exists
            subscription = await self.get_subscription(channel_id, agent_id)
            if not subscription:
                return False
                
            # Delete from DynamoDB
            await dynamodb.delete_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                key={"channel_id": channel_id, "agent_id": agent_id}
            )
            
            # Update channel subscriber count
            await self._update_channel_stats(
                tenant_id,
                channel_id,
                increment=False
            )
            
            # Update agent subscription list
            await self._update_agent_subscriptions(
                tenant_id,
                agent_id,
                channel_id,
                add=False
            )
            
            return True
        except Exception as e:
            logger.error(f"Error deleting subscription: {e}")
            raise
            
    async def list_channel_subscriptions(
        self,
        channel_id: str,
        limit: int = 100,
        next_token: Optional[str] = None
    ) -> Dict:
        """
        List subscriptions for a channel
        
        Args:
            channel_id: Channel ID
            limit: Max items to return
            next_token: Pagination token
            
        Returns:
            Subscriptions and pagination token
        """
        try:
            # Query subscriptions by channel
            response = await dynamodb.query(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                key_condition_expression="channel_id = :channel_id",
                expression_attribute_values={":channel_id": channel_id},
                limit=limit,
                exclusive_start_key=next_token
            )
            
            subscriptions = []
            for item in response.get("Items", []):
                subscriptions.append(ChannelSubscription(**item))
                
            return {
                "subscriptions": subscriptions,
                "next_token": response.get("LastEvaluatedKey")
            }
        except Exception as e:
            logger.error(f"Error listing channel subscriptions: {e}")
            raise
            
    async def list_agent_subscriptions(
        self,
        agent_id: str,
        limit: int = 100,
        next_token: Optional[str] = None
    ) -> Dict:
        """
        List subscriptions for an agent
        
        Args:
            agent_id: Agent ID
            limit: Max items to return
            next_token: Pagination token
            
        Returns:
            Subscriptions and pagination token
        """
        try:
            # Query subscriptions by agent using GSI
            response = await dynamodb.query(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                index_name="AgentIndex",
                key_condition_expression="agent_id = :agent_id",
                expression_attribute_values={":agent_id": agent_id},
                limit=limit,
                exclusive_start_key=next_token
            )
            
            subscriptions = []
            for item in response.get("Items", []):
                subscriptions.append(ChannelSubscription(**item))
                
            return {
                "subscriptions": subscriptions,
                "next_token": response.get("LastEvaluatedKey")
            }
        except Exception as e:
            logger.error(f"Error listing agent subscriptions: {e}")
            raise
            
    async def list_tenant_subscriptions(
        self,
        tenant_id: str,
        limit: int = 100,
        next_token: Optional[str] = None
    ) -> Dict:
        """
        List all subscriptions for a tenant
        
        Args:
            tenant_id: Tenant ID
            limit: Max items to return
            next_token: Pagination token
            
        Returns:
            Subscriptions and pagination token
        """
        try:
            # Query subscriptions by tenant using GSI
            response = await dynamodb.query(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                index_name="TenantIndex",
                key_condition_expression="tenant_id = :tenant_id",
                expression_attribute_values={":tenant_id": tenant_id},
                limit=limit,
                exclusive_start_key=next_token
            )
            
            subscriptions = []
            for item in response.get("Items", []):
                subscriptions.append(ChannelSubscription(**item))
                
            return {
                "subscriptions": subscriptions,
                "next_token": response.get("LastEvaluatedKey")
            }
        except Exception as e:
            logger.error(f"Error listing tenant subscriptions: {e}")
            raise
            
    async def update_last_activity(
        self,
        channel_id: str,
        agent_id: str,
        activity_type: str = "message"
    ) -> None:
        """
        Update last activity timestamp for a subscription
        
        Args:
            channel_id: Channel ID
            agent_id: Agent ID
            activity_type: Type of activity
        """
        try:
            # Update activity timestamp
            await dynamodb.update_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                key={"channel_id": channel_id, "agent_id": agent_id},
                update_expression="SET last_activity = :now, updated_at = :now",
                expression_attribute_values={
                    ":now": datetime.utcnow().isoformat()
                }
            )
            
            # Increment message counters if applicable
            if activity_type == "message_sent":
                await self._increment_message_counter(
                    channel_id, 
                    agent_id,
                    "messages_sent"
                )
            elif activity_type == "message_received":
                await self._increment_message_counter(
                    channel_id,
                    agent_id, 
                    "messages_received"
                )
        except Exception as e:
            logger.error(f"Error updating last activity: {e}")
            
    async def update_connection_status(
        self,
        channel_id: str,
        agent_id: str,
        connected: bool,
        connection_id: Optional[str] = None
    ) -> None:
        """
        Update connection status for a subscription
        
        Args:
            channel_id: Channel ID
            agent_id: Agent ID
            connected: Whether agent is connected
            connection_id: WebSocket connection ID
        """
        try:
            if connected:
                # Set connected status
                await dynamodb.update_item(
                    table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                    key={"channel_id": channel_id, "agent_id": agent_id},
                    update_expression="SET connection_id = :conn_id, connected_at = :now, updated_at = :now",
                    expression_attribute_values={
                        ":conn_id": connection_id,
                        ":now": datetime.utcnow().isoformat()
                    }
                )
            else:
                # Remove connection details
                await dynamodb.update_item(
                    table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                    key={"channel_id": channel_id, "agent_id": agent_id},
                    update_expression="REMOVE connection_id, connected_at SET updated_at = :now",
                    expression_attribute_values={
                        ":now": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            logger.error(f"Error updating connection status: {e}")
            
    async def _update_channel_stats(
        self,
        tenant_id: str,
        channel_id: str,
        increment: bool = True
    ) -> None:
        """
        Update channel subscriber count
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            increment: Whether to increment (True) or decrement (False)
        """
        try:
            # Update subscriber count
            update_expr = "ADD subscriber_count :val"
            expr_values = {":val": 1 if increment else -1}
            
            await dynamodb.update_item(
                table_name=settings.CHANNEL_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": channel_id},
                update_expression=update_expr,
                expression_attribute_values=expr_values
            )
        except Exception as e:
            logger.warning(f"Error updating channel stats: {e}")
            
    async def _update_agent_subscriptions(
        self,
        tenant_id: str,
        agent_id: str,
        channel_id: str,
        add: bool = True
    ) -> None:
        """
        Update agent's subscription list
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            channel_id: Channel ID
            add: Whether to add (True) or remove (False)
        """
        try:
            if add:
                # Add channel to agent's subscription list
                update_expr = "ADD channel_subscriptions :channel"
                expr_values = {":channel": {channel_id}}
            else:
                # Remove channel from agent's subscription list
                update_expr = "DELETE channel_subscriptions :channel"
                expr_values = {":channel": {channel_id}}
                
            await dynamodb.update_item(
                table_name=settings.AGENT_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": agent_id},
                update_expression=update_expr,
                expression_attribute_values=expr_values
            )
        except Exception as e:
            logger.warning(f"Error updating agent subscriptions: {e}")
            
    async def _increment_message_counter(
        self,
        channel_id: str,
        agent_id: str,
        counter_name: str
    ) -> None:
        """
        Increment message counter for a subscription
        
        Args:
            channel_id: Channel ID  
            agent_id: Agent ID
            counter_name: Counter to increment
        """
        try:
            await dynamodb.update_item(
                table_name=settings.CHANNEL_SUBSCRIPTIONS_TABLE_NAME,
                key={"channel_id": channel_id, "agent_id": agent_id},
                update_expression=f"ADD {counter_name} :val",
                expression_attribute_values={":val": 1}
            )
        except Exception as e:
            logger.warning(f"Error incrementing counter: {e}")
            
            
# Create singleton instance
channel_subscription_service = ChannelSubscriptionService()