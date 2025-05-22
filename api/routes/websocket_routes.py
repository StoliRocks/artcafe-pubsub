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
@router.websocket("/ws-debug")
async def websocket_debug_endpoint(websocket: WebSocket):
    # Debug endpoint with no authentication for testing
    logger.info("WebSocket DEBUG connection attempt")
    try:
        await websocket.accept()
        logger.info("WebSocket DEBUG connection accepted")
        
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"WebSocket DEBUG received: {data}")
                await websocket.send_text(f"Echo: {data}")
        except Exception as e:
            logger.error(f"WebSocket DEBUG error: {e}")
    except Exception as e:
        logger.error(f"WebSocket DEBUG connection error: {e}")



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
        channel_id: Optional[str] = None
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
                
                # Don't automatically set agent to online
                # Agent will be set online when it sends a heartbeat
                # await agent_service.update_agent_status(tenant_id, agent_id, "online")
                
                logger.info(f"WebSocket connected: tenant={tenant_id}, agent={agent_id}, channel={channel_id}")
            else:
                logger.info(f"WebSocket connected: tenant={tenant_id}, agent={agent_id}")
                
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
        channel_id: Optional[str] = None
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
                    # Update agent status to offline
                    await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                    # Remove the agent if it has no channels
                    del connected_clients[tenant_id][agent_id]
        else:
            # Remove all agent connections
            if tenant_id in connected_clients and agent_id in connected_clients[tenant_id]:
                # Update agent status to offline
                await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                # Remove all agent channels
                del connected_clients[tenant_id][agent_id]
                logger.info(f"WebSocket disconnected: tenant={tenant_id}, agent={agent_id}")
        
        # Clean up empty dictionaries
        if tenant_id in connected_clients and not connected_clients[tenant_id]:
            del connected_clients[tenant_id]


async def get_tenant_from_token(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """Get tenant information from token."""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        # Get user and tenant ID from token
        user_data = decode_token(token)
        tenant_id = user_data.get("tenant_id")
        
        if not tenant_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant ID not found in token"
            )
        
        # Validate tenant
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Verify tenant subscription is active
        if tenant.payment_status == "expired":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription has expired"
            )
        
        return tenant_id, user_data.get("agent_id"), tenant
    
    except Exception as e:
        logger.error(f"Error authenticating WebSocket connection: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )


async def on_message(subject: str, message: Dict):
    """
    Handle incoming messages from NATS.
    
    This function is called when a message is received on a NATS subject.
    It forwards the message to all WebSocket clients subscribed to the channel.
    """
    try:
        tenant_id = message.get("tenant_id")
        channel_id = message.get("channel_id")
        
        if not tenant_id or not channel_id:
            logger.error(f"Invalid message format: {message}")
            return
        
        # Add the message to the queue
        if tenant_id in message_queues and channel_id in message_queues[tenant_id]:
            await message_queues[tenant_id][channel_id].put(message)
            logger.debug(f"Message added to queue: tenant={tenant_id}, channel={channel_id}")
    
    except Exception as e:
        logger.error(f"Error handling NATS message: {e}")


async def process_message_queue(tenant_id: str, channel_id: str):
    """
    Process messages from the queue for a specific channel.
    
    This function runs in a separate task for each channel,
    continuously processing messages from the queue.
    """
    try:
        queue = message_queues[tenant_id][channel_id]
        
        while True:
            # Get the next message from the queue
            message = await queue.get()
            
            # Send the message to all connected clients for this channel
            for agent_id, channels in connected_clients.get(tenant_id, {}).items():
                if channel_id in channels:
                    websocket = channels[channel_id]
                    
                    try:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_json(message)
                            logger.debug(f"Message sent to client: tenant={tenant_id}, agent={agent_id}, channel={channel_id}")
                    except Exception as e:
                        logger.error(f"Error sending message to client: {e}")
            
            # Mark the task as done
            queue.task_done()
    
    except asyncio.CancelledError:
        logger.info(f"Message queue processor cancelled: tenant={tenant_id}, channel={channel_id}")
    
    except Exception as e:
        logger.error(f"Error processing message queue: {e}")




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


# Global variable to store the heartbeat checker task
heartbeat_checker_task = None

async def start_heartbeat_checker():
    """Start the heartbeat timeout checker"""
    global heartbeat_checker_task
    if heartbeat_checker_task is None:
        heartbeat_checker_task = asyncio.create_task(check_heartbeat_timeouts())
        logger.info("Started heartbeat timeout checker")


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
    manager = WebSocketConnectionManager()
    tenant_id = None
    agent_id = None
    tenant = None
    
    try:
        # Authenticate the connection
        tenant_id, agent_id, tenant = await get_tenant_from_token(websocket, token)
        
        if not agent_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify the agent exists
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # If channel_id is provided, verify the channel exists
        if channel_id:
            channel = await channel_service.get_channel(tenant_id, channel_id)
            if not channel:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        
        # Initialize message processor task if it doesn't exist
        if channel_id and tenant_id in message_queues and channel_id in message_queues[tenant_id]:
            if not hasattr(message_queues[tenant_id][channel_id], "processor_task"):
                message_queues[tenant_id][channel_id].processor_task = asyncio.create_task(
                    process_message_queue(tenant_id, channel_id)
                )
        
        # Connect the WebSocket
        await manager.connect(websocket, tenant_id, agent_id, channel_id)
        
        # Keep the connection alive
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                # Handle heartbeat messages from actual agents
                if msg_type == "heartbeat":
                    # Update heartbeat timestamp
                    if tenant_id not in agent_heartbeats:
                        agent_heartbeats[tenant_id] = {}
                    
                    agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
                    
                    # Update agent status to online if not already
                    current_agent = await agent_service.get_agent(tenant_id, agent_id)
                    if current_agent and current_agent.status != "online":
                        await agent_service.update_agent_status(tenant_id, agent_id, "online")
                    
                    logger.debug(f"Heartbeat received: tenant={tenant_id}, agent={agent_id}")
                
                # Add tenant and agent information
                message["tenant_id"] = tenant_id
                message["agent_id"] = agent_id
                message["timestamp"] = datetime.utcnow().isoformat()
                
                # If connected to a channel, publish the message
                if channel_id:
                    message["channel_id"] = channel_id
                    subject = subjects.get_channel_subject(tenant_id, channel_id)
                    await nats_manager.publish(subject, message)
                
                # Echo the message back to the client for confirmation
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
            await manager.disconnect(tenant_id, agent_id, channel_id)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@router.websocket("/ws/tenant/{tenant_id}/agent/{agent_id}/channel/{channel_id}")
async def channel_websocket_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    agent_id: str,
    channel_id: str,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for channel-specific messaging.
    
    This endpoint establishes a WebSocket connection for a specific channel.
    It provides an alternative to the main WebSocket endpoint with URL parameters.
    """
    manager = WebSocketConnectionManager()
    
    try:
        # Authenticate the connection
        user_data = decode_token(token)
        token_tenant_id = user_data.get("tenant_id")
        token_agent_id = user_data.get("agent_id")
        
        # Verify tenant and agent IDs match the token
        if token_tenant_id != tenant_id or (token_agent_id and token_agent_id != agent_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Validate tenant
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant or tenant.payment_status == "expired":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify the agent exists
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify the channel exists
        channel = await channel_service.get_channel(tenant_id, channel_id)
        if not channel:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Initialize message processor task if it doesn't exist
        if tenant_id not in message_queues:
            message_queues[tenant_id] = {}
        
        if channel_id not in message_queues[tenant_id]:
            message_queues[tenant_id][channel_id] = asyncio.Queue()
            message_queues[tenant_id][channel_id].processor_task = asyncio.create_task(
                process_message_queue(tenant_id, channel_id)
            )
        
        # Connect the WebSocket
        await manager.connect(websocket, tenant_id, agent_id, channel_id)
        
        # Keep the connection alive
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Add required fields
                message["tenant_id"] = tenant_id
                message["agent_id"] = agent_id
                message["channel_id"] = channel_id
                message["timestamp"] = datetime.utcnow().isoformat()
                
                # Publish the message to NATS
                subject = subjects.get_channel_subject(tenant_id, channel_id)
                await nats_manager.publish(subject, message)
                
                # Echo the message back to the client for confirmation
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
        await manager.disconnect(tenant_id, agent_id, channel_id)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)