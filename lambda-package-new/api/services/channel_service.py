import logging
import ulid
from typing import Dict, List, Optional
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models import Channel, ChannelCreate
from nats_client import nats_manager, subjects

logger = logging.getLogger(__name__)


class ChannelService:
    """Service for channel management"""
    
    async def list_channels(self, tenant_id: str, 
                          limit: int = 50, 
                          next_token: Optional[str] = None) -> Dict:
        """
        List channels for a tenant
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of results
            next_token: Pagination token
            
        Returns:
            Dictionary with channels and pagination token
        """
        try:
            # Query channels from DynamoDB
            result = await dynamodb.scan_items(
                table_name=settings.CHANNEL_TABLE_NAME,
                filter_expression="tenant_id = :tenant_id",
                expression_values={":tenant_id": tenant_id},
                limit=limit,
                next_token=next_token
            )
            
            # Convert to Channel models
            channels = [Channel(**item) for item in result["items"]]
            
            # Publish event to NATS
            await self._publish_channel_list_event(tenant_id, len(channels))
            
            return {
                "channels": channels,
                "next_token": result["next_token"]
            }
        except Exception as e:
            logger.error(f"Error listing channels for tenant {tenant_id}: {e}")
            raise
    
    async def get_channel(self, tenant_id: str, channel_id: str) -> Optional[Channel]:
        """
        Get channel by ID
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            
        Returns:
            Channel or None if not found
        """
        try:
            # Get channel from DynamoDB
            item = await dynamodb.get_item(
                table_name=settings.CHANNEL_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": channel_id}
            )
            
            if not item:
                return None
                
            # Convert to Channel model
            channel = Channel(**item)
            
            # Publish event to NATS
            await self._publish_channel_get_event(tenant_id, channel_id)
            
            return channel
        except Exception as e:
            logger.error(f"Error getting channel {channel_id} for tenant {tenant_id}: {e}")
            raise
            
    async def create_channel(self, tenant_id: str, channel_data: ChannelCreate) -> Channel:
        """
        Create a new channel
        
        Args:
            tenant_id: Tenant ID
            channel_data: Channel data
            
        Returns:
            Created channel
        """
        try:
            # Generate channel ID
            channel_id = str(ulid.new())
            
            # Prepare channel data
            channel_dict = channel_data.dict()
            channel_dict["id"] = channel_id
            channel_dict["tenant_id"] = tenant_id
            channel_dict["status"] = "active"
            
            # Store in DynamoDB
            item = await dynamodb.put_item(
                table_name=settings.CHANNEL_TABLE_NAME,
                item=channel_dict
            )
            
            # Convert to Channel model
            channel = Channel(**item)
            
            # Publish event to NATS
            await self._publish_channel_create_event(tenant_id, channel)
            
            # Create a NATS subject for the channel
            subject = subjects.get_channel_subject(tenant_id, channel_id)
            
            return channel
        except Exception as e:
            logger.error(f"Error creating channel for tenant {tenant_id}: {e}")
            raise
            
    async def delete_channel(self, tenant_id: str, channel_id: str) -> bool:
        """
        Delete a channel
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            
        Returns:
            True if channel was deleted
        """
        try:
            # Check if channel exists
            existing_channel = await self.get_channel(tenant_id, channel_id)
            if not existing_channel:
                return False
                
            # Delete channel from DynamoDB
            result = await dynamodb.delete_item(
                table_name=settings.CHANNEL_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": channel_id}
            )
            
            # Publish event to NATS
            if result:
                await self._publish_channel_delete_event(tenant_id, channel_id)
                
            return result
        except Exception as e:
            logger.error(f"Error deleting channel {channel_id} for tenant {tenant_id}: {e}")
            raise
            
    async def publish_message(self, tenant_id: str, channel_id: str, message: Dict) -> Dict:
        """
        Publish message to a channel
        
        Args:
            tenant_id: Tenant ID
            channel_id: Channel ID
            message: Message to publish
            
        Returns:
            Message info
        """
        try:
            # Check if channel exists
            channel = await self.get_channel(tenant_id, channel_id)
            if not channel:
                raise ValueError(f"Channel {channel_id} not found")
                
            # Get NATS subject for the channel
            subject = subjects.get_channel_subject(tenant_id, channel_id)
            
            # Add metadata to message
            message["_metadata"] = {
                "timestamp": datetime.utcnow().isoformat(),
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "message_id": str(ulid.new())
            }
            
            # Publish message to NATS
            await nats_manager.publish(subject, message)
            
            return {
                "message_id": message["_metadata"]["message_id"],
                "timestamp": message["_metadata"]["timestamp"],
                "success": True
            }
        except Exception as e:
            logger.error(f"Error publishing message to channel {channel_id} for tenant {tenant_id}: {e}")
            raise
            
    # NATS event publishing methods
    
    async def _publish_channel_list_event(self, tenant_id: str, count: int) -> None:
        """Publish channel list event to NATS"""
        try:
            subject = subjects.get_channels_subject(tenant_id)
            payload = {
                "event": "list_channels",
                "tenant_id": tenant_id,
                "count": count,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing channel list event: {e}")
    
    async def _publish_channel_get_event(self, tenant_id: str, channel_id: str) -> None:
        """Publish channel get event to NATS"""
        try:
            subject = subjects.get_channel_subject(tenant_id, channel_id)
            payload = {
                "event": "get_channel",
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing channel get event: {e}")
            
    async def _publish_channel_create_event(self, tenant_id: str, channel: Channel) -> None:
        """Publish channel create event to NATS"""
        try:
            subject = subjects.get_channel_subject(tenant_id, channel.channel_id)
            payload = {
                "event": "create_channel",
                "tenant_id": tenant_id,
                "channel_id": channel.channel_id,
                "channel": channel.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing channel create event: {e}")
            
    async def _publish_channel_delete_event(self, tenant_id: str, channel_id: str) -> None:
        """Publish channel delete event to NATS"""
        try:
            subject = subjects.get_channel_subject(tenant_id, channel_id)
            payload = {
                "event": "delete_channel",
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing channel delete event: {e}")


# Singleton instance
channel_service = ChannelService()