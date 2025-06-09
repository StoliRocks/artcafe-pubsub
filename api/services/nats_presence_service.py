"""
NATS Presence Service for tracking client connections and heartbeats.
Handles direct NATS client status updates without WebSocket.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Set
from nats.aio.msg import Msg

from api.services.client_service import client_service
from api.services.websocket_connection_service import WebSocketConnectionService
from api.db.dynamodb import DynamoDBService
from core.nats_client import nats_manager
from config.settings import settings

logger = logging.getLogger(__name__)


class NATSPresenceService:
    """
    Monitors NATS client presence through heartbeat messages.
    Updates client status in DynamoDB for dashboard visibility.
    """
    
    def __init__(self):
        self.db = DynamoDBService()
        self.ws_service = WebSocketConnectionService()
        self.running = False
        self.heartbeat_timeout = 90  # seconds
        self.cleanup_interval = 30  # seconds
        self.active_clients: Dict[str, datetime] = {}  # client_id -> last_heartbeat
        self._subscription = None
    
    async def start(self):
        """Start the presence monitoring service"""
        try:
            logger.info("Starting NATS Presence Service")
            
            # Subscribe to presence messages
            self._subscription = await nats_manager.subscribe(
                "_PRESENCE.>",
                callback=self._handle_presence_message
            )
            
            # Start cleanup task
            self.running = True
            asyncio.create_task(self._cleanup_loop())
            
            logger.info("NATS Presence Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start NATS Presence Service: {e}")
            raise
    
    async def stop(self):
        """Stop the presence monitoring service"""
        logger.info("Stopping NATS Presence Service")
        self.running = False
        
        if self._subscription:
            await self._subscription.unsubscribe()
            self._subscription = None
        
        logger.info("NATS Presence Service stopped")
    
    async def _handle_presence_message(self, msg: Msg):
        """Handle incoming presence messages"""
        try:
            # Parse subject: _PRESENCE.tenant.{tenant_id}.client.{client_id}
            parts = msg.subject.split('.')
            if len(parts) != 5 or parts[0] != '_PRESENCE':
                logger.warning(f"Invalid presence subject: {msg.subject}")
                return
            
            tenant_id = parts[2]
            client_id = parts[4]
            
            # Parse message data
            try:
                data = json.loads(msg.data.decode())
            except:
                logger.error(f"Invalid presence message data from {client_id}")
                return
            
            message_type = data.get('type', 'heartbeat')
            
            if message_type == 'heartbeat':
                await self._handle_heartbeat(tenant_id, client_id, data)
            elif message_type == 'connect':
                await self._handle_connect(tenant_id, client_id, data)
            elif message_type == 'disconnect':
                await self._handle_disconnect(tenant_id, client_id, data)
            else:
                logger.warning(f"Unknown presence message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Error handling presence message: {e}")
    
    async def _handle_heartbeat(self, tenant_id: str, client_id: str, data: Dict):
        """Handle client heartbeat"""
        try:
            # Update last heartbeat time
            now = datetime.now(timezone.utc)
            self.active_clients[client_id] = now
            
            # Update client status in database
            await self._update_client_status(tenant_id, client_id, "online", data.get('metadata', {}))
            
            # Register in WebSocket connection service for unified view
            await self.ws_service.register_connection(
                connection_id=f"nats-{client_id}",
                connection_type="client",
                tenant_id=tenant_id,
                metadata={
                    "connection_method": "nats",
                    "client_name": data.get('metadata', {}).get('name', 'Unknown'),
                    "last_heartbeat": now.isoformat()
                }
            )
            
            logger.debug(f"Heartbeat received from client {client_id}")
            
        except Exception as e:
            logger.error(f"Error handling heartbeat for {client_id}: {e}")
    
    async def _handle_connect(self, tenant_id: str, client_id: str, data: Dict):
        """Handle client connection"""
        try:
            logger.info(f"NATS client {client_id} connected")
            
            # Set initial heartbeat
            self.active_clients[client_id] = datetime.now(timezone.utc)
            
            # Update status
            await self._update_client_status(tenant_id, client_id, "online", data.get('metadata', {}))
            
            # Register connection
            await self.ws_service.register_connection(
                connection_id=f"nats-{client_id}",
                connection_type="client",
                tenant_id=tenant_id,
                metadata={
                    "connection_method": "nats",
                    "client_name": data.get('metadata', {}).get('name', 'Unknown'),
                    "connected_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling connect for {client_id}: {e}")
    
    async def _handle_disconnect(self, tenant_id: str, client_id: str, data: Dict):
        """Handle client disconnection"""
        try:
            logger.info(f"NATS client {client_id} disconnected")
            
            # Remove from active clients
            self.active_clients.pop(client_id, None)
            
            # Update status
            await self._update_client_status(tenant_id, client_id, "offline")
            
            # Unregister connection
            await self.ws_service.unregister_connection(f"nats-{client_id}")
            
        except Exception as e:
            logger.error(f"Error handling disconnect for {client_id}: {e}")
    
    async def _update_client_status(self, tenant_id: str, client_id: str, status: str, metadata: Optional[Dict] = None):
        """Update client status in database"""
        try:
            # Update in clients table
            update_data = {
                "status": status,
                "last_seen": datetime.now(timezone.utc).isoformat()
            }
            
            if status == "online":
                update_data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
                
            if metadata:
                update_data["connection_metadata"] = metadata
            
            # Use DynamoDB service to update
            self.db.update_item(
                table_name="artcafe-clients",
                key={"client_id": client_id},
                update_data=update_data
            )
            
            logger.info(f"Updated client {client_id} status to {status}")
            
        except Exception as e:
            logger.error(f"Failed to update client status: {e}")
    
    async def _cleanup_loop(self):
        """Periodically check for stale clients"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                now = datetime.now(timezone.utc)
                timeout_threshold = now - timedelta(seconds=self.heartbeat_timeout)
                
                # Find stale clients
                stale_clients = []
                for client_id, last_heartbeat in self.active_clients.items():
                    if last_heartbeat < timeout_threshold:
                        stale_clients.append(client_id)
                
                # Mark stale clients as offline
                for client_id in stale_clients:
                    logger.warning(f"Client {client_id} timed out (no heartbeat)")
                    
                    # Remove from active list
                    self.active_clients.pop(client_id, None)
                    
                    # We don't have tenant_id here, so we need to look it up
                    # For now, just unregister from connection service
                    await self.ws_service.unregister_connection(f"nats-{client_id}")
                    
                    # TODO: Look up tenant_id and update client status to offline
                
                if stale_clients:
                    logger.info(f"Cleaned up {len(stale_clients)} stale clients")
                    
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def get_active_clients(self) -> Dict[str, str]:
        """Get currently active NATS clients"""
        return {
            client_id: last_hb.isoformat()
            for client_id, last_hb in self.active_clients.items()
        }


# Global instance
nats_presence_service = NATSPresenceService()