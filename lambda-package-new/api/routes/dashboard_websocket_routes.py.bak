import json
import asyncio
import logging
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, Depends, HTTPException, status
from websockets.exceptions import ConnectionClosed

from auth.dependencies import get_current_tenant_id, get_current_user_id
from core.nats_client import nats_manager
from infrastructure.dynamodb_service import dynamodb
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket", "dashboard"])


class ConnectionManager:
    """Manages WebSocket connections for dashboard clients"""
    
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}  # tenant_id -> user_id -> websocket
        
    async def connect(self, websocket: WebSocket, tenant_id: str, user_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = {}
            
        self.active_connections[tenant_id][user_id] = websocket
        logger.info(f"Dashboard client connected: {user_id} for tenant {tenant_id}")
    
    def disconnect(self, tenant_id: str, user_id: str):
        """Remove a WebSocket connection"""
        if tenant_id in self.active_connections:
            if user_id in self.active_connections[tenant_id]:
                del self.active_connections[tenant_id][user_id]
                logger.info(f"Dashboard client disconnected: {user_id} for tenant {tenant_id}")
                
            # Clean up empty tenant entries
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
    
    async def send_to_tenant(self, tenant_id: str, message: dict):
        """Send a message to all connected users of a tenant"""
        if tenant_id not in self.active_connections:
            return
            
        disconnected_users = []
        
        for user_id, websocket in self.active_connections[tenant_id].items():
            try:
                await websocket.send_json(message)
            except:
                disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            self.disconnect(tenant_id, user_id)
    
    async def send_to_user(self, tenant_id: str, user_id: str, message: dict):
        """Send a message to a specific user"""
        if tenant_id in self.active_connections:
            if user_id in self.active_connections[tenant_id]:
                websocket = self.active_connections[tenant_id][user_id]
                try:
                    await websocket.send_json(message)
                except:
                    self.disconnect(tenant_id, user_id)


manager = ConnectionManager()


@router.websocket("/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    token: Optional[str] = None,
    x_tenant_id: Optional[str] = None
):
    """
    WebSocket endpoint for dashboard real-time updates
    
    Clients should connect with authentication headers:
    - Authorization: Bearer <token>
    - x-tenant-id: <tenant_id>
    """
    # Extract auth from query params or headers
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    if not x_tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # TODO: Validate JWT token and extract user_id
    # For now, we'll use a placeholder
    user_id = "user-placeholder"
    tenant_id = x_tenant_id
    
    await manager.connect(websocket, tenant_id, user_id)
    
    # Subscribe to NATS topics for this tenant
    subscriptions = []
    
    try:
        # Subscribe to agent events
        agent_sub = await nats_manager.subscribe(
            f"agents.{tenant_id}.>",
            handler=lambda msg: asyncio.create_task(
                handle_agent_event(tenant_id, msg)
            )
        )
        subscriptions.append(agent_sub)
        
        # Subscribe to channel events
        channel_sub = await nats_manager.subscribe(
            f"channels.{tenant_id}.>",
            handler=lambda msg: asyncio.create_task(
                handle_channel_event(tenant_id, msg)
            )
        )
        subscriptions.append(channel_sub)
        
        # Keep the connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from the client
                message = await websocket.receive_json()
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "id": message.get("id"),
                        "timestamp": message.get("timestamp")
                    })
                elif message.get("type") == "subscribe":
                    # Handle dynamic subscriptions
                    topic = message.get("topic")
                    if topic:
                        await handle_subscription(websocket, tenant_id, topic)
                elif message.get("type") == "unsubscribe":
                    # Handle unsubscriptions
                    topic = message.get("topic")
                    if topic:
                        await handle_unsubscription(websocket, tenant_id, topic)
                
            except ConnectionClosed:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up
        for sub in subscriptions:
            await sub.unsubscribe()
        manager.disconnect(tenant_id, user_id)


async def handle_agent_event(tenant_id: str, message):
    """Handle agent events from NATS and forward to dashboard clients"""
    try:
        data = json.loads(message.data.decode())
        subject = message.subject
        
        # Extract event type from subject
        # Format: agents.{tenant_id}.{agent_id}.{event_type}
        parts = subject.split('.')
        
        if len(parts) >= 4:
            event_type = parts[3]
            agent_id = parts[2]
            
            dashboard_event = {
                "type": f"agent.{event_type}",
                "topic": subject,
                "data": {
                    "agent_id": agent_id,
                    **data
                },
                "timestamp": data.get("timestamp")
            }
            
            await manager.send_to_tenant(tenant_id, dashboard_event)
        
    except Exception as e:
        logger.error(f"Error handling agent event: {e}")


async def handle_channel_event(tenant_id: str, message):
    """Handle channel events from NATS and forward to dashboard clients"""
    try:
        data = json.loads(message.data.decode())
        subject = message.subject
        
        # Extract event type from subject
        # Format: channels.{tenant_id}.{channel_id}.{event_type}
        parts = subject.split('.')
        
        if len(parts) >= 4:
            event_type = parts[3]
            channel_id = parts[2]
            
            dashboard_event = {
                "type": f"channel.{event_type}",
                "topic": subject,
                "data": {
                    "channel_id": channel_id,
                    **data
                },
                "timestamp": data.get("timestamp")
            }
            
            await manager.send_to_tenant(tenant_id, dashboard_event)
        
    except Exception as e:
        logger.error(f"Error handling channel event: {e}")


async def handle_subscription(websocket: WebSocket, tenant_id: str, topic: str):
    """Handle subscription requests from dashboard clients"""
    try:
        # Validate topic pattern
        if not topic.startswith(f"agents.{tenant_id}.") and not topic.startswith(f"channels.{tenant_id}."):
            await websocket.send_json({
                "type": "error",
                "message": "Unauthorized topic subscription"
            })
            return
        
        # Send confirmation
        await websocket.send_json({
            "type": "subscribed",
            "topic": topic,
            "timestamp": asyncio.get_event_loop().time()
        })
        
    except Exception as e:
        logger.error(f"Error handling subscription: {e}")


async def handle_unsubscription(websocket: WebSocket, tenant_id: str, topic: str):
    """Handle unsubscription requests from dashboard clients"""
    try:
        # Send confirmation
        await websocket.send_json({
            "type": "unsubscribed",
            "topic": topic,
            "timestamp": asyncio.get_event_loop().time()
        })
        
    except Exception as e:
        logger.error(f"Error handling unsubscription: {e}")