"""
WebSocket Connection Service using DynamoDB for distributed state management.
Implements Phase 1 of the scaling architecture.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Set
import boto3
from boto3.dynamodb.conditions import Key, Attr
import ulid

from api.db.dynamodb import get_dynamodb_client

logger = logging.getLogger(__name__)


class WebSocketConnectionService:
    """Manages WebSocket connections using DynamoDB for distributed state."""
    
    def __init__(self, server_id: str = None):
        self.dynamodb = get_dynamodb_client()
        self.table_name = "artcafe-websocket-connections"
        self.table = self.dynamodb.Table(self.table_name)
        
        # Generate a unique server ID if not provided
        self.server_id = server_id or f"server-{ulid.new().str}"
        
        # TTL for connections (24 hours)
        self.connection_ttl_hours = 24
        
        logger.info(f"WebSocketConnectionService initialized with server_id: {self.server_id}")
    
    def register_connection(
        self,
        connection_id: str,
        connection_type: str,  # "agent" or "dashboard"
        tenant_id: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Register a new WebSocket connection in DynamoDB."""
        try:
            now = datetime.now(timezone.utc)
            ttl = int((now + timedelta(hours=self.connection_ttl_hours)).timestamp())
            
            item = {
                "pk": f"CONN#{connection_id}",
                "sk": "META",
                "connection_id": connection_id,
                "connection_type": connection_type,
                "tenant_id": tenant_id,
                "server_id": self.server_id,
                "connected_at": now.isoformat(),
                "last_heartbeat": now.isoformat(),
                "ttl": ttl,
                "metadata": metadata or {}
            }
            
            self.table.put_item(Item=item)
            
            # Also create an entry for quick lookup by tenant
            tenant_item = {
                "pk": f"TENANT#{tenant_id}",
                "sk": f"CONN#{connection_type}#{connection_id}",
                "connection_id": connection_id,
                "server_id": self.server_id,
                "connected_at": now.isoformat(),
                "ttl": ttl
            }
            self.table.put_item(Item=tenant_item)
            
            logger.info(f"Registered {connection_type} connection {connection_id} for tenant {tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register connection {connection_id}: {e}")
            return False
    
    def unregister_connection(self, connection_id: str) -> bool:
        """Remove a WebSocket connection from DynamoDB."""
        try:
            # First get the connection details
            response = self.table.get_item(
                Key={"pk": f"CONN#{connection_id}", "sk": "META"}
            )
            
            if "Item" not in response:
                logger.warning(f"Connection {connection_id} not found")
                return False
            
            conn_data = response["Item"]
            tenant_id = conn_data["tenant_id"]
            connection_type = conn_data["connection_type"]
            
            # Delete the main connection record
            self.table.delete_item(
                Key={"pk": f"CONN#{connection_id}", "sk": "META"}
            )
            
            # Delete the tenant lookup record
            self.table.delete_item(
                Key={
                    "pk": f"TENANT#{tenant_id}",
                    "sk": f"CONN#{connection_type}#{connection_id}"
                }
            )
            
            # Clean up any subscription records
            self._cleanup_subscriptions(connection_id)
            
            logger.info(f"Unregistered connection {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister connection {connection_id}: {e}")
            return False
    
    def update_heartbeat(self, connection_id: str) -> bool:
        """Update the last heartbeat timestamp for a connection."""
        try:
            now = datetime.now(timezone.utc)
            
            self.table.update_item(
                Key={"pk": f"CONN#{connection_id}", "sk": "META"},
                UpdateExpression="SET last_heartbeat = :heartbeat",
                ExpressionAttributeValues={
                    ":heartbeat": now.isoformat()
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update heartbeat for {connection_id}: {e}")
            return False
    
    def get_connection(self, connection_id: str) -> Optional[Dict]:
        """Get connection details from DynamoDB."""
        try:
            response = self.table.get_item(
                Key={"pk": f"CONN#{connection_id}", "sk": "META"}
            )
            
            if "Item" in response:
                return response["Item"]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get connection {connection_id}: {e}")
            return None
    
    def get_tenant_connections(
        self, 
        tenant_id: str, 
        connection_type: Optional[str] = None
    ) -> List[Dict]:
        """Get all connections for a tenant, optionally filtered by type."""
        try:
            if connection_type:
                # Query for specific connection type
                response = self.table.query(
                    KeyConditionExpression=Key("pk").eq(f"TENANT#{tenant_id}") & 
                                         Key("sk").begins_with(f"CONN#{connection_type}#")
                )
            else:
                # Query for all connections
                response = self.table.query(
                    KeyConditionExpression=Key("pk").eq(f"TENANT#{tenant_id}")
                )
            
            connections = []
            for item in response.get("Items", []):
                # Fetch full connection details
                conn_id = item["connection_id"]
                conn_details = self.get_connection(conn_id)
                if conn_details:
                    connections.append(conn_details)
            
            return connections
            
        except Exception as e:
            logger.error(f"Failed to get tenant connections for {tenant_id}: {e}")
            return []
    
    def get_server_connections(self, server_id: Optional[str] = None) -> List[Dict]:
        """Get all connections for a specific server (or current server)."""
        try:
            target_server = server_id or self.server_id
            
            response = self.table.query(
                IndexName="ServerIndex",
                KeyConditionExpression=Key("server_id").eq(target_server)
            )
            
            return response.get("Items", [])
            
        except Exception as e:
            logger.error(f"Failed to get server connections for {target_server}: {e}")
            return []
    
    def add_subscription(self, connection_id: str, topic: str) -> bool:
        """Add a topic subscription for a connection."""
        try:
            now = datetime.now(timezone.utc)
            ttl = int((now + timedelta(hours=self.connection_ttl_hours)).timestamp())
            
            item = {
                "pk": f"SUB#{topic}",
                "sk": f"CONN#{connection_id}",
                "connection_id": connection_id,
                "server_id": self.server_id,
                "subscribed_at": now.isoformat(),
                "ttl": ttl
            }
            
            self.table.put_item(Item=item)
            
            logger.info(f"Added subscription to {topic} for connection {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add subscription: {e}")
            return False
    
    def remove_subscription(self, connection_id: str, topic: str) -> bool:
        """Remove a topic subscription for a connection."""
        try:
            self.table.delete_item(
                Key={"pk": f"SUB#{topic}", "sk": f"CONN#{connection_id}"}
            )
            
            logger.info(f"Removed subscription to {topic} for connection {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove subscription: {e}")
            return False
    
    def get_topic_subscribers(self, topic: str) -> List[Dict]:
        """Get all connections subscribed to a topic."""
        try:
            response = self.table.query(
                KeyConditionExpression=Key("pk").eq(f"SUB#{topic}")
            )
            
            subscribers = []
            for item in response.get("Items", []):
                # Include server_id so we know which server handles this connection
                subscribers.append({
                    "connection_id": item["connection_id"],
                    "server_id": item["server_id"]
                })
            
            return subscribers
            
        except Exception as e:
            logger.error(f"Failed to get subscribers for topic {topic}: {e}")
            return []
    
    def _cleanup_subscriptions(self, connection_id: str):
        """Clean up all subscriptions for a connection."""
        try:
            # This is a bit inefficient but necessary with current schema
            # In production, might want to maintain a reverse index
            response = self.table.scan(
                FilterExpression=Attr("sk").eq(f"CONN#{connection_id}") & 
                                Attr("pk").begins_with("SUB#")
            )
            
            for item in response.get("Items", []):
                self.table.delete_item(
                    Key={"pk": item["pk"], "sk": item["sk"]}
                )
            
        except Exception as e:
            logger.error(f"Failed to cleanup subscriptions for {connection_id}: {e}")
    
    def cleanup_stale_connections(self, hours: int = 24) -> int:
        """Clean up connections older than specified hours."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Scan for stale connections (this could be optimized with a GSI)
            response = self.table.scan(
                FilterExpression=Attr("pk").begins_with("CONN#") & 
                                Attr("last_heartbeat").lt(cutoff_time.isoformat())
            )
            
            cleaned = 0
            for item in response.get("Items", []):
                if "connection_id" in item:
                    if self.unregister_connection(item["connection_id"]):
                        cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} stale connections")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup stale connections: {e}")
            return 0
    
    def get_connection_stats(self) -> Dict:
        """Get statistics about current connections."""
        try:
            # Get counts by server
            server_stats = {}
            response = self.table.scan(
                FilterExpression=Attr("pk").begins_with("CONN#") & 
                                Attr("sk").eq("META")
            )
            
            total_connections = 0
            connections_by_type = {"agent": 0, "dashboard": 0}
            connections_by_tenant = {}
            
            for item in response.get("Items", []):
                total_connections += 1
                
                server_id = item.get("server_id", "unknown")
                if server_id not in server_stats:
                    server_stats[server_id] = 0
                server_stats[server_id] += 1
                
                conn_type = item.get("connection_type", "unknown")
                if conn_type in connections_by_type:
                    connections_by_type[conn_type] += 1
                
                tenant_id = item.get("tenant_id", "unknown")
                if tenant_id not in connections_by_tenant:
                    connections_by_tenant[tenant_id] = 0
                connections_by_tenant[tenant_id] += 1
            
            return {
                "total_connections": total_connections,
                "connections_by_type": connections_by_type,
                "connections_by_server": server_stats,
                "unique_tenants": len(connections_by_tenant),
                "connections_by_tenant": connections_by_tenant
            }
            
        except Exception as e:
            logger.error(f"Failed to get connection stats: {e}")
            return {}