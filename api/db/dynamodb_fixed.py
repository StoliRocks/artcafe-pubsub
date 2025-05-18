"""
DynamoDB service implementation - FIXED VERSION
"""
import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime
from boto3 import client, resource
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError, BotoCoreError

from config.settings import settings

# Boto3 type helpers
type_deserializer = TypeDeserializer()
type_serializer = TypeSerializer()

logger = logging.getLogger(__name__)


class DynamoDBService:
    """
    Service for interacting with DynamoDB tables
    """

    def __init__(self):
        """Initialize DynamoDB service"""
        self.client = client('dynamodb',
                           region_name=settings.aws_region,
                           aws_access_key_id=settings.aws_access_key_id,
                           aws_secret_access_key=settings.aws_secret_access_key)
        self.resource = resource('dynamodb',
                               region_name=settings.aws_region,
                               aws_access_key_id=settings.aws_access_key_id,
                               aws_secret_access_key=settings.aws_secret_access_key)
        self.table_prefix = settings.dynamodb_table_prefix
        self.environment = settings.environment
                               
    def get_table_name(self, table_suffix: str) -> str:
        """Get full table name with prefix and environment"""
        table_name = f"{self.table_prefix}-{table_suffix}"
        
        # Special handling for dev environment
        if self.environment == "dev" and table_suffix != "tenants":
            # For development, we suffix tables with -dev
            # But only non-critical tables
            if table_suffix not in ["tenants", "user-tenants", "channel-subscriptions", "user-tenant-index"]:
                table_name += f"-{self.environment}"
        
        return table_name
    
    async def create_table_if_not_exists(self, table_definition: Dict[str, Any]):
        """Create a DynamoDB table if it doesn't exist"""
        table_name = table_definition['TableName']
        
        try:
            # Check if table exists
            response = self.client.describe_table(TableName=table_name)
            logger.info(f"Table {table_name} already exists")
            return response['Table']
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
        
        # Table doesn't exist, create it
        try:
            response = self.client.create_table(**table_definition)
            logger.info(f"Creating table {table_name}")
            
            # Wait for table to be active
            waiter = self.client.get_waiter('table_exists')
            waiter.wait(TableName=table_name)
            
            return response['TableDescription']
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {str(e)}")
            raise

    def _convert_to_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python dict to DynamoDB item format"""
        # Convert Python types to DynamoDB AttributeValues
        converted = {}
        for key, value in item.items():
            if value is not None:  # Skip None values
                converted[key] = self._python_to_dynamodb_value(value)
        return converted
    
    def _python_to_dynamodb_value(self, value: Any) -> Dict[str, Any]:
        """Convert a Python value to DynamoDB AttributeValue format"""
        if isinstance(value, str):
            return {"S": value}
        elif isinstance(value, bool):
            return {"BOOL": value}
        elif isinstance(value, (int, float)):
            return {"N": str(value)}
        elif isinstance(value, dict):
            # For nested dictionaries, recursively convert
            nested = {}
            for k, v in value.items():
                if v is not None:
                    nested[k] = self._python_to_dynamodb_value(v)
            return {"M": nested}
        elif isinstance(value, list):
            # For lists, convert to list type
            if all(isinstance(v, str) for v in value):
                return {"SS": value}  # String set
            elif all(isinstance(v, (int, float)) for v in value):
                return {"NS": [str(v) for v in value]}  # Number set
            else:
                # Mixed type list
                return {"L": [self._python_to_dynamodb_value(v) for v in value]}
        else:
            # Default to string representation
            return {"S": str(value)}
    
    def _dynamodb_to_python(self, dynamo_value: Dict[str, Any]) -> Any:
        """Convert DynamoDB value to Python value"""
        if "S" in dynamo_value:
            return dynamo_value["S"]
        elif "N" in dynamo_value:
            num_str = dynamo_value["N"]
            if "." in num_str:
                return float(num_str)
            else:
                return int(num_str)
        elif "BOOL" in dynamo_value:
            return dynamo_value["BOOL"]
        elif "M" in dynamo_value:
            # Map/Dictionary
            result = {}
            for k, v in dynamo_value["M"].items():
                result[k] = self._dynamodb_to_python(v)
            return result
        elif "L" in dynamo_value:
            # List
            return [self._dynamodb_to_python(v) for v in dynamo_value["L"]]
        elif "SS" in dynamo_value:
            # String set
            return list(dynamo_value["SS"])
        elif "NS" in dynamo_value:
            # Number set
            return [int(v) if "." not in v else float(v) for v in dynamo_value["NS"]]
        elif "NULL" in dynamo_value:
            return None
        else:
            return None
    
    def _convert_from_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB item to Python dict"""
        result = {}
        for key, value in item.items():
            result[key] = self._dynamodb_to_python(value)
        return result
    
    async def put_item(self, table_name: str, item: Dict[str, Any], condition_expression: Optional[str] = None) -> bool:
        """
        Put item into DynamoDB table
        
        Args:
            table_name: Table name  
            item: Item to insert
            condition_expression: Optional condition expression
            
        Returns:
            True if successful
        """
        try:
            params = {
                'TableName': table_name,
                'Item': self._convert_to_dynamodb_item(item)
            }
            
            if condition_expression:
                params['ConditionExpression'] = condition_expression
            
            self.client.put_item(**params)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"Conditional check failed for put_item in {table_name}")
                return False
            else:
                logger.error(f"Error putting item to {table_name}: {str(e)}")
                raise
    
    async def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get item from DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key
            
        Returns:
            Item if found, None otherwise
        """
        try:
            response = self.client.get_item(
                TableName=table_name,
                Key=self._convert_to_dynamodb_item(key)
            )
            
            if 'Item' in response:
                return self._convert_from_dynamodb_item(response['Item'])
            return None
        except ClientError as e:
            logger.error(f"Error getting item from {table_name}: {str(e)}")
            raise
    
    async def update_item(self,
                         table_name: str,
                         key: Dict[str, Any],
                         update_expression: str,
                         expression_values: Optional[Dict[str, Any]] = None,
                         expression_names: Optional[Dict[str, str]] = None,
                         condition_expression: Optional[str] = None,
                         return_values: str = "ALL_NEW") -> Optional[Dict[str, Any]]:
        """
        Update item in DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key 
            update_expression: Update expression
            expression_values: Expression attribute values
            expression_names: Expression attribute names
            condition_expression: Optional condition expression
            return_values: Return values specification
            
        Returns:
            Updated item attributes
        """
        try:
            params = {
                'TableName': table_name,
                'Key': self._convert_to_dynamodb_item(key),
                'UpdateExpression': update_expression,
                'ReturnValues': return_values
            }
            
            if expression_values:
                # Convert values to DynamoDB format
                dynamo_values = {}
                for k, v in expression_values.items():
                    dynamo_values[k] = self._python_to_dynamodb_value(v)
                params['ExpressionAttributeValues'] = dynamo_values
            
            if expression_names:
                params['ExpressionAttributeNames'] = expression_names
            
            if condition_expression:
                params['ConditionExpression'] = condition_expression
            
            response = self.client.update_item(**params)
            
            if 'Attributes' in response:
                return self._convert_from_dynamodb_item(response['Attributes'])
            return None
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"Conditional check failed for update_item in {table_name}")
                return None
            else:
                logger.error(f"Error updating item in {table_name}: {str(e)}")
                raise
    
    async def delete_item(self, table_name: str, key: Dict[str, Any], condition_expression: Optional[str] = None) -> bool:
        """
        Delete item from DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key
            condition_expression: Optional condition expression
            
        Returns:
            True if successful
        """
        try:
            params = {
                'TableName': table_name,
                'Key': self._convert_to_dynamodb_item(key)
            }
            
            if condition_expression:
                params['ConditionExpression'] = condition_expression
            
            self.client.delete_item(**params)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"Conditional check failed for delete_item in {table_name}")
                return False
            else:
                logger.error(f"Error deleting item from {table_name}: {str(e)}")
                raise
    
    async def query_items(self,
                         table_name: str,
                         key_condition: str,
                         expression_values: Optional[Dict[str, Any]] = None,
                         expression_names: Optional[Dict[str, str]] = None,
                         index_name: Optional[str] = None,
                         limit: Optional[int] = None,
                         next_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Query items from DynamoDB table
        
        Args:
            table_name: Table name
            key_condition: Key condition expression
            expression_values: Expression attribute values
            expression_names: Expression attribute names
            index_name: Optional index name
            limit: Optional result limit
            next_token: Optional pagination token
            
        Returns:
            Query results
        """
        try:
            # Convert expression values to DynamoDB format
            dynamo_expression_values = {}
            if expression_values:
                for k, v in expression_values.items():
                    if isinstance(v, str):
                        dynamo_expression_values[k] = {"S": v}
                    elif isinstance(v, (int, float)):
                        dynamo_expression_values[k] = {"N": str(v)}
                    elif isinstance(v, bool):
                        dynamo_expression_values[k] = {"BOOL": v}
                    else:
                        # For complex types, use the conversion method
                        converted = self._convert_to_dynamodb_item({k: v})
                        dynamo_expression_values[k] = converted[k]
            
            # Build query parameters
            query_params = {
                "TableName": table_name,
                "KeyConditionExpression": key_condition,
            }
            
            if dynamo_expression_values:
                query_params["ExpressionAttributeValues"] = dynamo_expression_values
            
            if expression_names:
                query_params["ExpressionAttributeNames"] = expression_names
            
            if index_name:
                query_params["IndexName"] = index_name
            
            if limit:
                query_params["Limit"] = limit
            
            if next_token:
                query_params["ExclusiveStartKey"] = json.loads(next_token)
            
            response = self.client.query(**query_params)
            
            items = []
            if 'Items' in response:
                for item in response['Items']:
                    items.append(self._convert_from_dynamodb_item(item))
            
            result = {
                'items': items,
                'count': response.get('Count', 0)
            }
            
            if 'LastEvaluatedKey' in response:
                result['next_token'] = json.dumps(response['LastEvaluatedKey'])
            
            return result
        except ClientError as e:
            logger.error(f"Error querying items from {table_name}: {str(e)}")
            raise
    
    async def scan_items(self,
                        table_name: str,
                        filter_expression: Optional[str] = None,
                        expression_values: Optional[Dict[str, Any]] = None,
                        expression_names: Optional[Dict[str, str]] = None,
                        limit: Optional[int] = None,
                        next_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Scan items from DynamoDB table
        
        Args:
            table_name: Table name
            filter_expression: Optional filter expression
            expression_values: Expression attribute values
            expression_names: Expression attribute names
            limit: Optional result limit
            next_token: Optional pagination token
            
        Returns:
            Scan results
        """
        try:
            params = {
                'TableName': table_name
            }
            
            if filter_expression:
                params['FilterExpression'] = filter_expression
            
            if expression_values:
                # Convert values to DynamoDB format
                dynamo_values = {}
                for k, v in expression_values.items():
                    dynamo_values[k] = self._python_to_dynamodb_value(v)
                params['ExpressionAttributeValues'] = dynamo_values
            
            if expression_names:
                params['ExpressionAttributeNames'] = expression_names
            
            if limit:
                params['Limit'] = limit
            
            if next_token:
                params['ExclusiveStartKey'] = json.loads(next_token)
            
            response = self.client.scan(**params)
            
            items = []
            if 'Items' in response:
                for item in response['Items']:
                    items.append(self._convert_from_dynamodb_item(item))
            
            result = {
                'items': items,
                'count': response.get('Count', 0)
            }
            
            if 'LastEvaluatedKey' in response:
                result['next_token'] = json.dumps(response['LastEvaluatedKey'])
            
            return result
        except ClientError as e:
            logger.error(f"Error scanning items from {table_name}: {str(e)}")
            raise
    
    async def batch_get_items(self, requests: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Batch get items from multiple tables
        
        Args:
            requests: Dictionary of table names to keys
            
        Returns:
            Dictionary of table names to items
        """
        try:
            # Convert requests to DynamoDB format
            request_items = {}
            for table_name, keys in requests.items():
                request_items[table_name] = {
                    'Keys': [self._convert_to_dynamodb_item(key) for key in keys]
                }
            
            response = self.client.batch_get_item(RequestItems=request_items)
            
            # Convert response to Python format
            result = {}
            if 'Responses' in response:
                for table_name, items in response['Responses'].items():
                    result[table_name] = [self._convert_from_dynamodb_item(item) for item in items]
            
            return result
        except ClientError as e:
            logger.error(f"Error batch getting items: {str(e)}")
            raise
    
    async def batch_write_items(self, requests: Dict[str, List[Dict[str, Any]]]) -> bool:
        """
        Batch write items to multiple tables
        
        Args:
            requests: Dictionary of table names to write requests
            
        Returns:
            True if successful
        """
        try:
            # Convert requests to DynamoDB format
            request_items = {}
            for table_name, operations in requests.items():
                table_requests = []
                for op in operations:
                    if 'PutRequest' in op:
                        table_requests.append({
                            'PutRequest': {
                                'Item': self._convert_to_dynamodb_item(op['PutRequest']['Item'])
                            }
                        })
                    elif 'DeleteRequest' in op:
                        table_requests.append({
                            'DeleteRequest': {
                                'Key': self._convert_to_dynamodb_item(op['DeleteRequest']['Key'])
                            }
                        })
                request_items[table_name] = table_requests
            
            self.client.batch_write_item(RequestItems=request_items)
            return True
        except ClientError as e:
            logger.error(f"Error batch writing items: {str(e)}")
            raise
    
# Create singleton instance
dynamodb = DynamoDBService()