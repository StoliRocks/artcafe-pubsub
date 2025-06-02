"""
Scalable WebSocket implementation for ArtCafe.

This module provides WebSocket endpoints designed for horizontal scaling:
1. Connection state stored in Redis/DynamoDB (not local memory)
2. All message routing through NATS (no direct broadcasting)
3. Server-agnostic design (any server can handle any connection)
"""

import json
import logging
import asyncio
import base64
import os
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone, timedelta
import uuid

from fastapi import WebSocket, WebSocketDisconnect, Query, status
from fastapi.routing import APIRouter

from api.services.agent_service import agent_service
from api.services.tenant_service import tenant_service
from api.services.usage_service import usage_service
from auth.ssh_auth import SSHKeyManager
from auth.jwt_handler import decode_token
from nats_client import nats_manager

logger = logging.getLogger(__name__)

# Server ID for multi-server tracking
SERVER_ID = os.environ.get("SERVER_ID", f"server-{uuid.uuid4().hex[:8]}")

# Create routers - mount these WITHOUT /api/v1 prefix for clean URLs
agent_router = APIRouter(tags=["Agent WebSocket"])
dashboard_router = APIRouter(tags=["Dashboard WebSocket"])

# SSH key manager instance
ssh_key_manager = SSHKeyManager()


class ScalableConnectionManager:
    """
    Scalable connection manager that works across multiple servers.
    
    Key differences from original:
    1. No local state storage (connections stored in Redis/DynamoDB)
    2. All routing through NATS (no direct WebSocket broadcasting)
    3. Connection registry for multi-server awareness
    """
    
    def __init__(self):
        # Local WebSocket connections (only for this server instance)
        self.local_connections: Dict[str, WebSocket] = {}
        
        # NATS subscriptions for this server
        self.nats_subscriptions: Dict[str, Any] = {}
        
        logger.info(f"ScalableConnectionManager initialized on {SERVER_ID}")
    
    async def register_connection(self, connection_id: str, connection_type: str, 
                                tenant_id: str, websocket: WebSocket):
        """Register a new connection (agent or dashboard)."""
        # Store locally for this server
        self.local_connections[connection_id] = websocket
        
        # Register in shared store (Redis/DynamoDB)
        await self._register_in_shared_store(connection_id, connection_type, tenant_id)
        
        # Publish connection event to NATS
        await nats_manager.publish(
            f"system.connections.{connection_type}.connected",
            {
                "connection_id": connection_id,
                "tenant_id": tenant_id,
                "server_id": SERVER_ID,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"{connection_type} {connection_id} connected on {SERVER_ID}")
    
    async def unregister_connection(self, connection_id: str, connection_type: str):
        """Unregister a connection."""
        # Remove from local connections
        if connection_id in self.local_connections:
            del self.local_connections[connection_id]
        
        # Remove from shared store
        await self._remove_from_shared_store(connection_id)
        
        # Unsubscribe from NATS topics
        if connection_id in self.nats_subscriptions:
            for sub in self.nats_subscriptions[connection_id]:
                try:
                    await sub.unsubscribe()
                except:
                    pass
            del self.nats_subscriptions[connection_id]
        
        # Publish disconnection event
        await nats_manager.publish(
            f"system.connections.{connection_type}.disconnected",
            {
                "connection_id": connection_id,
                "server_id": SERVER_ID,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"{connection_type} {connection_id} disconnected from {SERVER_ID}")
    
    async def subscribe_to_topic(self, connection_id: str, topic: str):
        """Subscribe a connection to a NATS topic."""
        # Create NATS handler that routes to the specific connection
        async def handler(msg):
            await self.route_to_connection(connection_id, topic, msg)
        
        # Subscribe to NATS
        sub = await nats_manager.subscribe(topic, cb=handler)
        
        # Track subscription
        if connection_id not in self.nats_subscriptions:
            self.nats_subscriptions[connection_id] = []
        self.nats_subscriptions[connection_id].append(sub)
        
        logger.info(f"Connection {connection_id} subscribed to {topic}")
    
    async def route_to_connection(self, connection_id: str, topic: str, msg):
        """Route a NATS message to a local WebSocket connection."""
        # Only route if the connection is on this server
        if connection_id not in self.local_connections:
            return  # Connection is on another server
        
        try:
            websocket = self.local_connections[connection_id]
            data = json.loads(msg.data.decode())
            
            # Send to WebSocket with consistent format
            await websocket.send_json({
                "type": "message",
                "topic": topic,
                "payload": data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.debug(f"Routed message to {connection_id} on topic {topic}")
            
        except Exception as e:
            logger.error(f"Error routing to {connection_id}: {e}")
    
    async def _register_in_shared_store(self, connection_id: str, 
                                       connection_type: str, tenant_id: str):
        """Register connection in shared store (implement with Redis/DynamoDB)."""
        # TODO: Implement with your choice of shared store
        # For now, just log
        logger.info(f"TODO: Register {connection_id} in shared store")
    
    async def _remove_from_shared_store(self, connection_id: str):
        """Remove connection from shared store."""
        # TODO: Implement with your choice of shared store
        logger.info(f"TODO: Remove {connection_id} from shared store")


# Global connection manager
manager = ScalableConnectionManager()


@agent_router.websocket("/ws/agent/{agent_id}")
async def agent_websocket(
    websocket: WebSocket,
    agent_id: str,
    challenge: str = Query(...),
    signature: str = Query(...),
    tenant_id: str = Query(...)
):
    """
    WebSocket endpoint for agents.
    
    Scalable design:
    - Connection registered in shared store
    - All messages routed through NATS
    - No direct WebSocket-to-WebSocket communication
    """
    connection_id = f"agent:{agent_id}"
    
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
        
        # Register connection
        await manager.register_connection(connection_id, "agent", tenant_id, websocket)
        
        # Update agent status
        await agent_service.update_agent_status(tenant_id, agent_id, "online")
        
        # Send welcome message
        await websocket.send_json({
            "type": "welcome",
            "agent_id": agent_id,
            "server_id": SERVER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Handle messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    subject = message.get("subject")
                    if subject:
                        # Validate subject for tenant isolation
                        if not subject.startswith(f"tenant.{tenant_id}."):
                            logger.warning(f"Agent {agent_id} tried to subscribe to {subject}")
                            continue
                        
                        await manager.subscribe_to_topic(connection_id, subject)
                        
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
                        data["server_id"] = SERVER_ID
                        if "timestamp" not in data:
                            data["timestamp"] = datetime.now(timezone.utc).isoformat()
                        
                        # Publish to NATS (let NATS handle all routing)
                        logger.info(f"Agent {agent_id} publishing to {subject}")
                        await nats_manager.publish(subject, data)
                        
                        # Track usage
                        await usage_service.increment_messages(tenant_id)
                
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
        await manager.unregister_connection(connection_id, "agent")
        await agent_service.update_agent_status(tenant_id, agent_id, "offline")


@dashboard_router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for dashboard users.
    
    Scalable design:
    - Same architecture as agents
    - JWT authentication instead of SSH
    - All routing through NATS
    """
    user_id = None
    tenant_id = None
    connection_id = None
    
    try:
        # Verify JWT token
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            tenant_id = payload.get("tenant_id")
            
            if not user_id or not tenant_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return
            
            connection_id = f"dashboard:{user_id}"
            
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
            return
        
        # Accept connection
        await websocket.accept()
        
        # Register connection
        await manager.register_connection(connection_id, "dashboard", tenant_id, websocket)
        
        # Send welcome message
        await websocket.send_json({
            "type": "welcome",
            "connection_id": connection_id,
            "server_id": SERVER_ID,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Handle messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        # Validate topic for tenant isolation
                        allowed_prefixes = [
                            f"tenant.{tenant_id}.",
                            f"agents.{tenant_id}.broadcast"
                        ]
                        
                        if not any(topic.startswith(prefix) for prefix in allowed_prefixes):
                            logger.warning(f"Dashboard {user_id} tried to subscribe to {topic}")
                            continue
                        
                        await manager.subscribe_to_topic(connection_id, topic)
                        
                        await websocket.send_json({
                            "type": "subscribed",
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
        if connection_id:
            await manager.unregister_connection(connection_id, "dashboard")