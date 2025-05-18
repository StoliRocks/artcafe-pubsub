# ArtCafe.ai Agent API Implementation Guide

This document provides comprehensive guidance for implementing agents that connect to the ArtCafe.ai PubSub service.

## Overview

ArtCafe.ai agents authenticate using SSH key pairs, communicate over secure WebSockets, and follow a standard protocol for message exchange. This architecture provides secure, extensible, and real-time communication between agents and the platform.

## Authentication Flow

### 1. Registration

Before an agent can connect, a tenant must register it with the platform:

1. Tenant generates an SSH key pair for the agent
2. Tenant calls `POST /api/v1/agents` to create agent record
3. Tenant calls `POST /api/v1/ssh-keys` with public key, marking it as `key_type=agent`
4. Platform returns agent_id and key_id for future authentication

### 2. Authentication Process

When an agent connects to the platform:

1. Agent calls `POST /api/v1/auth/challenge` with its agent_id
2. Platform returns a random challenge string
3. Agent signs challenge with its private key
4. Agent sends signature to `POST /api/v1/auth/verify`
5. Platform verifies signature and issues a short-lived JWT token
6. Agent uses token for subsequent API calls

```
┌─────────┐                                     ┌────────────┐
│  Agent  │                                     │  Platform  │
└────┬────┘                                     └─────┬──────┘
     │                                                │
     │ POST /api/v1/auth/challenge {agent_id}         │
     │────────────────────────────────────────────────>
     │                                                │
     │ {challenge: "random_string", expires_at: ...}  │
     │<────────────────────────────────────────────────
     │                                                │
     │ [Agent signs challenge with private key]       │
     │                                                │
     │ POST /api/v1/auth/verify {response: "sig..."}  │
     │────────────────────────────────────────────────>
     │                                                │
     │ {valid: true, token: "jwt_token"}              │
     │<────────────────────────────────────────────────
     │                                                │
```

## Agent Implementation Requirements

### Required Capabilities

1. **SSH Signing**: Must be capable of signing challenge strings with private key
2. **JWT Handling**: Must store and use JWT tokens for API calls
3. **WebSocket Support**: Must maintain WebSocket connection for real-time updates
4. **Reconnection Logic**: Must implement exponential backoff for reconnection
5. **Heartbeat**: Must send periodic heartbeats to maintain connection

### Configuration Parameters

Agents should accept the following configuration:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api_endpoint` | Base URL for ArtCafe PubSub API | https://api.artcafe.ai |
| `agent_id` | Unique identifier for this agent | (required) |
| `tenant_id` | Tenant identifier | (required) |
| `private_key_path` | Path to agent's SSH private key | ~/.ssh/artcafe_agent |
| `log_level` | Logging verbosity | INFO |
| `heartbeat_interval` | Seconds between heartbeats | 30 |

## API Endpoints

### Authentication Endpoints

- `POST /api/v1/auth/challenge`: Get authentication challenge
  - Request: `{ "agent_id": "string" }`
  - Response: `{ "challenge": "string", "expires_at": "string" }`

- `POST /api/v1/auth/verify`: Verify challenge signature
  - Request: `{ "tenant_id": "string", "key_id": "string", "challenge": "string", "response": "string", "agent_id": "string" }`
  - Response: `{ "valid": true, "token": "string" }`

### Agent Lifecycle Management

- `GET /api/v1/agents/{agent_id}`: Get agent details
  - Response: Full agent object with capabilities

- `PUT /api/v1/agents/{agent_id}/status`: Update agent status
  - Request: `{ "status": "online|offline|busy|error" }`
  - Response: Updated agent object

### WebSocket Communication

- `WSS /api/v1/ws/agent/{agent_id}`: Real-time communication channel
  - Connect with header: `Authorization: Bearer {jwt_token}`
  - Messages use the following format:
    ```json
    {
      "type": "message|command|status|heartbeat",
      "id": "unique_message_id",
      "data": {/* message-specific data */},
      "timestamp": "ISO8601 timestamp"
    }
    ```

## Message Types

### Heartbeat
```json
{
  "type": "heartbeat",
  "id": "hb-123456",
  "data": {
    "agent_id": "agent-123",
    "status": "online",
    "cpu_usage": 12.5,
    "memory_usage": 256.3
  },
  "timestamp": "2023-05-01T12:34:56Z"
}
```

### Command
```json
{
  "type": "command",
  "id": "cmd-123456",
  "data": {
    "command": "execute_task",
    "args": {
      "task_id": "task-123",
      "parameters": {}
    },
    "timeout": 300
  },
  "timestamp": "2023-05-01T12:34:56Z"
}
```

### Status Update
```json
{
  "type": "status",
  "id": "status-123456",
  "data": {
    "status": "busy",
    "current_task": "task-123",
    "progress": 45
  },
  "timestamp": "2023-05-01T12:34:56Z"
}
```

## Error Handling

1. **Authentication Errors**: If authentication fails, wait 5 seconds before retrying
2. **Connection Errors**: Use exponential backoff starting at 1s, capped at 2 minutes
3. **Command Errors**: Send error response with reason and command ID
4. **Server Errors (5xx)**: Wait 10s before retrying request

## Example Implementation (Python)

```python
import asyncio
import json
import time
import logging
import jwt
import websockets
import paramiko
import base64
import uuid
import httpx
from datetime import datetime, timedelta

class ArtCafeAgent:
    def __init__(self, agent_id, tenant_id, private_key_path, api_endpoint="https://api.artcafe.ai"):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.private_key_path = private_key_path
        self.api_endpoint = api_endpoint
        self.jwt_token = None
        self.jwt_expires_at = None
        self.ws = None
        self.running = False
        self.logger = logging.getLogger("ArtCafeAgent")
        
    async def start(self):
        """Start the agent and maintain connection"""
        self.running = True
        retry_delay = 1
        
        while self.running:
            try:
                # Authenticate if needed
                if not self.is_authenticated():
                    await self.authenticate()
                
                # Connect to WebSocket
                async with websockets.connect(
                    f"{self.api_endpoint.replace('http', 'ws')}/api/v1/ws/agent/{self.agent_id}",
                    extra_headers={"Authorization": f"Bearer {self.jwt_token}"}
                ) as self.ws:
                    self.logger.info("Connected to WebSocket")
                    retry_delay = 1  # Reset backoff on successful connection
                    
                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(self.send_heartbeats())
                    
                    # Process messages
                    while self.running:
                        message = await self.ws.recv()
                        await self.process_message(json.loads(message))
                        
            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                if self.running:
                    # Exponential backoff with cap
                    sleep_time = min(retry_delay, 120)
                    self.logger.info(f"Reconnecting in {sleep_time}s")
                    await asyncio.sleep(sleep_time)
                    retry_delay *= 2
    
    def is_authenticated(self):
        """Check if we have a valid JWT token"""
        if not self.jwt_token or not self.jwt_expires_at:
            return False
        
        # Check if token expires in the next 5 minutes
        return datetime.now() + timedelta(minutes=5) < self.jwt_expires_at
    
    async def authenticate(self):
        """Authenticate with the platform using SSH key"""
        async with httpx.AsyncClient() as client:
            # Get challenge
            response = await client.post(
                f"{self.api_endpoint}/api/v1/auth/challenge",
                json={"agent_id": self.agent_id}
            )
            challenge_data = response.json()
            
            # Sign challenge
            key = paramiko.RSAKey.from_private_key_file(self.private_key_path)
            signature = key.sign_ssh_data(challenge_data["challenge"].encode())
            signature_b64 = base64.b64encode(signature).decode()
            
            # Verify signature
            response = await client.post(
                f"{self.api_endpoint}/api/v1/auth/verify",
                json={
                    "tenant_id": self.tenant_id,
                    "agent_id": self.agent_id,
                    "challenge": challenge_data["challenge"],
                    "response": signature_b64
                }
            )
            auth_result = response.json()
            
            if auth_result["valid"]:
                self.jwt_token = auth_result["token"]
                # Parse JWT to get expiration
                payload = jwt.decode(self.jwt_token, options={"verify_signature": False})
                self.jwt_expires_at = datetime.fromtimestamp(payload["exp"])
                self.logger.info("Authentication successful")
            else:
                raise Exception("Authentication failed")
    
    async def send_heartbeats(self):
        """Send periodic heartbeats"""
        while self.running and self.ws:
            try:
                heartbeat = {
                    "type": "heartbeat",
                    "id": f"hb-{uuid.uuid4()}",
                    "data": {
                        "agent_id": self.agent_id,
                        "status": "online",
                        "cpu_usage": 0.0,  # Add real metrics here
                        "memory_usage": 0.0
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.ws.send(json.dumps(heartbeat))
                await asyncio.sleep(30)
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break
    
    async def process_message(self, message):
        """Process incoming messages"""
        if message["type"] == "command":
            # Process command
            command = message["data"]["command"]
            self.logger.info(f"Received command: {command}")
            
            # Execute command logic here
            
            # Send response
            response = {
                "type": "response",
                "id": str(uuid.uuid4()),
                "data": {
                    "command_id": message["id"],
                    "status": "success",
                    "result": {}
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.ws.send(json.dumps(response))
    
    async def stop(self):
        """Stop the agent"""
        self.running = False
        if self.ws:
            await self.ws.close()

# Usage example
async def main():
    agent = ArtCafeAgent(
        agent_id="agent-123",
        tenant_id="tenant-456",
        private_key_path="/path/to/private_key"
    )
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

## Implementation Checklist

- [ ] Generate/store SSH key pair securely
- [ ] Implement challenge-response authentication
- [ ] Set up WebSocket connection with auto-reconnect
- [ ] Implement heartbeat mechanism
- [ ] Handle different message types
- [ ] Add proper error handling and logging
- [ ] Implement command execution
- [ ] Add status reporting
- [ ] Implement graceful shutdown
- [ ] Add metrics collection

## Security Best Practices

1. Never hardcode credentials or keys in your agent code
2. Store private keys securely with appropriate permissions
3. Validate server certificates to prevent MITM attacks
4. Log authentication attempts but never log authentication tokens
5. Implement proper error handling to avoid leaking information
6. Use secure random number generation for message IDs

## Support

For assistance with agent implementation:
- Email: support@artcafe.ai
- Documentation: https://docs.artcafe.ai
- GitHub: https://github.com/artcafe-ai/agent-sdk