# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the ArtCafe PubSub service codebase.

## Session Notes - May 18, 2025

### Changes Made
1. **CORS Configuration**: Added `api.artcafe.ai` to allowed origins
2. **Agent Model**: Started removing `type` field requirement
3. **Tags**: Made optional in AgentMetadata
4. **Deployment**: Set up API Gateway as proxy

### Current State
- Service running on EC2 at `/opt/artcafe/artcafe-pubsub`
- API Gateway proxying requests
- CORS properly configured
- Need to complete model updates

### Deployment Info
- **EC2 Instance**: `i-0cd295d6b239ca775`
- **Service**: `artcafe-pubsub.service`
- **Direct URL**: `http://3.229.1.223:8000`
- **API Gateway**: `https://m9lm7i9ed7.execute-api.us-east-1.amazonaws.com/prod`

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
curl http://3.229.1.223:8000/health
```

### Agents
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents` - Create agent
- `DELETE /api/v1/agents/{agent_id}` - Delete agent

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
- `artcafe-agents`
- `artcafe-tenants`
- `artcafe-user-tenants`
- `artcafe-ssh-keys`

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