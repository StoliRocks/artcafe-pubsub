# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the ArtCafe PubSub service codebase.

## Session Notes - May 26, 2025

### Major Architecture Changes
1. **Removed API Gateway**: Direct Nginx routing to FastAPI
2. **Simplified Agent Auth**: No JWT tokens for agents, just SSH key challenge on WebSocket
3. **CORS in Nginx Only**: Removed CORSMiddleware from FastAPI
4. **Unified Nginx Config**: Single config handles both api.artcafe.ai and ws.artcafe.ai
5. **Cleaned Up**: Removed hundreds of outdated deployment scripts and fixes

### Current State
- Service running on EC2 at `/opt/artcafe/artcafe-pubsub`
- NO API Gateway - direct Nginx routing
- CORS handled by Nginx only
- Agent auth simplified (no JWT)
- All model updates completed

### Deployment Info
- **EC2 Instance**: `i-0cd295d6b239ca775`
- **Service**: `artcafe-pubsub.service`
- **Internal URL**: `http://127.0.0.1:8000`
- **Public Access**: 
  - **REST API**: `https://api.artcafe.ai` → Nginx → FastAPI
  - **WebSocket**: `wss://ws.artcafe.ai` → Nginx → FastAPI
- **NO API Gateway** - removed for simplicity

## Previous Session Notes - May 18, 2025

### Changes Made
1. **CORS Configuration**: Added `api.artcafe.ai` to allowed origins
2. **Agent Model**: Started removing `type` field requirement
3. **Tags**: Made optional in AgentMetadata
4. **Deployment**: Set up API Gateway as proxy
5. **WebSocket Auth**: Added JWT validation to dashboard WebSocket endpoint
6. **Usage Metrics**: Fixed to fetch real data from database

## Project Overview

ArtCafe.ai PubSub Service - FastAPI backend for agent management and NATS messaging.

## Key Files

### Configuration
- `/config/settings.py` - Main settings including CORS origins
- `/api/middleware.py` - CORS middleware configuration

### Models
- `/models/agent.py` - Agent data model (type field being removed)
- `/models/user_tenant.py` - Multi-tenant user associations

### API Routes
- `/api/routes/agent_routes.py` - Agent CRUD operations
- `/api/routes/tenant_routes.py` - Tenant management

### Services
- `/api/services/agent_service.py` - Agent business logic
- `/api/services/tenant_service.py` - Tenant operations

## Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python -m api.app

# Run with NATS
docker run -p 4222:4222 nats
NATS_ENABLED=true python -m api.app
```

### Deployment
```bash
# Deploy via SSM
aws ssm send-command \
  --instance-ids i-0cd295d6b239ca775 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/artcafe/artcafe-pubsub", "sudo systemctl restart artcafe-pubsub"]'

# Check service status
sudo systemctl status artcafe-pubsub
```

## API Endpoints

### Health Check
```bash
# Via custom domain
curl https://api.artcafe.ai/prod/health

# Direct to backend
curl http://3.229.1.223:8000/health
```

### Authentication
- `POST /api/v1/auth/challenge` - Get challenge for JWT-authenticated users
- `POST /api/v1/auth/agent/challenge` - Get challenge for agent authentication (no auth required)
- `POST /api/v1/auth/verify` - Verify signed challenge response
- `POST /api/v1/auth/agent/verify` - Verify agent signed challenge response

### Agents
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents` - Create agent
- `GET /api/v1/agents/{agent_id}` - Get specific agent
- `PUT /api/v1/agents/{agent_id}` - Update agent
- `DELETE /api/v1/agents/{agent_id}` - Delete agent
- `PUT /api/v1/agents/{agent_id}/status` - Update agent status

### SSH Keys
- `GET /api/v1/ssh-keys` - List SSH keys
- `POST /api/v1/ssh-keys` - Create SSH key
- `POST /api/v1/ssh-keys/generate` - Generate new SSH keypair
- `GET /api/v1/ssh-keys/{key_id}` - Get specific SSH key
- `DELETE /api/v1/ssh-keys/{key_id}` - Delete SSH key

### Channels
- `GET /api/v1/channels` - List channels
- `POST /api/v1/channels` - Create channel
- `GET /api/v1/channels/{channel_id}` - Get specific channel
- `PUT /api/v1/channels/{channel_id}` - Update channel
- `DELETE /api/v1/channels/{channel_id}` - Delete channel

### Channel Subscriptions
- `GET /api/v1/channel-subscriptions` - List subscriptions
- `POST /api/v1/channel-subscriptions` - Create subscription
- `DELETE /api/v1/channel-subscriptions/{subscription_id}` - Delete subscription

### Tenants
- `GET /api/v1/tenants/current` - Get current tenant info
- `PUT /api/v1/tenants/current` - Update current tenant

### WebSocket
- `WS /api/v1/agents/ws` - Agent WebSocket connection
- `WS /api/v1/dashboard/ws` - Dashboard WebSocket connection

## CORS Configuration

Current allowed origins in `settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://www.artcafe.ai",
    "https://artcafe.ai",
    "https://api.artcafe.ai",
    "https://d1isgvgjiqe68i.cloudfront.net"
]
```

## Database

Using DynamoDB with tables:
- `artcafe-agents` - Agent configurations (includes public SSH keys)
- `artcafe-tenants` - Tenant/organization data
- `artcafe-user-tenants` - User-to-tenant mappings
- `artcafe-user-tenant-index` - Reverse index for tenant-to-user lookups
- `artcafe-channels` - Messaging channels
- `artcafe-channel-subscriptions` - Agent channel subscriptions
- `artcafe-usage-metrics` - Resource usage tracking
- `artcafe-terms-acceptance` - Legal terms acceptance records
- `artcafe-Challenges` - Temporary authentication challenges (5-min TTL)

Note: SSH keys are stored directly in agent records, not in a separate table.
See `/docs/dynamodb_tables.md` for detailed documentation.

## To-Do

1. Complete removal of `type` field from agent model
2. Deploy model changes to production
3. Update agent creation to not require type
4. Test with frontend after deployment

## Architecture Notes

### Multi-Tenancy
- Tenant ID from JWT token or API header
- All queries scoped by tenant
- Agents isolated per tenant

### Authentication
- JWT tokens from Cognito
- SSH keys for agent authentication
- Challenge-response for agent onboarding

### Status Management
- Agent status determined by NATS connection
- WebSocket updates for real-time status
- No manual status changes allowed

## Recent Issues Fixed

1. **CORS**: Now handled by API Gateway
2. **Boolean Values**: Fixed DynamoDB boolean handling
3. **User-Tenant**: Fixed query issues

Last updated: May 18, 2025