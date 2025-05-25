import os
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .routes import websocket_routes, subscription_routes, dashboard_websocket_routes, billing_routes, tenant_routes, agent_websocket_routes, billing_subscription_routes

from artcafe_pubsub.models.agent import (
    Agent, AgentStatus, AgentType, AgentCreate, AgentUpdate, 
    AgentResponse, AgentStatusUpdate
)
from artcafe_pubsub.models.ssh_key import (
    SSHKey, SSHKeyStatus, SSHKeyCreate, SSHKeyResponse
)
from artcafe_pubsub.models.channel import (
    Channel, ChannelStatus, ChannelType, ChannelCreate, ChannelResponse
)
from artcafe_pubsub.models.tenant import (
    Tenant, TenantStatus, SubscriptionTier, TenantCreate, TenantResponse
)
from artcafe_pubsub.models.usage import (
    UsageMetrics, UsageLimits, UsageTotals, UsageResponse, BillingInfo
)
from artcafe_pubsub.auth.jwt_auth import JWTAuth
from artcafe_pubsub.auth.ssh_auth import SSHKeyManager
from artcafe_pubsub.infrastructure.dynamodb_service import DynamoDBService
from artcafe_pubsub.core.messaging_service import MessagingService

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create router
router = APIRouter()

# Include WebSocket routes
router.include_router(websocket_routes.router, prefix="/api/v1")

# Include Subscription routes
router.include_router(subscription_routes.router, prefix="/api/v1")

# Include Dashboard WebSocket routes
router.include_router(dashboard_websocket_routes.router, prefix="/api/v1")

# Include Billing routes
router.include_router(billing_routes.router, prefix="/api/v1")

# Include Tenant routes
router.include_router(tenant_routes.router, prefix="/api/v1")

# Include Agent WebSocket routes (new protocol)
router.include_router(agent_websocket_routes.router, prefix="/api/v1")

# Include Billing Subscription routes
router.include_router(billing_subscription_routes.router, prefix="/api/v1")

# Create JWT authentication service
jwt_auth = JWTAuth(
    secret_key=os.getenv('JWT_SECRET_KEY', 'your-secret-key-for-development-only'),
    audience=os.getenv('JWT_AUDIENCE', 'artcafe-api'),
    issuer=os.getenv('JWT_ISSUER', 'artcafe-auth')
)

# Create SSH key manager
ssh_key_manager = SSHKeyManager()

# Create DynamoDB service
db_service = DynamoDBService(
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    endpoint_url=os.getenv('DYNAMODB_ENDPOINT'),
    table_prefix=os.getenv('DYNAMODB_TABLE_PREFIX', 'ArtCafe-PubSub-')
)

# Dependency for tenant ID extraction
async def get_tenant_id(
    request: Request,
    x_tenant_id: Optional[str] = Header(None),
    authorization: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> str:
    """Get tenant ID from request."""
    # First check header
    if x_tenant_id:
        return x_tenant_id
    
    # Then check JWT token
    payload = jwt_auth.verify_token(authorization.credentials)
    tenant_id = payload.get('tenant_id')
    
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Missing tenant ID")
    
    return tenant_id

# AGENT ROUTES

@router.post("/agents", response_model=AgentResponse, tags=["Agents"])
async def register_agent(
    agent_data: AgentCreate,
    tenant_id: str = Depends(get_tenant_id)
):
    """Register a new agent."""
    # Convert to Agent model
    agent = agent_data.to_agent(tenant_id)
    
    # Create agent in database
    await db_service.create_agent(agent)
    
    # Create JWT token for agent (returned in response)
    token = jwt_auth.create_agent_token(agent.agent_id, tenant_id)
    
    # Return response
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.type.value,
        "status": agent.status.value,
        "capabilities": [cap.dict() for cap in agent.capabilities],
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "created_at": agent.created_at.isoformat(),
        "metadata": agent.metadata
    }

@router.get("/agents", response_model=Dict[str, Any], tags=["Agents"])
async def list_agents(
    tenant_id: str = Depends(get_tenant_id),
    status: Optional[str] = Query(None, description="Filter by agent status"),
    type: Optional[str] = Query(None, description="Filter by agent type"),
    limit: int = Query(50, description="Maximum number of agents to return"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """List agents with optional filters."""
    # Query database
    result = await db_service.list_agents(
        tenant_id=tenant_id,
        status=status,
        agent_type=type,
        limit=limit,
        next_token=next_token,
        model_class=Agent
    )
    
    # Convert agents to response format
    agents_response = []
    for agent in result["agents"]:
        agents_response.append({
            "agent_id": agent.agent_id,
            "name": agent.name,
            "type": agent.type.value,
            "status": agent.status.value,
            "capabilities": [cap.dict() for cap in agent.capabilities],
            "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
            "created_at": agent.created_at.isoformat(),
            "metadata": agent.metadata
        })
    
    # Return response
    return {
        "agents": agents_response,
        "next_token": result["next_token"]
    }

@router.get("/agents/{agent_id}", response_model=AgentResponse, tags=["Agents"])
async def get_agent(
    agent_id: str = Path(..., description="Agent ID"),
    tenant_id: str = Depends(get_tenant_id)
):
    """Get agent details."""
    # Get agent from database
    agent = await db_service.get_agent(tenant_id, agent_id, Agent)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Return response
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.type.value,
        "status": agent.status.value,
        "capabilities": [cap.dict() for cap in agent.capabilities],
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "created_at": agent.created_at.isoformat(),
        "metadata": agent.metadata
    }

@router.put("/agents/{agent_id}/status", response_model=AgentResponse, tags=["Agents"])
async def update_agent_status(
    status_update: AgentStatusUpdate,
    agent_id: str = Path(..., description="Agent ID"),
    tenant_id: str = Depends(get_tenant_id)
):
    """Update agent status."""
    # Get agent from database
    agent = await db_service.get_agent(tenant_id, agent_id, Agent)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Update status
    await db_service.update_agent_status(tenant_id, agent_id, status_update.status.value)
    
    # Update in-memory agent object
    agent.status = status_update.status
    agent.last_seen = datetime.utcnow()
    
    # Return updated agent
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.type.value,
        "status": agent.status.value,
        "capabilities": [cap.dict() for cap in agent.capabilities],
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "created_at": agent.created_at.isoformat(),
        "metadata": agent.metadata
    }

# SSH KEY ROUTES

@router.get("/ssh-keys", response_model=Dict[str, Any], tags=["SSH Keys"])
async def list_ssh_keys(
    tenant_id: str = Depends(get_tenant_id),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    limit: int = Query(50, description="Maximum number of keys to return"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """List SSH keys with optional filters."""
    # Query database
    result = await db_service.list_ssh_keys(
        tenant_id=tenant_id,
        agent_id=agent_id,
        limit=limit,
        next_token=next_token,
        model_class=SSHKey
    )
    
    # Convert keys to response format
    keys_response = []
    for key in result["ssh_keys"]:
        keys_response.append({
            "key_id": key.key_id,
            "name": key.name,
            "public_key": key.public_key,
            "status": key.status.value,
            "created_at": key.created_at.isoformat(),
            "fingerprint": key.fingerprint,
            "metadata": key.metadata,
            "agent_id": key.agent_id
        })
    
    # Return response
    return {
        "ssh_keys": keys_response,
        "next_token": result["next_token"]
    }

@router.post("/ssh-keys", response_model=SSHKeyResponse, tags=["SSH Keys"])
async def add_ssh_key(
    key_data: SSHKeyCreate,
    tenant_id: str = Depends(get_tenant_id)
):
    """Add a new SSH key."""
    try:
        # Calculate key fingerprint
        fingerprint = ssh_key_manager.calculate_fingerprint(key_data.public_key)
        
        # Convert to SSHKey model
        ssh_key = key_data.to_ssh_key(tenant_id)
        ssh_key.fingerprint = fingerprint
        
        # Create SSH key in database
        await db_service.create_ssh_key(ssh_key)
        
        # Return response
        return {
            "key_id": ssh_key.key_id,
            "name": ssh_key.name,
            "public_key": ssh_key.public_key,
            "status": ssh_key.status.value,
            "created_at": ssh_key.created_at.isoformat(),
            "fingerprint": ssh_key.fingerprint,
            "metadata": ssh_key.metadata,
            "agent_id": ssh_key.agent_id
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/ssh-keys/{key_id}", response_model=Dict[str, Any], tags=["SSH Keys"])
async def delete_ssh_key(
    key_id: str = Path(..., description="Key ID"),
    tenant_id: str = Depends(get_tenant_id)
):
    """Delete an SSH key."""
    # Delete key from database
    success = await db_service.delete_ssh_key(tenant_id, key_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"SSH key {key_id} not found")
    
    # Return success response
    return {"success": True}

# CHANNEL ROUTES

@router.get("/channels", response_model=Dict[str, Any], tags=["Channels"])
async def list_channels(
    tenant_id: str = Depends(get_tenant_id),
    status: Optional[str] = Query(None, description="Filter by channel status"),
    type: Optional[str] = Query(None, description="Filter by channel type"),
    limit: int = Query(50, description="Maximum number of channels to return"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """List channels with optional filters."""
    # Query database
    result = await db_service.list_channels(
        tenant_id=tenant_id,
        status=status,
        channel_type=type,
        limit=limit,
        next_token=next_token,
        model_class=Channel
    )
    
    # Convert channels to response format
    channels_response = []
    for channel in result["channels"]:
        channels_response.append({
            "id": channel.id,
            "name": channel.name,
            "description": channel.description,
            "type": channel.type.value,
            "status": channel.status.value,
            "created_at": channel.created_at.isoformat(),
            "metadata": channel.metadata,
            "allowed_agents": channel.allowed_agents
        })
    
    # Return response
    return {
        "channels": channels_response,
        "next_token": result["next_token"]
    }

@router.post("/channels", response_model=ChannelResponse, tags=["Channels"])
async def create_channel(
    channel_data: ChannelCreate,
    tenant_id: str = Depends(get_tenant_id)
):
    """Create a new channel."""
    # Convert to Channel model
    channel = channel_data.to_channel(tenant_id)
    
    # Create channel in database
    await db_service.create_channel(channel)
    
    # Return response
    return {
        "id": channel.id,
        "name": channel.name,
        "description": channel.description,
        "type": channel.type.value,
        "status": channel.status.value,
        "created_at": channel.created_at.isoformat(),
        "metadata": channel.metadata,
        "allowed_agents": channel.allowed_agents
    }

@router.get("/channels/{channel_id}", response_model=ChannelResponse, tags=["Channels"])
async def get_channel(
    channel_id: str = Path(..., description="Channel ID"),
    tenant_id: str = Depends(get_tenant_id)
):
    """Get channel details."""
    # Get channel from database
    channel = await db_service.get_channel(tenant_id, channel_id, Channel)
    
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    
    # Return response
    return {
        "id": channel.id,
        "name": channel.name,
        "description": channel.description,
        "type": channel.type.value,
        "status": channel.status.value,
        "created_at": channel.created_at.isoformat(),
        "metadata": channel.metadata,
        "allowed_agents": channel.allowed_agents
    }

# USAGE METRICS ROUTES

@router.get("/usage-metrics", response_model=UsageResponse, tags=["Usage"])
async def get_usage_metrics(
    tenant_id: str = Depends(get_tenant_id),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """Get usage metrics for the tenant."""
    # Set default date range if not provided
    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today - timedelta(days=6)).isoformat()  # Last 7 days by default
    
    # Get usage metrics from database
    metrics = await db_service.get_usage_metrics(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        model_class=UsageMetrics
    )
    
    # Return metrics
    return metrics

@router.get("/billing", response_model=BillingInfo, tags=["Usage"])
async def get_billing_info(
    tenant_id: str = Depends(get_tenant_id)
):
    """Get billing information for the tenant."""
    # TODO: Get real billing information from a billing service
    
    # For now, return mock data
    return {
        "tenant_id": tenant_id,
        "plan": "standard",
        "billing_cycle": "monthly",
        "next_billing_date": (date.today().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
        "amount": 49.99,
        "currency": "USD",
        "payment_method": "credit_card",
        "status": "active"
    }

# TENANT ROUTES

@router.post("/tenants", response_model=TenantResponse, tags=["Tenants"])
async def create_tenant(
    tenant_data: TenantCreate
):
    """Create a new tenant."""
    # Convert to Tenant model
    tenant = tenant_data.to_tenant()
    
    # Create tenant in database
    await db_service.create_tenant(tenant)
    
    # Return response
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "admin_email": tenant.admin_email,
        "status": tenant.status.value,
        "subscription_tier": tenant.subscription_tier.value,
        "created_at": tenant.created_at.isoformat(),
        "metadata": tenant.metadata,
        "api_key": tenant.api_key,
        "admin_token": tenant.admin_token
    }