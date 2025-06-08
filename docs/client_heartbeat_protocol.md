# Client Heartbeat Protocol

## Overview

All clients connecting to ArtCafe via NATS must implement a heartbeat protocol to maintain presence status and enable proper tracking.

## Protocol Requirements

### 1. Heartbeat Subject

Clients must publish heartbeats to:
```
_HEARTBEAT.tenant.{tenant_id}.client.{client_id}
```

### 2. Heartbeat Payload

```json
{
  "client_id": "string",
  "tenant_id": "string", 
  "timestamp": "ISO8601",
  "version": "1.0.0",
  "status": "healthy|degraded|unhealthy",
  "metrics": {
    "messages_sent": 0,
    "messages_received": 0,
    "errors": 0,
    "uptime_seconds": 0
  },
  "metadata": {
    "name": "string",
    "type": "string",
    "capabilities": ["array", "of", "strings"]
  }
}
```

### 3. Heartbeat Frequency

- **Required**: Every 30 seconds
- **Timeout**: Client marked offline after 90 seconds without heartbeat
- **Recommended**: Send heartbeat every 25-28 seconds to account for network latency

### 4. Connection Lifecycle

#### On Connect
1. Send initial heartbeat immediately
2. Include full metadata in first heartbeat
3. Start heartbeat timer

#### During Operation
1. Send heartbeat every 30 seconds
2. Include current metrics in each heartbeat
3. Update status based on internal health checks

#### On Disconnect
1. Send final heartbeat with status "disconnecting" (if graceful)
2. Stop heartbeat timer
3. Close NATS connection

### 5. Example Implementation

```python
import asyncio
import json
from datetime import datetime, timezone
import nats

class ArtCafeClient:
    def __init__(self, client_id, tenant_id, nkey_seed):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.nkey_seed = nkey_seed
        self.nc = None
        self.heartbeat_task = None
        self.start_time = datetime.now(timezone.utc)
        self.metrics = {
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0
        }
        
    async def connect(self):
        # Connect to NATS with NKey
        self.nc = await nats.connect(
            servers=["nats://nats.artcafe.ai:4222"],
            nkeys_seed=self.nkey_seed.encode()
        )
        
        # Send initial heartbeat
        await self._send_heartbeat()
        
        # Start heartbeat loop
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(30)
            await self._send_heartbeat()
            
    async def _send_heartbeat(self):
        subject = f"_HEARTBEAT.tenant.{self.tenant_id}.client.{self.client_id}"
        
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        heartbeat = {
            "client_id": self.client_id,
            "tenant_id": self.tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "status": "healthy",
            "metrics": {
                **self.metrics,
                "uptime_seconds": int(uptime)
            },
            "metadata": {
                "name": "My Client",
                "type": "data_processor",
                "capabilities": ["process", "analyze", "report"]
            }
        }
        
        await self.nc.publish(subject, json.dumps(heartbeat).encode())
```

## Monitoring Benefits

Clients that implement the heartbeat protocol gain access to:

1. **Presence Tracking**: Real-time online/offline status
2. **Health Monitoring**: Track client health and performance
3. **Usage Analytics**: Detailed metrics about message flow
4. **Alerting**: Get notified of client issues
5. **Debugging**: Historical data for troubleshooting

## Compliance

- Clients not implementing heartbeats will show as "status unknown"
- May be subject to rate limiting or connection termination
- Premium features require heartbeat compliance