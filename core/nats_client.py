import os
import json
import uuid
import logging
import asyncio
from typing import Dict, Any, Callable, Optional, List, Union, Awaitable

import nats
from nats import NATS
from nats.msg import Msg

logger = logging.getLogger(__name__)

class NATSClient:
    """
    NATS client for pub/sub messaging.
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        server_url: str = None,
        token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls_enabled: bool = False,
        tls_cert_path: Optional[str] = None,
        tls_key_path: Optional[str] = None,
        tls_ca_path: Optional[str] = None,
        max_reconnect_attempts: int = 60,
        reconnect_time_wait: int = 2,
    ):
        """
        Initialize NATS client.
        
        Args:
            client_id: Unique client identifier, defaults to a random UUID if not provided
            server_url: NATS server URL (can be comma-separated list for clusters)
            token: Authentication token
            username: Username for authentication
            password: Password for authentication
            tls_enabled: Whether to use TLS for connection
            tls_cert_path: Path to TLS certificate
            tls_key_path: Path to TLS key
            tls_ca_path: Path to TLS CA certificate
            max_reconnect_attempts: Maximum number of reconnect attempts
            reconnect_time_wait: Time to wait between reconnect attempts (seconds)
        """
        self.client_id = client_id or f"artcafe-{uuid.uuid4()}"
        
        # Get server URL from environment or use default
        self.server_url = server_url or os.getenv('NATS_SERVER_URL', 'nats://localhost:4222')
        
        # Parse server URLs
        if isinstance(self.server_url, str):
            self.server_urls = self.server_url.split(",")
        else:
            self.server_urls = self.server_url
        
        # Authentication options
        self.token = token or os.getenv('NATS_TOKEN')
        self.username = username or os.getenv('NATS_USERNAME')
        self.password = password or os.getenv('NATS_PASSWORD')
        
        # TLS options
        self.tls_enabled = tls_enabled or os.getenv('NATS_TLS_ENABLED', 'false').lower() == 'true'
        self.tls_cert_path = tls_cert_path or os.getenv('NATS_TLS_CERT_PATH')
        self.tls_key_path = tls_key_path or os.getenv('NATS_TLS_KEY_PATH')
        self.tls_ca_path = tls_ca_path or os.getenv('NATS_TLS_CA_PATH')
        
        # Reconnection options
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_time_wait = reconnect_time_wait
        
        # NATS client
        self.client: Optional[NATS] = None
        
        # Subscription handlers
        self._subscriptions: Dict[int, Dict[str, Any]] = {}
        
        # Connection status
        self.connected = False
        
        # Event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def connect(self) -> None:
        """Connect to the NATS server."""
        try:
            # Create NATS client if not exists
            if self.client is None:
                self.client = NATS()
            
            # Set current event loop
            self._loop = asyncio.get_event_loop()
            
            # Connection options
            options = {
                "servers": self.server_urls,
                "name": self.client_id,
                "max_reconnect_attempts": self.max_reconnect_attempts,
                "reconnect_time_wait": self.reconnect_time_wait,
                "verbose": False,
                "allow_reconnect": True,
                "connect_timeout": 5,
                "error_cb": self._on_error,
                "disconnected_cb": self._on_disconnect,
                "reconnected_cb": self._on_reconnect,
                "closed_cb": self._on_close,
            }
            
            # Add authentication if provided
            if self.token:
                options["token"] = self.token
            elif self.username and self.password:
                options["user"] = self.username
                options["password"] = self.password
            
            # Add TLS options if enabled
            if self.tls_enabled:
                tls_context = {}
                if self.tls_cert_path and self.tls_key_path:
                    tls_context["cert_file"] = self.tls_cert_path
                    tls_context["key_file"] = self.tls_key_path
                if self.tls_ca_path:
                    tls_context["ca_file"] = self.tls_ca_path
                
                options["tls"] = tls_context
            
            # Connect to NATS server
            await self.client.connect(**options)
            
            self.connected = True
            logger.info(f"Connected to NATS server: {self.server_urls}")
        
        except Exception as e:
            logger.error(f"Failed to connect to NATS server: {e}")
            self.connected = False
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from the NATS server."""
        if self.client:
            try:
                # Unsubscribe from all subscriptions
                for sub_id in list(self._subscriptions.keys()):
                    await self.unsubscribe(sub_id)
                
                # Drain the connection
                await self.client.drain()
                
                # Close the connection
                await self.client.close()
                
                self.connected = False
                logger.info("Disconnected from NATS server")
            
            except Exception as e:
                logger.error(f"Error disconnecting from NATS server: {e}")
                raise
    
    async def publish(
        self,
        subject: str,
        payload: Dict[str, Any],
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Publish a message to a subject.
        
        Args:
            subject: Subject to publish to
            payload: Message payload (will be serialized to JSON)
            reply_to: Optional reply subject
            headers: Optional message headers
        """
        if not self.client or not self.connected:
            await self.connect()
        
        try:
            # Convert payload to JSON
            json_payload = json.dumps(payload).encode("utf-8")
            
            # Publish message
            await self.client.publish(
                subject=subject,
                payload=json_payload,
                reply=reply_to,
                headers=headers
            )
            
            logger.debug(f"Published message to subject {subject}")
        
        except Exception as e:
            logger.error(f"Error publishing message to subject {subject}: {e}")
            raise
    
    async def subscribe(
        self,
        subject: str,
        queue_group: Optional[str] = None,
        callback: Optional[Callable[[Msg], Awaitable[None]]] = None,
    ) -> int:
        """
        Subscribe to a subject.
        
        Args:
            subject: Subject to subscribe to
            queue_group: Optional queue group for load balancing
            callback: Callback function to handle messages for this subject
            
        Returns:
            Subscription ID
        """
        if not self.client or not self.connected:
            await self.connect()
        
        try:
            # Create wrapper for callback to handle JSON decoding
            async def message_handler(msg: Msg) -> None:
                try:
                    # Decode JSON payload
                    payload_str = msg.data.decode("utf-8")
                    payload = json.loads(payload_str)
                    
                    # Call user callback if provided
                    if callback:
                        await callback(msg)
                    
                    logger.debug(f"Processed message from subject {msg.subject}")
                
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON message: {msg.data}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
            
            # Subscribe to subject
            sub = await self.client.subscribe(
                subject=subject,
                queue=queue_group,
                cb=message_handler if callback else None
            )
            
            # Store subscription
            sub_id = sub.sid
            self._subscriptions[sub_id] = {
                "subject": subject,
                "queue_group": queue_group,
                "callback": callback,
                "subscription": sub
            }
            
            logger.info(f"Subscribed to subject: {subject}, sid: {sub_id}")
            
            return sub_id
        
        except Exception as e:
            logger.error(f"Error subscribing to subject {subject}: {e}")
            raise
    
    async def unsubscribe(self, subscription_id: int) -> None:
        """
        Unsubscribe from a subscription.
        
        Args:
            subscription_id: Subscription ID to unsubscribe from
        """
        if not self.client or not self.connected:
            logger.warning("Not connected to NATS server")
            return
        
        try:
            # Get subscription
            sub_info = self._subscriptions.get(subscription_id)
            if not sub_info:
                logger.warning(f"Subscription {subscription_id} not found")
                return
            
            # Unsubscribe
            await sub_info["subscription"].unsubscribe()
            
            # Remove from subscriptions
            del self._subscriptions[subscription_id]
            
            logger.info(f"Unsubscribed from subject: {sub_info['subject']}, sid: {subscription_id}")
        
        except Exception as e:
            logger.error(f"Error unsubscribing from subscription {subscription_id}: {e}")
            raise
    
    async def request(
        self,
        subject: str,
        payload: Dict[str, Any],
        timeout: float = 2.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a request and wait for a response.
        
        Args:
            subject: Subject to send request to
            payload: Request payload (will be serialized to JSON)
            timeout: Timeout in seconds
            headers: Optional message headers
            
        Returns:
            Response payload (deserialized from JSON)
        """
        if not self.client or not self.connected:
            await self.connect()
        
        try:
            # Convert payload to JSON
            json_payload = json.dumps(payload).encode("utf-8")
            
            # Send request
            response = await self.client.request(
                subject=subject,
                payload=json_payload,
                timeout=timeout,
                headers=headers
            )
            
            # Decode response
            response_str = response.data.decode("utf-8")
            response_payload = json.loads(response_str)
            
            logger.debug(f"Received response for request to subject {subject}")
            
            return response_payload
        
        except nats.errors.TimeoutError:
            logger.error(f"Request to subject {subject} timed out after {timeout} seconds")
            raise
        except Exception as e:
            logger.error(f"Error sending request to subject {subject}: {e}")
            raise
    
    # NATS callback handlers
    
    def _on_error(self, error: Exception) -> None:
        """Called when an error occurs."""
        logger.error(f"NATS client error: {error}")
    
    def _on_disconnect(self) -> None:
        """Called when client disconnects from the server."""
        logger.warning("Disconnected from NATS server")
        self.connected = False
    
    def _on_reconnect(self) -> None:
        """Called when client reconnects to the server."""
        logger.info("Reconnected to NATS server")
        self.connected = True
    
    def _on_close(self) -> None:
        """Called when client connection is closed."""
        logger.info("NATS client connection closed")
        self.connected = False
    
    # Context manager support
    
    async def __aenter__(self):
        """Enter async context manager."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        await self.disconnect()