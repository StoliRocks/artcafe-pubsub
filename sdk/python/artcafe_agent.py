"""
ArtCafe.ai Agent SDK for Python

This module provides a client implementation for ArtCafe.ai agents to
connect to the PubSub service.

NOTE: This is the legacy SDK. For new agents, use artcafe_agent_v2.py
which supports the new AgentMessage protocol.
"""

import asyncio
import json
import time
import logging
import base64
import uuid
import socket
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Awaitable, Union

import jwt
import websockets
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives import hashes

__version__ = "0.1.0"


class ArtCafeAgentError(Exception):
    """Base exception for ArtCafe Agent errors"""
    pass


class AuthenticationError(ArtCafeAgentError):
    """Authentication error"""
    pass


class ConnectionError(ArtCafeAgentError):
    """Connection error"""
    pass


class CommandError(ArtCafeAgentError):
    """Command execution error"""
    pass


class ArtCafeAgent:
    """
    Client for ArtCafe.ai agents to connect to the PubSub service.
    """
    
    def __init__(
        self,
        agent_id: str,
        tenant_id: str,
        private_key_path: str,
        api_endpoint: str = "https://api.artcafe.ai",
        log_level: str = "INFO",
        heartbeat_interval: int = 30
    ):
        """
        Initialize the ArtCafe agent client.
        
        Args:
            agent_id: Agent ID
            tenant_id: Tenant ID
            private_key_path: Path to the SSH private key file
            api_endpoint: API endpoint URL
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            heartbeat_interval: Seconds between heartbeats
        """
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.private_key_path = private_key_path
        self.api_endpoint = api_endpoint
        self.heartbeat_interval = heartbeat_interval
        
        # Setup logging
        self.logger = logging.getLogger(f"ArtCafeAgent-{agent_id}")
        log_level_value = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(log_level_value)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Authentication
        self.jwt_token = None
        self.jwt_expires_at = None
        self.key_id = None
        
        # WebSocket
        self.ws = None
        self.ws_url = f"{self.api_endpoint.replace('http', 'ws')}/ws/agent/{self.agent_id}"
        
        # State
        self.running = False
        self.status = "offline"
        self.current_task = None
        self.hostname = socket.gethostname()
        
        # Message handlers
        self.message_handlers = {
            "command": self._handle_command,
            "ping": self._handle_ping,
            "status_request": self._handle_status_request
        }
        self.command_handlers = {}
        
        # Load private key
        self._load_private_key()
        
        self.logger.info(f"Agent initialized: {agent_id} on {self.hostname}")
    
    def _load_private_key(self):
        """Load private key from file"""
        try:
            with open(self.private_key_path, 'rb') as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None
                )
            
            self.logger.debug(f"Private key loaded from {self.private_key_path}")
        except Exception as e:
            self.logger.error(f"Failed to load private key: {e}")
            raise AuthenticationError(f"Failed to load private key: {e}")
    
    def register_command(self, command_name: str, handler: Callable):
        """
        Register a handler for a specific command.
        
        Args:
            command_name: Name of the command
            handler: Function to handle the command
        """
        self.command_handlers[command_name] = handler
        self.logger.debug(f"Registered handler for command: {command_name}")
    
    async def authenticate(self) -> bool:
        """
        Authenticate with the ArtCafe.ai platform using SSH key.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            self.logger.info("Starting authentication")
            
            # Get challenge
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_endpoint}/auth/challenge",
                    json={"agent_id": self.agent_id}
                )
                
                if response.status_code != 200:
                    self.logger.error(f"Failed to get challenge: {response.text}")
                    return False
                
                challenge_data = response.json()
                challenge = challenge_data["challenge"]
                
                self.logger.debug(f"Received challenge: {challenge[:10]}...")
                
                # Sign challenge
                signature = self._sign_challenge(challenge)
                signature_b64 = base64.b64encode(signature).decode()
                
                # Get key_id from previous auth if available
                key_id = self.key_id
                
                if not key_id:
                    # Try to fetch agent info to get associated keys
                    key_id = await self._get_agent_key_id()
                
                if not key_id:
                    self.logger.error("No key ID available for authentication")
                    return False
                
                # Verify signature
                response = await client.post(
                    f"{self.api_endpoint}/auth/verify",
                    json={
                        "tenant_id": self.tenant_id,
                        "key_id": key_id,
                        "challenge": challenge,
                        "response": signature_b64,
                        "agent_id": self.agent_id
                    }
                )
                
                if response.status_code != 200:
                    self.logger.error(f"Authentication failed: {response.text}")
                    return False
                
                auth_result = response.json()
                
                if not auth_result["valid"]:
                    self.logger.error("Invalid signature")
                    return False
                
                self.jwt_token = auth_result["token"]
                payload = jwt.decode(
                    self.jwt_token,
                    options={"verify_signature": False}
                )
                self.jwt_expires_at = datetime.fromtimestamp(payload["exp"])
                self.key_id = key_id
                
                self.logger.info("Authentication successful")
                return True
                
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return False
    
    async def _get_agent_key_id(self) -> Optional[str]:
        """
        Get the agent's SSH key ID by querying its details.
        
        Returns:
            SSH key ID or None if not found
        """
        try:
            # Get temporary JWT token for querying
            temp_token = jwt.encode(
                {
                    "sub": self.agent_id,
                    "tenant_id": self.tenant_id,
                    "exp": datetime.utcnow() + timedelta(minutes=5)
                },
                "temporary",
                algorithm="HS256"
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get keys for this agent
                response = await client.get(
                    f"{self.api_endpoint}/ssh-keys",
                    params={"agent_id": self.agent_id, "key_type": "agent"},
                    headers={
                        "Authorization": f"Bearer {temp_token}",
                        "x-tenant-id": self.tenant_id
                    }
                )
                
                if response.status_code != 200:
                    self.logger.error(f"Failed to get agent keys: {response.text}")
                    return None
                
                data = response.json()
                
                if not data["ssh_keys"]:
                    self.logger.error(f"No SSH keys found for agent {self.agent_id}")
                    return None
                
                # Use the first active key
                for key in data["ssh_keys"]:
                    if not key.get("revoked", False):
                        return key["key_id"]
                
                self.logger.error("No active SSH keys found")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting agent key ID: {e}")
            return None
    
    def _sign_challenge(self, challenge: str) -> bytes:
        """
        Sign a challenge string with the private key.
        
        Args:
            challenge: Challenge string to sign
            
        Returns:
            Signature bytes
        """
        try:
            # Convert challenge to bytes
            message = challenge.encode('utf-8')
            
            # Create digest
            digest = hashes.Hash(hashes.SHA256())
            digest.update(message)
            digest_bytes = digest.finalize()
            
            # Sign the digest
            signature = self.private_key.sign(
                digest_bytes,
                padding.PKCS1v15(),
                Prehashed(hashes.SHA256())
            )
            
            return signature
            
        except Exception as e:
            self.logger.error(f"Error signing challenge: {e}")
            raise AuthenticationError(f"Error signing challenge: {e}")
    
    def is_authenticated(self) -> bool:
        """
        Check if the agent is authenticated with a valid token.
        
        Returns:
            True if authenticated, False otherwise
        """
        if not self.jwt_token or not self.jwt_expires_at:
            return False
        
        # Check if token expires in the next 5 minutes
        return datetime.now() + timedelta(minutes=5) < self.jwt_expires_at
    
    async def connect(self) -> bool:
        """
        Connect to the WebSocket server.
        
        Returns:
            True if connected, False otherwise
        """
        try:
            if not self.is_authenticated():
                self.logger.info("Not authenticated, authenticating...")
                if not await self.authenticate():
                    return False
            
            self.logger.info(f"Connecting to WebSocket: {self.ws_url}")
            
            self.ws = await websockets.connect(
                self.ws_url,
                extra_headers={
                    "Authorization": f"Bearer {self.jwt_token}",
                    "x-tenant-id": self.tenant_id
                }
            )
            
            self.logger.info("Connected to WebSocket")
            
            # Send initial status update
            await self.update_status("online")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.ws:
            self.logger.info("Disconnecting from WebSocket")
            
            try:
                # Send offline status
                await self.update_status("offline")
                
                # Close connection
                await self.ws.close()
                self.ws = None
                
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
                self.ws = None
    
    async def update_status(self, status: str, task_id: Optional[str] = None, progress: Optional[int] = None):
        """
        Update agent status.
        
        Args:
            status: New status (online, offline, busy, error)
            task_id: Optional current task ID
            progress: Optional task progress (0-100)
        """
        self.status = status
        self.current_task = task_id
        
        status_data = {
            "status": status,
            "hostname": self.hostname
        }
        
        if task_id:
            status_data["current_task"] = task_id
        
        if progress is not None:
            status_data["progress"] = progress
        
        # Send status update via API
        try:
            if not self.is_authenticated():
                await self.authenticate()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    f"{self.api_endpoint}/agents/{self.agent_id}/status",
                    json={"status": status},
                    headers={
                        "Authorization": f"Bearer {self.jwt_token}",
                        "x-tenant-id": self.tenant_id
                    }
                )
            
            # Also send through WebSocket if connected
            if self.ws:
                status_msg = {
                    "type": "status",
                    "id": str(uuid.uuid4()),
                    "data": status_data,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.ws.send(json.dumps(status_msg))
                
        except Exception as e:
            self.logger.error(f"Error updating status: {e}")
    
    async def _send_heartbeat(self):
        """Send heartbeat message to the server"""
        if not self.ws:
            return
        
        try:
            # Get system metrics
            heartbeat_data = {
                "agent_id": self.agent_id,
                "status": self.status,
                "hostname": self.hostname,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add CPU and memory usage if psutil is available
            try:
                import psutil
                process = psutil.Process(os.getpid())
                heartbeat_data["cpu_percent"] = process.cpu_percent()
                heartbeat_data["memory_percent"] = process.memory_percent()
                heartbeat_data["memory_mb"] = process.memory_info().rss / (1024 * 1024)
            except ImportError:
                pass
            
            heartbeat_msg = {
                "type": "heartbeat",
                "id": f"hb-{uuid.uuid4()}",
                "data": heartbeat_data,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.ws.send(json.dumps(heartbeat_msg))
            self.logger.debug("Heartbeat sent")
            
        except Exception as e:
            self.logger.error(f"Error sending heartbeat: {e}")
    
    async def start(self):
        """
        Start the agent and maintain connection.
        
        This method blocks until stop() is called.
        """
        self.running = True
        retry_delay = 1
        
        while self.running:
            try:
                if not self.ws:
                    if not await self.connect():
                        # Connection failed, wait before retry
                        sleep_time = min(retry_delay, 120)
                        self.logger.info(f"Connection failed, retrying in {sleep_time}s")
                        await asyncio.sleep(sleep_time)
                        retry_delay *= 2
                        continue
                    
                    # Reset backoff on successful connection
                    retry_delay = 1
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                # Message processing loop
                try:
                    async for message in self.ws:
                        retry_delay = 1  # Reset backoff on successful messages
                        
                        # Process message
                        asyncio.create_task(self._process_message(message))
                        
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("WebSocket connection closed")
                
                finally:
                    # Clean up heartbeat task
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    
                    self.ws = None
                
                # Wait before reconnecting
                if self.running:
                    await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                
                if self.running:
                    # Exponential backoff with cap
                    sleep_time = min(retry_delay, 120)
                    self.logger.info(f"Reconnecting in {sleep_time}s")
                    await asyncio.sleep(sleep_time)
                    retry_delay *= 2
                    
                    # Reset connection
                    self.ws = None
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.ws and self.running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    async def _process_message(self, message: str):
        """
        Process incoming WebSocket message.
        
        Args:
            message: Raw message string from WebSocket
        """
        try:
            data = json.loads(message)
            
            # Get message type
            msg_type = data.get("type")
            msg_id = data.get("id", str(uuid.uuid4()))
            
            self.logger.debug(f"Received message type={msg_type}, id={msg_id}")
            
            # Handle message based on type
            handler = self.message_handlers.get(msg_type)
            
            if handler:
                response = await handler(data)
                
                # Send response if provided
                if response:
                    await self.ws.send(json.dumps(response))
            else:
                self.logger.warning(f"No handler for message type: {msg_type}")
                
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON message: {message}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    async def _handle_command(self, message: Dict) -> Dict:
        """
        Handle command message.
        
        Args:
            message: Command message
            
        Returns:
            Response message
        """
        command_data = message.get("data", {})
        command_name = command_data.get("command")
        
        if not command_name:
            return {
                "type": "response",
                "id": str(uuid.uuid4()),
                "data": {
                    "command_id": message.get("id"),
                    "status": "error",
                    "error": "Invalid command format"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
        self.logger.info(f"Received command: {command_name}")
        
        # Update status to busy
        await self.update_status("busy", task_id=message.get("id"))
        
        # Find command handler
        handler = self.command_handlers.get(command_name)
        
        if not handler:
            await self.update_status("online")
            return {
                "type": "response",
                "id": str(uuid.uuid4()),
                "data": {
                    "command_id": message.get("id"),
                    "status": "error",
                    "error": f"Unknown command: {command_name}"
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Execute command
        try:
            result = await handler(command_data.get("args", {}))
            
            # Update status back to online
            await self.update_status("online")
            
            return {
                "type": "response",
                "id": str(uuid.uuid4()),
                "data": {
                    "command_id": message.get("id"),
                    "status": "success",
                    "result": result
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error executing command {command_name}: {e}")
            
            # Update status back to online
            await self.update_status("online")
            
            return {
                "type": "response",
                "id": str(uuid.uuid4()),
                "data": {
                    "command_id": message.get("id"),
                    "status": "error",
                    "error": str(e)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _handle_ping(self, message: Dict) -> Dict:
        """
        Handle ping message.
        
        Args:
            message: Ping message
            
        Returns:
            Pong response
        """
        return {
            "type": "pong",
            "id": str(uuid.uuid4()),
            "data": {
                "ping_id": message.get("id"),
                "time": datetime.utcnow().isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _handle_status_request(self, message: Dict) -> Dict:
        """
        Handle status request message.
        
        Args:
            message: Status request message
            
        Returns:
            Status response
        """
        return {
            "type": "status",
            "id": str(uuid.uuid4()),
            "data": {
                "request_id": message.get("id"),
                "agent_id": self.agent_id,
                "status": self.status,
                "hostname": self.hostname,
                "current_task": self.current_task
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def stop(self):
        """Stop the agent"""
        self.logger.info("Stopping agent")
        self.running = False
        
        # Disconnect from WebSocket
        await self.disconnect()
        
        self.logger.info("Agent stopped")


# Example usage
async def example_agent():
    """Example agent implementation"""
    # Create agent
    agent = ArtCafeAgent(
        agent_id="agent-123",
        tenant_id="tenant-456",
        private_key_path="/path/to/private_key"
    )
    
    # Register command handlers
    async def handle_echo(args):
        return {"message": args.get("message", "Hello")}
    
    agent.register_command("echo", handle_echo)
    
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