"""
WebSocket implementation for ArtCafe.

This module provides WebSocket endpoints for:
1. Agents - SSH key authenticated, NATS bridge
2. Dashboard - JWT authenticated, real-time updates
"""

import json
import logging
import asyncio
import base64
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect, Query, status
from fastapi.routing import APIRouter

from api.services.agent_service import agent_service
from api.services.tenant_service import tenant_service
from api.services.usage_service import usage_service
from auth.ssh_auth import SSHKeyManager
from auth.jwt_handler import decode_token
from nats_client import nats_manager

logger = logging.getLogger(__name__)

# Create routers
agent_router = APIRouter(tags=["Agent WebSocket"])
dashboard_router = APIRouter(tags=["Dashboard WebSocket"])

# SSH key manager instance
ssh_key_manager = SSHKeyManager()

# Active connections tracking
class ConnectionManager:
    """Manages WebSocket connections and NATS subscriptions."""
    
    def __init__(self):
        # Agent connections: {agent_id: {"ws": WebSocket, "subs": [], "tenant_id": str}}
        self.agents: Dict[str, Dict[str, Any]] = {}
        # Dashboard connections: {user_id: {"ws": WebSocket, "tenant_id": str, "subs": []}}
        self.dashboards: Dict[str, Dict[str, Any]] = {}
        # NATS subscription tracking: {subject: set(agent_ids)}
        self.subject_subscribers: Dict[str, Set[str]] = {}
        # Dashboard subscription tracking: {subject: set(user_ids)}
        self.dashboard_subscribers: Dict[str, Set[str]] = {}
    
    async def connect_agent(self, agent_id: str, tenant_id: str, websocket: WebSocket):
        """Register an agent connection."""
        self.agents[agent_id] = {
            "ws": websocket,
            "subs": [],
            "tenant_id": tenant_id
        }
        logger.info(f"Agent {agent_id} connected")
    
    async def disconnect_agent(self, agent_id: str):
        """Remove an agent connection and clean up subscriptions."""
        if agent_id in self.agents:
            # Unsubscribe from all NATS subjects
            for sub in self.agents[agent_id]["subs"]:
                try:
                    await sub.unsubscribe()
                except:
                    pass
            
            # Remove from subject tracking
            for subject, subscribers in self.subject_subscribers.items():
                subscribers.discard(agent_id)
            
            del self.agents[agent_id]
            logger.info(f"Agent {agent_id} disconnected")
    
    async def connect_dashboard(self, user_id: str, tenant_id: str, websocket: WebSocket):
        """Register a dashboard connection."""
        self.dashboards[user_id] = {
            "ws": websocket,
            "tenant_id": tenant_id,
            "subs": []
        }
        logger.info(f"Dashboard user {user_id} connected")
    
    async def disconnect_dashboard(self, user_id: str):
        """Remove a dashboard connection and clean up subscriptions."""
        if user_id in self.dashboards:
            # Unsubscribe from all NATS subjects
            for sub in self.dashboards[user_id]["subs"]:
                try:
                    await sub.unsubscribe()
                except:
                    pass
            
            # Remove from subject tracking
            for subject, subscribers in self.dashboard_subscribers.items():
                subscribers.discard(user_id)
            
            del self.dashboards[user_id]
            logger.info(f"Dashboard user {user_id} disconnected")
    
    async def subscribe_agent(self, agent_id: str, subject: str):
        """Subscribe an agent to a NATS subject."""
        if agent_id not in self.agents:
            return
        
        # Track subscription
        if subject not in self.subject_subscribers:
            self.subject_subscribers[subject] = set()
        self.subject_subscribers[subject].add(agent_id)
        
        # Create NATS handler
        async def handler(msg):
            await self.route_to_agent(agent_id, subject, msg)
        
        # Subscribe to NATS
        sub = await nats_manager.subscribe(subject, cb=handler)
        self.agents[agent_id]["subs"].append(sub)
        
        logger.info(f"Agent {agent_id} subscribed to {subject}")
    
    async def route_to_agent(self, agent_id: str, subject: str, msg):
        """Route a NATS message to an agent via WebSocket."""
        if agent_id not in self.agents:
            return
        
        try:
            data = json.loads(msg.data.decode())
            websocket = self.agents[agent_id]["ws"]
            tenant_id = self.agents[agent_id]["tenant_id"]
            
            await websocket.send_json({
                "type": "message",
                "subject": subject,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Track message usage for inbound messages
            try:
                await usage_service.increment_messages(tenant_id)
            except Exception as e:
                logger.error(f"Failed to track message usage: {e}")
        except Exception as e:
            logger.error(f"Error routing message to agent {agent_id}: {e}")
    
    async def subscribe_dashboard(self, user_id: str, topic: str):
        """Subscribe a dashboard to a topic (typically a channel)."""
        if user_id not in self.dashboards:
            return
        
        dashboard_info = self.dashboards[user_id]
        tenant_id = dashboard_info["tenant_id"]
        
        # Ensure topic is properly scoped to tenant
        # Accept both old format (tenant.{tenant_id}.channel.) and new format (channels.{tenant_id}.)
        if not (topic.startswith(f"tenant.{tenant_id}.channel.") or topic.startswith(f"channels.{tenant_id}.")):
            logger.warning(f"Dashboard {user_id} tried to subscribe to unauthorized topic: {topic}")
            return
        
        # Track subscription
        if topic not in self.dashboard_subscribers:
            self.dashboard_subscribers[topic] = set()
        self.dashboard_subscribers[topic].add(user_id)
        
        # Create NATS handler
        async def handler(msg):
            await self.route_to_dashboard(user_id, topic, msg)
        
        # Subscribe to NATS
        sub = await nats_manager.subscribe(topic, cb=handler)
        self.dashboards[user_id]["subs"].append(sub)
        
        logger.info(f"Dashboard user {user_id} subscribed to {topic}")
    
    async def route_to_dashboard(self, user_id: str, topic: str, msg):
        """Route a NATS message to a dashboard via WebSocket."""
        if user_id not in self.dashboards:
            return
        
        try:
            data = json.loads(msg.data.decode())
            websocket = self.dashboards[user_id]["ws"]
            tenant_id = self.dashboards[user_id]["tenant_id"]
            
            await websocket.send_json({
                "type": "message",
                "topic": topic,
                "payload": data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Track message usage for dashboard messages
            try:
                await usage_service.increment_messages(tenant_id)
            except Exception as e:
                logger.error(f"Failed to track message usage: {e}")
        except Exception as e:
            logger.error(f"Error routing message to dashboard {user_id}: {e}")
    
    async def broadcast_to_dashboards(self, tenant_id: str, message: dict):
        """Send a message to all dashboards for a tenant."""
        for user_id, info in self.dashboards.items():
            if info["tenant_id"] == tenant_id:
                try:
                    await info["ws"].send_json(message)
                except:
                    pass

# Global connection manager
manager = ConnectionManager()


@agent_router.websocket("/api/v1/ws/agent/{agent_id}")
async def agent_websocket(
    websocket: WebSocket,
    agent_id: str,
    challenge: str = Query(...),
    signature: str = Query(...),
    tenant_id: str = Query(...)
):
    """
    WebSocket endpoint for agents.
    
    Authentication: SSH key challenge-response
    Purpose: Bridge agent messages to/from NATS
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
                
                if msg_type == "subscribe":
                    subject = message.get("subject")
                    if subject:
                        # Add tenant prefix for security (unless it's a global subject)
                        if not subject.startswith("agents.presence."):
                            if not subject.startswith(f"agents.{tenant_id}."):
                                subject = f"agents.{tenant_id}.{subject}"
                        
                        await manager.subscribe_agent(agent_id, subject)
                        
                        await websocket.send_json({
                            "type": "subscribed",
                            "subject": subject
                        })
                
                elif msg_type == "publish":
                    subject = message.get("subject")
                    data = message.get("data", {})
                    
                    if subject:
                        # Add metadata
                        data["agent_id"] = agent_id
                        data["tenant_id"] = tenant_id
                        if "timestamp" not in data:
                            data["timestamp"] = datetime.now(timezone.utc).isoformat()
                        
                        # Publish to NATS
                        await nats_manager.publish(subject, json.dumps(data).encode())
                        
                        # Track message usage
                        try:
                            await usage_service.increment_messages(tenant_id)
                        except Exception as e:
                            logger.error(f"Failed to track message usage: {e}")
                        
                        # Also broadcast to dashboards if it's a channel message
                        if subject.startswith(f"channels.{tenant_id}."):
                            await manager.broadcast_to_dashboards(tenant_id, {
                                "type": "channel_message",
                                "subject": subject,
                                "data": data
                            })
                
                elif msg_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling agent message: {e}")
    
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
    finally:
        await manager.disconnect_agent(agent_id)
        try:
            await agent_service.update_agent_status(tenant_id, agent_id, "offline")
        except:
            pass


@dashboard_router.websocket("/api/v1/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for dashboard users.
    
    Authentication: JWT token
    Purpose: Real-time updates for UI
    """
    user_id = None
    tenant_id = None
    
    try:
        # Verify JWT token
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            tenant_id = payload.get("tenant_id")
            
            if not user_id or not tenant_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return
                
            # Verify tenant exists
            tenant = await tenant_service.get_tenant(tenant_id)
            if not tenant:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Tenant not found")
                return
                
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
            return
        
        # Accept connection
        await websocket.accept()
        await manager.connect_dashboard(user_id, tenant_id, websocket)
        
        # Send initial status
        await websocket.send_json({
            "type": "connected",
            "tenant_id": tenant_id
        })
        
        # Ensure NATS is connected
        if not nats_manager.is_connected:
            await nats_manager.connect()
        
        # Keep connection alive
        while True:
            try:
                # Handle dashboard messages
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        await manager.subscribe_dashboard(user_id, topic)
                        await websocket.send_json({
                            "type": "subscribed",
                            "topic": topic
                        })
                
                elif msg_type == "unsubscribe":
                    topic = message.get("topic")
                    if topic and topic in manager.dashboard_subscribers:
                        # Remove user from topic subscribers
                        if user_id in manager.dashboard_subscribers[topic]:
                            manager.dashboard_subscribers[topic].discard(user_id)
                        
                        # Unsubscribe from NATS if no more subscribers
                        if not manager.dashboard_subscribers[topic]:
                            # Find and remove the subscription
                            for i, sub in enumerate(manager.dashboards[user_id]["subs"]):
                                # This is a simple approach - in production you'd track topic->sub mapping
                                try:
                                    await sub.unsubscribe()
                                    manager.dashboards[user_id]["subs"].pop(i)
                                    break
                                except:
                                    pass
                        
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "topic": topic
                        })
                
                elif msg_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Dashboard WebSocket error: {e}")
    
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    finally:
        if user_id:
            await manager.disconnect_dashboard(user_id)