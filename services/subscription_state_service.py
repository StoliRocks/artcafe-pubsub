"""
Subscription State Management Service

Handles agent channel subscriptions and online/offline state tracking
with heartbeat monitoring.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import logging
from boto3.dynamodb.conditions import Key, Attr

from api.db.dynamodb import get_dynamodb_resource
from models.channel_subscription import ChannelSubscription

logger = logging.getLogger(__name__)

class SubscriptionStateService:
    """Manages agent subscription states and heartbeats"""
    
    def __init__(self, server_id: str = "ws-01", heartbeat_timeout: int = 120):
        self.server_id = server_id
        self.heartbeat_timeout = heartbeat_timeout
        self.dynamodb = get_dynamodb_resource()
        self.subscriptions_table = self.dynamodb.Table('artcafe-channel-subscriptions')
        
        # In-memory cache for performance
        self._active_connections: Dict[str, Dict] = {}  # agent_id -> connection info
        self._channel_subscribers: Dict[str, Set[str]] = {}  # channel_id -> set of agent_ids
        
        # Start heartbeat monitor
        self._heartbeat_task = None
        
    async def start(self):
        """Start the heartbeat monitoring task"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        logger.info(f"Subscription state service started on server {self.server_id}")
        
    async def stop(self):
        """Stop the heartbeat monitoring task"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
        
        # Mark all connections as offline
        for agent_id in list(self._active_connections.keys()):
            await self.on_agent_disconnect(agent_id)
            
    async def on_agent_connect(self, agent_id: str, websocket_id: str, tenant_id: str) -> List[str]:
        """
        Handle agent connection - update subscription states and return subscribed channels
        
        Returns:
            List of channel IDs the agent is subscribed to
        """
        try:
            # Store connection info
            self._active_connections[agent_id] = {
                'websocket_id': websocket_id,
                'tenant_id': tenant_id,
                'connected_at': datetime.now(timezone.utc).isoformat(),
                'last_heartbeat': time.time()
            }
            
            # Get all subscriptions for this agent
            response = self.subscriptions_table.query(
                IndexName='agent-index',
                KeyConditionExpression=Key('agent_id').eq(agent_id)
            )
            
            subscribed_channels = []
            
            # Update each subscription to online state
            for item in response.get('Items', []):
                channel_id = item['channel_id']
                
                # Update subscription state
                self.subscriptions_table.update_item(
                    Key={
                        'channel_id': channel_id,
                        'agent_id': agent_id
                    },
                    UpdateExpression='SET #state = :state, websocket_id = :ws_id, server_id = :server_id, connected_at = :connected_at, last_heartbeat = :heartbeat',
                    ExpressionAttributeNames={
                        '#state': 'state'
                    },
                    ExpressionAttributeValues={
                        ':state': 'online',
                        ':ws_id': websocket_id,
                        ':server_id': self.server_id,
                        ':connected_at': datetime.now(timezone.utc).isoformat(),
                        ':heartbeat': datetime.now(timezone.utc).isoformat()
                    }
                )
                
                # Update in-memory cache
                if channel_id not in self._channel_subscribers:
                    self._channel_subscribers[channel_id] = set()
                self._channel_subscribers[channel_id].add(agent_id)
                
                subscribed_channels.append(channel_id)
                
            logger.info(f"Agent {agent_id} connected with {len(subscribed_channels)} channel subscriptions")
            return subscribed_channels
            
        except Exception as e:
            logger.error(f"Error handling agent connection: {e}")
            return []
            
    async def on_agent_disconnect(self, agent_id: str):
        """Handle agent disconnection - update all subscriptions to offline"""
        try:
            # Remove from active connections
            if agent_id in self._active_connections:
                del self._active_connections[agent_id]
            
            # Get all subscriptions for this agent
            response = self.subscriptions_table.query(
                IndexName='agent-index',
                KeyConditionExpression=Key('agent_id').eq(agent_id)
            )
            
            # Update each subscription to offline state
            for item in response.get('Items', []):
                channel_id = item['channel_id']
                
                self.subscriptions_table.update_item(
                    Key={
                        'channel_id': channel_id,
                        'agent_id': agent_id
                    },
                    UpdateExpression='SET #state = :state, websocket_id = :null, disconnected_at = :disconnected_at',
                    ExpressionAttributeNames={
                        '#state': 'state'
                    },
                    ExpressionAttributeValues={
                        ':state': 'offline',
                        ':null': None,
                        ':disconnected_at': datetime.now(timezone.utc).isoformat()
                    }
                )
                
                # Update in-memory cache
                if channel_id in self._channel_subscribers:
                    self._channel_subscribers[channel_id].discard(agent_id)
                    
            logger.info(f"Agent {agent_id} disconnected")
            
        except Exception as e:
            logger.error(f"Error handling agent disconnection: {e}")
            
    async def on_heartbeat(self, agent_id: str, data: Optional[Dict] = None):
        """Update agent heartbeat timestamp"""
        if agent_id in self._active_connections:
            self._active_connections[agent_id]['last_heartbeat'] = time.time()
            
            # Update database
            try:
                response = self.subscriptions_table.query(
                    IndexName='agent-index',
                    KeyConditionExpression=Key('agent_id').eq(agent_id)
                )
                
                for item in response.get('Items', []):
                    self.subscriptions_table.update_item(
                        Key={
                            'channel_id': item['channel_id'],
                            'agent_id': agent_id
                        },
                        UpdateExpression='SET last_heartbeat = :heartbeat',
                        ExpressionAttributeValues={
                            ':heartbeat': datetime.now(timezone.utc).isoformat()
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Error updating heartbeat for agent {agent_id}: {e}")
                
    async def get_channel_subscribers(self, channel_id: str, online_only: bool = True) -> List[Dict]:
        """
        Get all subscribers for a channel
        
        Args:
            channel_id: The channel ID
            online_only: If True, only return online subscribers
            
        Returns:
            List of subscriber info dictionaries
        """
        try:
            if online_only and channel_id in self._channel_subscribers:
                # Use cache for online subscribers
                subscribers = []
                for agent_id in self._channel_subscribers[channel_id]:
                    if agent_id in self._active_connections:
                        subscribers.append({
                            'agent_id': agent_id,
                            'websocket_id': self._active_connections[agent_id]['websocket_id'],
                            'server_id': self.server_id
                        })
                return subscribers
            else:
                # Query database
                response = self.subscriptions_table.query(
                    KeyConditionExpression=Key('channel_id').eq(channel_id)
                )
                
                subscribers = []
                for item in response.get('Items', []):
                    if not online_only or item.get('state') == 'online':
                        subscribers.append({
                            'agent_id': item['agent_id'],
                            'websocket_id': item.get('websocket_id'),
                            'server_id': item.get('server_id'),
                            'state': item.get('state', 'offline')
                        })
                        
                return subscribers
                
        except Exception as e:
            logger.error(f"Error getting channel subscribers: {e}")
            return []
            
    async def add_subscription(self, channel_id: str, agent_id: str, tenant_id: str):
        """Add a new channel subscription"""
        try:
            # Check if agent is online
            is_online = agent_id in self._active_connections
            
            item = {
                'channel_id': channel_id,
                'agent_id': agent_id,
                'tenant_id': tenant_id,
                'state': 'online' if is_online else 'offline',
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            if is_online:
                item.update({
                    'websocket_id': self._active_connections[agent_id]['websocket_id'],
                    'server_id': self.server_id,
                    'connected_at': datetime.now(timezone.utc).isoformat()
                })
                
                # Update cache
                if channel_id not in self._channel_subscribers:
                    self._channel_subscribers[channel_id] = set()
                self._channel_subscribers[channel_id].add(agent_id)
                
            self.subscriptions_table.put_item(Item=item)
            logger.info(f"Added subscription: agent {agent_id} to channel {channel_id}")
            
        except Exception as e:
            logger.error(f"Error adding subscription: {e}")
            raise
            
    async def remove_subscription(self, channel_id: str, agent_id: str):
        """Remove a channel subscription"""
        try:
            self.subscriptions_table.delete_item(
                Key={
                    'channel_id': channel_id,
                    'agent_id': agent_id
                }
            )
            
            # Update cache
            if channel_id in self._channel_subscribers:
                self._channel_subscribers[channel_id].discard(agent_id)
                
            logger.info(f"Removed subscription: agent {agent_id} from channel {channel_id}")
            
        except Exception as e:
            logger.error(f"Error removing subscription: {e}")
            raise
            
    async def _heartbeat_monitor(self):
        """Monitor heartbeats and disconnect stale connections"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = time.time()
                stale_agents = []
                
                # Check for stale connections
                for agent_id, info in self._active_connections.items():
                    last_heartbeat = info.get('last_heartbeat', 0)
                    if current_time - last_heartbeat > self.heartbeat_timeout:
                        stale_agents.append(agent_id)
                        
                # Disconnect stale agents
                for agent_id in stale_agents:
                    logger.warning(f"Agent {agent_id} heartbeat timeout - marking as offline")
                    await self.on_agent_disconnect(agent_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                
# Global instance
subscription_service = SubscriptionStateService()