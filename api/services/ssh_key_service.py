import logging
import ulid
from typing import Dict, List, Optional
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models import SSHKey, SSHKeyCreate
from nats import nats_manager, subjects

logger = logging.getLogger(__name__)


class SSHKeyService:
    """Service for SSH key management"""
    
    async def list_ssh_keys(self, tenant_id: str, 
                          limit: int = 50, 
                          next_token: Optional[str] = None) -> Dict:
        """
        List SSH keys for a tenant
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of results
            next_token: Pagination token
            
        Returns:
            Dictionary with SSH keys and pagination token
        """
        try:
            # Query SSH keys from DynamoDB
            result = await dynamodb.scan_items(
                table_name=settings.SSH_KEY_TABLE_NAME,
                filter_expression="tenant_id = :tenant_id",
                expression_values={":tenant_id": tenant_id},
                limit=limit,
                next_token=next_token
            )
            
            # Convert to SSHKey models
            keys = [SSHKey(**item) for item in result["items"]]
            
            # Publish event to NATS
            await self._publish_key_list_event(tenant_id, len(keys))
            
            return {
                "keys": keys,
                "next_token": result["next_token"]
            }
        except Exception as e:
            logger.error(f"Error listing SSH keys for tenant {tenant_id}: {e}")
            raise
    
    async def get_ssh_key(self, tenant_id: str, key_id: str) -> Optional[SSHKey]:
        """
        Get SSH key by ID
        
        Args:
            tenant_id: Tenant ID
            key_id: SSH key ID
            
        Returns:
            SSHKey or None if not found
        """
        try:
            # Get SSH key from DynamoDB
            item = await dynamodb.get_item(
                table_name=settings.SSH_KEY_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": key_id}
            )
            
            if not item:
                return None
                
            # Convert to SSHKey model
            key = SSHKey(**item)
            
            # Publish event to NATS
            await self._publish_key_get_event(tenant_id, key_id)
            
            return key
        except Exception as e:
            logger.error(f"Error getting SSH key {key_id} for tenant {tenant_id}: {e}")
            raise
            
    async def create_ssh_key(self, tenant_id: str, key_data: SSHKeyCreate) -> SSHKey:
        """
        Create a new SSH key
        
        Args:
            tenant_id: Tenant ID
            key_data: SSH key data
            
        Returns:
            Created SSH key
        """
        try:
            # Generate key ID
            key_id = str(ulid.new())
            
            # Prepare key data
            key_dict = key_data.dict()
            key_dict["id"] = key_id
            key_dict["tenant_id"] = tenant_id
            key_dict["status"] = "active"
            
            # Store in DynamoDB
            item = await dynamodb.put_item(
                table_name=settings.SSH_KEY_TABLE_NAME,
                item=key_dict
            )
            
            # Convert to SSHKey model
            key = SSHKey(**item)
            
            # Publish event to NATS
            await self._publish_key_create_event(tenant_id, key)
            
            return key
        except Exception as e:
            logger.error(f"Error creating SSH key for tenant {tenant_id}: {e}")
            raise
            
    async def delete_ssh_key(self, tenant_id: str, key_id: str) -> bool:
        """
        Delete an SSH key
        
        Args:
            tenant_id: Tenant ID
            key_id: SSH key ID
            
        Returns:
            True if key was deleted
        """
        try:
            # Check if key exists
            existing_key = await self.get_ssh_key(tenant_id, key_id)
            if not existing_key:
                return False
                
            # Delete key from DynamoDB
            result = await dynamodb.delete_item(
                table_name=settings.SSH_KEY_TABLE_NAME,
                key={"tenant_id": tenant_id, "id": key_id}
            )
            
            # Publish event to NATS
            if result:
                await self._publish_key_delete_event(tenant_id, key_id)
                
            return result
        except Exception as e:
            logger.error(f"Error deleting SSH key {key_id} for tenant {tenant_id}: {e}")
            raise
            
    # NATS event publishing methods
    
    async def _publish_key_list_event(self, tenant_id: str, count: int) -> None:
        """Publish SSH key list event to NATS"""
        try:
            subject = subjects.get_ssh_keys_subject(tenant_id)
            payload = {
                "event": "list_ssh_keys",
                "tenant_id": tenant_id,
                "count": count,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing SSH key list event: {e}")
    
    async def _publish_key_get_event(self, tenant_id: str, key_id: str) -> None:
        """Publish SSH key get event to NATS"""
        try:
            subject = subjects.get_ssh_key_subject(tenant_id, key_id)
            payload = {
                "event": "get_ssh_key",
                "tenant_id": tenant_id,
                "key_id": key_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing SSH key get event: {e}")
            
    async def _publish_key_create_event(self, tenant_id: str, key: SSHKey) -> None:
        """Publish SSH key create event to NATS"""
        try:
            subject = subjects.get_ssh_key_subject(tenant_id, key.key_id)
            payload = {
                "event": "create_ssh_key",
                "tenant_id": tenant_id,
                "key_id": key.key_id,
                "key": key.dict(),
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing SSH key create event: {e}")
            
    async def _publish_key_delete_event(self, tenant_id: str, key_id: str) -> None:
        """Publish SSH key delete event to NATS"""
        try:
            subject = subjects.get_ssh_key_subject(tenant_id, key_id)
            payload = {
                "event": "delete_ssh_key",
                "tenant_id": tenant_id,
                "key_id": key_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await nats_manager.publish(subject, payload)
        except Exception as e:
            logger.error(f"Error publishing SSH key delete event: {e}")


# Singleton instance
ssh_key_service = SSHKeyService()