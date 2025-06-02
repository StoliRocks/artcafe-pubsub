"""
Scalable heartbeat monitoring service for WebSocket connections.
Uses DynamoDB for distributed heartbeat tracking across multiple servers.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Set
import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)


class ConnectionHeartbeatService:
    """
    Manages connection heartbeats using DynamoDB for horizontal scaling.
    
    This service ensures that agent status accurately reflects their actual
    availability by requiring periodic heartbeats. Works across multiple
    servers without coordination.
    """
    
    def __init__(self, 
                 heartbeat_interval_seconds: int = 30,
                 heartbeat_timeout_seconds: int = 90,
                 cleanup_interval_seconds: int = 300):  # 5 minutes instead of 60 seconds
        """
        Initialize the heartbeat service.
        
        Args:
            heartbeat_interval_seconds: Expected interval between heartbeats
            heartbeat_timeout_seconds: Time after which a connection is considered stale
            cleanup_interval_seconds: How often to run the cleanup task
        """
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        self.connections_table = self.dynamodb.Table('artcafe-websocket-connections')
        self.agents_table = self.dynamodb.Table('artcafe-agents')
        
        self.heartbeat_interval = heartbeat_interval_seconds
        self.heartbeat_timeout = heartbeat_timeout_seconds
        self.cleanup_interval = cleanup_interval_seconds
        
        # Task reference for cleanup
        self._cleanup_task = None
        
        logger.info(f"HeartbeatService initialized: interval={heartbeat_interval_seconds}s, timeout={heartbeat_timeout_seconds}s")
    
    async def record_heartbeat(self, connection_id: str, connection_type: str = "agent") -> bool:
        """
        Record a heartbeat for a connection.
        
        Args:
            connection_id: The connection (agent or dashboard) ID
            connection_type: Type of connection ("agent" or "dashboard")
            
        Returns:
            bool: True if heartbeat was recorded successfully
        """
        try:
            now = datetime.now(timezone.utc)
            
            # Update the heartbeat timestamp
            response = self.connections_table.update_item(
                Key={
                    'pk': f'CONN#{connection_id}',
                    'sk': 'META'
                },
                UpdateExpression='SET last_heartbeat = :heartbeat, last_heartbeat_epoch = :epoch',
                ExpressionAttributeValues={
                    ':heartbeat': now.isoformat(),
                    ':epoch': int(now.timestamp())
                },
                ConditionExpression='attribute_exists(pk)',
                ReturnValues='ALL_NEW'
            )
            
            # If this is an agent, check if we need to update status to online
            if connection_type == "agent":
                item = response.get('Attributes', {})
                tenant_id = item.get('tenant_id')
                
                if tenant_id:
                    # Check current agent status
                    agent_response = self.agents_table.get_item(
                        Key={
                            'tenant_id': tenant_id,
                            'agent_id': connection_id
                        }
                    )
                    
                    agent = agent_response.get('Item', {})
                    current_status = agent.get('status', 'offline')
                    
                    # Update to online if not already
                    if current_status != 'online':
                        await self._update_agent_status(tenant_id, connection_id, 'online')
                        logger.info(f"Agent {connection_id} marked online after heartbeat")
            
            logger.debug(f"Heartbeat recorded for {connection_type} {connection_id}")
            return True
            
        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"Connection {connection_id} not found for heartbeat")
            return False
        except Exception as e:
            logger.error(f"Failed to record heartbeat for {connection_id}: {e}")
            return False
    
    async def check_stale_connections(self) -> List[Dict]:
        """
        Find all connections that haven't sent a heartbeat within the timeout period.
        
        Returns:
            List of stale connections
        """
        try:
            now = datetime.now(timezone.utc)
            timeout_epoch = int((now - timedelta(seconds=self.heartbeat_timeout)).timestamp())
            
            # Scan for connections with stale heartbeats
            # In production, consider using a GSI on last_heartbeat_epoch for better performance
            response = self.connections_table.scan(
                FilterExpression=(
                    Attr('pk').begins_with('CONN#') & 
                    Attr('sk').eq('META') &
                    (Attr('last_heartbeat_epoch').lt(timeout_epoch) | 
                     Attr('last_heartbeat_epoch').not_exists())
                )
            )
            
            stale_connections = response.get('Items', [])
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.connections_table.scan(
                    FilterExpression=(
                        Attr('pk').begins_with('CONN#') & 
                        Attr('sk').eq('META') &
                        (Attr('last_heartbeat_epoch').lt(timeout_epoch) | 
                         Attr('last_heartbeat_epoch').not_exists())
                    ),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                stale_connections.extend(response.get('Items', []))
            
            logger.info(f"Found {len(stale_connections)} stale connections")
            return stale_connections
            
        except Exception as e:
            logger.error(f"Failed to check stale connections: {e}")
            return []
    
    async def cleanup_stale_connections(self) -> int:
        """
        Clean up stale connections and update agent statuses.
        
        Returns:
            Number of connections cleaned up
        """
        try:
            stale_connections = await self.check_stale_connections()
            cleaned_count = 0
            
            for conn in stale_connections:
                connection_id = conn.get('connection_id')
                connection_type = conn.get('connection_type')
                tenant_id = conn.get('tenant_id')
                server_id = conn.get('server_id')
                last_heartbeat = conn.get('last_heartbeat', 'Never')
                
                logger.warning(
                    f"Cleaning up stale {connection_type} connection: {connection_id} "
                    f"(tenant: {tenant_id}, server: {server_id}, last heartbeat: {last_heartbeat})"
                )
                
                # Remove the connection record
                try:
                    # Delete main connection record
                    self.connections_table.delete_item(
                        Key={
                            'pk': f'CONN#{connection_id}',
                            'sk': 'META'
                        }
                    )
                    
                    # Delete tenant lookup record
                    if tenant_id and connection_type:
                        self.connections_table.delete_item(
                            Key={
                                'pk': f'TENANT#{tenant_id}',
                                'sk': f'CONN#{connection_type}#{connection_id}'
                            }
                        )
                    
                    # Update agent status to offline
                    if connection_type == 'agent' and tenant_id:
                        await self._update_agent_status(tenant_id, connection_id, 'offline')
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup connection {connection_id}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale connections")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed during cleanup: {e}")
            return 0
    
    async def _update_agent_status(self, tenant_id: str, agent_id: str, status: str):
        """Update agent status in DynamoDB and publish to NATS."""
        try:
            # Update in DynamoDB
            self.agents_table.update_item(
                Key={
                    'tenant_id': tenant_id,
                    'agent_id': agent_id
                },
                UpdateExpression='SET #status = :status, last_seen = :last_seen',
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': status,
                    ':last_seen': datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Publish status change event
            # This will be picked up by the main app if NATS is available
            try:
                from nats_client import nats_manager
                if nats_manager and nats_manager.is_connected:
                    event = {
                        'type': 'agent.status_changed',
                        'agent_id': agent_id,
                        'tenant_id': tenant_id,
                        'status': status,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    await nats_manager.publish(f'agents.{tenant_id}.events', event)
            except:
                # NATS publish is best-effort
                pass
                
        except Exception as e:
            logger.error(f"Failed to update agent status: {e}")
    
    async def start_cleanup_task(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Started heartbeat cleanup task")
    
    async def stop_cleanup_task(self):
        """Stop the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped heartbeat cleanup task")
    
    async def _cleanup_loop(self):
        """Background task that periodically cleans up stale connections."""
        logger.info(f"Heartbeat cleanup task started (runs every {self.cleanup_interval}s)")
        
        while True:
            try:
                # Wait for the cleanup interval
                await asyncio.sleep(self.cleanup_interval)
                
                # Run cleanup
                await self.cleanup_stale_connections()
                
            except asyncio.CancelledError:
                logger.info("Heartbeat cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                # Continue running even if there's an error
                await asyncio.sleep(self.cleanup_interval)
    
    def get_heartbeat_stats(self) -> Dict:
        """Get statistics about heartbeats and connections."""
        try:
            now = datetime.now(timezone.utc)
            warning_epoch = int((now - timedelta(seconds=self.heartbeat_interval * 2)).timestamp())
            timeout_epoch = int((now - timedelta(seconds=self.heartbeat_timeout)).timestamp())
            
            # Get all connections
            response = self.connections_table.scan(
                FilterExpression=Attr('pk').begins_with('CONN#') & Attr('sk').eq('META')
            )
            
            connections = response.get('Items', [])
            
            stats = {
                'total_connections': len(connections),
                'healthy_connections': 0,
                'warning_connections': 0,
                'stale_connections': 0,
                'by_type': {'agent': 0, 'dashboard': 0},
                'by_server': {}
            }
            
            for conn in connections:
                conn_type = conn.get('connection_type', 'unknown')
                server_id = conn.get('server_id', 'unknown')
                heartbeat_epoch = conn.get('last_heartbeat_epoch', 0)
                
                # Count by type
                if conn_type in stats['by_type']:
                    stats['by_type'][conn_type] += 1
                
                # Count by server
                if server_id not in stats['by_server']:
                    stats['by_server'][server_id] = 0
                stats['by_server'][server_id] += 1
                
                # Categorize by heartbeat health
                if heartbeat_epoch > warning_epoch:
                    stats['healthy_connections'] += 1
                elif heartbeat_epoch > timeout_epoch:
                    stats['warning_connections'] += 1
                else:
                    stats['stale_connections'] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get heartbeat stats: {e}")
            return {}


# Global instance for easy access
heartbeat_service = ConnectionHeartbeatService()