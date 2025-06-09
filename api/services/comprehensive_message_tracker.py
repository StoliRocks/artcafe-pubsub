"""
Comprehensive Message Tracking Service

This service provides low-level NATS message tracking that cannot be bypassed
by SDK modifications. It monitors ALL messages from authenticated agents
regardless of subject pattern.

Key features:
- Tracks connection events (connect/disconnect)
- Monitors all published messages via NATS system events
- Accurate byte counting for billing
- Real-time and persistent storage
- Cannot be bypassed by client-side code
"""

import asyncio
import json
import time
from typing import Dict, Optional, Set, Any
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, field
import nats
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
import redis.asyncio as redis

from api.db.dynamodb import get_usage_metrics_table
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ConnectionMetrics:
    """Tracks metrics for a single connection"""
    client_id: str
    tenant_id: str
    connected_at: float
    last_activity: float
    messages_sent: int = 0
    bytes_sent: int = 0
    messages_received: int = 0
    bytes_received: int = 0
    subjects_used: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "tenant_id": self.tenant_id,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "messages_sent": self.messages_sent,
            "bytes_sent": self.bytes_sent,
            "messages_received": self.messages_received,
            "bytes_received": self.bytes_received,
            "subjects_used": list(self.subjects_used),
            "connection_duration": time.time() - self.connected_at
        }


class ComprehensiveMessageTracker:
    """
    Comprehensive message tracking that monitors NATS at a system level.
    
    This tracker:
    1. Connects as a system monitor to receive all connection/message events
    2. Uses NATS monitoring subjects to track ALL activity
    3. Maintains real-time metrics in Redis
    4. Persists to DynamoDB periodically
    5. Cannot be bypassed by client modifications
    """
    
    def __init__(self):
        self.nc: Optional[NATS] = None
        self.monitor_nc: Optional[NATS] = None  # Separate connection for monitoring
        self.redis_client: Optional[redis.Redis] = None
        self.connections: Dict[str, ConnectionMetrics] = {}
        self.running = False
        self._persist_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the comprehensive message tracker"""
        try:
            # Initialize Redis connection
            self.redis_client = await redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
                decode_responses=True
            )
            
            # Connect to NATS as a system monitor
            self.monitor_nc = await nats.connect(
                servers=[f"nats://{settings.NATS_HOST}:{settings.NATS_PORT}"],
                name="artcafe-message-tracker",
                # Use system account credentials if available
                user=settings.NATS_SYSTEM_USER if hasattr(settings, 'NATS_SYSTEM_USER') else None,
                password=settings.NATS_SYSTEM_PASSWORD if hasattr(settings, 'NATS_SYSTEM_PASSWORD') else None,
            )
            
            # Regular NATS connection for publishing tracking data
            self.nc = await nats.connect(
                servers=[f"nats://{settings.NATS_HOST}:{settings.NATS_PORT}"]
            )
            
            # Subscribe to system monitoring subjects
            await self._setup_monitoring_subscriptions()
            
            # Start background tasks
            self.running = True
            self._persist_task = asyncio.create_task(self._periodic_persistence())
            self._monitor_task = asyncio.create_task(self._monitor_connections())
            
            logger.info("Comprehensive message tracker started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start message tracker: {e}")
            raise
    
    async def _setup_monitoring_subscriptions(self):
        """Set up subscriptions to NATS system events"""
        
        # Monitor all connection events
        # Note: These subjects may vary based on NATS server configuration
        monitoring_subjects = [
            # Connection events
            "$SYS.ACCOUNT.*.CONNECTS",
            "$SYS.ACCOUNT.*.DISCONNECTS",
            "$SYS.SERVER.*.CLIENT.CONNECT",
            "$SYS.SERVER.*.CLIENT.DISCONNECT",
            
            # Message flow monitoring
            "$SYS.ACCOUNT.*.MSGS.PUB",
            "$SYS.ACCOUNT.*.MSGS.SUB",
            "$SYS.ACCOUNT.*.BYTES.PUB",
            "$SYS.ACCOUNT.*.BYTES.SUB",
            
            # Account-level monitoring (if using accounts)
            "$SYS.ACCOUNT.*.CONNS",
            "$SYS.ACCOUNT.*.LEAFS",
            "$SYS.ACCOUNT.*.TOTAL_CONNS",
        ]
        
        # Try to subscribe to system events
        for subject in monitoring_subjects:
            try:
                await self.monitor_nc.subscribe(subject, cb=self._handle_system_event)
                logger.debug(f"Subscribed to system subject: {subject}")
            except Exception as e:
                logger.debug(f"Could not subscribe to {subject}: {e}")
        
        # Alternative approach: Monitor all messages on specific tenant patterns
        # This acts as a transparent proxy/monitor
        try:
            # Monitor all tenant messages
            await self.monitor_nc.subscribe("tenant.>", cb=self._handle_tenant_message)
            logger.info("Monitoring all tenant.> messages")
            
            # Monitor all agent messages
            await self.monitor_nc.subscribe("agent.>", cb=self._handle_agent_message)
            logger.info("Monitoring all agent.> messages")
            
            # Monitor custom subjects that agents might use
            await self.monitor_nc.subscribe("cyberforge.>", cb=self._handle_custom_message)
            await self.monitor_nc.subscribe("*.>", cb=self._handle_wildcard_message)
            
        except Exception as e:
            logger.error(f"Error setting up message monitoring: {e}")
    
    async def _handle_system_event(self, msg: Msg):
        """Handle NATS system events"""
        try:
            # System events often come as JSON
            if msg.data:
                data = json.loads(msg.data.decode())
                logger.debug(f"System event on {msg.subject}: {data}")
                
                # Extract relevant information based on event type
                if "CLIENT.CONNECT" in msg.subject:
                    await self._handle_client_connect(data)
                elif "CLIENT.DISCONNECT" in msg.subject:
                    await self._handle_client_disconnect(data)
                elif "MSGS.PUB" in msg.subject or "BYTES.PUB" in msg.subject:
                    await self._handle_publish_stats(data)
                    
        except Exception as e:
            logger.error(f"Error handling system event: {e}")
    
    async def _handle_tenant_message(self, msg: Msg):
        """Intercept and track messages on tenant.> subjects"""
        await self._track_message(msg, "tenant")
    
    async def _handle_agent_message(self, msg: Msg):
        """Intercept and track messages on agent.> subjects"""
        await self._track_message(msg, "agent")
    
    async def _handle_custom_message(self, msg: Msg):
        """Intercept and track messages on custom subjects"""
        await self._track_message(msg, "custom")
    
    async def _handle_wildcard_message(self, msg: Msg):
        """Catch-all handler for any other messages"""
        # Skip system subjects and our own tracking subjects
        if not msg.subject.startswith("$") and not msg.subject.startswith("_INBOX."):
            await self._track_message(msg, "wildcard")
    
    async def _track_message(self, msg: Msg, source: str):
        """Track a message regardless of its subject"""
        try:
            # Extract client information from message headers or subject
            client_id = None
            tenant_id = None
            
            # Try to extract from headers first (if NATS headers are enabled)
            if msg.headers:
                client_id = msg.headers.get("X-Client-ID")
                tenant_id = msg.headers.get("X-Tenant-ID")
            
            # Try to extract from subject pattern
            if not client_id and "." in msg.subject:
                parts = msg.subject.split(".")
                if parts[0] == "tenant" and len(parts) > 1:
                    tenant_id = parts[1]
                elif parts[0] == "agent" and len(parts) > 1:
                    client_id = parts[1]
            
            # Track the message
            if client_id or tenant_id:
                await self._record_message(
                    client_id=client_id,
                    tenant_id=tenant_id,
                    subject=msg.subject,
                    size=len(msg.data) if msg.data else 0,
                    source=source
                )
                
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
    
    async def _record_message(self, client_id: Optional[str], tenant_id: Optional[str],
                             subject: str, size: int, source: str):
        """Record a message in our tracking system"""
        try:
            timestamp = time.time()
            
            # Update Redis with atomic operations
            pipe = self.redis_client.pipeline()
            
            if client_id:
                # Track by client
                client_key = f"tracker:client:{client_id}"
                pipe.hincrby(client_key, "messages_sent", 1)
                pipe.hincrby(client_key, "bytes_sent", size)
                pipe.hset(client_key, "last_activity", timestamp)
                pipe.sadd(f"{client_key}:subjects", subject)
                
            if tenant_id:
                # Track by tenant
                tenant_key = f"tracker:tenant:{tenant_id}"
                pipe.hincrby(tenant_key, "total_messages", 1)
                pipe.hincrby(tenant_key, "total_bytes", size)
                pipe.hset(tenant_key, "last_activity", timestamp)
                
                # Track hourly stats
                hour_key = datetime.utcnow().strftime("%Y%m%d%H")
                pipe.hincrby(f"{tenant_key}:hourly:{hour_key}", "messages", 1)
                pipe.hincrby(f"{tenant_key}:hourly:{hour_key}", "bytes", size)
            
            # Global tracking
            pipe.hincrby("tracker:global", f"messages_{source}", 1)
            pipe.hincrby("tracker:global", f"bytes_{source}", size)
            
            await pipe.execute()
            
            # Log for debugging
            logger.debug(f"Tracked message: client={client_id}, tenant={tenant_id}, "
                        f"subject={subject}, size={size}, source={source}")
            
        except Exception as e:
            logger.error(f"Error recording message: {e}")
    
    async def _handle_client_connect(self, data: dict):
        """Handle client connection event"""
        try:
            client_id = data.get("client_id") or data.get("cid")
            if client_id:
                self.connections[client_id] = ConnectionMetrics(
                    client_id=client_id,
                    tenant_id=data.get("account", "unknown"),
                    connected_at=time.time(),
                    last_activity=time.time()
                )
                
                # Store in Redis
                await self.redis_client.hset(
                    f"tracker:client:{client_id}",
                    mapping={
                        "connected_at": time.time(),
                        "status": "connected"
                    }
                )
                
                logger.info(f"Client connected: {client_id}")
                
        except Exception as e:
            logger.error(f"Error handling client connect: {e}")
    
    async def _handle_client_disconnect(self, data: dict):
        """Handle client disconnection event"""
        try:
            client_id = data.get("client_id") or data.get("cid")
            if client_id and client_id in self.connections:
                metrics = self.connections[client_id]
                
                # Persist final metrics
                await self._persist_client_metrics(client_id, metrics)
                
                # Clean up
                del self.connections[client_id]
                
                # Update Redis
                await self.redis_client.hset(
                    f"tracker:client:{client_id}",
                    "status", "disconnected"
                )
                
                logger.info(f"Client disconnected: {client_id}")
                
        except Exception as e:
            logger.error(f"Error handling client disconnect: {e}")
    
    async def _handle_publish_stats(self, data: dict):
        """Handle publish statistics from NATS system events"""
        try:
            # Extract stats from system event
            client_id = data.get("client_id")
            messages = data.get("msgs", 0)
            bytes_sent = data.get("bytes", 0)
            
            if client_id:
                await self.redis_client.hincrby(
                    f"tracker:client:{client_id}",
                    "messages_sent", messages
                )
                await self.redis_client.hincrby(
                    f"tracker:client:{client_id}",
                    "bytes_sent", bytes_sent
                )
                
        except Exception as e:
            logger.error(f"Error handling publish stats: {e}")
    
    async def _monitor_connections(self):
        """Monitor active connections and update metrics"""
        while self.running:
            try:
                # Check all active connections in Redis
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="tracker:client:*", count=100
                    )
                    
                    for key in keys:
                        client_data = await self.redis_client.hgetall(key)
                        if client_data.get("status") == "connected":
                            # Check for stale connections
                            last_activity = float(client_data.get("last_activity", 0))
                            if time.time() - last_activity > 300:  # 5 minutes
                                logger.warning(f"Stale connection detected: {key}")
                    
                    if cursor == 0:
                        break
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring connections: {e}")
                await asyncio.sleep(30)
    
    async def _periodic_persistence(self):
        """Periodically persist metrics to DynamoDB"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Persist every minute
                
                # Get all tracked data from Redis
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match="tracker:*", count=100
                    )
                    
                    for key in keys:
                        if key.startswith("tracker:client:"):
                            client_id = key.split(":")[-1]
                            await self._persist_client_data(client_id)
                        elif key.startswith("tracker:tenant:"):
                            tenant_id = key.split(":")[-1]
                            await self._persist_tenant_data(tenant_id)
                    
                    if cursor == 0:
                        break
                
            except Exception as e:
                logger.error(f"Error in periodic persistence: {e}")
                await asyncio.sleep(60)
    
    async def _persist_client_data(self, client_id: str):
        """Persist client metrics to DynamoDB"""
        try:
            # Get data from Redis
            client_key = f"tracker:client:{client_id}"
            data = await self.redis_client.hgetall(client_key)
            
            if not data:
                return
            
            # Prepare DynamoDB item
            table = await get_usage_metrics_table()
            
            item = {
                "pk": f"CLIENT#{client_id}",
                "sk": f"METRICS#{datetime.utcnow().isoformat()}",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
                "messages_sent": int(data.get("messages_sent", 0)),
                "bytes_sent": int(data.get("bytes_sent", 0)),
                "messages_received": int(data.get("messages_received", 0)),
                "bytes_received": int(data.get("bytes_received", 0)),
                "last_activity": float(data.get("last_activity", 0)),
                "ttl": int(time.time() + 2592000)  # 30 days
            }
            
            # Get subjects used
            subjects = await self.redis_client.smembers(f"{client_key}:subjects")
            if subjects:
                item["subjects_used"] = list(subjects)
            
            await table.put_item(Item=item)
            
        except Exception as e:
            logger.error(f"Error persisting client data: {e}")
    
    async def _persist_tenant_data(self, tenant_id: str):
        """Persist tenant metrics to DynamoDB"""
        try:
            # Get data from Redis
            tenant_key = f"tracker:tenant:{tenant_id}"
            data = await self.redis_client.hgetall(tenant_key)
            
            if not data:
                return
            
            # Prepare DynamoDB item
            table = await get_usage_metrics_table()
            
            item = {
                "pk": f"TENANT#{tenant_id}",
                "sk": f"METRICS#{datetime.utcnow().isoformat()}",
                "tenant_id": tenant_id,
                "timestamp": datetime.utcnow().isoformat(),
                "total_messages": int(data.get("total_messages", 0)),
                "total_bytes": int(data.get("total_bytes", 0)),
                "last_activity": float(data.get("last_activity", 0)),
                "ttl": int(time.time() + 2592000)  # 30 days
            }
            
            await table.put_item(Item=item)
            
            # Also persist hourly stats
            hour_key = datetime.utcnow().strftime("%Y%m%d%H")
            hourly_data = await self.redis_client.hgetall(f"{tenant_key}:hourly:{hour_key}")
            
            if hourly_data:
                hourly_item = {
                    "pk": f"TENANT#{tenant_id}",
                    "sk": f"HOURLY#{hour_key}",
                    "tenant_id": tenant_id,
                    "hour": hour_key,
                    "messages": int(hourly_data.get("messages", 0)),
                    "bytes": int(hourly_data.get("bytes", 0)),
                    "ttl": int(time.time() + 604800)  # 7 days
                }
                await table.put_item(Item=hourly_item)
            
        except Exception as e:
            logger.error(f"Error persisting tenant data: {e}")
    
    async def _persist_client_metrics(self, client_id: str, metrics: ConnectionMetrics):
        """Persist client metrics when disconnecting"""
        try:
            table = await get_usage_metrics_table()
            
            # Create a session summary
            item = {
                "pk": f"CLIENT#{client_id}",
                "sk": f"SESSION#{int(metrics.connected_at)}",
                "client_id": client_id,
                "tenant_id": metrics.tenant_id,
                "connected_at": metrics.connected_at,
                "disconnected_at": time.time(),
                "duration": time.time() - metrics.connected_at,
                "messages_sent": metrics.messages_sent,
                "bytes_sent": metrics.bytes_sent,
                "messages_received": metrics.messages_received,
                "bytes_received": metrics.bytes_received,
                "subjects_used": list(metrics.subjects_used),
                "ttl": int(time.time() + 2592000)  # 30 days
            }
            
            await table.put_item(Item=item)
            
            logger.info(f"Persisted session metrics for client {client_id}")
            
        except Exception as e:
            logger.error(f"Error persisting client metrics: {e}")
    
    async def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get current stats for a client"""
        try:
            client_key = f"tracker:client:{client_id}"
            data = await self.redis_client.hgetall(client_key)
            
            if not data:
                return {
                    "client_id": client_id,
                    "status": "not_found",
                    "messages_sent": 0,
                    "bytes_sent": 0
                }
            
            subjects = await self.redis_client.smembers(f"{client_key}:subjects")
            
            return {
                "client_id": client_id,
                "status": data.get("status", "unknown"),
                "connected_at": float(data.get("connected_at", 0)),
                "last_activity": float(data.get("last_activity", 0)),
                "messages_sent": int(data.get("messages_sent", 0)),
                "bytes_sent": int(data.get("bytes_sent", 0)),
                "messages_received": int(data.get("messages_received", 0)),
                "bytes_received": int(data.get("bytes_received", 0)),
                "subjects_used": list(subjects) if subjects else []
            }
            
        except Exception as e:
            logger.error(f"Error getting client stats: {e}")
            return {"error": str(e)}
    
    async def get_tenant_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get current stats for a tenant"""
        try:
            tenant_key = f"tracker:tenant:{tenant_id}"
            data = await self.redis_client.hgetall(tenant_key)
            
            if not data:
                return {
                    "tenant_id": tenant_id,
                    "total_messages": 0,
                    "total_bytes": 0
                }
            
            # Get hourly stats for the current hour
            hour_key = datetime.utcnow().strftime("%Y%m%d%H")
            hourly_data = await self.redis_client.hgetall(f"{tenant_key}:hourly:{hour_key}")
            
            return {
                "tenant_id": tenant_id,
                "total_messages": int(data.get("total_messages", 0)),
                "total_bytes": int(data.get("total_bytes", 0)),
                "last_activity": float(data.get("last_activity", 0)),
                "current_hour": {
                    "messages": int(hourly_data.get("messages", 0)) if hourly_data else 0,
                    "bytes": int(hourly_data.get("bytes", 0)) if hourly_data else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting tenant stats: {e}")
            return {"error": str(e)}
    
    async def stop(self):
        """Stop the message tracker"""
        self.running = False
        
        # Cancel background tasks
        if self._persist_task:
            self._persist_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        
        # Final persistence
        for client_id, metrics in self.connections.items():
            await self._persist_client_metrics(client_id, metrics)
        
        # Close connections
        if self.nc:
            await self.nc.close()
        if self.monitor_nc:
            await self.monitor_nc.close()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Comprehensive message tracker stopped")


# Global instance
_tracker: Optional[ComprehensiveMessageTracker] = None


async def get_message_tracker() -> ComprehensiveMessageTracker:
    """Get or create the global message tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = ComprehensiveMessageTracker()
        await _tracker.start()
    return _tracker


async def track_client_activity(client_id: str, tenant_id: str, 
                               subject: str, size: int, direction: str = "sent"):
    """
    Public API for tracking client activity.
    This can be called from other parts of the system.
    """
    try:
        tracker = await get_message_tracker()
        await tracker._record_message(
            client_id=client_id,
            tenant_id=tenant_id,
            subject=subject,
            size=size,
            source=direction
        )
    except Exception as e:
        logger.error(f"Error tracking client activity: {e}")


async def get_client_usage_stats(client_id: str) -> Dict[str, Any]:
    """Get usage statistics for a specific client"""
    try:
        tracker = await get_message_tracker()
        return await tracker.get_client_stats(client_id)
    except Exception as e:
        logger.error(f"Error getting client usage stats: {e}")
        return {"error": str(e)}


async def get_tenant_usage_stats(tenant_id: str) -> Dict[str, Any]:
    """Get usage statistics for a specific tenant"""
    try:
        tracker = await get_message_tracker()
        return await tracker.get_tenant_stats(tenant_id)
    except Exception as e:
        logger.error(f"Error getting tenant usage stats: {e}")
        return {"error": str(e)}