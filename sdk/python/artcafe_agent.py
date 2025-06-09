"""
ArtCafe.ai Agent SDK for Python

This module provides a client implementation for ArtCafe.ai agents to
connect directly to NATS using NKey authentication.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from typing import Any, Callable, Dict, Optional, Union
from datetime import datetime

import nats
from nats.errors import ConnectionClosedError, TimeoutError, NoRespondersError

__version__ = "1.0.0"


class ArtCafeAgentError(Exception):
    """Base exception for ArtCafe Agent errors"""
    pass


class AuthenticationError(ArtCafeAgentError):
    """Authentication error"""
    pass


class ConnectionError(ArtCafeAgentError):
    """Connection error"""
    pass


class ArtCafeAgent:
    """
    ArtCafe.ai agent with direct NATS connection using NKey authentication.
    """
    
    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        nkey_seed: Union[str, bytes],
        nats_url: str = "nats://nats.artcafe.ai:4222",
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        log_level: str = "INFO",
        heartbeat_interval: int = 30
    ):
        """
        Initialize the ArtCafe agent client.
        
        Args:
            client_id: Client ID from the ArtCafe dashboard
            tenant_id: Tenant/organization ID
            nkey_seed: NKey seed string or path to seed file
            nats_url: NATS server URL
            name: Optional name for the agent
            metadata: Optional metadata dictionary
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            heartbeat_interval: Seconds between heartbeats
        """
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.nkey_seed = nkey_seed
        self.nats_url = nats_url
        self.name = name or client_id
        self.metadata = metadata or {}
        self.heartbeat_interval = heartbeat_interval
        
        # Setup logging
        self.logger = logging.getLogger(f"ArtCafeAgent-{client_id}")
        log_level_value = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(log_level_value)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # NATS connection
        self.nc: Optional[nats.NATS] = None
        self._subscriptions = {}
        self._message_handlers = {}
        self._is_connected = False
        self._heartbeat_task = None
        
        self.logger.info(f"Agent initialized: {client_id}")
    
    async def connect(self):
        """Connect to NATS using NKey authentication."""
        try:
            # Handle NKey seed
            if isinstance(self.nkey_seed, bytes):
                seed_str = self.nkey_seed.decode()
            else:
                seed_str = self.nkey_seed
                
            self.nc = await nats.connect(
                self.nats_url,
                nkeys_seed=seed_str,
                name=f"{self.name} ({self.client_id})",
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback,
                closed_cb=self._closed_callback,
            )
            
            self._is_connected = True
            self.logger.info(f"Connected to NATS as {self.client_id}")
            
            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Clean up temp file if created
            if creds_file != self.nkey_seed and os.path.exists(creds_file):
                os.unlink(creds_file)
                
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise ConnectionError(f"Failed to connect: {e}")
    
    async def disconnect(self):
        """Disconnect from NATS."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            
        if self.nc:
            await self.nc.close()
            
        self._is_connected = False
        self.logger.info("Disconnected from NATS")
    
    async def subscribe(self, subject: str, handler: Optional[Callable] = None):
        """
        Subscribe to a subject pattern.
        
        Args:
            subject: Subject pattern (e.g., "tasks.*", "alerts.>")
            handler: Optional message handler function
        """
        # Add tenant prefix
        full_subject = f"{self.tenant_id}.{subject}"
        
        # Create subscription
        sub = await self.nc.subscribe(full_subject)
        self._subscriptions[subject] = sub
        
        if handler:
            self._message_handlers[subject] = handler
            
        self.logger.info(f"Subscribed to {full_subject}")
        
        # Start message processor if handler provided
        if handler:
            asyncio.create_task(self._process_messages(sub, subject, handler))
    
    async def unsubscribe(self, subject: str):
        """Unsubscribe from a subject."""
        if subject in self._subscriptions:
            await self._subscriptions[subject].unsubscribe()
            del self._subscriptions[subject]
            if subject in self._message_handlers:
                del self._message_handlers[subject]
            self.logger.info(f"Unsubscribed from {subject}")
    
    async def publish(self, subject: str, data: Any, reply: Optional[str] = None):
        """
        Publish a message to a subject.
        
        Args:
            subject: Target subject
            data: Message data (will be JSON encoded if not bytes)
            reply: Optional reply-to subject
        """
        # Add tenant prefix
        full_subject = f"{self.tenant_id}.{subject}"
        
        # Encode data
        if isinstance(data, bytes):
            payload = data
        else:
            payload = json.dumps(data).encode()
        
        # Publish
        await self.nc.publish(full_subject, payload, reply=reply)
        self.logger.debug(f"Published to {full_subject}")
    
    async def request(self, subject: str, data: Any, timeout: float = 5.0) -> Any:
        """
        Send a request and wait for a response.
        
        Args:
            subject: Target subject
            data: Request data
            timeout: Response timeout in seconds
            
        Returns:
            Response data (JSON decoded if possible)
        """
        # Add tenant prefix
        full_subject = f"{self.tenant_id}.{subject}"
        
        # Encode data
        if isinstance(data, bytes):
            payload = data
        else:
            payload = json.dumps(data).encode()
        
        try:
            # Send request
            response = await self.nc.request(full_subject, payload, timeout=timeout)
            
            # Decode response
            try:
                return json.loads(response.data.decode())
            except:
                return response.data
                
        except TimeoutError:
            self.logger.error(f"Request timeout for {subject}")
            raise
        except NoRespondersError:
            self.logger.error(f"No responders for {subject}")
            raise
    
    def on_message(self, subject: str):
        """
        Decorator for message handlers.
        
        Example:
            @agent.on_message("tasks.new")
            async def handle_new_task(subject, data):
                # Process task
                await agent.publish("tasks.result", result)
        """
        def decorator(func):
            asyncio.create_task(self.subscribe(subject, func))
            return func
        return decorator
    
    async def start(self):
        """
        Start the agent and maintain connection.
        """
        if not self._is_connected:
            await self.connect()
            
        try:
            while self._is_connected:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
        finally:
            await self.disconnect()
    
    async def stop(self):
        """Stop the agent"""
        self.logger.info("Stopping agent")
        self._is_connected = False
        await self.disconnect()
        self.logger.info("Agent stopped")
    
    # Compatibility method names
    async def run_forever(self):
        """Alias for start() for compatibility"""
        await self.start()
    
    # Private methods
    
    async def _process_messages(self, subscription, subject: str, handler: Callable):
        """Process messages for a subscription."""
        async for msg in subscription.messages:
            try:
                # Decode message
                try:
                    data = json.loads(msg.data.decode())
                except:
                    data = msg.data
                
                # Remove tenant prefix from subject for handler
                clean_subject = msg.subject.replace(f"{self.tenant_id}.", "", 1)
                
                # Call handler
                if asyncio.iscoroutinefunction(handler):
                    await handler(clean_subject, data)
                else:
                    handler(clean_subject, data)
                    
            except Exception as e:
                self.logger.error(f"Error processing message on {subject}: {e}")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        # Use efficient heartbeat subject pattern
        heartbeat_subject = f"_heartbeat.{self.tenant_id}.{self.client_id}"
        
        while self._is_connected:
            try:
                # Send minimal heartbeat (just timestamp)
                heartbeat_data = {
                    "ts": int(time.time()),
                    "v": "1.0"  # Version for future compatibility
                }
                
                # Publish directly to heartbeat subject (no tenant prefix needed)
                await self.nc.publish(
                    heartbeat_subject,
                    json.dumps(heartbeat_data).encode()
                )
                
                self.logger.debug(f"Heartbeat sent to {heartbeat_subject}")
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)
    
    def _error_callback(self, e):
        """Handle NATS errors."""
        self.logger.error(f"NATS error: {e}")
    
    def _disconnected_callback(self):
        """Handle disconnection."""
        self.logger.warning("Disconnected from NATS")
        self._is_connected = False
    
    def _reconnected_callback(self):
        """Handle reconnection."""
        self.logger.info("Reconnected to NATS")
        self._is_connected = True
    
    def _closed_callback(self):
        """Handle connection closed."""
        self.logger.info("NATS connection closed")
        self._is_connected = False


# Example usage
async def example_agent():
    """Example agent implementation"""
    # Create agent
    agent = ArtCafeAgent(
        client_id="demo-client",
        tenant_id="your-tenant-id",
        nkey_seed="SUABTHCUEEB7DW66XQTPYIJT4OXFHX72FYAC26I6F4MWCKMTFSFP7MRY5U"
    )
    
    # Define handler
    async def handle_task(subject, data):
        print(f"Received task on {subject}: {data}")
        # Process and publish result
        result = {"task_id": data.get("id"), "status": "completed"}
        await agent.publish("tasks.complete", result)
    
    # Subscribe to tasks
    await agent.subscribe("tasks.new", handle_task)
    
    # Start agent
    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Run example agent
    asyncio.run(example_agent())