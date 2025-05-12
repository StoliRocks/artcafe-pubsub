"""
Challenge storage service for SSH key authentication.

This module provides a DynamoDB-based storage service for challenge strings
used in SSH key authentication. Challenges are stored with a TTL of 5 minutes.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from config.settings import settings
from api.db.dynamodb import dynamodb

logger = logging.getLogger(__name__)

# Table name for challenge storage
CHALLENGE_TABLE_NAME = f"{settings.DYNAMODB_TABLE_PREFIX}Challenges"


class ChallengeStore:
    """
    DynamoDB-based challenge storage service.
    
    This class provides methods for storing and retrieving challenge strings
    used in SSH key authentication. Challenges are stored with a TTL of 5 minutes.
    """
    
    def __init__(self):
        """Initialize challenge store."""
        self.expiry_time = 300  # 5 minutes in seconds
    
    async def ensure_table_exists(self):
        """
        Ensure the challenge table exists in DynamoDB.
        
        This method checks if the challenge table exists and creates it if not.
        The table has a TTL attribute for automatic expiration of challenges.
        """
        try:
            # Check if the table exists
            exists = await dynamodb.table_exists(CHALLENGE_TABLE_NAME)
            
            if not exists:
                # Create the table
                await dynamodb.create_table(
                    table_name=CHALLENGE_TABLE_NAME,
                    key_schema=[
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                        {"AttributeName": "challenge", "KeyType": "RANGE"}
                    ],
                    attribute_definitions=[
                        {"AttributeName": "tenant_id", "AttributeType": "S"},
                        {"AttributeName": "challenge", "AttributeType": "S"}
                    ],
                    provisioned_throughput={
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                )
                
                # Wait for the table to be created
                logger.info(f"Waiting for table {CHALLENGE_TABLE_NAME} to be created...")
                await dynamodb.wait_for_table(CHALLENGE_TABLE_NAME)
                
                # Enable TTL on the table
                await dynamodb.update_ttl(
                    table_name=CHALLENGE_TABLE_NAME,
                    attribute_name="expires_at_epoch"
                )
                
                logger.info(f"Created table {CHALLENGE_TABLE_NAME} with TTL")
            
            return True
        
        except Exception as e:
            logger.error(f"Error ensuring challenge table exists: {e}")
            return False
    
    async def store_challenge(
        self,
        tenant_id: str,
        challenge: str,
        agent_id: Optional[str] = None,
        expiry_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Store a challenge in DynamoDB.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            agent_id: Optional agent ID
            expiry_time: Optional expiry time in seconds (default: 5 minutes)
            
        Returns:
            Challenge data
        """
        try:
            # Calculate expiry time
            expiry_seconds = expiry_time or self.expiry_time
            expiry_datetime = datetime.utcnow() + timedelta(seconds=expiry_seconds)
            expiry_epoch = int(expiry_datetime.timestamp())
            
            # Create challenge data
            challenge_data = {
                "tenant_id": tenant_id,
                "challenge": challenge,
                "expires_at": expiry_datetime.isoformat(),
                "expires_at_epoch": expiry_epoch,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Add agent ID if provided
            if agent_id:
                challenge_data["agent_id"] = agent_id
            
            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=CHALLENGE_TABLE_NAME,
                item=challenge_data
            )
            
            return challenge_data
        
        except Exception as e:
            logger.error(f"Error storing challenge: {e}")
            raise
    
    async def get_challenge(
        self,
        tenant_id: str,
        challenge: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a challenge from DynamoDB.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            
        Returns:
            Challenge data or None if not found or expired
        """
        try:
            # Get the challenge from DynamoDB
            item = await dynamodb.get_item(
                table_name=CHALLENGE_TABLE_NAME,
                key={"tenant_id": tenant_id, "challenge": challenge}
            )
            
            if not item:
                return None
            
            # Check if the challenge has expired
            now_epoch = int(time.time())
            expires_at_epoch = item.get("expires_at_epoch", 0)
            
            if now_epoch >= expires_at_epoch:
                # The challenge has expired
                # (This should be handled by DynamoDB TTL but we check anyway)
                logger.warning(f"Challenge expired: tenant={tenant_id}, challenge={challenge}")
                return None
            
            return item
        
        except Exception as e:
            logger.error(f"Error getting challenge: {e}")
            return None
    
    async def delete_challenge(
        self,
        tenant_id: str,
        challenge: str
    ) -> bool:
        """
        Delete a challenge from DynamoDB.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete the challenge from DynamoDB
            await dynamodb.delete_item(
                table_name=CHALLENGE_TABLE_NAME,
                key={"tenant_id": tenant_id, "challenge": challenge}
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error deleting challenge: {e}")
            return False


# Create a singleton instance
challenge_store = ChallengeStore()