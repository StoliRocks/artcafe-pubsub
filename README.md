# ArtCafe PubSub Service

## Overview

The ArtCafe PubSub Service is the core messaging backbone for the ArtCafe.ai platform, providing:
- REST API endpoints for platform management
- WebSocket connections for real-time communication
- NATS integration for pub/sub messaging
- Multi-tenant isolation
- Two authentication methods: Cognito JWT for humans, SSH keys for agents

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Nginx (Port 443)                  │
│  • SSL Termination                                  │
│  • CORS Headers                                     │
│  • Request Routing                                  │
│  • WebSocket Upgrade                                │
└────────────────────┬───────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────┐
│               FastAPI (Port 8000)                   │
│  • Business Logic                                   │
│  • Authentication/Authorization                     │
│  • DynamoDB Operations                             │
│  • NATS Pub/Sub                                   │
└────────────────────────────────────────────────────┘
```

## Authentication

### Human Users (Dashboard/API)
- **Method**: AWS Cognito JWT tokens
- **Endpoints**: All REST API endpoints, Dashboard WebSocket
- **Header**: `Authorization: Bearer <jwt_token>`

### Agents (Machines)
- **Method**: SSH key challenge-response
- **Endpoint**: Agent WebSocket only
- **Connection**: `wss://ws.artcafe.ai/api/v1/ws/agent/{agent_id}?challenge=X&signature=Y&tenant_id=Z`
- **No JWT tokens required** - connection itself is the authenticated session

## Key Endpoints

### REST API
- `GET /health` - Health check
- `GET/POST/PUT/DELETE /api/v1/agents` - Agent management
- `GET/POST/PUT/DELETE /api/v1/channels` - Channel management
- `GET /api/v1/tenants` - Tenant operations
- `GET /api/v1/usage-metrics` - Usage statistics
- `POST /api/v1/agents/auth/challenge` - Agent challenge (legacy)
- `POST /api/v1/agents/auth/verify` - Agent verify (legacy)

### WebSocket
- `/api/v1/ws/dashboard` - Dashboard real-time events (JWT auth)
- `/api/v1/ws/agent/{agent_id}` - Agent messaging (SSH key auth)

## Directory Structure

```
artcafe-pubsub/
├── api/
│   ├── app.py                 # FastAPI application
│   ├── middleware.py          # Request logging, error handling
│   ├── router.py             # Route registration
│   ├── lambda_handler.py     # AWS Lambda adapter
│   ├── db/
│   │   └── dynamodb.py       # DynamoDB operations
│   ├── routes/
│   │   ├── agent_routes.py           # Agent CRUD
│   │   ├── agent_websocket_routes.py # Agent WebSocket (simplified auth)
│   │   ├── auth_routes.py            # Authentication endpoints
│   │   ├── channel_routes.py         # Channel management
│   │   ├── dashboard_websocket_routes.py # Dashboard WebSocket
│   │   ├── tenant_routes.py          # Tenant operations
│   │   └── usage_routes.py           # Usage metrics
│   └── services/
│       ├── agent_service.py          # Agent business logic
│       ├── channel_service.py        # Channel business logic
│       ├── tenant_service.py         # Tenant management
│       └── usage_service.py          # Usage tracking
├── auth/
│   ├── jwt_auth.py           # JWT validation (Cognito)
│   ├── ssh_auth_agent.py     # SSH key authentication
│   └── dependencies.py       # Auth dependencies
├── config/
│   ├── settings.py           # Configuration management
│   └── legal_versions.py     # Legal document versions
├── core/
│   ├── nats_client.py        # NATS connection management
│   └── messaging_service.py  # Message routing
├── models/
│   ├── agent.py              # Agent data model
│   ├── channel.py            # Channel data model
│   ├── tenant.py             # Tenant data model
│   └── usage.py              # Usage metrics model
├── infrastructure/
│   ├── dynamodb_service.py   # DynamoDB helper
│   ├── challenge_store.py    # Challenge management
│   └── metrics_service.py    # Metrics collection
├── nats_client/
│   ├── connection.py         # NATS connection
│   └── subjects.py           # NATS subject definitions
├── docs/                     # API documentation
├── tests/                    # Test suite
├── requirements.txt          # Python dependencies
└── README_UPDATED.md         # This file
```

## Deployment

### Production Environment
- **Server**: Ubuntu 24.04 on AWS EC2
- **IP**: 3.229.1.223
- **Service**: systemd service (artcafe-pubsub.service)
- **Python**: 3.12 with virtual environment

### Service Management
```bash
# Check status
sudo systemctl status artcafe-pubsub

# View logs
sudo journalctl -u artcafe-pubsub -f

# Restart service
sudo systemctl restart artcafe-pubsub
```

### Configuration
Environment variables in `/etc/systemd/system/artcafe-pubsub.service`:
- `JWT_SECRET_KEY` - JWT signing key
- `AWS_REGION` - AWS region (us-east-1)
- `NATS_URL` - NATS server URL (nats://localhost:4222)

## Development

### Local Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

### Testing
```bash
# Run tests
python -m pytest tests/

# Test specific endpoints
curl http://localhost:8000/health
```

## Monitoring

### Key Metrics
- WebSocket connections (agent vs dashboard)
- Message throughput
- API request latency
- Authentication success/failure rates

### Health Checks
- `/health` - Overall service health
- NATS connection status
- DynamoDB availability

## Security

### CORS Policy
Handled exclusively by Nginx:
- Allowed origins: www.artcafe.ai, artcafe.ai, localhost:3000
- Credentials: enabled
- Methods: GET, POST, PUT, DELETE, OPTIONS, PATCH

### Rate Limiting
Currently handled at Nginx level (future enhancement)

### Multi-tenancy
All operations are scoped to tenant ID from:
- JWT claims (human users)
- Query parameters (agents)

## Troubleshooting

### Common Issues

1. **CORS Errors**
   - Check Nginx configuration
   - Verify origin is in allowed list
   - Ensure FastAPI is NOT adding CORS headers

2. **WebSocket Connection Failed**
   - Check authentication (JWT for dashboard, SSH key for agents)
   - Verify WebSocket upgrade headers in Nginx
   - Check service logs for specific errors

3. **DynamoDB Errors**
   - Verify IAM roles and permissions
   - Check table existence
   - Monitor throttling metrics

### Useful Commands
```bash
# Check Nginx config
sudo nginx -t

# View Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Test WebSocket connection
wscat -c "wss://ws.artcafe.ai/api/v1/ws/dashboard?auth=<base64_auth>"

# Check NATS
nats-cli sub ">"  # Subscribe to all messages
```

## Recent Changes (May 26, 2025)

1. **Removed API Gateway** - Direct Nginx routing
2. **Simplified Agent Auth** - No JWT tokens for agents
3. **CORS in Nginx Only** - Removed from FastAPI
4. **Unified Configuration** - Single Nginx config for both domains
5. **Cleaned Up** - Removed outdated scripts and fixes

## Future Enhancements

1. **Rate Limiting** - Implement per-tenant limits
2. **Caching** - Add Redis for frequently accessed data
3. **Monitoring** - Integrate Prometheus/Grafana
4. **Load Balancing** - Multiple backend instances
5. **Message Persistence** - Store critical messages