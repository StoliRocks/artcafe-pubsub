import json
import asyncio
import logging
from typing import Any, Optional, Dict, List, Callable, Awaitable, TYPE_CHECKING

import nats

# For type hints
if TYPE_CHECKING:
    from nats.aio.msg import Msg

from config.settings import settings

logger = logging.getLogger(__name__)


class NatsConnectionManager:
    """NATS connection manager for ArtCafe pub/sub"""
    
    def __init__(self, 
                 servers: Optional[List[str]] = None,
                 connection_options: Optional[Dict[str, Any]] = None):
        """Initialize NATS connection manager"""
        self.servers = servers or settings.NATS_SERVERS
        self.connection_options = connection_options or self._get_default_options()
        self._client: Optional[nats.NATS] = None
        self._js = None
        self._lock = asyncio.Lock()
        
    def _get_default_options(self) -> Dict[str, Any]:
        """Get default connection options from settings"""
        options = {
            "reconnected_cb": self._reconnected_cb,
            "disconnected_cb": self._disconnected_cb,
            "error_cb": self._error_cb,
            "closed_cb": self._closed_cb,
            "max_reconnect_attempts": 0,  # No reconnect attempts
            "reconnect_time_wait": 2,  # 2 seconds between reconnect attempts
        }
        
        # Add authentication if configured
        if settings.NATS_USERNAME and settings.NATS_PASSWORD:
            options["user"] = settings.NATS_USERNAME
            options["password"] = settings.NATS_PASSWORD
        elif settings.NATS_TOKEN:
            options["token"] = settings.NATS_TOKEN
            
        # Add TLS if enabled
        if settings.NATS_TLS_ENABLED:
            options["tls"] = {
                "cert_file": settings.NATS_TLS_CERT_PATH,
                "key_file": settings.NATS_TLS_KEY_PATH,
                "ca_file": settings.NATS_TLS_CA_PATH,
            }
            
        return options
        
    async def connect(self):
        """Connect to NATS server"""
        async with self._lock:
            if self._client and self._client.is_connected:
                return self._client
                
            logger.info(f"Connecting to NATS servers: {self.servers}")
            try:
                self._client = await asyncio.wait_for(
                    nats.connect(
                        servers=self.servers,
                        **self.connection_options
                    ),
                    timeout=5.0
                )
                logger.info("Connected to NATS")
                
                # Initialize JetStream
                self._js = self._client.jetstream()
                
                return self._client
            except Exception as e:
                logger.error(f"Error connecting to NATS: {e}")
                self._client = None
                self._js = None
                raise
        
    async def get_jetstream(self):
        """Get JetStream context"""
        if not self._client or not self._client.is_connected:
            await self.connect()
        return self._js
        
    async def close(self) -> None:
        """Close NATS connection"""
        async with self._lock:
            if self._client and self._client.is_connected:
                await self._client.close()
                self._client = None
                self._js = None
                logger.info("NATS connection closed")
                
    async def publish(self, subject: str, payload: dict) -> None:
        """Publish message to NATS"""
        if not self._client or not self._client.is_connected:
            await self.connect()
            
        payload_bytes = json.dumps(payload).encode("utf-8")
        await self._client.publish(subject, payload_bytes)
        
    async def subscribe(self, 
                      subject: str, 
                      callback: Callable[[Any], Awaitable[None]],
                      queue: Optional[str] = None):
        """Subscribe to NATS subject"""
        if not self._client or not self._client.is_connected:
            await self.connect()
            
        return await self._client.subscribe(
            subject=subject,
            cb=callback,
            queue=queue
        )
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to NATS"""
        return self._client is not None and self._client.is_connected
        
    # Callback handlers
    async def _reconnected_cb(self) -> None:
        """Called when NATS client reconnects"""
        logger.info("Reconnected to NATS server")
        
    async def _disconnected_cb(self) -> None:
        """Called when NATS client disconnects"""
        logger.warning("Disconnected from NATS server")
        
    async def _error_cb(self, e) -> None:
        """Called when NATS client encounters an error"""
        logger.error(f"NATS client error: {e}")
        
    async def _closed_cb(self) -> None:
        """Called when NATS client connection is closed"""
        logger.info("NATS connection closed")


    async def get_stats(self) -> Optional[Dict[str, Any]]:
        """Get NATS connection statistics (stub for now)"""
        # TODO: Implement actual stats collection if needed
        return None

# Singleton instance
nats_manager = NatsConnectionManager()