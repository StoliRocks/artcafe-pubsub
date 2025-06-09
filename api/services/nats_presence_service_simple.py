"""
Simple NATS Presence Service for tracking client heartbeats.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict
from nats.aio.msg import Msg

from core.nats_client import nats_manager

logger = logging.getLogger(__name__)


class NATSPresenceService:
    """Simple presence monitoring via NATS heartbeats"""
    
    def __init__(self):
        self.running = False
        self.active_clients: Dict[str, dict] = {}
        self._subscription = None
    
    async def start(self):
        """Start monitoring presence messages"""
        try:
            logger.info("Starting NATS Presence Service")
            
            # Subscribe to presence messages
            self._subscription = await nats_manager.subscribe(
                "_PRESENCE.>",
                callback=self._handle_presence
            )
            
            self.running = True
            logger.info("NATS Presence Service started")
            
        except Exception as e:
            logger.error(f"Failed to start presence service: {e}")
    
    async def stop(self):
        """Stop the service"""
        self.running = False
        if self._subscription:
            await self._subscription.unsubscribe()
        logger.info("NATS Presence Service stopped")
    
    async def _handle_presence(self, msg: Msg):
        """Handle presence messages"""
        try:
            # Parse the message
            data = json.loads(msg.data.decode())
            client_id = data.get('client_id')
            tenant_id = data.get('tenant_id')
            msg_type = data.get('type', 'heartbeat')
            
            if not client_id:
                return
            
            # Update active clients
            if msg_type in ['connect', 'heartbeat']:
                self.active_clients[client_id] = {
                    'tenant_id': tenant_id,
                    'last_seen': datetime.now(timezone.utc),
                    'metadata': data.get('metadata', {})
                }
                if msg_type == 'connect':
                    logger.info(f"Client {client_id} connected")
            elif msg_type == 'disconnect':
                self.active_clients.pop(client_id, None)
                logger.info(f"Client {client_id} disconnected")
                
        except Exception as e:
            logger.error(f"Error handling presence: {e}")


# Global instance
nats_presence_service = NATSPresenceService()