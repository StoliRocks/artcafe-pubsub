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
    
    def _fix_booleans_for_dynamodb(self, data: Any) -> Any:
        """Recursively convert all boolean values to numbers"""
        if isinstance(data, dict):
            fixed = {}
            for key, value in data.items():
                fixed[key] = self._fix_booleans_for_dynamodb(value)
            return fixed
        elif isinstance(data, list):
            return [self._fix_booleans_for_dynamodb(item) for item in data]
        elif isinstance(data, bool):
            return 1 if data else 0
        else:
            return data

    def _convert_to_dynamodb_item(self, item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Convert Python dict to DynamoDB item format"""
        # First, convert all boolean values to numbers
        fixed_item = self._fix_booleans_for_dynamodb(item)
        
        result = {}
        for key, value in fixed_item.items():
            if isinstance(value, str):
                result[key] = {"S": value}
            elif isinstance(value, (int, float)):
                result[key] = {"N": str(value)}
            elif isinstance(value, bool):
                # This should not happen after fix, but just in case
                result[key] = {"N": "1" if value else "0"}
            elif isinstance(value, (list, tuple)):
                if not value:
                    # Empty list
                    result[key] = {"L": []}
                elif all(isinstance(x, str) for x in value):
                    # List of strings
                    result[key] = {"SS": value}
                elif all(isinstance(x, (int, float)) for x in value):
                    # List of numbers
                    result[key] = {"NS": [str(x) for x in value]}
                else:
                    # Mixed list
                    result[key] = {"L": [self._convert_to_dynamodb_item({"value": x})["value"] for x in value]}
            elif isinstance(value, dict):
                result[key] = {"M": self._convert_to_dynamodb_item(value)}
            elif isinstance(value, (datetime, date)):
                result[key] = {"S": value.isoformat()}
            elif value is None:
                result[key] = {"NULL": True}
            else:
                # Try to JSON serialize
                try:
                    result[key] = {"S": json.dumps(value)}
                except:
                    logger.warning(f"Failed to serialize value for key {key}: {value}")
                    result[key] = {"S": str(value)}
        
        return result
        
    def _convert_from_dynamodb_item(self, item: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Convert DynamoDB item format to Python dict"""
        if not item:
            return {}
            
        result = {}
        for key, value in item.items():
            if "S" in value:
                result[key] = value["S"]
            elif "N" in value:
                # Convert to int if possible, otherwise float
                try:
                    if "." in value["N"]:
                        result[key] = float(value["N"])
                    else:
                        result[key] = int(value["N"])
                except:
                    result[key] = float(value["N"])
            elif "BOOL" in value:
                result[key] = value["BOOL"]
            elif "NULL" in value:
                result[key] = None
            elif "L" in value:
                result[key] = [self._convert_from_dynamodb_item({"value": x})["value"] for x in value["L"]]
            elif "M" in value:
                result[key] = self._convert_from_dynamodb_item(value["M"])
            elif "SS" in value:
                result[key] = list(value["SS"])
            elif "NS" in value:
                result[key] = [int(x) if x.isdigit() else float(x) for x in value["NS"]]
            else:
                logger.warning(f"Unknown DynamoDB type for key {key}: {value}")
                result[key] = str(value)
                
        return result
    
    async def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get item from DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key
            
        Returns:
            Item or None if not found
        """
        try:
            response = self.client.get_item(
                TableName=table_name,
                Key=self._convert_to_dynamodb_item(key)
            )
            
            if "Item" not in response:
                return None
                
            return self._convert_from_dynamodb_item(response["Item"])
        except Exception as e:
            logger.error(f"Error getting item from {table_name}: {e}")
            return None
            
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
            logger.info(f"[DYNAMODB_DEBUG] Putting item to {table_name}: {item}")
            
            # Convert item for DynamoDB
            dynamodb_item = self._convert_to_dynamodb_item(item)
            logger.info(f"[DYNAMODB_DEBUG] Converted item: {dynamodb_item}")
            
            self.client.put_item(
                TableName=table_name,
                Item=dynamodb_item
            )
            
            return item
        except Exception as e:
            logger.error(f"Error putting item in {table_name}: {e}")
            logger.error(f"[DYNAMODB_DEBUG] Failed item: {item}")
            raise
            
    async def update_item(self, table_name: str, key: Dict[str, Any], 
                        updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update item in DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key
            updates: Attributes to update
            
        Returns:
            Updated item
        """
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            # Build update expression
            update_expressions = []
            expression_attribute_names = {}
            expression_attribute_values = {}
            
            # Process each update
            for attr_name, attr_value in updates.items():
                update_expressions.append(f"#{attr_name} = :{attr_name}")
                expression_attribute_names[f"#{attr_name}"] = attr_name
                
                # Convert value to DynamoDB format
                if isinstance(attr_value, str):
                    expression_attribute_values[f":{attr_name}"] = {"S": attr_value}
                elif isinstance(attr_value, (int, float)):
                    expression_attribute_values[f":{attr_name}"] = {"N": str(attr_value)}
                elif isinstance(attr_value, bool):
                    expression_attribute_values[f":{attr_name}"] = {"BOOL": attr_value}
                elif attr_value is None:
                    expression_attribute_values[f":{attr_name}"] = {"NULL": True}
                else:
                    # Use the existing conversion method for complex types
                    temp_key = f"temp_{attr_name}"
                    converted = self._convert_to_dynamodb_item({temp_key: attr_value})
                    expression_attribute_values[f":{attr_name}"] = converted[temp_key]
                
            # Create update expression
            update_expression = "SET " + ", ".join(update_expressions)
            
            # Perform update
            response = self.client.update_item(
                TableName=table_name,
                Key=self._convert_to_dynamodb_item(key),
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="ALL_NEW"
            )
            
            # Return updated item
            return self._convert_from_dynamodb_item(response["Attributes"])
        except Exception as e:
            logger.error(f"Error updating item in {table_name}: {e}")
            raise
            
    async def delete_item(self, table_name: str, key: Dict[str, Any]) -> bool:
        """
        Delete item from DynamoDB table
        
        Args:
            table_name: Table name
            key: Primary key
            
        Returns:
            True if item was deleted
        """
        try:
            self.client.delete_item(
                TableName=table_name,
                Key=self._convert_to_dynamodb_item(key)
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting item from {table_name}: {e}")
            return False
            
    async def query_items(self, table_name: str, key_condition: str,
                        expression_values: Dict[str, Any], 
                        index_name: Optional[str] = None,
                        limit: Optional[int] = None,
                        next_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Query items from DynamoDB table
        
        Args:
            table_name: Table name
            key_condition: Key condition expression
            expression_values: Expression attribute values
            index_name: Optional index name
            limit: Optional result limit
            next_token: Optional pagination token
            
        Returns:
            Query results
        """
        try:
            # Convert expression values to DynamoDB format
            dynamo_expression_values = {}
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
                "ExpressionAttributeValues": dynamo_expression_values
            }
            
            # Add optional parameters
            if index_name:
                query_params["IndexName"] = index_name
            if limit:
                query_params["Limit"] = limit
            if next_token:
                query_params["ExclusiveStartKey"] = json.loads(next_token)
                
            # Execute query
            response = self.client.query(**query_params)
            
            # Parse results
            items = [self._convert_from_dynamodb_item(item) for item in response.get("Items", [])]
            
            # Get pagination token
            pagination_token = None
            if "LastEvaluatedKey" in response:
                pagination_token = json.dumps(response["LastEvaluatedKey"])
                
            return {
                "items": items,
                "next_token": pagination_token
            }
        except Exception as e:
            logger.error(f"Error querying items from {table_name}: {e}")
            raise
            
    async def scan_items(self, table_name: str, 
                       filter_expression: Optional[str] = None,
                       expression_values: Optional[Dict[str, Any]] = None,
                       expression_attribute_names: Optional[Dict[str, str]] = None,
                       limit: Optional[int] = None,
                       next_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Scan items from DynamoDB table
        
        Args:
            table_name: Table name
            filter_expression: Optional filter expression
            expression_values: Optional expression attribute values
            limit: Optional result limit
            next_token: Optional pagination token
            
        Returns:
            Scan results
        """
        try:
            # Build scan parameters
            scan_params = {
                "TableName": table_name
            }
            
            # Add optional parameters
            if filter_expression:
                scan_params["FilterExpression"] = filter_expression
            
            if expression_values:
                # Convert expression values to DynamoDB format properly
                dynamo_expression_values = {}
                for k, v in expression_values.items():
                    if isinstance(v, str):
                        dynamo_expression_values[k] = {"S": v}
                    elif isinstance(v, (int, float)):
                        dynamo_expression_values[k] = {"N": str(v)}
                    elif isinstance(v, bool):
                        dynamo_expression_values[k] = {"BOOL": v}
                    else:
                        # Use the existing conversion method
                        converted = self._convert_to_dynamodb_item({k[1:]: v})
                        dynamo_expression_values[k] = list(converted.values())[0]
                
                scan_params["ExpressionAttributeValues"] = dynamo_expression_values
            
            if expression_attribute_names:
                scan_params["ExpressionAttributeNames"] = expression_attribute_names
                
            if limit:
                scan_params["Limit"] = limit
                
            if next_token:
                scan_params["ExclusiveStartKey"] = json.loads(next_token)
                
            # Execute scan
            response = self.client.scan(**scan_params)
            
            # Parse results
            items = [self._convert_from_dynamodb_item(item) for item in response.get("Items", [])]
            
            # Get pagination token
            pagination_token = None
            if "LastEvaluatedKey" in response:
                pagination_token = json.dumps(response["LastEvaluatedKey"])
                
            return {
                "items": items,
                "next_token": pagination_token
            }
        except Exception as e:
            logger.error(f"Error scanning items from {table_name}: {e}")
            raise
            
    async def create_table(self, table_name: str, key_schema: List[Dict[str, str]],
                         attribute_definitions: List[Dict[str, str]],
                         provisioned_throughput: Dict[str, int],
                         global_secondary_indexes: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Create DynamoDB table
        
        Args:
            table_name: Table name
            key_schema: Key schema
            attribute_definitions: Attribute definitions
            provisioned_throughput: Provisioned throughput
            global_secondary_indexes: Optional list of global secondary indexes
            
        Returns:
            True if table was created
        """
        try:
            create_params = {
                "TableName": table_name,
                "KeySchema": key_schema,
                "AttributeDefinitions": attribute_definitions,
                "ProvisionedThroughput": provisioned_throughput
            }
            
            # Add global secondary indexes if provided
            if global_secondary_indexes:
                create_params["GlobalSecondaryIndexes"] = global_secondary_indexes
            
            self.client.create_table(**create_params)
            return True
        except self.client.exceptions.ResourceInUseException:
            # Table already exists
            logger.info(f"Table {table_name} already exists")
            
            # If we have GSIs to add, try to update the table
            if global_secondary_indexes:
                try:
                    # Get existing table
                    table_description = self.client.describe_table(TableName=table_name)
                    existing_gsis = table_description.get("Table", {}).get("GlobalSecondaryIndexes", [])
                    existing_gsi_names = [gsi["IndexName"] for gsi in existing_gsis]
                    
                    # Add any missing GSIs
                    updates = []
                    for gsi in global_secondary_indexes:
                        if gsi["IndexName"] not in existing_gsi_names:
                            logger.info(f"Adding GSI {gsi['IndexName']} to table {table_name}")
                            updates.append({
                                "Create": gsi
                            })
                    
                    # Update table if we have changes
                    if updates:
                        self.client.update_table(
                            TableName=table_name,
                            AttributeDefinitions=attribute_definitions,
                            GlobalSecondaryIndexUpdates=updates
                        )
                except Exception as e:
                    logger.error(f"Error updating GSIs for table {table_name}: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Error creating table {table_name}: {e}")
            return False
            
    async def ensure_tables_exist(self) -> bool:
        """
        Ensure required DynamoDB tables exist
        
        Returns:
            True if all tables exist
        """
        tables = [
            # Agents table
            {
                "table_name": settings.AGENT_TABLE_NAME,
                "key_schema": [
                    {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    {"AttributeName": "id", "KeyType": "RANGE"}
                ],
                "attribute_definitions": [
                    {"AttributeName": "tenant_id", "AttributeType": "S"},
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"},
                    {"AttributeName": "type", "AttributeType": "S"}
                ],
                "provisioned_throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "global_secondary_indexes": [
                    # Index for querying agents by type
                    {
                        "IndexName": "TenantTypeIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "type", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    },
                    # Index for querying agents by status
                    {
                        "IndexName": "TenantStatusIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "status", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ]
            },
            # SSH keys table
            {
                "table_name": settings.SSH_KEY_TABLE_NAME,
                "key_schema": [
                    {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    {"AttributeName": "id", "KeyType": "RANGE"}
                ],
                "attribute_definitions": [
                    {"AttributeName": "tenant_id", "AttributeType": "S"},
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "agent_id", "AttributeType": "S"},
                    {"AttributeName": "key_type", "AttributeType": "S"}
                ],
                "provisioned_throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "global_secondary_indexes": [
                    # Index for querying keys by agent
                    {
                        "IndexName": "TenantAgentIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "agent_id", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    },
                    # Index for querying keys by type
                    {
                        "IndexName": "TenantKeyTypeIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "key_type", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ]
            },
            # Channels table
            {
                "table_name": settings.CHANNEL_TABLE_NAME,
                "key_schema": [
                    {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    {"AttributeName": "id", "KeyType": "RANGE"}
                ],
                "attribute_definitions": [
                    {"AttributeName": "tenant_id", "AttributeType": "S"},
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"}
                ],
                "provisioned_throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "global_secondary_indexes": [
                    # Index for querying channels by status
                    {
                        "IndexName": "TenantStatusIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "status", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ]
            },
            # Tenants table
            {
                "table_name": settings.TENANT_TABLE_NAME,
                "key_schema": [
                    {"AttributeName": "id", "KeyType": "HASH"}
                ],
                "attribute_definitions": [
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"}
                ],
                "provisioned_throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "global_secondary_indexes": [
                    # Index for querying tenants by status
                    {
                        "IndexName": "StatusIndex",
                        "KeySchema": [
                            {"AttributeName": "status", "KeyType": "HASH"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ]
            },
            # Usage metrics table
            {
                "table_name": settings.USAGE_METRICS_TABLE_NAME,
                "key_schema": [
                    {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    {"AttributeName": "date", "KeyType": "RANGE"}
                ],
                "attribute_definitions": [
                    {"AttributeName": "tenant_id", "AttributeType": "S"},
                    {"AttributeName": "date", "AttributeType": "S"},
                    {"AttributeName": "metric_type", "AttributeType": "S"}
                ],
                "provisioned_throughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                },
                "global_secondary_indexes": [
                    # Index for querying usage by metric type and tenant
                    {
                        "IndexName": "TenantMetricTypeIndex",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                            {"AttributeName": "metric_type", "KeyType": "RANGE"}
                        ],
                        "Projection": {
                            "ProjectionType": "ALL"
                        },
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ]
            }
        ]
        
        # Create tables
        success = True
        for table in tables:
            result = await self.create_table(
                table_name=table["table_name"],
                key_schema=table["key_schema"],
                attribute_definitions=table["attribute_definitions"],
                provisioned_throughput=table["provisioned_throughput"],
                global_secondary_indexes=table.get("global_secondary_indexes")
            )
            if not result:
                success = False
                
        return success


# Singleton instance
dynamodb = DynamoDBService()