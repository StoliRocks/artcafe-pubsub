"""
Integration module for the Comprehensive Message Tracker

This module provides integration points to ensure the tracker is properly
initialized and integrated with the existing ArtCafe infrastructure.
"""

import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from api.services.comprehensive_message_tracker import get_message_tracker

logger = logging.getLogger(__name__)


async def initialize_message_tracker(app: FastAPI):
    """
    Initialize the comprehensive message tracker during app startup.
    
    This should be called in the FastAPI lifespan context manager.
    """
    try:
        logger.info("Initializing comprehensive message tracker...")
        tracker = await get_message_tracker()
        
        # Store tracker instance in app state for access
        app.state.message_tracker = tracker
        
        logger.info("Message tracker initialized successfully")
        return tracker
        
    except Exception as e:
        logger.error(f"Failed to initialize message tracker: {e}")
        # Don't fail app startup, but log the error
        return None


async def shutdown_message_tracker(app: FastAPI):
    """
    Gracefully shutdown the message tracker.
    
    This should be called during app shutdown.
    """
    try:
        if hasattr(app.state, 'message_tracker') and app.state.message_tracker:
            logger.info("Shutting down message tracker...")
            await app.state.message_tracker.stop()
            logger.info("Message tracker shut down successfully")
            
    except Exception as e:
        logger.error(f"Error shutting down message tracker: {e}")


@asynccontextmanager
async def lifespan_with_tracker(app: FastAPI):
    """
    FastAPI lifespan context manager that includes message tracker.
    
    Usage in app.py:
    ```python
    from api.services.tracker_integration import lifespan_with_tracker
    
    app = FastAPI(lifespan=lifespan_with_tracker)
    ```
    """
    # Startup
    await initialize_message_tracker(app)
    
    yield
    
    # Shutdown
    await shutdown_message_tracker(app)


# Middleware for tracking HTTP-initiated messages
async def track_api_message(tenant_id: str, client_id: str, 
                           subject: str, payload_size: int):
    """
    Track messages that are initiated via HTTP API.
    
    This ensures even REST API-triggered messages are tracked.
    """
    from api.services.comprehensive_message_tracker import track_client_activity
    
    try:
        await track_client_activity(
            client_id=client_id,
            tenant_id=tenant_id,
            subject=subject,
            size=payload_size,
            direction="api"
        )
    except Exception as e:
        logger.error(f"Error tracking API message: {e}")


# Integration with existing NATS client
class TrackedNATSClient:
    """
    Wrapper around NATS client that automatically tracks all messages.
    
    This can replace the existing NATS client to ensure all messages
    are tracked at the client level as a backup to system-level tracking.
    """
    
    def __init__(self, nats_client):
        self.nc = nats_client
        self.client_id = None
        self.tenant_id = None
        
    def set_identity(self, client_id: str, tenant_id: str):
        """Set the identity for message tracking"""
        self.client_id = client_id
        self.tenant_id = tenant_id
        
    async def publish(self, subject: str, payload: bytes, **kwargs):
        """Publish with automatic tracking"""
        # Publish the message
        await self.nc.publish(subject, payload, **kwargs)
        
        # Track it
        if self.client_id and self.tenant_id:
            from api.services.comprehensive_message_tracker import track_client_activity
            await track_client_activity(
                client_id=self.client_id,
                tenant_id=self.tenant_id,
                subject=subject,
                size=len(payload),
                direction="sent"
            )
    
    async def subscribe(self, subject: str, cb=None, **kwargs):
        """Subscribe with automatic tracking of received messages"""
        
        async def tracking_callback(msg):
            # Track received message
            if self.client_id and self.tenant_id:
                from api.services.comprehensive_message_tracker import track_client_activity
                await track_client_activity(
                    client_id=self.client_id,
                    tenant_id=self.tenant_id,
                    subject=msg.subject,
                    size=len(msg.data) if msg.data else 0,
                    direction="received"
                )
            
            # Call original callback
            if cb:
                await cb(msg)
        
        # Subscribe with tracking callback
        return await self.nc.subscribe(subject, cb=tracking_callback, **kwargs)
    
    # Proxy all other methods
    def __getattr__(self, name):
        return getattr(self.nc, name)


# Usage tracking endpoints integration
async def get_comprehensive_usage_stats(tenant_id: str, client_id: Optional[str] = None):
    """
    Get comprehensive usage statistics from the tracker.
    
    This can be used by the existing usage endpoints.
    """
    from api.services.comprehensive_message_tracker import (
        get_client_usage_stats, get_tenant_usage_stats
    )
    
    stats = {
        "tenant": await get_tenant_usage_stats(tenant_id)
    }
    
    if client_id:
        stats["client"] = await get_client_usage_stats(client_id)
    
    return stats


# WebSocket integration
async def track_websocket_message(connection_id: str, tenant_id: str,
                                 message_type: str, size: int):
    """
    Track WebSocket messages through the comprehensive tracker.
    
    This ensures WebSocket traffic is also monitored.
    """
    from api.services.comprehensive_message_tracker import track_client_activity
    
    try:
        await track_client_activity(
            client_id=f"ws_{connection_id}",
            tenant_id=tenant_id,
            subject=f"websocket.{message_type}",
            size=size,
            direction="websocket"
        )
    except Exception as e:
        logger.error(f"Error tracking WebSocket message: {e}")


# NATS server configuration helper
def get_nats_monitoring_config():
    """
    Get NATS server configuration for enabling system monitoring.
    
    This configuration should be added to the NATS server to enable
    system-level monitoring subjects.
    
    Returns a dictionary of recommended NATS server settings.
    """
    return {
        "accounts": {
            "$SYS": {
                "users": [
                    {
                        "user": "artcafe-monitor",
                        "password": "generate-secure-password",
                        "permissions": {
                            "publish": {
                                "deny": [">"]
                            },
                            "subscribe": {
                                "allow": ["$SYS.>"]
                            }
                        }
                    }
                ]
            }
        },
        "system_account": "$SYS",
        "no_sys_acc": False,  # Enable system account
        "max_control_line": 4096,
        "max_payload": 1048576,  # 1MB
        "write_deadline": "10s",
        "debug": False,
        "trace": False,
        "logtime": True,
        "log_file": "/var/log/nats-server.log",
        "pid_file": "/var/run/nats-server.pid",
        
        # Enable monitoring
        "server_name": "artcafe-nats-1",
        "monitor_port": 8222,
        "http_port": 8222,
        
        # Connection events
        "connect_error_reports": 10,
        "reconnect_error_reports": 10,
        
        # Accounts configuration for multi-tenancy
        "accounts": {
            # System account for monitoring
            "$SYS": {
                "exports": [
                    {
                        "stream": "$SYS.ACCOUNT.*.>",
                        "accounts": ["artcafe-monitor"]
                    }
                ]
            },
            # Monitor account
            "artcafe-monitor": {
                "imports": [
                    {
                        "stream": {
                            "account": "$SYS",
                            "subject": "$SYS.ACCOUNT.*.>"
                        }
                    }
                ]
            }
        }
    }


# Example update for app.py
TRACKER_APP_INTEGRATION = """
# In your app.py file, add this integration:

from api.services.tracker_integration import lifespan_with_tracker

# Replace existing lifespan or add if not present
app = FastAPI(
    title="ArtCafe PubSub API",
    lifespan=lifespan_with_tracker  # This handles tracker lifecycle
)

# Or if you have existing lifespan logic:
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Your existing startup logic
    
    # Add tracker initialization
    from api.services.tracker_integration import initialize_message_tracker
    await initialize_message_tracker(app)
    
    yield
    
    # Your existing shutdown logic
    
    # Add tracker shutdown
    from api.services.tracker_integration import shutdown_message_tracker
    await shutdown_message_tracker(app)

app = FastAPI(lifespan=lifespan)
"""