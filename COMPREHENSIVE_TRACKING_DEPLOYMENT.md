# Comprehensive Message Tracking Deployment Guide

## Overview

The Comprehensive Message Tracker provides bulletproof message tracking that:
- Cannot be bypassed by SDK modifications
- Tracks ALL messages regardless of subject pattern
- Monitors at the NATS system level
- Provides accurate byte counting for billing
- Stores metrics in Redis (real-time) and DynamoDB (persistent)

## Architecture

### 1. System-Level Monitoring
The tracker connects to NATS as a system monitor and subscribes to:
- System events (`$SYS.>` subjects)
- All tenant message patterns (`tenant.>`, `agent.>`, etc.)
- Connection/disconnection events
- Message flow statistics

### 2. Multi-Layer Tracking
```
┌─────────────────┐
│   NATS Server   │
│                 │
│ ┌─────────────┐ │     ┌──────────────────┐
│ │System Events│ │────▶│ Comprehensive    │
│ └─────────────┘ │     │ Message Tracker  │
│                 │     │                  │
│ ┌─────────────┐ │     │ ┌──────────────┐ │
│ │Message Flow │ │────▶│ │Redis Storage │ │
│ └─────────────┘ │     │ └──────────────┘ │
│                 │     │         │        │
│ ┌─────────────┐ │     │         ▼        │
│ │ Connection  │ │────▶│ ┌──────────────┐ │
│ │   Events    │ │     │ │  DynamoDB    │ │
│ └─────────────┘ │     │ │ Persistence  │ │
└─────────────────┘     │ └──────────────┘ │
                        └──────────────────┘
```

### 3. Data Flow
1. **Real-time Tracking**: All messages are intercepted and counted
2. **Redis Storage**: Immediate storage for current metrics
3. **DynamoDB Persistence**: Periodic persistence for billing/analytics
4. **Aggregation**: Hourly, daily, and monthly aggregations

## Deployment Steps

### Step 1: Update NATS Server Configuration

1. SSH into NATS server:
```bash
ssh -i your-key.pem ubuntu@3.239.238.118
```

2. Update NATS configuration to enable system events:
```bash
sudo nano /etc/nats-server.conf
```

Add or update:
```conf
# Enable system account
system_account: SYS

# System account configuration
accounts {
  SYS {
    users: [
      {
        user: "artcafe-monitor"
        password: "change-to-secure-password"
        permissions: {
          subscribe: {
            allow: ["$SYS.>", "_INBOX.>"]
          }
          publish: {
            deny: [">"]
          }
        }
      }
    ]
  }
}

# Enable monitoring
http_port: 8222
monitor_port: 8222

# Server identification
server_name: "artcafe-nats-1"

# Connection tracking
connect_error_reports: 10
reconnect_error_reports: 10
```

3. Restart NATS:
```bash
sudo systemctl restart nats-server
```

### Step 2: Deploy the Tracker Code

1. Deploy the comprehensive tracker:
```bash
cd /home/stvwhite/projects/artcafe/artcafe-pubsub

# Create base64 encoded files
base64 -w0 api/services/comprehensive_message_tracker.py > tracker.b64
base64 -w0 api/services/tracker_integration.py > integration.b64

# Deploy tracker
aws ssm send-command --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/artcafe/artcafe-pubsub",
    "echo '"$(cat tracker.b64)"' | base64 -d > api/services/comprehensive_message_tracker.py",
    "echo '"$(cat integration.b64)"' | base64 -d > api/services/tracker_integration.py",
    "sudo chown -R ubuntu:ubuntu api/services/",
    "sudo chmod 644 api/services/comprehensive_message_tracker.py",
    "sudo chmod 644 api/services/tracker_integration.py"
  ]' --query 'Command.CommandId' --output text
```

### Step 3: Update app.py

1. Create the app.py update:
```python
# In api/app.py, add at the top:
from api.services.tracker_integration import lifespan_with_tracker

# Update the FastAPI initialization:
app = FastAPI(
    title="ArtCafe PubSub API",
    description="Real-time messaging for AI agents",
    version="1.0.0",
    lifespan=lifespan_with_tracker  # Add this
)
```

2. Deploy the update:
```bash
# Update and deploy app.py with the tracker integration
```

### Step 4: Update Environment Variables

Add to the environment if not present:
```bash
aws ssm send-command --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "echo \"NATS_SYSTEM_USER=artcafe-monitor\" | sudo tee -a /etc/environment",
    "echo \"NATS_SYSTEM_PASSWORD=your-secure-password\" | sudo tee -a /etc/environment"
  ]'
```

### Step 5: Create DynamoDB Indexes (if needed)

The tracker uses the existing `artcafe-usage-metrics` table with these access patterns:
- `pk = CLIENT#{client_id}, sk = METRICS#{timestamp}`
- `pk = CLIENT#{client_id}, sk = SESSION#{connected_at}`
- `pk = TENANT#{tenant_id}, sk = METRICS#{timestamp}`
- `pk = TENANT#{tenant_id}, sk = HOURLY#{YYYYMMDDHH}`

### Step 6: Restart Services

```bash
aws ssm send-command --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "sudo systemctl restart artcafe-pubsub",
    "sleep 3",
    "curl -s https://api.artcafe.ai/health",
    "sudo journalctl -u artcafe-pubsub -n 50 --no-pager"
  ]' --query 'Command.CommandId' --output text
```

## Integration Points

### 1. Usage API Integration

Update usage routes to use comprehensive tracker:
```python
# In api/routes/usage_routes.py
from api.services.tracker_integration import get_comprehensive_usage_stats

@router.get("/api/v1/usage/stats")
async def get_usage_stats(tenant_id: str, client_id: Optional[str] = None):
    return await get_comprehensive_usage_stats(tenant_id, client_id)
```

### 2. WebSocket Integration

Track WebSocket messages:
```python
# In api/websocket.py
from api.services.tracker_integration import track_websocket_message

# When receiving a message
await track_websocket_message(
    connection_id=connection_id,
    tenant_id=tenant_id,
    message_type=message["type"],
    size=len(json.dumps(message))
)
```

### 3. Client Library Integration

For additional safety, wrap NATS clients:
```python
# In core/nats_client.py
from api.services.tracker_integration import TrackedNATSClient

# Wrap the NATS client
tracked_nc = TrackedNATSClient(nc)
tracked_nc.set_identity(client_id, tenant_id)
```

## Monitoring & Verification

### 1. Check Tracker Status
```bash
# Check if tracker is running
curl https://api.artcafe.ai/health

# Check Redis for tracking data
aws ssm send-command --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "redis-cli KEYS \"tracker:*\" | head -20",
    "redis-cli HGETALL \"tracker:global\""
  ]'
```

### 2. Monitor NATS System Events
```bash
# Check NATS monitoring endpoint
curl http://3.239.238.118:8222/varz
curl http://3.239.238.118:8222/subsz
curl http://3.239.238.118:8222/connz
```

### 3. Verify Message Tracking
```python
# Test script
import requests

# Get usage stats for a tenant
response = requests.get(
    "https://api.artcafe.ai/api/v1/usage/stats",
    params={"tenant_id": "your-tenant-id"},
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
print(response.json())
```

## Benefits

1. **Unbypassable**: Operates at NATS system level
2. **Comprehensive**: Tracks all messages, not just specific patterns
3. **Accurate**: Byte-level accuracy for billing
4. **Scalable**: Redis for speed, DynamoDB for persistence
5. **Resilient**: Continues tracking even if client crashes
6. **Auditable**: Complete message flow history

## Security Considerations

1. **System Account**: Use strong passwords for NATS system account
2. **Permissions**: Monitor account has read-only access
3. **Data Retention**: 30-day TTL on detailed metrics
4. **PII**: No message content is stored, only metadata

## Troubleshooting

### Tracker Not Starting
```bash
# Check logs
sudo journalctl -u artcafe-pubsub -f

# Common issues:
# - NATS system account not configured
# - Redis connection failed
# - Missing environment variables
```

### No Data Being Tracked
```bash
# Verify NATS subscriptions
curl http://3.239.238.118:8222/subsz

# Check Redis
redis-cli
> KEYS tracker:*
> HGETALL tracker:global
```

### High Memory Usage
```bash
# Check Redis memory
redis-cli INFO memory

# Clear old data if needed
redis-cli
> SCAN 0 MATCH tracker:client:* COUNT 1000
> DEL <old-keys>
```

## Cost Optimization

1. **DynamoDB**: Uses on-demand pricing, ~$0.25 per million writes
2. **Redis**: 60-second persistence interval reduces writes
3. **TTL**: Automatic cleanup of old data
4. **Aggregation**: Hourly rollups reduce storage

## Future Enhancements

1. **Machine Learning**: Anomaly detection for usage patterns
2. **Real-time Alerts**: Notify on usage spikes
3. **GraphQL API**: For complex usage queries
4. **Kafka Integration**: For event streaming
5. **Multi-region**: Cross-region replication