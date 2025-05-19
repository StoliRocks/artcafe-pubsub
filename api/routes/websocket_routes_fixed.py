import json
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, status
from starlette.websockets import WebSocketState

from auth.jwt_auth import get_current_user, get_user_from_token
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


class WebSocketConnectionManager:
    """Manager for WebSocket connections."""
    
    @staticmethod
    async def connect(
        websocket: WebSocket,
        tenant_id: str,
        agent_id: str,
        channel_id: Optional[str] = None,
        is_actual_agent: bool = False  # New parameter to distinguish actual agents
    ):
        """Connect a WebSocket client."""
        try:
            # Get tenant for limits check
            tenant = await tenant_service.get_tenant(tenant_id)
            if not tenant:
                logger.error(f"Tenant {tenant_id} not found, rejecting WebSocket connection")
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
                
            # Check connection limit before accepting
            await check_tenant_limits("connection", tenant)
            
            # Accept the connection
            await websocket.accept()
            
            # Increment connection count for tenant
            metrics_service.update_tenant_connection(tenant_id, 1)
            
            # Initialize the tenant and agent dictionaries if they don't exist
            if tenant_id not in connected_clients:
                connected_clients[tenant_id] = {}
                message_queues[tenant_id] = {}
                agent_heartbeats[tenant_id] = {}
            
            if agent_id not in connected_clients[tenant_id]:
                connected_clients[tenant_id][agent_id] = {}
            
            # If the channel ID is provided, register the client for that channel
            if channel_id:
                # Check channel limit before subscribing
                await check_tenant_limits("channel", tenant)
                
                # Register the client for the channel
                connected_clients[tenant_id][agent_id][channel_id] = websocket
                
                # Initialize the message queue for the channel if it doesn't exist
                if channel_id not in message_queues[tenant_id]:
                    message_queues[tenant_id][channel_id] = asyncio.Queue()
                
                # Subscribe to the channel in NATS
                subject = subjects.get_channel_subject(tenant_id, channel_id)
                await nats_manager.subscribe(subject, on_message)
                
                # Only set agent as online if it's an actual agent connection
                # Dashboard/UI connections should not affect agent status
                if is_actual_agent:
                    await agent_service.update_agent_status(tenant_id, agent_id, "online")
                    agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
                
                logger.info(f"WebSocket connected: tenant={tenant_id}, agent={agent_id}, channel={channel_id}, is_agent={is_actual_agent}")
            else:
                logger.info(f"WebSocket connected: tenant={tenant_id}, agent={agent_id}, is_agent={is_actual_agent}")
                
        except HTTPException as e:
            # Quota exceeded or other HTTP exception
            logger.warning(f"WebSocket connection rejected: tenant={tenant_id}, agent={agent_id}, reason={e.detail}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=e.detail)
            
        except Exception as e:
            # General error
            logger.error(f"Error connecting WebSocket: tenant={tenant_id}, agent={agent_id}, error={str(e)}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            
            # Ensure connection count is not incremented in error case
            metrics_service.update_tenant_connection(tenant_id, -1)
    
    @staticmethod
    async def disconnect(
        tenant_id: str,
        agent_id: str,
        channel_id: Optional[str] = None,
        is_actual_agent: bool = False
    ):
        """Disconnect a WebSocket client."""
        if channel_id:
            # Remove the channel connection
            if (tenant_id in connected_clients and
                agent_id in connected_clients[tenant_id] and
                channel_id in connected_clients[tenant_id][agent_id]):
                
                del connected_clients[tenant_id][agent_id][channel_id]
                logger.info(f"WebSocket disconnected: tenant={tenant_id}, agent={agent_id}, channel={channel_id}")
                
                # Check if agent has any other channel connections
                if not connected_clients[tenant_id][agent_id]:
                    # Only update agent status if it's an actual agent disconnect
                    if is_actual_agent:
                        await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                        # Remove heartbeat tracking
                        if tenant_id in agent_heartbeats and agent_id in agent_heartbeats[tenant_id]:
                            del agent_heartbeats[tenant_id][agent_id]
                    # Remove the agent if it has no channels
                    del connected_clients[tenant_id][agent_id]
        else:
            # Remove all agent connections
            if tenant_id in connected_clients and agent_id in connected_clients[tenant_id]:
                # Only update agent status if it's an actual agent disconnect
                if is_actual_agent:
                    await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                    # Remove heartbeat tracking
                    if tenant_id in agent_heartbeats and agent_id in agent_heartbeats[tenant_id]:
                        del agent_heartbeats[tenant_id][agent_id]
                # Remove all agent channels
                del connected_clients[tenant_id][agent_id]
                logger.info(f"WebSocket disconnected: tenant={tenant_id}, agent={agent_id}")
        
        # Clean up empty dictionaries
        if tenant_id in connected_clients and not connected_clients[tenant_id]:
            del connected_clients[tenant_id]


async def handle_heartbeat(tenant_id: str, agent_id: str, message: Dict):
    """Handle heartbeat message from agent."""
    # Update heartbeat timestamp
    if tenant_id not in agent_heartbeats:
        agent_heartbeats[tenant_id] = {}
    
    agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
    
    # Update agent status to online if not already
    current_agent = await agent_service.get_agent(tenant_id, agent_id)
    if current_agent and current_agent.status != "online":
        await agent_service.update_agent_status(tenant_id, agent_id, "online")
    
    logger.debug(f"Heartbeat received: tenant={tenant_id}, agent={agent_id}")


async def check_heartbeat_timeouts():
    """Background task to check for agent heartbeat timeouts."""
    while True:
        try:
            current_time = datetime.utcnow()
            timeout_delta = timedelta(seconds=HEARTBEAT_TIMEOUT)
            
            # Check all agents for heartbeat timeout
            for tenant_id in list(agent_heartbeats.keys()):
                for agent_id in list(agent_heartbeats.get(tenant_id, {}).keys()):
                    last_heartbeat = agent_heartbeats[tenant_id].get(agent_id)
                    
                    if last_heartbeat and (current_time - last_heartbeat) > timeout_delta:
                        # Agent hasn't sent heartbeat within timeout
                        logger.warning(f"Agent heartbeat timeout: tenant={tenant_id}, agent={agent_id}")
                        
                        # Update agent status to offline
                        await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                        
                        # Remove from heartbeat tracking
                        if tenant_id in agent_heartbeats and agent_id in agent_heartbeats[tenant_id]:
                            del agent_heartbeats[tenant_id][agent_id]
            
            # Check every 10 seconds
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Error in heartbeat timeout check: {e}")
            await asyncio.sleep(10)


# Start heartbeat timeout checker on module load
asyncio.create_task(check_heartbeat_timeouts())


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Main WebSocket endpoint for agent connections.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        # Get tenant and agent info from token
        tenant_id, agent_id, tenant = await get_tenant_from_token(websocket, token)
        
        # Check if this is an actual agent by looking at token claims
        user_data = get_user_from_token(token)
        is_actual_agent = user_data.get("type") == "agent" or user_data.get("is_agent", False)
        
        # Connect the WebSocket
        manager = WebSocketConnectionManager()
        await manager.connect(websocket, tenant_id, agent_id, is_actual_agent=is_actual_agent)
        
        # Decrement connection count on disconnect
        decrement_connection = True
        
        # Main message processing loop
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                # Handle different message types
                if msg_type == "heartbeat" and is_actual_agent:
                    await handle_heartbeat(tenant_id, agent_id, message)
                elif msg_type == "status" and is_actual_agent:
                    # Update agent status
                    new_status = message.get("data", {}).get("status")
                    if new_status in ["online", "offline", "busy", "error"]:
                        await agent_service.update_agent_status(tenant_id, agent_id, new_status)
                else:
                    # Process other message types as before
                    message["tenant_id"] = tenant_id
                    message["agent_id"] = agent_id
                    message["timestamp"] = datetime.utcnow().isoformat()
                    
                    # Echo acknowledgment
                    await websocket.send_json({
                        "type": "ACK",
                        "message_id": message.get("id"),
                        "timestamp": datetime.utcnow().isoformat()
                    })
            
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "ERROR",
                    "error": "Invalid JSON format",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await websocket.send_json({
                    "type": "ERROR",
                    "error": "Internal server error",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except WebSocketDisconnect:
        if tenant_id and agent_id:
            await manager.disconnect(tenant_id, agent_id, is_actual_agent=is_actual_agent)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    
    finally:
        # Ensure connection count is decremented
        if decrement_connection and tenant_id:
            metrics_service.update_tenant_connection(tenant_id, -1)


# Add similar fixes to other WebSocket endpoints...