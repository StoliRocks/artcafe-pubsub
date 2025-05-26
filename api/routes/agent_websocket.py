"""
Agent WebSocket implementation with NATS bridge.

This provides WebSocket connectivity for agents with:
- SSH key challenge-response authentication
- Direct NATS subject routing
- No JWT tokens or channels required
"""

import json
import logging
import asyncio
import base64
from typing import Dict, Set, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from api.services.agent_service import agent_service
from auth.ssh_auth_utils import verify_signed_challenge
from nats_client import nats_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Agent WebSocket"])

# Track active WebSocket connections
# {agent_id: {"websocket": WebSocket, "subscriptions": [Subscription]}}
active_agents: Dict[str, Dict] = {}


async def verify_agent_auth(tenant_id: str, agent_id: str, challenge: str, signature_b64: str) -> bool:
    """
    Verify agent authentication using SSH key signature.
    
    Args:
        tenant_id: The tenant ID
        agent_id: The agent ID  
        challenge: The challenge string that was signed
        signature_b64: Base64-encoded signature
        
    Returns:
        True if authentication succeeds
    """
    try:
        # Get agent and verify it exists
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent or not agent.public_key:
            logger.error(f"Agent {agent_id} not found or missing public key")
            return False
        
        # Decode signature
        try:
            signature = base64.b64decode(signature_b64)
        except Exception as e:
            logger.error(f"Failed to decode signature: {e}")
            return False
        
        # Verify signature using agent's public key
        return verify_signed_challenge(challenge, signature, agent.public_key)
        
    except Exception as e:
        logger.error(f"Error during agent auth: {e}")
        return False


@router.websocket("/ws/agent/{agent_id}")
async def agent_websocket(
    websocket: WebSocket,
    agent_id: str,
    challenge: str = Query(..., description="Challenge string to sign"),
    signature: str = Query(..., description="Base64-encoded signature"),
    tenant_id: str = Query(..., description="Tenant ID")
):
    """
    WebSocket endpoint for agents with NATS bridge.
    
    Agents authenticate using SSH key signatures, then can:
    - Subscribe to NATS subjects
    - Publish to NATS subjects
    - Receive messages from subscribed subjects
    
    All routing happens through NATS - no channel concept needed.
    """
    nats_subscriptions = []
    
    try:
        # Verify authentication
        if not await verify_agent_auth(tenant_id, agent_id, challenge, signature):
            logger.warning(f"Agent {agent_id} failed authentication")
            await websocket.close(code=4001, reason="Authentication failed")
            return
        
        # Accept connection
        await websocket.accept()
        logger.info(f"Agent {agent_id} connected from tenant {tenant_id}")
        
        # Track connection
        active_agents[agent_id] = {
            "websocket": websocket,
            "subscriptions": nats_subscriptions,
            "tenant_id": tenant_id
        }
        
        # Update agent status
        try:
            await agent_service.update_agent_status(tenant_id, agent_id, "online")
        except Exception as e:
            logger.error(f"Failed to update agent status: {e}")
        
        # Ensure NATS is connected
        if not nats_manager.is_connected:
            await nats_manager.connect()
        
        # Message handler for NATS -> WebSocket
        async def nats_message_handler(msg):
            """Forward NATS messages to WebSocket"""
            try:
                # Parse NATS message
                data = json.loads(msg.data.decode())
                
                # Send to WebSocket
                await websocket.send_json({
                    "type": "message",
                    "subject": msg.subject,
                    "data": data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error forwarding NATS message: {e}")
        
        # Handle WebSocket messages
        while True:
            try:
                # Receive from WebSocket
                message = await websocket.receive_json()
                msg_type = message.get("type")
                
                if msg_type == "subscribe":
                    # Subscribe to NATS subject
                    subject = message.get("subject")
                    if subject:
                        # Add tenant prefix for security
                        if not subject.startswith(f"agents.{tenant_id}.") and not subject.startswith("agents.presence."):
                            subject = f"agents.{tenant_id}.{subject}"
                        
                        # Subscribe in NATS
                        sub = await nats_manager.subscribe(subject, cb=nats_message_handler)
                        nats_subscriptions.append(sub)
                        
                        logger.info(f"Agent {agent_id} subscribed to {subject}")
                        
                        # Confirm subscription
                        await websocket.send_json({
                            "type": "subscribed",
                            "subject": subject
                        })
                
                elif msg_type == "unsubscribe":
                    # Unsubscribe from NATS subject
                    subject = message.get("subject")
                    if subject:
                        # Find and remove subscription
                        for sub in nats_subscriptions:
                            if sub.subject == subject:
                                await sub.unsubscribe()
                                nats_subscriptions.remove(sub)
                                break
                        
                        logger.info(f"Agent {agent_id} unsubscribed from {subject}")
                        
                        # Confirm unsubscription
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "subject": subject
                        })
                
                elif msg_type == "publish":
                    # Publish to NATS subject
                    subject = message.get("subject")
                    data = message.get("data", {})
                    
                    if subject:
                        # Add metadata
                        data["agent_id"] = agent_id
                        data["tenant_id"] = tenant_id
                        if "timestamp" not in data:
                            data["timestamp"] = datetime.now(timezone.utc).isoformat()
                        
                        # Publish to NATS
                        await nats_manager.publish(
                            subject,
                            json.dumps(data).encode()
                        )
                        
                        logger.debug(f"Agent {agent_id} published to {subject}")
                        
                        # Acknowledge if requested
                        if message.get("id"):
                            await websocket.send_json({
                                "type": "ack",
                                "id": message["id"],
                                "status": "published"
                            })
                
                elif msg_type == "ping":
                    # Respond to ping
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                else:
                    logger.warning(f"Unknown message type from agent {agent_id}: {msg_type}")
                    
            except WebSocketDisconnect:
                logger.info(f"Agent {agent_id} disconnected")
                break
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from agent {agent_id}")
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON"
                })
            except Exception as e:
                logger.error(f"Error handling agent {agent_id} message: {e}")
                
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
    finally:
        # Cleanup
        # Unsubscribe from all NATS subjects
        for sub in nats_subscriptions:
            try:
                await sub.unsubscribe()
            except:
                pass
        
        # Remove from active agents
        active_agents.pop(agent_id, None)
        
        # Update agent status
        try:
            await agent_service.update_agent_status(tenant_id, agent_id, "offline")
        except Exception as e:
            logger.error(f"Failed to update agent status on disconnect: {e}")
        
        logger.info(f"Agent {agent_id} cleanup complete")