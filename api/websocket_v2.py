"""
Enhanced WebSocket implementation with subscription state management.

This module provides WebSocket endpoints with:
1. Proper channel subscription state tracking
2. Heartbeat monitoring
3. Multi-server support ready
"""

import json
import logging
import asyncio
import base64
import uuid
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect, Query, status, HTTPException
from fastapi.routing import APIRouter

from api.services.agent_service import agent_service
from api.services.tenant_service import tenant_service
from api.services.usage_service import usage_service
from services.subscription_state_service import subscription_service
from auth.ssh_auth import SSHKeyManager
from auth.jwt_handler import decode_token
from nats_client import nats_manager
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create routers
agent_router = APIRouter(tags=["Agent WebSocket V2"])
dashboard_router = APIRouter(tags=["Dashboard WebSocket V2"])

# SSH key manager instance
ssh_key_manager = SSHKeyManager()

# Server ID for multi-server support
SERVER_ID = settings.get("SERVER_ID", "ws-01")

class EnhancedConnectionManager:
    """Enhanced WebSocket connection manager with subscription state tracking."""
    
    def __init__(self):
        # Agent connections: {agent_id: {"ws": WebSocket, "ws_id": str, "tenant_id": str, "channels": set()}}
        self.agents: Dict[str, Dict[str, Any]] = {}
        # Dashboard connections: {user_id: {"ws": WebSocket, "tenant_id": str, "subscribed_channels": set()}}
        self.dashboards: Dict[str, Dict[str, Any]] = {}
        # WebSocket ID to agent ID mapping for fast lookup
        self.ws_to_agent: Dict[str, str] = {}
    
    async def connect_agent(self, agent_id: str, tenant_id: str, websocket: WebSocket):
        """Register an agent connection and update subscription states."""
        ws_id = str(uuid.uuid4())
        
        # Get subscribed channels from subscription service
        subscribed_channels = await subscription_service.on_agent_connect(agent_id, ws_id, tenant_id)
        
        # Store connection info
        self.agents[agent_id] = {
            "ws": websocket,
            "ws_id": ws_id,
            "tenant_id": tenant_id,
            "channels": set(subscribed_channels),
            "connected_at": datetime.now(timezone.utc)
        }
        self.ws_to_agent[ws_id] = agent_id
        
        # Subscribe to NATS topics for each channel
        for channel_id in subscribed_channels:
            subject = f"tenant.{tenant_id}.channel.{channel_id}"
            await self._subscribe_to_nats(agent_id, subject)
        
        # Send welcome message with subscribed channels
        await websocket.send_json({
            "type": "welcome",
            "agent_id": agent_id,
            "connection_id": ws_id,
            "subscribed_channels": subscribed_channels,
            "server_id": SERVER_ID
        })
        
        logger.info(f"Agent {agent_id} connected with {len(subscribed_channels)} channel subscriptions")
    
    async def disconnect_agent(self, agent_id: str):
        """Disconnect agent and update subscription states."""
        if agent_id in self.agents:
            info = self.agents[agent_id]
            
            # Update subscription states to offline
            await subscription_service.on_agent_disconnect(agent_id)
            
            # Unsubscribe from NATS topics
            for channel_id in info["channels"]:
                subject = f"tenant.{info['tenant_id']}.channel.{channel_id}"
                await self._unsubscribe_from_nats(agent_id, subject)
            
            # Clean up connection info
            if info["ws_id"] in self.ws_to_agent:
                del self.ws_to_agent[info["ws_id"]]
            del self.agents[agent_id]
            
            logger.info(f"Agent {agent_id} disconnected")
    
    async def handle_agent_heartbeat(self, agent_id: str, data: Optional[Dict] = None):
        """Handle agent heartbeat."""
        await subscription_service.on_heartbeat(agent_id, data)
        
        # Send heartbeat acknowledgment
        if agent_id in self.agents:
            await self.agents[agent_id]["ws"].send_json({
                "type": "heartbeat_ack",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def subscribe_agent_to_channel(self, agent_id: str, channel_id: str):
        """Subscribe an agent to a new channel."""
        if agent_id not in self.agents:
            return
        
        info = self.agents[agent_id]
        tenant_id = info["tenant_id"]
        
        # Add to subscription database
        await subscription_service.add_subscription(channel_id, agent_id, tenant_id)
        
        # Add to local tracking
        info["channels"].add(channel_id)
        
        # Subscribe to NATS
        subject = f"tenant.{tenant_id}.channel.{channel_id}"
        await self._subscribe_to_nats(agent_id, subject)
        
        # Send confirmation
        await info["ws"].send_json({
            "type": "subscribed",
            "channel_id": channel_id
        })
    
    async def unsubscribe_agent_from_channel(self, agent_id: str, channel_id: str):
        """Unsubscribe an agent from a channel."""
        if agent_id not in self.agents:
            return
        
        info = self.agents[agent_id]
        tenant_id = info["tenant_id"]
        
        # Remove from subscription database
        await subscription_service.remove_subscription(channel_id, agent_id)
        
        # Remove from local tracking
        info["channels"].discard(channel_id)
        
        # Unsubscribe from NATS
        subject = f"tenant.{tenant_id}.channel.{channel_id}"
        await self._unsubscribe_from_nats(agent_id, subject)
        
        # Send confirmation
        await info["ws"].send_json({
            "type": "unsubscribed",
            "channel_id": channel_id
        })
    
    async def route_channel_message(self, channel_id: str, message: dict):
        """Route a message to all subscribers of a channel."""
        # Get online subscribers from subscription service
        subscribers = await subscription_service.get_channel_subscribers(channel_id, online_only=True)
        
        for subscriber in subscribers:
            agent_id = subscriber['agent_id']
            
            # Only route to agents on this server
            if subscriber.get('server_id') == SERVER_ID and agent_id in self.agents:
                try:
                    await self.agents[agent_id]["ws"].send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message to agent {agent_id}: {e}")
    
    async def _subscribe_to_nats(self, agent_id: str, subject: str):
        """Subscribe to a NATS subject for an agent."""
        try:
            async def message_handler(msg):
                """Handle messages from NATS."""
                try:
                    data = json.loads(msg.data.decode())
                    
                    # Route to agent
                    if agent_id in self.agents:
                        await self.agents[agent_id]["ws"].send_json({
                            "type": "message",
                            "subject": subject,
                            "data": data,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                except Exception as e:
                    logger.error(f"Error handling NATS message: {e}")
            
            # Subscribe to NATS
            if nats_manager.nc:
                sub = await nats_manager.nc.subscribe(subject, cb=message_handler)
                
                # Store subscription reference
                if agent_id in self.agents:
                    if "nats_subs" not in self.agents[agent_id]:
                        self.agents[agent_id]["nats_subs"] = {}
                    self.agents[agent_id]["nats_subs"][subject] = sub
                    
        except Exception as e:
            logger.error(f"Failed to subscribe to NATS subject {subject}: {e}")
    
    async def _unsubscribe_from_nats(self, agent_id: str, subject: str):
        """Unsubscribe from a NATS subject."""
        try:
            if agent_id in self.agents and "nats_subs" in self.agents[agent_id]:
                if subject in self.agents[agent_id]["nats_subs"]:
                    sub = self.agents[agent_id]["nats_subs"][subject]
                    await sub.unsubscribe()
                    del self.agents[agent_id]["nats_subs"][subject]
        except Exception as e:
            logger.error(f"Failed to unsubscribe from NATS subject {subject}: {e}")

# Global connection manager
manager = EnhancedConnectionManager()

@agent_router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_v2(
    websocket: WebSocket,
    agent_id: str,
    challenge: str = Query(...),
    signature: str = Query(...),
    tenant_id: str = Query(...)
):
    """
    Enhanced WebSocket endpoint for agents with subscription state management.
    
    Features:
    - Channel subscription state tracking
    - Heartbeat monitoring
    - Multi-server support ready
    """
    try:
        # Verify agent exists and get public key
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            logger.warning(f"Agent {agent_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Agent not found")
            return
        
        # Verify signature
        try:
            signature_bytes = base64.b64decode(signature)
            challenge_bytes = challenge.encode('utf-8')
            
            if not ssh_key_manager.verify_signature(agent.public_key, challenge_bytes, signature_bytes):
                logger.warning(f"Invalid signature for agent {agent_id}")
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid signature")
                return
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
            return
        
        # Accept connection
        await websocket.accept()
        await manager.connect_agent(agent_id, tenant_id, websocket)
        
        # Update agent status
        try:
            await agent_service.update_agent_status(tenant_id, agent_id, "online")
        except:
            pass
        
        # Ensure NATS is connected
        if not nats_manager.is_connected:
            await nats_manager.connect()
        
        # Handle messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "heartbeat":
                    # Handle heartbeat
                    await manager.handle_agent_heartbeat(agent_id, message.get("data"))
                
                elif msg_type == "subscribe":
                    # Subscribe to a channel
                    channel_id = message.get("channel_id")
                    if channel_id:
                        await manager.subscribe_agent_to_channel(agent_id, channel_id)
                
                elif msg_type == "unsubscribe":
                    # Unsubscribe from a channel
                    channel_id = message.get("channel_id")
                    if channel_id:
                        await manager.unsubscribe_agent_from_channel(agent_id, channel_id)
                
                elif msg_type == "publish":
                    # Publish message to a channel
                    channel_id = message.get("channel_id")
                    data = message.get("data", {})
                    
                    if channel_id:
                        # Check if agent is subscribed to this channel
                        if channel_id in manager.agents[agent_id]["channels"]:
                            subject = f"tenant.{tenant_id}.channel.{channel_id}"
                            
                            # Publish to NATS
                            if nats_manager.nc:
                                await nats_manager.nc.publish(
                                    subject,
                                    json.dumps({
                                        "agent_id": agent_id,
                                        "data": data,
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }).encode()
                                )
                                
                                # Track usage
                                await usage_service.increment_messages(tenant_id)
                                
                                # Send acknowledgment
                                await websocket.send_json({
                                    "type": "published",
                                    "channel_id": channel_id
                                })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "error": "Not subscribed to channel"
                            })
                
                elif msg_type == "ping":
                    # Simple ping/pong
                    await websocket.send_json({"type": "pong"})
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling agent message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
    
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
    
    finally:
        # Clean up on disconnect
        await manager.disconnect_agent(agent_id)
        
        # Update agent status
        try:
            await agent_service.update_agent_status(tenant_id, agent_id, "offline")
        except:
            pass

@dashboard_router.websocket("/ws/dashboard")
async def dashboard_websocket_v2(websocket: WebSocket, token: str = Query(...)):
    """
    Enhanced dashboard WebSocket endpoint with channel monitoring.
    """
    user_id = None
    try:
        # Validate JWT token
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if not user_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
            return
        
        # Get tenant ID
        tenant = await tenant_service.get_current_tenant(user_id)
        if not tenant:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No tenant found")
            return
        
        tenant_id = tenant.id
        
        # Accept connection
        await websocket.accept()
        ws_id = str(uuid.uuid4())
        
        # Store connection
        manager.dashboards[user_id] = {
            "ws": websocket,
            "ws_id": ws_id,
            "tenant_id": tenant_id,
            "subscribed_channels": set(),
            "connected_at": datetime.now(timezone.utc)
        }
        
        # Send welcome message
        await websocket.send_json({
            "type": "welcome",
            "user_id": user_id,
            "connection_id": ws_id,
            "tenant_id": tenant_id
        })
        
        # Handle messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "monitor_channel":
                    # Subscribe to monitor a channel
                    channel_id = message.get("channel_id")
                    if channel_id:
                        manager.dashboards[user_id]["subscribed_channels"].add(channel_id)
                        
                        # Subscribe to NATS for this channel
                        subject = f"tenant.{tenant_id}.channel.{channel_id}"
                        
                        async def channel_handler(msg):
                            """Route channel messages to dashboard."""
                            try:
                                data = json.loads(msg.data.decode())
                                await websocket.send_json({
                                    "type": "channel_message",
                                    "channel_id": channel_id,
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })
                            except Exception as e:
                                logger.error(f"Error routing to dashboard: {e}")
                        
                        if nats_manager.nc:
                            sub = await nats_manager.nc.subscribe(subject, cb=channel_handler)
                            
                            # Store subscription
                            if "nats_subs" not in manager.dashboards[user_id]:
                                manager.dashboards[user_id]["nats_subs"] = {}
                            manager.dashboards[user_id]["nats_subs"][channel_id] = sub
                        
                        await websocket.send_json({
                            "type": "monitoring_channel",
                            "channel_id": channel_id
                        })
                
                elif msg_type == "stop_monitoring":
                    # Stop monitoring a channel
                    channel_id = message.get("channel_id")
                    if channel_id and channel_id in manager.dashboards[user_id]["subscribed_channels"]:
                        manager.dashboards[user_id]["subscribed_channels"].discard(channel_id)
                        
                        # Unsubscribe from NATS
                        if "nats_subs" in manager.dashboards[user_id] and channel_id in manager.dashboards[user_id]["nats_subs"]:
                            await manager.dashboards[user_id]["nats_subs"][channel_id].unsubscribe()
                            del manager.dashboards[user_id]["nats_subs"][channel_id]
                        
                        await websocket.send_json({
                            "type": "stopped_monitoring",
                            "channel_id": channel_id
                        })
                
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling dashboard message: {e}")
    
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    
    finally:
        # Clean up on disconnect
        if user_id and user_id in manager.dashboards:
            # Unsubscribe from all NATS topics
            if "nats_subs" in manager.dashboards[user_id]:
                for sub in manager.dashboards[user_id]["nats_subs"].values():
                    try:
                        await sub.unsubscribe()
                    except:
                        pass
            
            del manager.dashboards[user_id]

# Start subscription service when module loads
async def startup():
    """Start the subscription state service."""
    await subscription_service.start()
    logger.info("WebSocket V2 service started")

async def shutdown():
    """Stop the subscription state service."""
    await subscription_service.stop()
    logger.info("WebSocket V2 service stopped")