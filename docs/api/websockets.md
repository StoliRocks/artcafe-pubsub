# WebSocket API Guide

This document explains how to use the ArtCafe.ai PubSub WebSocket API for real-time messaging.

## Overview

The WebSocket API allows agents to:

1. Establish real-time bidirectional communication
2. Send and receive messages in channels
3. Receive real-time updates and notifications

## Authentication

WebSocket connections require authentication using JWT tokens. The token can be provided as a query parameter when establishing the connection:

```
ws://api.artcafe.ai/v1/ws?token=your_jwt_token
```

If no token is provided, the connection will be rejected.

## WebSocket Endpoints

### Main WebSocket Endpoint

```
ws://api.artcafe.ai/v1/ws?token=your_jwt_token&channel_id=optional_channel_id
```

Parameters:
- `token` (required): JWT authentication token
- `channel_id` (optional): Channel ID to connect to

If a channel ID is provided, the WebSocket will be subscribed to messages from that channel. If not, the WebSocket will only receive direct messages addressed to the agent.

### Channel-Specific WebSocket Endpoint

```
ws://api.artcafe.ai/v1/ws/tenant/{tenant_id}/agent/{agent_id}/channel/{channel_id}?token=your_jwt_token
```

Parameters:
- `tenant_id`: Tenant ID
- `agent_id`: Agent ID
- `channel_id`: Channel ID
- `token` (required): JWT authentication token

This endpoint is specifically for connecting to a particular channel. The tenant ID, agent ID, and channel ID must match the ones in the token.

## Message Format

### Sending Messages

Messages sent to the WebSocket server must be in JSON format:

```json
{
  "id": "unique-message-id",
  "type": "message",
  "content": "Hello, world!",
  "metadata": {
    "key": "value"
  }
}
```

The server will automatically add the following fields:
- `tenant_id`: Tenant ID from the token
- `agent_id`: Agent ID from the token
- `channel_id`: Channel ID from the connection (if applicable)
- `timestamp`: Current timestamp in ISO 8601 format

### Receiving Messages

Messages received from the WebSocket server will be in JSON format:

```json
{
  "id": "unique-message-id",
  "type": "message",
  "content": "Hello, world!",
  "tenant_id": "tenant-123",
  "agent_id": "agent-456",
  "channel_id": "channel-789",
  "timestamp": "2023-07-01T12:00:00Z",
  "metadata": {
    "key": "value"
  }
}
```

### Acknowledgments

When a message is successfully received and processed by the server, an acknowledgment is sent back:

```json
{
  "type": "ACK",
  "message_id": "unique-message-id",
  "timestamp": "2023-07-01T12:00:00Z"
}
```

### Errors

If an error occurs while processing a message, an error response is sent back:

```json
{
  "type": "ERROR",
  "error": "Error message",
  "timestamp": "2023-07-01T12:00:00Z"
}
```

## WebSocket Lifecycle

1. **Connection**
   - The client establishes a WebSocket connection with authentication
   - The server validates the token and tenant/agent information
   - If valid, the connection is accepted

2. **Message Exchange**
   - The client can send messages to the server
   - The server forwards messages to all connected clients in the same channel
   - The server sends acknowledgments for received messages

3. **Disconnection**
   - The client or server can close the connection
   - When disconnected, the agent's status is automatically set to "offline"
   - To reconnect, a new WebSocket connection must be established

## Client Implementation Examples

### JavaScript (Browser) Example

```javascript
class ArtCafeWebSocketClient {
  constructor(baseUrl, token, channelId = null) {
    this.baseUrl = baseUrl;
    this.token = token;
    this.channelId = channelId;
    this.socket = null;
    this.messageCallbacks = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectTimeout = 1000; // Start with 1 second, will increase exponentially
  }

  connect() {
    // Build the WebSocket URL
    let url = `${this.baseUrl}/ws?token=${this.token}`;
    if (this.channelId) {
      url += `&channel_id=${this.channelId}`;
    }

    // Create WebSocket connection
    this.socket = new WebSocket(url);

    // Set up event handlers
    this.socket.onopen = this._onOpen.bind(this);
    this.socket.onmessage = this._onMessage.bind(this);
    this.socket.onclose = this._onClose.bind(this);
    this.socket.onerror = this._onError.bind(this);

    // Return a promise that resolves when the connection is open
    return new Promise((resolve, reject) => {
      const onOpen = () => {
        this.socket.removeEventListener('open', onOpen);
        resolve();
      };
      const onError = (error) => {
        this.socket.removeEventListener('error', onError);
        reject(error);
      };
      this.socket.addEventListener('open', onOpen);
      this.socket.addEventListener('error', onError);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  sendMessage(content, metadata = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    const messageId = this._generateId();
    const message = {
      id: messageId,
      type: 'message',
      content: content,
      metadata: metadata
    };

    // Send the message
    this.socket.send(JSON.stringify(message));

    // Return a promise that resolves when the message is acknowledged
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.messageCallbacks.delete(messageId);
        reject(new Error('Message acknowledgment timeout'));
      }, 5000);

      this.messageCallbacks.set(messageId, {
        resolve,
        reject,
        timeout
      });
    });
  }

  onMessage(callback) {
    this._onMessageCallback = callback;
    return this;
  }

  _onOpen(event) {
    console.log('WebSocket connected');
    this.reconnectAttempts = 0;
  }

  _onMessage(event) {
    try {
      const message = JSON.parse(event.data);

      // Handle ACK messages
      if (message.type === 'ACK' && message.message_id) {
        const callback = this.messageCallbacks.get(message.message_id);
        if (callback) {
          clearTimeout(callback.timeout);
          callback.resolve(message);
          this.messageCallbacks.delete(message.message_id);
        }
        return;
      }

      // Handle ERROR messages
      if (message.type === 'ERROR' && message.message_id) {
        const callback = this.messageCallbacks.get(message.message_id);
        if (callback) {
          clearTimeout(callback.timeout);
          callback.reject(new Error(message.error));
          this.messageCallbacks.delete(message.message_id);
        }
        return;
      }

      // Handle regular messages
      if (this._onMessageCallback) {
        this._onMessageCallback(message);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  }

  _onClose(event) {
    console.log('WebSocket disconnected:', event.code, event.reason);

    // Clean up callbacks
    for (const [messageId, callback] of this.messageCallbacks.entries()) {
      clearTimeout(callback.timeout);
      callback.reject(new Error('WebSocket disconnected'));
      this.messageCallbacks.delete(messageId);
    }

    // Attempt to reconnect if not a deliberate close
    if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(30000, this.reconnectTimeout * Math.pow(2, this.reconnectAttempts - 1));
      console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      setTimeout(() => this.connect(), delay);
    }
  }

  _onError(error) {
    console.error('WebSocket error:', error);
  }

  _generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
  }
}

// Usage example
async function connectToChannel() {
  const client = new ArtCafeWebSocketClient(
    'wss://api.artcafe.ai/v1',
    'your_jwt_token',
    'channel-123'
  );

  try {
    await client.connect();
    
    // Set up message handler
    client.onMessage((message) => {
      console.log('Received message:', message);
      // Handle message...
    });
    
    // Send a message
    await client.sendMessage('Hello, world!', { importance: 'high' });
    console.log('Message sent and acknowledged');
    
    // Disconnect after some time
    setTimeout(() => {
      client.disconnect();
    }, 60000);
  } catch (error) {
    console.error('Error connecting to WebSocket:', error);
  }
}

connectToChannel();
```

### Python Example

```python
import json
import asyncio
import websockets
import time
import random
import string

class ArtCafeWebSocketClient:
    def __init__(self, base_url, token, channel_id=None):
        self.base_url = base_url
        self.token = token
        self.channel_id = channel_id
        self.websocket = None
        self.message_callbacks = {}
        self.on_message_callback = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_timeout = 1  # Start with 1 second, will increase exponentially
        self.running = False
    
    async def connect(self):
        # Build the WebSocket URL
        url = f"{self.base_url}/ws?token={self.token}"
        if self.channel_id:
            url += f"&channel_id={self.channel_id}"
        
        try:
            # Create WebSocket connection
            self.websocket = await websockets.connect(url)
            self.running = True
            self.reconnect_attempts = 0
            print("WebSocket connected")
            
            # Start the message receiving loop
            asyncio.create_task(self._message_loop())
            
            return True
        except Exception as e:
            print(f"Error connecting to WebSocket: {e}")
            self.websocket = None
            return False
    
    async def disconnect(self):
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
    
    async def send_message(self, content, metadata=None):
        if not self.websocket:
            raise Exception("WebSocket is not connected")
        
        message_id = self._generate_id()
        message = {
            "id": message_id,
            "type": "message",
            "content": content,
            "metadata": metadata or {}
        }
        
        # Send the message
        await self.websocket.send(json.dumps(message))
        
        # Create a future for the acknowledgment
        future = asyncio.Future()
        self.message_callbacks[message_id] = future
        
        # Set a timeout for the acknowledgment
        def timeout_callback():
            if not future.done():
                future.set_exception(Exception("Message acknowledgment timeout"))
                self.message_callbacks.pop(message_id, None)
        
        asyncio.get_event_loop().call_later(5, timeout_callback)
        
        # Wait for the acknowledgment
        return await future
    
    def on_message(self, callback):
        self.on_message_callback = callback
        return self
    
    async def _message_loop(self):
        try:
            while self.running and self.websocket:
                message = await self.websocket.recv()
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")
            await self._handle_disconnect()
        except Exception as e:
            print(f"Error in message loop: {e}")
            await self._handle_disconnect()
    
    async def _handle_message(self, message_data):
        try:
            message = json.loads(message_data)
            
            # Handle ACK messages
            if message.get("type") == "ACK" and "message_id" in message:
                message_id = message["message_id"]
                if message_id in self.message_callbacks:
                    self.message_callbacks[message_id].set_result(message)
                    self.message_callbacks.pop(message_id, None)
                return
            
            # Handle ERROR messages
            if message.get("type") == "ERROR" and "message_id" in message:
                message_id = message["message_id"]
                if message_id in self.message_callbacks:
                    self.message_callbacks[message_id].set_exception(
                        Exception(message.get("error", "Unknown error"))
                    )
                    self.message_callbacks.pop(message_id, None)
                return
            
            # Handle regular messages
            if self.on_message_callback:
                await self.on_message_callback(message)
        except json.JSONDecodeError:
            print(f"Error parsing WebSocket message: {message_data}")
        except Exception as e:
            print(f"Error handling WebSocket message: {e}")
    
    async def _handle_disconnect(self):
        self.websocket = None
        
        # Reject all pending callbacks
        for message_id, future in self.message_callbacks.items():
            if not future.done():
                future.set_exception(Exception("WebSocket disconnected"))
        self.message_callbacks.clear()
        
        # Attempt to reconnect if not a deliberate close
        if self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = min(30, self.reconnect_timeout * (2 ** (self.reconnect_attempts - 1)))
            print(f"Reconnecting in {delay} seconds (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})...")
            await asyncio.sleep(delay)
            await self.connect()
    
    def _generate_id(self):
        timestamp = int(time.time() * 1000)
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{timestamp}-{random_str}"

# Usage example
async def connect_to_channel():
    client = ArtCafeWebSocketClient(
        "wss://api.artcafe.ai/v1",
        "your_jwt_token",
        "channel-123"
    )
    
    try:
        await client.connect()
        
        # Set up message handler
        async def handle_message(message):
            print(f"Received message: {message}")
            # Handle message...
        
        client.on_message(handle_message)
        
        # Send a message
        response = await client.send_message("Hello, world!", {"importance": "high"})
        print(f"Message sent and acknowledged: {response}")
        
        # Keep the connection open for a while
        await asyncio.sleep(60)
        
        # Disconnect
        await client.disconnect()
    except Exception as e:
        print(f"Error: {e}")

# Run the example
if __name__ == "__main__":
    asyncio.run(connect_to_channel())
```

## Best Practices

1. **Authentication**
   - Always use HTTPS/WSS for secure connections
   - Store tokens securely and refresh them as needed
   - Validate token expiration and refresh proactively

2. **Connection Management**
   - Implement reconnection logic with exponential backoff
   - Handle disconnections gracefully
   - Monitor connection state and health

3. **Message Handling**
   - Use unique message IDs for tracking
   - Implement acknowledgment timeouts
   - Handle and log errors appropriately

4. **Performance**
   - Limit the number of concurrent WebSocket connections
   - Batch messages when possible
   - Implement proper error handling and recovery

5. **Security**
   - Validate all incoming messages
   - Never trust client data without validation
   - Implement rate limiting to prevent abuse