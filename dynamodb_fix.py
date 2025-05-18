import logging
import boto3
import json
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, date

from config.settings import settings

logger = logging.getLogger(__name__)


class DynamoDBService:
    """DynamoDB service for ArtCafe pub/sub"""
    
    def __init__(self):
        """Initialize DynamoDB service"""
        self.client = self._create_dynamodb_client()
        
    def _create_dynamodb_client(self):
        """Create DynamoDB client"""
        config = {}
        
        # Use local endpoint if configured (for development)
        if settings.DYNAMODB_ENDPOINT:
            config["endpoint_url"] = settings.DYNAMODB_ENDPOINT
            
        # Use AWS credentials if configured
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            config["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            config["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            
        # Use AWS region
        config["region_name"] = settings.AWS_REGION
        
        return boto3.client("dynamodb", **config)

    def _convert_to_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Convert Python dict to DynamoDB item format"""
        result = {}
        for key, value in item.items():
            if isinstance(value, str):
                result[key] = {"S": value}
            elif isinstance(value, (int, float)):
                result[key] = {"N": str(value)}
            elif isinstance(value, bool):
                result[key] = {"BOOL": value}
            elif isinstance(value, (list, tuple)):
                if not value:
                    result[key] = {"L": []}
                elif all(isinstance(v, str) for v in value):
                    result[key] = {"SS": list(value)}
                elif all(isinstance(v, (int, float)) for v in value):
                    result[key] = {"NS": [str(v) for v in value]}
                else:
                    result[key] = {"L": [self._convert_value(v) for v in value]}
            elif isinstance(value, dict):
                result[key] = {"M": self._convert_to_dynamodb_item(value)}
            elif value is None:
                result[key] = {"NULL": True}
            elif isinstance(value, (datetime, date)):
                result[key] = {"S": value.isoformat()}
            else:
                # Default to string conversion  
                result[key] = {"S": str(value)}
                
        return result
    
    def _convert_value(self, value: Any) -> Dict[str, Any]:
        """Convert single value to DynamoDB format"""
        if isinstance(value, str):
            return {"S": value}
        elif isinstance(value, (int, float)):
            return {"N": str(value)}
        elif isinstance(value, bool):
            return {"BOOL": value}
        elif isinstance(value, dict):
            return {"M": self._convert_to_dynamodb_item(value)}
        elif isinstance(value, list):
            return {"L": [self._convert_value(v) for v in value]}
        elif value is None:
            return {"NULL": True}
        else:
            return {"S": str(value)}
    
    async def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Put item in DynamoDB table
        
        Args:
            table_name: Table name
            item: Item to put
            
        Returns:
            Item
        """
        try:
            # Add timestamps
            if "created_at" not in item:
                item["created_at"] = datetime.utcnow().isoformat()
            if "updated_at" not in item:
                item["updated_at"] = datetime.utcnow().isoformat()
                
            # Add ID if not present
            if "id" not in item:
                item["id"] = str(uuid.uuid4())
            
            # Debug: log the item being saved
            logger.info(f"[DYNAMODB_DEBUG] Putting item to {table_name}: {json.dumps(item, default=str)}")
            
            # Convert item for DynamoDB - ensure proper type conversion
            dynamodb_item = self._convert_to_dynamodb_item(item)
            logger.info(f"[DYNAMODB_DEBUG] Converted item: {json.dumps(dynamodb_item, default=str)}")
            
            try:
                self.client.put_item(
                    TableName=table_name,
                    Item=dynamodb_item
                )
            except Exception as e:
                logger.error(f"[DYNAMODB_DEBUG] DynamoDB error: {e}")
                logger.error(f"[DYNAMODB_DEBUG] Item was: {json.dumps(item, default=str)}")
                logger.error(f"[DYNAMODB_DEBUG] Converted item was: {json.dumps(dynamodb_item, default=str)}")
                raise
            
            return item
        except Exception as e:
            logger.error(f"Error putting item in {table_name}: {e}")
            raise
            
    # ... rest of the file remains the same


# Export the fixed put_item method
PUT_ITEM_FIXED = DynamoDBService().put_item