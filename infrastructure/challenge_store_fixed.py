"""
Challenge storage service for SSH key authentication.

This module provides a DynamoDB-based storage service for challenge strings
used in SSH key authentication. Challenges are stored with a TTL of 5 minutes.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import uuid

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
            # Check if table exists
            tables = await dynamodb.list_tables()
            
            if CHALLENGE_TABLE_NAME not in tables.get("TableNames", []):
                logger.info(f"Creating challenge table: {CHALLENGE_TABLE_NAME}")
                
                # Create table
                await dynamodb.create_table(
                    table_name=CHALLENGE_TABLE_NAME,
                    key_schema=[
                        {
                            "AttributeName": "challenge_id",
                            "KeyType": "HASH"
                        }
                    ],
                    attribute_definitions=[
                        {
                            "AttributeName": "challenge_id",
                            "AttributeType": "S"
                        }
                    ],
                    billing_mode="PAY_PER_REQUEST"
                )
                
                # Wait for table to be active
                logger.info("Waiting for challenge table to be active...")
                # In a real implementation, we'd poll the table status
                await asyncio.sleep(5)
                
                # Enable TTL
                await dynamodb.update_time_to_live(
                    table_name=CHALLENGE_TABLE_NAME,
                    ttl_attribute_name="ttl"
                )
                
                logger.info(f"Challenge table created: {CHALLENGE_TABLE_NAME}")
            
        except Exception as e:
            logger.error(f"Error ensuring challenge table exists: {e}")
            # Don't raise - the table might already exist
    
    async def store_challenge(
        self,
        tenant_id: str,
        challenge: str,
        agent_id: Optional[str] = None,
        expiry_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Store a challenge in DynamoDB with TTL.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            agent_id: Optional agent ID
            expiry_time: Optional custom expiry time in seconds
            
        Returns:
            Dictionary containing challenge data
        """
        try:
            # Calculate expiry time
            expiry_seconds = expiry_time or self.expiry_time
            expiry_datetime = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
            expiry_epoch = int(expiry_datetime.timestamp())
            
            # Generate a unique challenge ID
            challenge_id = str(uuid.uuid4())
            
            # Create challenge data
            challenge_data = {
                "challenge_id": challenge_id,
                "tenant_id": tenant_id,
                "challenge": challenge,
                "expires_at": expiry_datetime.isoformat(),
                "ttl": expiry_epoch,  # DynamoDB TTL field
                "created_at": datetime.now(timezone.utc).isoformat()
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
        challenge_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a challenge from DynamoDB by its ID.
        
        Args:
            challenge_id: Unique challenge ID
            
        Returns:
            Challenge data or None if not found
        """
        try:
            # Get from DynamoDB
            result = await dynamodb.get_item(
                table_name=CHALLENGE_TABLE_NAME,
                key={"challenge_id": challenge_id}
            )
            
            if result and "Item" in result:
                return result["Item"]
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting challenge: {e}")
            return None
    
    async def get_challenge_by_value(
        self,
        tenant_id: str,
        challenge: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a challenge from DynamoDB by tenant and challenge value.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            
        Returns:
            Challenge data or None if not found
        """
        try:
            # Query by tenant_id and challenge value
            # Note: This requires a GSI in production for efficiency
            result = await dynamodb.scan_items(
                table_name=CHALLENGE_TABLE_NAME,
                filter_expression="tenant_id = :tenant_id AND challenge = :challenge",
                expression_values={
                    ":tenant_id": tenant_id,
                    ":challenge": challenge
                }
            )
            
            items = result.get("items", [])
            if items:
                # Return the most recent one
                return items[0]
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting challenge by value: {e}")
            return None
    
    async def delete_challenge(
        self,
        challenge_id: str
    ) -> bool:
        """
        Delete a challenge from DynamoDB.
        
        Args:
            challenge_id: Challenge ID
            
        Returns:
            True if deleted successfully
        """
        try:
            await dynamodb.delete_item(
                table_name=CHALLENGE_TABLE_NAME,
                key={"challenge_id": challenge_id}
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error deleting challenge: {e}")
            return False


# Create singleton instance
challenge_store = ChallengeStore()