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
  - Client: `wss://ws.artcafe.ai/ws/client/{client_id}` (NKey auth - coming soon)
  - Agent (Legacy): `wss://ws.artcafe.ai/ws/agent/{agent_id}` (SSH auth - still supported)

### EC2 Instances
- **API Server**: `i-0cd295d6b239ca775` (3.229.1.223) - `prod-server-1`
- **NATS Server**: `i-089fc5ec51567037f` (3.239.238.118)

## Recent Changes (June 7-8, 2025)

### NKey Implementation and Python Library Fix

#### Problem Solved
The Python `nkeys` library (v0.2.1) was missing the `create_user_seed()` and `create_account_seed()` functions that exist in other language implementations (Go, JavaScript, Rust). This prevented proper NKey generation for clients.

#### Solution Implemented
Created a production-ready monkey patch (`nkeys_fix.py`) that adds the missing functions using the library's existing `encode_seed()` function:

```python
def create_user_seed() -> bytes:
    """Generate a new user NKey seed."""
    random_bytes = secrets.token_bytes(32)
    seed = nkeys.encode_seed(random_bytes, nkeys.PREFIX_BYTE_USER)
    return seed
```

#### Key Files
- `/nkeys_fix.py` - Monkey patch adding missing nkeys functions
- `/api/app.py` - Imports nkeys_fix at startup
- `/api/routes/client_routes.py` - Uses monkey-patched functions

#### Implementation Details
- Seeds follow NATS format: 58 characters, starting with 'SU' (user) or 'SA' (account)
- Uses cryptographically secure random generation (`secrets.token_bytes`)
- Properly validates seeds using `nkeys.from_seed()` before returning
- Includes rate limiting (100 keys per hour per tenant)

### NKey Authentication Migration
- **IMPORTANT**: System is transitioning from SSH keys to NATS NKeys
- **Terminology Changes**:
  - Tenant remains as tenant (organization)
  - Agent → Client (NKey-based)
  - Channel → Subject (coming soon)
- **Backend Updates**:
  - Added NKey fields to tenant model
  - New client model replaces agent model
  - Client routes use tenant_id (not account_id)
  - Account routes map to tenant service for compatibility
  - Fixed datetime serialization in client routes (must use `.isoformat()`)

### Previous Implementations (June 2025)

#### Topic Preview with NATS Forwarding (June 3)
- **Feature**: Real-time message monitoring for dashboard users
- **Implementation**:
  - Dashboard WebSocket handlers: `subscribe_topic_preview`, `unsubscribe_topic_preview`
  - NATS subscription pattern: `tenant.{tenant_id}.>`
  - Real-time forwarding from NATS to WebSocket clients
  - Proper cleanup on disconnect
- **Key Files**:
  - `/api/websocket.py` - Topic preview handlers and NATS forwarding
  - `/api/services/local_message_tracker.py` - Message tracking service

#### Message Tracking with Redis/Valkey (June 3)
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

#### Scalable WebSocket Management (June 1)
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
- `/api/services/agent_service.py` - Agent CRUD operations (legacy)
- `/api/services/client_service.py` - Client CRUD operations (new)
- `/api/services/tenant_service.py` - Multi-tenant management
- `/api/services/channel_service.py` - Channel management

### Authentication
- **JWT Auth**: Dashboard users via Cognito
- **NKey Auth**: Clients use Ed25519 keys (new)
- **SSH Auth**: Agents use SSH key challenge/response (legacy)

## Database Schema (DynamoDB)

### Active Tables (as of June 7, 2025)
1. **artcafe-tenants** - Organizations (with NKey fields added)
   - Primary key: `id` (tenant_id)
   - Fields: name, admin_email, subscription info, nkey_public, issuer_key
   
2. **artcafe-clients** - AI clients with NKey auth
   - Primary key: `client_id`
   - Indexes: TenantIndex, NKeyIndex
   - Fields: tenant_id, name, nkey_public, permissions, status
   
3. **artcafe-agents** - Legacy SSH-based agents
   - Primary key: `id` (agent_id)
   - Will be migrated to clients table
   
4. **artcafe-websocket-connections** - Active connections
   - Primary key: `connection_id`
   - TTL: 24 hours
   - Indexes: ServerIndex, TenantIndex, AgentIdIndex
   
5. **artcafe-channels** - Pub/sub channels
   - Primary key: `channel_id`
   
6. **artcafe-channel-subscriptions** - Agent-channel mappings
   - Primary key: agent_id + channel_id
   
7. **artcafe-user-profiles** - User profile data
   - Primary key: `user_id`
   
8. **artcafe-user-tenants** - User-organization mappings
   - Primary key: `user_id`
   
9. **artcafe-usage-metrics** - Usage tracking
   - Primary key: `id`
   
10. **artcafe-activity-logs** - Audit trail
    - Primary key: `id`
    
11. **artcafe-Challenges** - SSH auth challenges
    - Primary key: `challenge`
    - TTL: 5 minutes
    
12. **artcafe-nkey-seeds** - Encrypted NKey storage
    - Primary key: `seed_id`
    
13. **artcafe-subjects** - Future channel replacement
    - Primary key: `subject_id`

### Deleted Tables
- **artcafe-accounts** - Deleted June 7 (was unused duplicate of tenants)
- **artcafe-ssh-keys** - Deleted May 29 (keys now in agent records)

## Message Flow

```
Client/Agent → WebSocket → NATS → Other Clients/Agents
                ↓           ↓
             DynamoDB    Redis/Valkey
           (connection)  (tracking)
                ↓           ↓
             Dashboard ← Usage API
```

## Deployment Instructions

### Deploy Code Changes via SSM

```bash
# Basic deployment
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/artcafe/artcafe-pubsub",
    "git pull",
    "sudo systemctl restart artcafe-pubsub"
  ]'

# Deploy specific files (when not using git)
# 1. Create tar file locally
tar -czf deploy.tar.gz file1.py file2.py

# 2. Upload to EC2
scp -i ~/.ssh/agent-pubsub-key.pem deploy.tar.gz ubuntu@3.229.1.223:/tmp/

# 3. Extract and restart
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/artcafe/artcafe-pubsub",
    "sudo tar -xzf /tmp/deploy.tar.gz",
    "sudo chown -R ubuntu:ubuntu .",
    "sudo systemctl restart artcafe-pubsub"
  ]'
```

### Check Service Status

```bash
# Check logs
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo journalctl -u artcafe-pubsub -n 100 --no-pager"]'

# Test health
curl https://api.artcafe.ai/health

# Check service status
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo systemctl status artcafe-pubsub"]'
```

### Monitor Resources

```bash
# WebSocket connections
aws dynamodb scan --table-name artcafe-websocket-connections --select COUNT

# Active agents
aws dynamodb scan --table-name artcafe-agents \
  --filter-expression "status = :status" \
  --expression-attribute-values '{":status":{"S":"online"}}' \
  --select COUNT

# Redis stats
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["redis-cli INFO stats"]'
```

## API Endpoints

### Health & Status
- `GET /health` - Service health check

### Authentication
- `POST /api/v1/auth/agent/challenge` - Get agent auth challenge (legacy)
- `POST /api/v1/auth/agent/verify` - Verify agent signature (legacy)

### Accounts (Maps to Tenants)
- `GET /api/v1/accounts` - List user's organizations
- `GET /api/v1/accounts/{account_id}` - Get organization details
- `POST /api/v1/accounts/generate-nkey/{account_id}` - Generate NKey for organization
- `PUT /api/v1/accounts/{account_id}` - Update organization

### Clients (NKey-based)
- `GET /api/v1/clients` - List clients
- `POST /api/v1/clients` - Create client (returns NKey seed once!)
- `GET /api/v1/clients/{client_id}` - Get client details
- `PUT /api/v1/clients/{client_id}` - Update client
- `DELETE /api/v1/clients/{client_id}` - Delete client
- `POST /api/v1/clients/{client_id}/regenerate-nkey` - Regenerate NKey
- `GET /api/v1/clients/{client_id}/status` - Get connection status

### Agents (Legacy SSH-based)
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
- `GET /api/v1/usage/local/stats` - Local Redis stats

### Profile & Settings
- `GET /api/v1/profile/me` - Get user profile
- `PUT /api/v1/profile/me` - Update profile
- `GET /api/v1/profile/preferences` - Get preferences
- `PUT /api/v1/profile/preferences` - Update preferences

### Activity Logs
- `GET /api/v1/activity/logs` - Get activity logs
- `GET /api/v1/activity/summary` - Get activity summary

### WebSocket
- `WS /ws/agent/{agent_id}` - Agent connection (SSH auth)
- `WS /ws/client/{client_id}` - Client connection (NKey auth - coming)
- `WS /ws/dashboard` - Dashboard connection (JWT auth)

## WebSocket Message Types

### Agent/Client Messages
- `heartbeat` - Keep connection alive
- `publish` - Send message to channel/subject
- `subscribe` - Subscribe to channel/subject
- `unsubscribe` - Unsubscribe from channel/subject

### Dashboard Messages
- `subscribe_channel` - Monitor specific channel
- `unsubscribe_channel` - Stop monitoring channel
- `subscribe_topic_preview` - Monitor all tenant messages
- `unsubscribe_topic_preview` - Stop monitoring tenant

## Configuration

### Environment Variables
- `ARTCAFE_SERVER_ID` - Unique server identifier (e.g., "prod-server-1")
- `NATS_URL` - NATS server URL (nats://10.0.2.120:4222)
- `REDIS_URL` - Redis/Valkey URL for message tracking
- `AWS_REGION` - AWS region for DynamoDB (us-east-1)

### Service Configuration
- **Location**: `/etc/systemd/system/artcafe-pubsub.service`
- **User**: ubuntu
- **Working Directory**: `/opt/artcafe/artcafe-pubsub`
- **Port**: 8000

### CORS Configuration
Handled entirely by Nginx - no CORS middleware in FastAPI.

## Common Issues & Solutions

### Import Errors
- Always use absolute imports: `from models.tenant import Tenant`
- Never use relative imports beyond current package

### DynamoDB Indexes
- When changing key fields, must create new index first
- Delete old indexes after migration
- Pay-per-request mode doesn't need provisioned throughput

### Service Won't Start
1. Check for Python syntax errors
2. Verify all imports resolve
3. Check for missing dependencies (`pip list`)
4. Review systemd logs: `sudo journalctl -u artcafe-pubsub -n 100`

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

### Tenant-Based Architecture
- "Tenant" is the core organizational unit
- "Account" is just frontend-friendly terminology
- All backend services use tenant_id consistently

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

## Migration Notes

### SSH to NKey Migration (In Progress)
1. Agents table still uses SSH keys
2. Clients table uses NKeys
3. Both supported during transition
4. Frontend shows "Clients" but backend has both endpoints

### Future Changes
1. Channels → Subjects migration pending
2. Full NATS direct connection (remove WebSocket layer)
3. Deprecate agent endpoints in favor of client endpoints

## NKey Testing & Verification

### Testing Client Creation
```bash
# Create test script
cat > test_client.py << 'EOF'
import requests
import json

url = "https://api.artcafe.ai/api/v1/clients/"
headers = {
    "Authorization": "Bearer YOUR_JWT_TOKEN",
    "Content-Type": "application/json"
}

data = {
    "name": "Test Client",
    "metadata": {
        "description": "Testing NKey creation"
    }
}

response = requests.post(url, json=data, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
EOF

python3 test_client.py
```

### Verifying NKey Format
- Seeds: 58 characters starting with 'SU' (user) or 'SA' (account)
- Public keys: Start with 'U' (user) or 'A' (account)
- Example seed: `SUABNJPFBNZRAKTPYQQKAK2AQCB3YW7LIXUOQQX6KON7JRWCJHVBMOUASM`
- Example public key: `UBU7KSEJNNAN5L65PXC6GPWN2VKMWLLJRZDM6HVZKNV63Y4AAXY73Y2A`

### Common Deployment Commands
```bash
# Deploy single file using base64 encoding
base64 -w0 myfile.py > myfile.b64
aws ssm send-command --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "cd /opt/artcafe/artcafe-pubsub",
    "echo '"$(cat myfile.b64)"' | base64 -d > /tmp/myfile.py",
    "sudo mv /tmp/myfile.py path/to/destination.py",
    "sudo chown ubuntu:ubuntu path/to/destination.py",
    "sudo systemctl restart artcafe-pubsub"
  ]' --query 'Command.CommandId' --output text

# Check command result
sleep 5 && aws ssm get-command-invocation \
  --command-id COMMAND_ID \
  --instance-id i-0cd295d6b239ca775 \
  --query 'StandardOutputContent' --output text
```

Last updated: June 8, 2025