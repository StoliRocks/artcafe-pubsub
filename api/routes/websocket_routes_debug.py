"""
Debug version of websocket routes to find the issue
"""
import json
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, status
from starlette.websockets import WebSocketState

from auth.dependencies import get_current_user
from auth.jwt_handler import decode_token
from auth.tenant_auth import get_tenant_id, validate_tenant, check_tenant_limits
from nats_client import nats_manager, subjects
from models.tenant import Tenant
from api.services.tenant_service import tenant_service
from api.services.agent_service import agent_service
from api.services.channel_service import channel_service
from infrastructure.metrics_service import metrics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSockets"])

# Connect clients - Used to keep track of connected WebSocket clients
# Structure: {"tenant_id": {"agent_id": {"channel_id": WebSocket}}}
connected_clients: Dict[str, Dict[str, Dict[str, WebSocket]]] = {}

# Message queues - Used to buffer messages while processing
# Structure: {"tenant_id": {"channel_id": Queue}}
message_queues: Dict[str, Dict[str, asyncio.Queue]] = {}

# Track last heartbeat for agents
# Structure: {"tenant_id": {"agent_id": datetime}}
agent_heartbeats: Dict[str, Dict[str, datetime]] = {}

# Heartbeat timeout in seconds
HEARTBEAT_TIMEOUT = 60


async def get_tenant_from_token(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """Get tenant information from token."""
    logger.info(f"[DEBUG] get_tenant_from_token called with token: {token[:50] if token else 'None'}...")
    
    if not token:
        logger.warning("[DEBUG] No token provided")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        # Get user and tenant ID from token
        logger.info("[DEBUG] Decoding token...")
        user_data = decode_token(token)
        logger.info(f"[DEBUG] Token decoded: {user_data}")
        
        tenant_id = user_data.get("tenant_id")
        
        if not tenant_id:
            logger.warning("[DEBUG] No tenant_id in token")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant ID not found in token"
            )
        
        logger.info(f"[DEBUG] Got tenant_id: {tenant_id}")
        
        # Validate tenant
        logger.info(f"[DEBUG] Fetching tenant from service...")
        tenant = await tenant_service.get_tenant(tenant_id)
        
        if not tenant:
            logger.warning(f"[DEBUG] Tenant not found: {tenant_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        logger.info(f"[DEBUG] Found tenant: {tenant.name}")
        
        # Verify tenant subscription is active
        if hasattr(tenant, 'payment_status') and tenant.payment_status == "expired":
            logger.warning(f"[DEBUG] Tenant subscription expired: {tenant_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription has expired"
            )
        
        agent_id = user_data.get("agent_id")
        logger.info(f"[DEBUG] Returning tenant_id={tenant_id}, agent_id={agent_id}")
        
        return tenant_id, agent_id, tenant
    
    except Exception as e:
        logger.error(f"[DEBUG] Error authenticating WebSocket connection: {e}", exc_info=True)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    channel_id: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time messaging.
    
    This endpoint establishes a WebSocket connection for a specific agent and channel.
    If channel_id is not provided, the connection is established for the agent only.
    """
    logger.info(f"[DEBUG] WebSocket endpoint called with token: {token[:50] if token else 'None'}...")
    
    tenant_id = None
    agent_id = None
    tenant = None
    
    try:
        # Authenticate the connection
        logger.info("[DEBUG] Authenticating connection...")
        tenant_id, agent_id, tenant = await get_tenant_from_token(websocket, token)
        
        logger.info(f"[DEBUG] Authentication successful: tenant_id={tenant_id}, agent_id={agent_id}")
        
        if not agent_id:
            logger.warning("[DEBUG] No agent_id found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify the agent exists
        logger.info(f"[DEBUG] Verifying agent {agent_id} exists...")
        agent = await agent_service.get_agent(tenant_id, agent_id)
        
        if not agent:
            logger.warning(f"[DEBUG] Agent not found: {agent_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        logger.info(f"[DEBUG] Agent found: {agent.id}")
        
        # Accept the WebSocket connection first
        logger.info("[DEBUG] Accepting WebSocket connection...")
        await websocket.accept()
        logger.info("[DEBUG] WebSocket connection accepted!")
        
        # Keep the connection alive
        while True:
            try:
                message = await websocket.receive_text()
                logger.info(f"[DEBUG] Received message: {message}")
                
                # Echo back for testing
                await websocket.send_text(f"Echo: {message}")
                
            except WebSocketDisconnect:
                logger.info("[DEBUG] WebSocket disconnected")
                break
                
    except HTTPException as e:
        logger.warning(f"[DEBUG] HTTPException in WebSocket: {e.detail}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    except Exception as e:
        logger.error(f"[DEBUG] Unexpected error in WebSocket: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)