"""
Agent-specific WebSocket routes using the new AgentMessage protocol.

This module provides WebSocket endpoints specifically for agents that use
the standardized AgentMessage protocol for communication.
"""

import json
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from starlette.websockets import WebSocketState

from auth.jwt_handler import decode_token
from auth.tenant_auth import check_tenant_limits
from nats_client import nats_manager, subjects
from models.agent_message import (
    AgentMessage, MessageType, AgentIdentity,
    MessageContext, MessagePayload, MessageRouting
)
from api.services.tenant_service import tenant_service
from api.services.agent_service import agent_service
from api.services.agent_lifecycle_service import get_agent_lifecycle_service
from infrastructure.metrics_service import metrics_service
from core.messaging_service import MessagingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent WebSockets"])

# Track agent heartbeats
agent_heartbeats: Dict[str, Dict[str, datetime]] = {}


@router.websocket("/ws/agent/{agent_id}")
async def agent_protocol_websocket_endpoint(
    websocket: WebSocket,
    agent_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for agents using the new AgentMessage protocol.
    
    This endpoint provides:
    - AgentMessage protocol support
    - Capability-based routing
    - Discovery handling
    - Heartbeat management
    - Streaming support
    """
    tenant_id = None
    lifecycle_service = None
    messaging_service = None
    subscriptions = []
    
    try:
        # Authenticate
        user_data = decode_token(token)
        tenant_id = user_data.get("tenant_id")
        token_agent_id = user_data.get("agent_id")
        
        if not tenant_id or (token_agent_id and token_agent_id != agent_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Validate tenant
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Tenant not found")
            return
            
        if tenant.payment_status == "expired":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Subscription expired")
            return
            
        # Get agent details
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Agent not found")
            return
            
        # Check connection limits
        await check_tenant_limits("connection", tenant)
        
        # Accept connection
        await websocket.accept()
        metrics_service.update_tenant_connection(tenant_id, 1)
        
        # Initialize services
        # Create a messaging service instance with NATS client
        nats_client = nats_manager.client if hasattr(nats_manager, 'client') else nats_manager
        messaging_service = MessagingService(nats_client)
        lifecycle_service = get_agent_lifecycle_service(messaging_service)
        
        # Update connection tracking
        if tenant_id not in agent_heartbeats:
            agent_heartbeats[tenant_id] = {}
        agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
        
        # Announce agent online
        await lifecycle_service.announce_agent_online(
            tenant_id,
            agent_id,
            agent.capabilities or [],
            agent.capability_definitions
        )
        
        # Setup discovery handler
        await lifecycle_service.setup_discovery_handler(tenant_id, agent_id, agent)
        
        # Start heartbeat monitor
        await lifecycle_service.start_heartbeat_monitor(tenant_id, agent_id)
        
        # Subscribe to agent-specific topics
        
        # Subscribe to direct commands
        command_subject = subjects.get_agent_command_subject(tenant_id, agent_id)
        async def handle_command(msg: AgentMessage):
            await websocket.send_text(msg.json())
        await messaging_service.subscribe_agent_message(command_subject, handle_command, tenant_id)
        subscriptions.append(command_subject)
        
        # Subscribe to broadcast commands
        broadcast_subject = subjects.get_agent_command_subject(tenant_id)
        await messaging_service.subscribe_agent_message(broadcast_subject, handle_command, tenant_id)
        subscriptions.append(broadcast_subject)
        
        # Subscribe to capability-based tasks
        for capability in agent.capabilities or []:
            task_subject = subjects.get_agent_task_subject(tenant_id, capability)
            async def handle_task(msg: AgentMessage):
                # Only forward if agent has capacity
                if agent.active_connections < agent.max_concurrent_tasks:
                    await websocket.send_text(msg.json())
            await messaging_service.subscribe_agent_message(task_subject, handle_task, tenant_id)
            subscriptions.append(task_subject)
        
        # Subscribe to discovery requests
        discovery_subject = subjects.get_agent_discovery_request_subject(tenant_id)
        await messaging_service.subscribe_agent_message(
            discovery_subject, 
            lifecycle_service._discovery_handlers.get(agent_id), 
            tenant_id
        )
        subscriptions.append(discovery_subject)
        
        # Main message loop
        while True:
            data = await websocket.receive_text()
            
            try:
                # Parse as AgentMessage
                agent_msg = AgentMessage.parse_raw(data)
                
                # Verify source matches authenticated agent
                if agent_msg.source.id != agent_id or agent_msg.source.tenant_id != tenant_id:
                    await websocket.send_json({
                        "error": "Source mismatch",
                        "type": "ERROR"
                    })
                    continue
                
                # Handle different message types
                if agent_msg.type == MessageType.HEARTBEAT:
                    # Update heartbeat
                    agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
                    await lifecycle_service.handle_agent_heartbeat(
                        tenant_id,
                        agent_id,
                        agent_msg.payload.content
                    )
                    
                    # Send ACK
                    ack = AgentMessage(
                        type=MessageType.EVENT,
                        source=AgentIdentity(
                            id="system",
                            type="system",
                            tenant_id=tenant_id
                        ),
                        correlation_id=agent_msg.id,
                        context=agent_msg.context,
                        payload=MessagePayload(
                            content={"status": "heartbeat_received"}
                        ),
                        routing=MessageRouting(priority=0)
                    )
                    await websocket.send_text(ack.json())
                    
                elif agent_msg.type == MessageType.RESULT:
                    # Forward result to appropriate topic
                    await messaging_service.send_agent_message(agent_msg)
                    
                elif agent_msg.type == MessageType.EVENT:
                    # Forward event
                    await messaging_service.send_agent_message(agent_msg)
                    
                elif agent_msg.type == MessageType.STREAM:
                    # Handle streaming response
                    await messaging_service.send_agent_message(agent_msg)
                    
                elif agent_msg.type == MessageType.QUERY:
                    # Handle query (e.g., status requests)
                    if agent_msg.payload.content.get("query") == "status":
                        status_response = agent_msg.create_response(
                            content={
                                "status": agent.status,
                                "capabilities": agent.capabilities,
                                "active_connections": agent.active_connections,
                                "success_rate": agent.success_rate
                            },
                            success=True,
                            source=AgentIdentity(
                                id=agent_id,
                                tenant_id=tenant_id,
                                capabilities=agent.capabilities or []
                            )
                        )
                        await websocket.send_text(status_response.json())
                    else:
                        # Forward other queries
                        await messaging_service.send_agent_message(agent_msg)
                    
                else:
                    logger.warning(f"Unhandled message type: {agent_msg.type}")
                    
            except Exception as e:
                logger.error(f"Error processing agent message: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "ERROR"
                })
                
    except WebSocketDisconnect:
        logger.info(f"Agent {agent_id} disconnected")
        
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            
    finally:
        # Cleanup
        if tenant_id and agent_id and lifecycle_service:
            try:
                # Announce offline
                await lifecycle_service.announce_agent_offline(tenant_id, agent_id)
                
                # Cleanup discovery handler
                await lifecycle_service.cleanup_discovery_handler(tenant_id, agent_id)
                
                # Unsubscribe from all topics
                if messaging_service:
                    for subject in subscriptions:
                        try:
                            await messaging_service.unsubscribe(subject)
                        except Exception as e:
                            logger.error(f"Error unsubscribing from {subject}: {e}")
                
                # Update metrics
                metrics_service.update_tenant_connection(tenant_id, -1)
                
                # Remove from heartbeats
                if tenant_id in agent_heartbeats and agent_id in agent_heartbeats[tenant_id]:
                    del agent_heartbeats[tenant_id][agent_id]
                    
            except Exception as e:
                logger.error(f"Error during cleanup for agent {agent_id}: {e}")


@router.websocket("/ws/agent/{agent_id}/stream")
async def agent_stream_websocket_endpoint(
    websocket: WebSocket,
    agent_id: str,
    token: str = Query(...),
):
    """
    Dedicated WebSocket endpoint for streaming responses.
    
    This endpoint is optimized for agents that need to stream large responses
    or real-time data back to clients.
    """
    tenant_id = None
    messaging_service = None
    
    try:
        # Authenticate
        user_data = decode_token(token)
        tenant_id = user_data.get("tenant_id")
        token_agent_id = user_data.get("agent_id")
        
        if not tenant_id or (token_agent_id and token_agent_id != agent_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Validate tenant and agent
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant or tenant.payment_status == "expired":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        agent = await agent_service.get_agent(tenant_id, agent_id)
        if not agent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        # Accept connection
        await websocket.accept()
        
        # Initialize messaging service
        nats_client = nats_manager.client if hasattr(nats_manager, 'client') else nats_manager
        messaging_service = MessagingService(nats_client)
        
        # Stream handler
        async def stream_generator():
            """Generator that yields stream chunks from WebSocket"""
            while True:
                try:
                    data = await websocket.receive_text()
                    chunk = json.loads(data)
                    
                    if chunk.get("type") == "end":
                        break
                        
                    yield chunk.get("content", "")
                    
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error in stream generator: {e}")
                    break
        
        # Wait for initial message with context
        initial_data = await websocket.receive_text()
        initial_msg = AgentMessage.parse_raw(initial_data)
        
        # Start streaming response
        source = AgentIdentity(
            id=agent_id,
            tenant_id=tenant_id,
            capabilities=agent.capabilities or []
        )
        
        await messaging_service.stream_response(
            initial_msg,
            stream_generator(),
            source
        )
        
        # Send completion acknowledgment
        await websocket.send_json({
            "type": "STREAM_COMPLETE",
            "correlation_id": initial_msg.id
        })
        
    except WebSocketDisconnect:
        logger.info(f"Stream connection closed for agent {agent_id}")
        
    except Exception as e:
        logger.error(f"Stream WebSocket error for agent {agent_id}: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)