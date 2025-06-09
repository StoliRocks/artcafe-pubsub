# ArtCafe.ai Python SDK

This SDK provides a client implementation for ArtCafe.ai agents to connect directly to NATS using NKey authentication.

## Installation

```bash
pip install nats-py
```

## Quick Start

```python
import asyncio
from artcafe_agent import ArtCafeAgent

async def main():
    # Create agent with NKey authentication
    agent = ArtCafeAgent(
        client_id="your-client-id",
        tenant_id="your-tenant-id",
        nkey_seed="SUABTHCUEEB7DW66XQTPYIJT4OXFHX72FYAC26I6F4MWCKMTFSFP7MRY5U"
    )
    
    # Connect to NATS
    await agent.connect()
    
    # Subscribe to messages
    async def handle_task(subject, data):
        print(f"Received task on {subject}: {data}")
        # Process and return result
        result = {"task_id": data.get("id"), "status": "completed"}
        await agent.publish("tasks.complete", result)
    
    await agent.subscribe("tasks.*", handle_task)
    
    # Publish a message
    await agent.publish("status.online", {"client_id": agent.client_id})
    
    # Keep running
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
```

## Authentication

The SDK uses NKey authentication for secure connection to NATS:

1. Create a client in the ArtCafe dashboard
2. Save the NKey seed (shown only once)
3. Use the seed to authenticate your agent

## Core Methods

### Connect and Disconnect

```python
# Connect to NATS
await agent.connect()

# Disconnect when done
await agent.disconnect()
```

### Subscribe to Messages

```python
# Subscribe with a handler function
async def message_handler(subject, data):
    print(f"Message on {subject}: {data}")

await agent.subscribe("events.*", message_handler)

# Or use the decorator pattern
@agent.on_message("alerts.high")
async def handle_alert(subject, data):
    print(f"Alert: {data}")
```

### Publish Messages

```python
# Publish JSON data
await agent.publish("sensor.temperature", {"value": 23.5, "unit": "celsius"})

# Publish raw bytes
await agent.publish("binary.data", b"raw bytes data")
```

### Request/Response Pattern

```python
# Send request and wait for response
try:
    response = await agent.request("service.echo", {"message": "hello"}, timeout=5.0)
    print(f"Response: {response}")
except TimeoutError:
    print("Request timed out")
```

## Configuration

The SDK accepts the following parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `client_id` | Your client ID from ArtCafe dashboard | (required) |
| `tenant_id` | Your tenant/organization ID | (required) |
| `nkey_seed` | NKey seed string or path to seed file | (required) |
| `nats_url` | NATS server URL | nats://nats.artcafe.ai:4222 |
| `name` | Friendly name for the agent | (client_id) |
| `metadata` | Optional metadata dictionary | {} |
| `log_level` | Logging verbosity | INFO |
| `heartbeat_interval` | Seconds between heartbeats | 30 |

## Subject Patterns

NATS uses dot-separated subjects with wildcards:

- `*` matches a single token
- `>` matches one or more tokens

Examples:
```python
# Subscribe to all temperature sensors
await agent.subscribe("sensors.temperature.*")

# Subscribe to all sensor data
await agent.subscribe("sensors.>")

# Subscribe to specific sensor
await agent.subscribe("sensors.temperature.room1")
```

## Error Handling

The SDK includes automatic reconnection and error callbacks:

```python
# Connection will automatically reconnect on failure
# Errors are logged automatically

# For custom error handling
agent = ArtCafeAgent(
    client_id="my-client",
    tenant_id="my-tenant",
    nkey_seed=seed,
    log_level="DEBUG"  # More verbose logging
)
```

## Example: Multi-Agent System

```python
# Agent 1: Data Producer
producer = ArtCafeAgent(
    client_id="producer-1",
    tenant_id="my-tenant",
    nkey_seed=producer_seed
)

await producer.connect()

# Publish sensor data
while True:
    data = {"temperature": read_sensor(), "timestamp": datetime.utcnow().isoformat()}
    await producer.publish("sensors.temperature.outdoor", data)
    await asyncio.sleep(5)

# Agent 2: Data Processor
processor = ArtCafeAgent(
    client_id="processor-1", 
    tenant_id="my-tenant",
    nkey_seed=processor_seed
)

await processor.connect()

@processor.on_message("sensors.temperature.*")
async def process_temperature(subject, data):
    if data["temperature"] > 30:
        await processor.publish("alerts.high_temp", {
            "sensor": subject,
            "value": data["temperature"],
            "timestamp": data["timestamp"]
        })

await processor.start()
```

## Support

For assistance:
- Documentation: https://docs.artcafe.ai
- Dashboard: https://www.artcafe.ai/dashboard