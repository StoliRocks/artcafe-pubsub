# ArtCafe.ai Agent Python SDK

This SDK provides a client implementation for ArtCafe.ai agents to connect to the PubSub service.

## Installation

```bash
# From PyPI (once published)
pip install artcafe-agent

# From source
git clone https://github.com/artcafe-ai/agent-sdk.git
cd agent-sdk/python
pip install -e .
```

## Quick Start

```python
import asyncio
import logging
from artcafe_agent import ArtCafeAgent

# Setup logging
logging.basicConfig(level=logging.INFO)

async def main():
    # Create agent
    agent = ArtCafeAgent(
        agent_id="your-agent-id",
        tenant_id="your-tenant-id",
        private_key_path="/path/to/private_key"
    )
    
    # Register command handlers
    async def handle_process_data(args):
        # Process data and return result
        data = args.get("data", {})
        return {"processed": True, "result": f"Processed {len(data)} items"}
    
    agent.register_command("process_data", handle_process_data)
    
    # Start agent
    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Authentication

The SDK handles authentication automatically using the SSH key challenge-response flow:

1. The agent requests a challenge from the ArtCafe.ai platform
2. The agent signs the challenge with its private key
3. The platform verifies the signature and issues a JWT token
4. The agent uses the JWT token for subsequent API calls

## Commands

Register command handlers for your agent:

```python
# Simple command
async def handle_ping(args):
    return {"pong": True}

agent.register_command("ping", handle_ping)

# More complex command
async def handle_transform(args):
    data = args.get("data", [])
    transform_type = args.get("type", "uppercase")
    
    if transform_type == "uppercase":
        result = [item.upper() for item in data]
    elif transform_type == "lowercase":
        result = [item.lower() for item in data]
    else:
        raise ValueError(f"Unknown transform type: {transform_type}")
    
    return {"transformed": result}

agent.register_command("transform", handle_transform)
```

## Status Updates

Update your agent's status:

```python
# Set status to busy with current task
await agent.update_status("busy", task_id="task-123", progress=50)

# Set status to error
await agent.update_status("error")

# Set status back to online
await agent.update_status("online")
```

## Configuration

The SDK accepts the following configuration:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent_id` | Unique identifier for this agent | (required) |
| `tenant_id` | Tenant identifier | (required) |
| `private_key_path` | Path to agent's SSH private key | (required) |
| `api_endpoint` | Base URL for ArtCafe PubSub API | https://api.artcafe.ai |
| `log_level` | Logging verbosity | INFO |
| `heartbeat_interval` | Seconds between heartbeats | 30 |

## Advanced Usage

### Custom Metrics

Send custom metrics with heartbeats:

```python
import psutil

# The SDK will automatically include these metrics if psutil is installed
# But you can also manually include metrics in your status updates:

memory = psutil.virtual_memory()
cpu = psutil.cpu_percent(interval=1)

await agent.update_status("online", metrics={
    "cpu_percent": cpu,
    "memory_percent": memory.percent,
    "disk_usage": psutil.disk_usage('/').percent
})
```

### Error Handling

The SDK implements automatic reconnection with exponential backoff:

```python
# Customize error handling
try:
    await agent.start()
except Exception as e:
    logging.error(f"Fatal error: {e}")
    # Implement custom error reporting
    send_alert_email(f"Agent {agent.agent_id} failed: {e}")
```

## Security Considerations

1. Store private keys securely with appropriate permissions
2. Never hardcode credentials in your agent code
3. Use environment variables for sensitive values
4. Run agents with minimal privileges
5. Regularly rotate SSH keys

## Support

For assistance with the SDK:
- Email: support@artcafe.ai
- Documentation: https://docs.artcafe.ai
- GitHub: https://github.com/artcafe-ai/agent-sdk