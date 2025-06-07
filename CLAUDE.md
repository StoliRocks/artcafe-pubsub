# CLAUDE.md - ArtCafe PubSub Service Backend Guide

This file provides guidance to Claude Code (claude.ai/code) when working with the ArtCafe PubSub backend service.

## Current Architecture (June 2025)

### Infrastructure Overview
- **Direct EC2 Deployment**: FastAPI app running on EC2 via systemd
- **NO API Gateway**: Removed May 26 for simplicity
- **Nginx Reverse Proxy**: Routes requests directly to FastAPI
- **NATS Messaging**: Core message broker for agent communication
- **Redis/Valkey**: Message tracking and usage metrics
- **DynamoDB**: All persistent data storage

### Service URLs
- **REST API**: `https://api.artcafe.ai` → Nginx → FastAPI
- **WebSocket Endpoints**:
  - Dashboard: `wss://ws.artcafe.ai/ws/dashboard` (JWT auth)
  - Agent: `wss://ws.artcafe.ai/ws/agent/{agent_id}` (SSH auth)

### EC2 Instances
- **API Server**: `i-0cd295d6b239ca775` (3.229.1.223) - `prod-server-1`
- **NATS Server**: `i-089fc5ec51567037f` (3.239.238.118)

## Recent Implementations (June 2025)

### Topic Preview with NATS Forwarding (June 3)
- **Feature**: Real-time message monitoring for dashboard users
- **Implementation**:
  - Dashboard WebSocket handlers: `subscribe_topic_preview`, `unsubscribe_topic_preview`
  - NATS subscription pattern: `tenant.{tenant_id}.>`
  - Real-time forwarding from NATS to WebSocket clients
  - Proper cleanup on disconnect
- **Key Files**:
  - `/api/websocket.py` - Topic preview handlers and NATS forwarding
  - `/api/services/local_message_tracker.py` - Message tracking service

### Message Tracking with Redis/Valkey (June 3)
- **Feature**: Real-time usage metrics for billing
- **Implementation**:
  - Redis/Valkey stores message counts by tenant/agent/channel
  - Tracking integrated into websocket.py message flow
  - Stats stored in `stats:d:{date}:{tenant_id}` keys
  - Frontend fetches data via `/api/v1/usage/metrics` endpoint
- **Fixed Issues**:
  - Singleton pattern for message tracker
  - Added startup event to connect to Redis
  - JWT clock drift (added 30-second leeway)

### Scalable WebSocket Management (June 1)
- **DynamoDB Table**: `artcafe-websocket-connections`
  - Tracks all WebSocket connections across servers
  - TTL-enabled (24 hours) for automatic cleanup
  - Supports horizontal scaling
- **Heartbeat System**:
  - Agents send heartbeats every 30s
  - Timeout after 90s marks agents offline
  - Cleanup task runs every 5 minutes (cost-optimized)
  - HeartbeatAgent class in SDK for automatic heartbeats

## Key Services

### Core Services
- `/api/services/websocket_connection_service.py` - DynamoDB connection state
- `/api/services/connection_heartbeat_service.py` - Agent health monitoring
- `/api/services/local_message_tracker.py` - Redis/Valkey message tracking
- `/api/services/agent_service.py` - Agent CRUD operations
- `/api/services/tenant_service.py` - Multi-tenant management
- `/api/services/channel_service.py` - Channel management

### Authentication
- **JWT Auth**: Dashboard users via Cognito
- **SSH Auth**: Agents use SSH key challenge/response
- **No JWT for Agents**: Simplified auth flow

## Database Schema (DynamoDB)

### Core Tables
- `artcafe-agents` - Agent configurations with SSH keys
- `artcafe-websocket-connections` - Active WebSocket connections
- `artcafe-tenants` - Organization data
- `artcafe-channels` - Messaging channels
- `artcafe-channel-subscriptions` - Agent-channel mappings
- `artcafe-usage-metrics` - Usage tracking
- `artcafe-Challenges` - Auth challenges (5-min TTL)

## Message Flow

```
Agent → WebSocket → NATS → Other Agents
         ↓           ↓
      DynamoDB    Redis/Valkey
    (connection)  (tracking)
         ↓           ↓
      Dashboard ← Usage API
```

## Deployment Commands

```bash
# Deploy via SSM
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/artcafe/artcafe-pubsub", "sudo systemctl restart artcafe-pubsub"]'

# Check logs
sudo journalctl -u artcafe-pubsub -f

# Test health
curl https://api.artcafe.ai/health

# Monitor connections
aws dynamodb scan --table-name artcafe-websocket-connections --query "Count"
```

## API Endpoints

### Health & Status
- `GET /health` - Service health check

### Authentication
- `POST /api/v1/auth/agent/challenge` - Get agent auth challenge
- `POST /api/v1/auth/agent/verify` - Verify agent signature

### Agents
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents` - Create agent
- `GET /api/v1/agents/{agent_id}` - Get agent details
- `PUT /api/v1/agents/{agent_id}` - Update agent
- `DELETE /api/v1/agents/{agent_id}` - Delete agent

### Channels
- `GET /api/v1/channels` - List channels
- `POST /api/v1/channels` - Create channel
- `POST /api/v1/channels/{channel_id}/messages` - Publish to channel

### Usage & Metrics
- `GET /api/v1/usage/metrics` - Get real-time usage data
- `GET /api/v1/usage/current` - Current billing period usage

### WebSocket
- `WS /ws/agent/{agent_id}` - Agent connection (SSH auth)
- `WS /ws/dashboard` - Dashboard connection (JWT auth)

## WebSocket Message Types

### Agent Messages
- `heartbeat` - Keep connection alive
- `publish` - Send message to channel
- `subscribe` - Subscribe to channel
- `unsubscribe` - Unsubscribe from channel

### Dashboard Messages
- `subscribe_channel` - Monitor specific channel
- `unsubscribe_channel` - Stop monitoring channel
- `subscribe_topic_preview` - Monitor all tenant messages
- `unsubscribe_topic_preview` - Stop monitoring tenant

## Configuration

### Environment Variables
- `ARTCAFE_SERVER_ID` - Unique server identifier (e.g., "prod-server-1")
- `NATS_URL` - NATS server URL
- `REDIS_URL` - Redis/Valkey URL for message tracking
- `AWS_REGION` - AWS region for DynamoDB

### CORS Configuration
Handled entirely by Nginx - no CORS middleware in FastAPI.

## Known Issues & TODOs

### Topic Preview Enhancements Needed
1. Add rate limiting to prevent message flooding
2. Implement message filtering by topic pattern
3. Add support for granular subscription patterns
4. Include message routing path metadata
5. Add circuit breaker for overloaded clients

### Message Tracking Enhancements
1. Add hourly/daily rollup aggregations
2. Implement data retention policies
3. Add export capabilities for billing

## Testing

### Monitor WebSocket Connections
```python
# See /test_websocket_tracking.py for connection monitoring
# See /test_agent_status.py for agent status checks
# See /test_heartbeat_agent.py for heartbeat example
```

### Channel Testing
```bash
# Publish test message
curl -X POST https://api.artcafe.ai/api/v1/channels/{channel_id}/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

## Architecture Decisions

### No Lambda Functions
- All services run directly on EC2
- Simplifies deployment and debugging
- Better performance for WebSocket connections

### Direct Nginx Routing
- No API Gateway complexity
- Lower latency
- Easier SSL/WebSocket configuration

### DynamoDB for Shared State
- No coordination required between servers
- Each server operates independently
- Supports horizontal scaling

### Redis/Valkey for Metrics
- Fast message counting
- Real-time usage tracking
- Separate from persistent storage

## Data Persistence & Backup (June 4)

### Redis/Valkey Persistence
- **AOF Enabled**: `appendfsync everysec` - 1-second max data loss
- **RDB Snapshots**: Every 30 seconds with 1000+ changes
- **Config Location**: `/etc/redis/redis.conf`
- **Data Files**: `/var/lib/redis/dump.rdb` and `appendonly.aof`

### Backup Infrastructure
- **Local Backups**: `/opt/artcafe/redis-backups/` (48-hour retention)
- **S3 Bucket**: `artcafe-usage-backups` (ready but not active)
- **Recovery**: Automatic on Redis restart from AOF/RDB files

### Recovery Commands
```bash
# Check persistence status
redis-cli CONFIG GET appendonly
redis-cli CONFIG GET save

# Manual backup
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb /opt/artcafe/redis-backups/dump_$(date +%Y%m%d_%H%M%S).rdb

# View backups
ls -la /opt/artcafe/redis-backups/
```

Last updated: June 4, 2025