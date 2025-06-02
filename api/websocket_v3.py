"""
WebSocket implementation for ArtCafe with DynamoDB-based connection management.
Implements Phase 1 of the scaling architecture.

This module provides WebSocket endpoints for:
1. Agents - SSH key authenticated, NATS bridge
2. Dashboard - JWT authenticated, real-time updates
"""

import json
import logging
import asyncio
import base64
import os
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect, Query, status
from fastapi.routing import APIRouter

from api.services.agent_service import agent_service
from api.services.tenant_service import tenant_service
from api.services.usage_service import usage_service
from api.services.websocket_connection_service import WebSocketConnectionService
from auth.ssh_auth import SSHKeyManager
from auth.jwt_handler import decode_token
from nats_client import nats_manager

logger = logging.getLogger(__name__)

# Create routers
agent_router = APIRouter(tags=["Agent WebSocket"])
dashboard_router = APIRouter(tags=["Dashboard WebSocket"])

# SSH key manager instance
ssh_key_manager = SSHKeyManager()

# Get server ID from environment or generate one
SERVER_ID = os.environ.get("ARTCAFE_SERVER_ID", None)

# Active connections tracking - local cache for this server only
class ConnectionManager:
    """Manages WebSocket connections with DynamoDB backing and local cache."""
    
    def __init__(self):
        # Local WebSocket references - only for connections on THIS server
        self.local_agents: Dict[str, WebSocket] = {}
        self.local_dashboards: Dict[str, WebSocket] = {}
        
        # DynamoDB connection service
        self.db_service = WebSocketConnectionService(server_id=SERVER_ID)
        
        # NATS subscription references
        self.agent_subs: Dict[str, list] = {}
        self.dashboard_subs: Dict[str, list] = {}
        
        logger.info(f"ConnectionManager initialized with server_id: {self.db_service.server_id}")
    
    async def connect_agent(self, agent_id: str, tenant_id: str, websocket: WebSocket):
        """Register an agent connection."""
        # Store locally
        self.local_agents[agent_id] = websocket
        
        # Register in DynamoDB
        self.db_service.register_connection(
            connection_id=agent_id,
            connection_type="agent",
            tenant_id=tenant_id,
            metadata={"status": "online"}
        )
        
        # Initialize subscription list
        self.agent_subs[agent_id] = []
        
        logger.info(f"Agent {agent_id} connected from tenant {tenant_id}")
        logger.info(f"Local connected agents: {len(self.local_agents)}")
        
        # Get global stats
        stats = self.db_service.get_connection_stats()
        logger.info(f"Global connection stats: {stats}")
    
    async def disconnect_agent(self, agent_id: str):
        """Remove an agent connection and clean up subscriptions."""
        # Unsubscribe from all NATS subjects
        if agent_id in self.agent_subs:
            for sub in self.agent_subs[agent_id]:
                try:
                    await sub.unsubscribe()
                except:
                    pass
            del self.agent_subs[agent_id]
        
        # Remove from local cache
        if agent_id in self.local_agents:
            del self.local_agents[agent_id]
        
        # Remove from DynamoDB
        self.db_service.unregister_connection(agent_id)
        
        logger.info(f"Agent {agent_id} disconnected")
    
    async def connect_dashboard(self, user_id: str, tenant_id: str, websocket: WebSocket):
        """Register a dashboard connection."""
        # Store locally
        self.local_dashboards[user_id] = websocket
        
        # Register in DynamoDB
        self.db_service.register_connection(
            connection_id=user_id,
            connection_type="dashboard",
            tenant_id=tenant_id,
            metadata={"connected_at": datetime.now(timezone.utc).isoformat()}
        )
        
        # Initialize subscription list
        self.dashboard_subs[user_id] = []
        
        logger.info(f"Dashboard user {user_id} connected from tenant {tenant_id}")
        logger.info(f"Local connected dashboards: {len(self.local_dashboards)}")
    
    async def disconnect_dashboard(self, user_id: str):
        """Remove a dashboard connection and clean up subscriptions."""
        # Unsubscribe from all NATS subjects
        if user_id in self.dashboard_subs:
            for sub in self.dashboard_subs[user_id]:
                try:
                    await sub.unsubscribe()
                except:
                    pass
            del self.dashboard_subs[user_id]
        
        # Remove from local cache
        if user_id in self.local_dashboards:
            del self.local_dashboards[user_id]
        
        # Remove from DynamoDB
        self.db_service.unregister_connection(user_id)
        
        logger.info(f"Dashboard user {user_id} disconnected")
    
    async def add_agent_subscription(self, agent_id: str, subject: str, subscription):
        """Add a NATS subscription for an agent."""
        if agent_id in self.agent_subs:
            self.agent_subs[agent_id].append(subscription)
            # Also track in DynamoDB for cross-server visibility
            self.db_service.add_subscription(agent_id, subject)
    
    async def add_dashboard_subscription(self, user_id: str, subject: str, subscription):
        """Add a NATS subscription for a dashboard."""
        if user_id in self.dashboard_subs:
            self.dashboard_subs[user_id].append(subscription)
            # Also track in DynamoDB for cross-server visibility
            self.db_service.add_subscription(user_id, subject)
    
    async def send_to_agent(self, agent_id: str, message: dict):
        """Send message to an agent if connected to this server."""
        if agent_id in self.local_agents:
            try:
                await self.local_agents[agent_id].send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send to agent {agent_id}: {e}")
                return False
        else:
            # Check if agent is connected to another server
            conn = self.db_service.get_connection(agent_id)
            if conn:
                logger.debug(f"Agent {agent_id} is connected to server {conn.get('server_id')}")
            return False
    
    async def send_to_dashboard(self, user_id: str, message: dict):
        """Send message to a dashboard if connected to this server."""
        if user_id in self.local_dashboards:
            try:
                await self.local_dashboards[user_id].send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send to dashboard {user_id}: {e}")
                return False
        else:
            # Check if dashboard is connected to another server
            conn = self.db_service.get_connection(user_id)
            if conn:
                logger.debug(f"Dashboard {user_id} is connected to server {conn.get('server_id')}")
            return False
    
    async def broadcast_to_tenant_dashboards(self, tenant_id: str, message: dict):
        """Broadcast message to all dashboards of a tenant across all servers."""
        # Get all dashboard connections for this tenant from DynamoDB
        connections = self.db_service.get_tenant_connections(tenant_id, "dashboard")
        
        sent_count = 0
        for conn in connections:
            user_id = conn.get("connection_id")
            server_id = conn.get("server_id")
            
            # Only send if on this server
            if server_id == self.db_service.server_id and user_id in self.local_dashboards:
                if await self.send_to_dashboard(user_id, message):
                    sent_count += 1
        
        logger.debug(f"Broadcast to {sent_count} dashboards on this server for tenant {tenant_id}")
        return sent_count
    
    def get_local_stats(self) -> dict:
        """Get statistics for connections on this server."""
        return {
            "server_id": self.db_service.server_id,
            "local_agents": len(self.local_agents),
            "local_dashboards": len(self.local_dashboards),
            "agent_ids": list(self.local_agents.keys()),
            "dashboard_ids": list(self.local_dashboards.keys())
        }
    
    def get_global_stats(self) -> dict:
        """Get global connection statistics from DynamoDB."""
        return self.db_service.get_connection_stats()

# Global connection manager instance
manager = ConnectionManager()

# Background task for heartbeats and cleanup
async def connection_maintenance():
    """Periodic maintenance of connections."""
    while True:
        try:
            # Update heartbeats for all local connections
            for agent_id in list(manager.local_agents.keys()):
                manager.db_service.update_heartbeat(agent_id)
            
            for user_id in list(manager.local_dashboards.keys()):
                manager.db_service.update_heartbeat(user_id)
            
            # Clean up stale connections (older than 24 hours)
            cleaned = manager.db_service.cleanup_stale_connections()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale connections")
            
        except Exception as e:
            logger.error(f"Error in connection maintenance: {e}")
        
        # Run every 5 minutes
        await asyncio.sleep(300)

# Start maintenance task when module loads
asyncio.create_task(connection_maintenance())

@agent_router.websocket("/ws/agent/{agent_id}")
async def agent_websocket_endpoint(
    websocket: WebSocket,
    agent_id: str,
    challenge: str = Query(...),
    signature: str = Query(...)
):
    """
    WebSocket endpoint for agent connections.
    
    Authentication:
    - Challenge/response using agent's SSH key
    - No JWT required
    """
    logger.info(f"Agent WebSocket connection attempt for {agent_id}")
    
    # Decode the base64 signature
    try:
        signature_bytes = base64.b64decode(signature)
    except Exception as e:
        logger.error(f"Failed to decode signature: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Verify the agent and signature
    agent_data = await agent_service.verify_agent_signature(
        agent_id, challenge, signature_bytes
    )
    if not agent_data:
        logger.error(f"Agent verification failed for {agent_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    tenant_id = agent_data["tenant_id"]
    
    # Accept the connection
    await websocket.accept()
    
    # Register the connection
    await manager.connect_agent(agent_id, tenant_id, websocket)
    
    # Update agent status
    await agent_service.update_agent_status(agent_id, "online")
    
    # Send welcome message
    await websocket.send_json({
        "type": "welcome",
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "server_id": manager.db_service.server_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Track usage
    usage_service.track_connection(tenant_id, agent_id, "agent")
    
    try:
        # Main message loop
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                await handle_agent_message(agent_id, tenant_id, data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON"
                })
            except Exception as e:
                logger.error(f"Error handling agent message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info(f"Agent {agent_id} disconnected normally")
    except Exception as e:
        logger.error(f"Agent WebSocket error: {e}")
    finally:
        # Clean up
        await manager.disconnect_agent(agent_id)
        await agent_service.update_agent_status(agent_id, "offline")
        usage_service.track_disconnection(tenant_id, agent_id, "agent")


@dashboard_router.websocket("/ws/dashboard")
async def dashboard_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for dashboard connections.
    
    Authentication:
    - JWT token required
    """
    logger.info("Dashboard WebSocket connection attempt")
    
    # Verify JWT token
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        username = payload.get("cognito:username", user_id)
        logger.info(f"Dashboard token valid for user: {username}")
    except Exception as e:
        logger.error(f"Dashboard JWT validation failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Get tenant ID from user profile
    tenant_data = await tenant_service.get_user_tenant(user_id)
    if not tenant_data:
        logger.error(f"No tenant found for user {user_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    tenant_id = tenant_data["tenant_id"]
    
    # Accept the connection
    await websocket.accept()
    
    # Register the connection
    await manager.connect_dashboard(user_id, tenant_id, websocket)
    
    # Send welcome message
    await websocket.send_json({
        "type": "welcome",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "server_id": manager.db_service.server_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Subscribe to default topics
    await subscribe_dashboard_to_defaults(user_id, tenant_id)
    
    # Track usage
    usage_service.track_connection(tenant_id, user_id, "dashboard")
    
    try:
        # Main message loop
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                await handle_dashboard_message(user_id, tenant_id, data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON"
                })
            except Exception as e:
                logger.error(f"Error handling dashboard message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info(f"Dashboard {user_id} disconnected normally")
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    finally:
        # Clean up
        await manager.disconnect_dashboard(user_id)
        usage_service.track_disconnection(tenant_id, user_id, "dashboard")


async def handle_agent_message(agent_id: str, tenant_id: str, data: dict):
    """Handle messages from agents."""
    msg_type = data.get("type")
    
    if msg_type == "subscribe":
        # Subscribe to NATS subjects
        subjects = data.get("subjects", [])
        for subject in subjects:
            # Ensure subject is scoped to tenant
            if not subject.startswith(f"tenant.{tenant_id}."):
                subject = f"tenant.{tenant_id}.{subject}"
            
            # Create NATS subscription
            async def message_handler(msg):
                await manager.send_to_agent(agent_id, {
                    "type": "message",
                    "subject": msg.subject,
                    "data": json.loads(msg.data.decode())
                })
            
            sub = await nats_manager.subscribe(subject, message_handler)
            await manager.add_agent_subscription(agent_id, subject, sub)
            
            logger.info(f"Agent {agent_id} subscribed to {subject}")
    
    elif msg_type == "publish":
        # Publish to NATS
        subject = data.get("subject")
        payload = data.get("data", {})
        
        # Handle channel publishing without agent prefix
        if subject and subject.startswith(f"tenant.{tenant_id}.channel."):
            # This is a channel message - publish as-is
            logger.info(f"Agent {agent_id} publishing to channel: {subject}")
            await nats_manager.publish(subject, json.dumps(payload).encode())
        else:
            # Regular agent message - add agent prefix
            if not subject.startswith(f"agents.{tenant_id}."):
                subject = f"agents.{tenant_id}.{subject}"
            
            # Wrap in agent envelope
            agent_msg = {
                "agent_id": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload
            }
            
            logger.info(f"Agent {agent_id} publishing to {subject}")
            await nats_manager.publish(subject, json.dumps(agent_msg).encode())
        
        # Track usage
        usage_service.track_message(tenant_id, agent_id, "publish")
        
        # Echo back to agent for confirmation
        await manager.send_to_agent(agent_id, {
            "type": "published",
            "subject": subject,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    elif msg_type == "ping":
        # Heartbeat
        await manager.send_to_agent(agent_id, {"type": "pong"})
        manager.db_service.update_heartbeat(agent_id)


async def handle_dashboard_message(user_id: str, tenant_id: str, data: dict):
    """Handle messages from dashboard."""
    msg_type = data.get("type")
    
    if msg_type == "subscribe":
        # Subscribe to additional topics
        topics = data.get("topics", [])
        for topic in topics:
            # Ensure topic is scoped to tenant
            if not topic.startswith(f"tenant.{tenant_id}."):
                topic = f"tenant.{tenant_id}.{topic}"
            
            # Create NATS subscription
            async def message_handler(msg):
                await manager.send_to_dashboard(user_id, {
                    "type": "message",
                    "topic": msg.subject,
                    "data": json.loads(msg.data.decode())
                })
            
            sub = await nats_manager.subscribe(topic, message_handler)
            await manager.add_dashboard_subscription(user_id, topic, sub)
            
            logger.info(f"Dashboard {user_id} subscribed to {topic}")
    
    elif msg_type == "publish":
        # Dashboard publishing (admin actions, etc.)
        topic = data.get("topic")
        payload = data.get("data", {})
        
        if topic and topic.startswith(f"tenant.{tenant_id}."):
            await nats_manager.publish(topic, json.dumps(payload).encode())
            logger.info(f"Dashboard {user_id} published to {topic}")
    
    elif msg_type == "ping":
        # Heartbeat
        await manager.send_to_dashboard(user_id, {"type": "pong"})
        manager.db_service.update_heartbeat(user_id)


async def subscribe_dashboard_to_defaults(user_id: str, tenant_id: str):
    """Subscribe dashboard to default topics."""
    default_topics = [
        f"agents.{tenant_id}.>",  # All agent messages
        f"tenant.{tenant_id}.notifications",  # System notifications
        f"tenant.{tenant_id}.channel.>",  # All channels
    ]
    
    for topic in default_topics:
        async def message_handler(msg):
            await manager.send_to_dashboard(user_id, {
                "type": "message",
                "topic": msg.subject,
                "data": json.loads(msg.data.decode())
            })
        
        sub = await nats_manager.subscribe(topic, message_handler)
        await manager.add_dashboard_subscription(user_id, topic, sub)
        
        logger.info(f"Dashboard {user_id} auto-subscribed to {topic}")


# Export the manager for external access
__all__ = ["agent_router", "dashboard_router", "manager"]