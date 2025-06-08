"""
NATS heartbeat handler for client presence detection
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from nats.aio.msg import Msg

from api.services.client_service import client_service
from api.services.local_message_tracker import message_tracker

logger = logging.getLogger(__name__)


class HeartbeatHandler:
    """Handles client heartbeats for presence detection"""
    
    def __init__(self, monitoring_service):
        """Initialize with reference to monitoring service"""
        self.monitoring_service = monitoring_service
        
    async def handle_heartbeat(self, msg: Msg):
        """Process a heartbeat message"""
        try:
            # Parse heartbeat subject: _HEARTBEAT.tenant.{tenant_id}.client.{client_id}
            parts = msg.subject.split(".")
            if len(parts) != 5:
                logger.warning(f"Invalid heartbeat subject: {msg.subject}")
                return
                
            tenant_id = parts[2]
            client_id = parts[4]
            
            # Parse heartbeat data
            try:
                data = json.loads(msg.data.decode())
            except:
                logger.warning(f"Invalid heartbeat data from {client_id}")
                return
            
            # Validate heartbeat
            if not self._validate_heartbeat(data, tenant_id, client_id):
                return
            
            # Update client presence
            await self._update_presence(tenant_id, client_id, data)
            
            # Track metrics from heartbeat
            await self._track_heartbeat_metrics(tenant_id, client_id, data)
            
            # Check client health
            await self._check_client_health(tenant_id, client_id, data)
            
        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")
    
    def _validate_heartbeat(self, data: Dict[str, Any], tenant_id: str, client_id: str) -> bool:
        """Validate heartbeat data"""
        # Check required fields
        required_fields = ["client_id", "tenant_id", "timestamp", "status"]
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field '{field}' in heartbeat from {client_id}")
                return False
        
        # Validate IDs match
        if data.get("client_id") != client_id or data.get("tenant_id") != tenant_id:
            logger.warning(f"ID mismatch in heartbeat from {client_id}")
            return False
            
        # Check timestamp is recent (allow 60 seconds of clock drift)
        try:
            timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age = (now - timestamp).total_seconds()
            
            if abs(age) > 60:
                logger.warning(f"Heartbeat timestamp too old/future from {client_id}: {age}s")
                return False
                
        except:
            logger.warning(f"Invalid timestamp in heartbeat from {client_id}")
            return False
            
        return True
    
    async def _update_presence(self, tenant_id: str, client_id: str, data: Dict[str, Any]):
        """Update client presence information"""
        timestamp = datetime.now(timezone.utc)
        
        # Update in monitoring service
        if tenant_id not in self.monitoring_service.client_presence:
            self.monitoring_service.client_presence[tenant_id] = {}
        
        # Get current presence or create new
        current = self.monitoring_service.client_presence[tenant_id].get(client_id, {})
        
        self.monitoring_service.client_presence[tenant_id][client_id] = {
            "last_seen": timestamp,
            "last_heartbeat": timestamp,
            "status": data.get("status", "healthy"),
            "version": data.get("version", "unknown"),
            "metadata": data.get("metadata", {}),
            "metrics": data.get("metrics", {}),
            "message_count": current.get("message_count", 0),  # Preserve message count
            "health_status": data.get("status", "healthy")
        }
        
        # Update client status in database
        try:
            await client_service.update_client_status(client_id, "online")
        except Exception as e:
            logger.debug(f"Could not update client status in DB: {e}")
    
    async def _track_heartbeat_metrics(self, tenant_id: str, client_id: str, data: Dict[str, Any]):
        """Track metrics from heartbeat data"""
        metrics = data.get("metrics", {})
        
        # If client reports message counts, verify against our tracking
        reported_sent = metrics.get("messages_sent", 0)
        reported_received = metrics.get("messages_received", 0)
        
        # Log any major discrepancies for investigation
        presence = self.monitoring_service.client_presence.get(tenant_id, {}).get(client_id, {})
        our_count = presence.get("message_count", 0)
        
        if abs(reported_sent - our_count) > 100:
            logger.info(f"Message count discrepancy for {client_id}: "
                      f"reported={reported_sent}, tracked={our_count}")
    
    async def _check_client_health(self, tenant_id: str, client_id: str, data: Dict[str, Any]):
        """Check client health and alert on issues"""
        status = data.get("status", "healthy")
        metrics = data.get("metrics", {})
        
        # Check for degraded/unhealthy status
        if status != "healthy":
            logger.warning(f"Client {client_id} reporting {status} status")
            
            # Track unhealthy clients for alerting
            await self.monitoring_service._alert_anomaly(tenant_id, "unhealthy_client", {
                "client_id": client_id,
                "status": status,
                "metrics": metrics
            })
        
        # Check error rates
        errors = metrics.get("errors", 0)
        messages = metrics.get("messages_sent", 0) + metrics.get("messages_received", 0)
        
        if messages > 0 and errors > 0:
            error_rate = errors / messages
            if error_rate > 0.05:  # 5% error rate
                await self.monitoring_service._alert_anomaly(tenant_id, "high_error_rate", {
                    "client_id": client_id,
                    "error_rate": error_rate,
                    "errors": errors,
                    "messages": messages
                })


async def setup_heartbeat_subscription(monitoring_service, nats_manager):
    """Setup subscription for heartbeat messages"""
    handler = HeartbeatHandler(monitoring_service)
    
    # Subscribe to all heartbeat messages
    await nats_manager.subscribe(
        "_HEARTBEAT.>",
        cb=handler.handle_heartbeat
    )
    
    logger.info("Heartbeat handler subscription active")