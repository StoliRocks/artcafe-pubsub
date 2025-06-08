"""
NATS-based monitoring service for multi-tenant message tracking and analytics.

This service provides:
- Real-time message tracking across all tenants
- Client presence detection
- Advanced metrics collection
- Security monitoring and anomaly detection
- Multi-tenant isolation
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict, deque
import statistics

from nats import NATS
from nats.aio.msg import Msg
from nats.errors import Error as NATSError

from api.services.local_message_tracker import message_tracker
from api.services.tenant_service import tenant_service
from api.services.client_service import client_service
from nats_client import nats_manager
from models.tenant import Tenant
from config.settings import settings

logger = logging.getLogger(__name__)


class MetricTier:
    """Metric tiers for different subscription levels"""
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class NATSMonitoringService:
    """
    Comprehensive NATS monitoring service for multi-tenant environments.
    
    Features:
    - Secure multi-tenant message tracking
    - Client presence detection
    - Advanced metrics collection
    - Anomaly detection
    - Performance analytics
    """
    
    def __init__(self):
        """Initialize the monitoring service"""
        self.running = False
        self.subscriptions: Dict[str, Any] = {}  # tenant_id -> subscription
        self.client_presence: Dict[str, Dict[str, Any]] = {}  # tenant_id -> {client_id -> presence_info}
        
        # Advanced metrics storage
        self.message_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.message_patterns: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.error_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.throughput_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=60))  # 60 minutes
        
        # Security monitoring
        self.anomaly_thresholds = {
            "message_rate_spike": 10.0,  # 10x normal rate
            "error_rate_threshold": 0.1,  # 10% error rate
            "unusual_subject_threshold": 0.2,  # 20% new subjects
        }
        
        # Background tasks
        self.monitor_task: Optional[asyncio.Task] = None
        self.analytics_task: Optional[asyncio.Task] = None
        self.presence_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the monitoring service"""
        if self.running:
            logger.warning("NATS monitoring service already running")
            return
            
        self.running = True
        logger.info("Starting NATS monitoring service")
        
        # Start monitoring for all active tenants
        tenants = await self._get_active_tenants()
        for tenant in tenants:
            await self._start_tenant_monitoring(tenant.id)
        
        # Start background tasks
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        self.analytics_task = asyncio.create_task(self._analytics_loop())
        self.presence_task = asyncio.create_task(self._presence_loop())
        
        logger.info("NATS monitoring service started successfully")
    
    async def stop(self):
        """Stop the monitoring service"""
        self.running = False
        
        # Cancel background tasks
        for task in [self.monitor_task, self.analytics_task, self.presence_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Unsubscribe from all tenants
        for tenant_id, sub in self.subscriptions.items():
            try:
                await sub.unsubscribe()
            except Exception as e:
                logger.error(f"Error unsubscribing from tenant {tenant_id}: {e}")
        
        self.subscriptions.clear()
        logger.info("NATS monitoring service stopped")
    
    async def _start_tenant_monitoring(self, tenant_id: str):
        """Start monitoring for a specific tenant"""
        try:
            # Subscribe to all messages for this tenant with wildcard
            subject = f"tenant.{tenant_id}.>"
            
            # Create subscription with message handler
            sub = await nats_manager.subscribe(
                subject,
                cb=lambda msg: asyncio.create_task(self._handle_message(tenant_id, msg))
            )
            
            self.subscriptions[tenant_id] = sub
            logger.info(f"Started monitoring tenant {tenant_id} on subject {subject}")
            
            # Also monitor system subjects for this tenant
            system_subject = f"_SYS.tenant.{tenant_id}.>"
            system_sub = await nats_manager.subscribe(
                system_subject,
                cb=lambda msg: asyncio.create_task(self._handle_system_message(tenant_id, msg))
            )
            self.subscriptions[f"{tenant_id}_system"] = system_sub
            
        except Exception as e:
            logger.error(f"Error starting monitoring for tenant {tenant_id}: {e}")
    
    async def _handle_message(self, tenant_id: str, msg: Msg):
        """Handle a message from a tenant's subject"""
        try:
            # Extract message metadata
            subject = msg.subject
            timestamp = datetime.now(timezone.utc)
            
            # Parse message data
            try:
                data = json.loads(msg.data.decode())
            except:
                data = {"raw": msg.data.decode()}
            
            # Extract client information
            client_id = data.get("agent_id") or data.get("client_id") or "unknown"
            
            # Update client presence
            if client_id != "unknown":
                await self._update_client_presence(tenant_id, client_id, timestamp)
            
            # Track message
            message_size = len(msg.data)
            await self._track_message(tenant_id, client_id, subject, message_size, timestamp)
            
            # Collect advanced metrics
            await self._collect_advanced_metrics(tenant_id, client_id, subject, data, timestamp)
            
            # Check for anomalies
            await self._check_anomalies(tenant_id, client_id, subject, data)
            
        except Exception as e:
            logger.error(f"Error handling message for tenant {tenant_id}: {e}")
            await self._track_error(tenant_id, "message_handling", str(e))
    
    async def _handle_system_message(self, tenant_id: str, msg: Msg):
        """Handle system messages (connection events, etc.)"""
        try:
            subject = msg.subject
            
            # Handle different system events
            if "CONNECT" in subject:
                await self._handle_client_connect(tenant_id, msg)
            elif "DISCONNECT" in subject:
                await self._handle_client_disconnect(tenant_id, msg)
            elif "ERROR" in subject:
                await self._handle_client_error(tenant_id, msg)
                
        except Exception as e:
            logger.error(f"Error handling system message for tenant {tenant_id}: {e}")
    
    async def _track_message(self, tenant_id: str, client_id: str, subject: str, 
                           message_size: int, timestamp: datetime):
        """Track a message in our metrics system"""
        try:
            # Extract channel if present
            channel_id = None
            if ".channel." in subject:
                parts = subject.split(".")
                if len(parts) > 3:
                    channel_id = parts[3]
            
            # Track in Redis for real-time metrics
            await message_tracker.track_message(
                tenant_id=tenant_id,
                agent_id=client_id,
                channel_id=channel_id,
                message_size=message_size
            )
            
            # Update throughput history
            hour_key = timestamp.strftime("%Y%m%d:%H")
            self.throughput_history[tenant_id].append((timestamp, message_size))
            
            # Track message patterns
            subject_pattern = self._extract_subject_pattern(subject)
            self.message_patterns[tenant_id][subject_pattern] += 1
            
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
    
    async def _collect_advanced_metrics(self, tenant_id: str, client_id: str, 
                                      subject: str, data: Dict[str, Any], 
                                      timestamp: datetime):
        """Collect advanced metrics for premium tiers"""
        try:
            # Check tenant's subscription tier
            tenant = await tenant_service.get_tenant(tenant_id)
            if not tenant:
                return
            
            tier = tenant.subscription_tier
            
            # Basic metrics (all tiers)
            if tier in [MetricTier.BASIC, MetricTier.PROFESSIONAL, MetricTier.ENTERPRISE]:
                # Message count and size are already tracked
                pass
            
            # Professional metrics
            if tier in [MetricTier.PROFESSIONAL, MetricTier.ENTERPRISE]:
                # Track message latency if timestamp is in message
                if "timestamp" in data:
                    try:
                        msg_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                        latency = (timestamp - msg_time).total_seconds() * 1000  # ms
                        self.message_latencies[tenant_id].append(latency)
                    except:
                        pass
                
                # Track subject distribution
                await self._track_subject_distribution(tenant_id, subject)
            
            # Enterprise metrics
            if tier == MetricTier.ENTERPRISE:
                # Track message flow patterns
                await self._track_message_flow(tenant_id, client_id, subject, data)
                
                # Track payload analytics
                await self._analyze_payload(tenant_id, subject, data)
                
                # Track client behavior patterns
                await self._track_client_behavior(tenant_id, client_id, subject)
                
        except Exception as e:
            logger.error(f"Error collecting advanced metrics: {e}")
    
    async def _check_anomalies(self, tenant_id: str, client_id: str, 
                              subject: str, data: Dict[str, Any]):
        """Check for anomalies in message patterns"""
        try:
            # Check message rate spike
            current_rate = self._calculate_message_rate(tenant_id)
            normal_rate = self._get_normal_message_rate(tenant_id)
            
            if normal_rate > 0 and current_rate > normal_rate * self.anomaly_thresholds["message_rate_spike"]:
                await self._alert_anomaly(tenant_id, "message_rate_spike", {
                    "current_rate": current_rate,
                    "normal_rate": normal_rate,
                    "client_id": client_id
                })
            
            # Check for unusual subjects
            if self._is_unusual_subject(tenant_id, subject):
                await self._alert_anomaly(tenant_id, "unusual_subject", {
                    "subject": subject,
                    "client_id": client_id
                })
            
            # Check error patterns
            if "error" in data or "exception" in data:
                await self._track_error(tenant_id, client_id, data.get("error", "unknown"))
                
        except Exception as e:
            logger.error(f"Error checking anomalies: {e}")
    
    async def _update_client_presence(self, tenant_id: str, client_id: str, 
                                    timestamp: datetime):
        """Update client presence information"""
        if tenant_id not in self.client_presence:
            self.client_presence[tenant_id] = {}
        
        self.client_presence[tenant_id][client_id] = {
            "last_seen": timestamp,
            "status": "online",
            "message_count": self.client_presence[tenant_id].get(client_id, {}).get("message_count", 0) + 1
        }
        
        # Update client status in database
        try:
            await client_service.update_client_status(client_id, "online")
        except Exception as e:
            logger.debug(f"Could not update client status: {e}")
    
    async def _monitor_loop(self):
        """Background loop for monitoring new tenants"""
        while self.running:
            try:
                # Check for new tenants every minute
                await asyncio.sleep(60)
                
                # Get all active tenants
                tenants = await self._get_active_tenants()
                
                # Start monitoring for new tenants
                for tenant in tenants:
                    if tenant.id not in self.subscriptions:
                        await self._start_tenant_monitoring(tenant.id)
                
                # Stop monitoring for deleted tenants
                current_tenant_ids = {t.id for t in tenants}
                for tenant_id in list(self.subscriptions.keys()):
                    if tenant_id not in current_tenant_ids and not tenant_id.endswith("_system"):
                        sub = self.subscriptions.pop(tenant_id, None)
                        if sub:
                            await sub.unsubscribe()
                        # Also remove system subscription
                        system_sub = self.subscriptions.pop(f"{tenant_id}_system", None)
                        if system_sub:
                            await system_sub.unsubscribe()
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
    
    async def _analytics_loop(self):
        """Background loop for processing analytics"""
        while self.running:
            try:
                # Process analytics every 5 minutes
                await asyncio.sleep(300)
                
                # Calculate and store analytics for each tenant
                for tenant_id in list(self.client_presence.keys()):
                    await self._process_tenant_analytics(tenant_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in analytics loop: {e}")
    
    async def _presence_loop(self):
        """Background loop for updating client presence"""
        while self.running:
            try:
                # Check client presence every 30 seconds
                await asyncio.sleep(30)
                
                now = datetime.now(timezone.utc)
                
                # Update offline clients
                for tenant_id, clients in self.client_presence.items():
                    for client_id, presence in clients.items():
                        last_seen = presence.get("last_seen")
                        if last_seen and (now - last_seen).total_seconds() > 90:
                            # Mark client as offline after 90 seconds of inactivity
                            presence["status"] = "offline"
                            try:
                                await client_service.update_client_status(client_id, "offline")
                            except:
                                pass
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in presence loop: {e}")
    
    async def _get_active_tenants(self) -> List[Tenant]:
        """Get all active tenants"""
        try:
            # This would query DynamoDB for all active tenants
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Error getting active tenants: {e}")
            return []
    
    async def _process_tenant_analytics(self, tenant_id: str):
        """Process analytics for a tenant"""
        try:
            # Calculate various analytics
            analytics = {
                "message_rate": self._calculate_message_rate(tenant_id),
                "average_latency": self._calculate_average_latency(tenant_id),
                "error_rate": self._calculate_error_rate(tenant_id),
                "active_clients": len([c for c in self.client_presence.get(tenant_id, {}).values() 
                                     if c.get("status") == "online"]),
                "subject_distribution": dict(self.message_patterns.get(tenant_id, {})),
                "throughput_mbps": self._calculate_throughput(tenant_id),
            }
            
            # Store analytics (would go to DynamoDB)
            logger.info(f"Analytics for tenant {tenant_id}: {analytics}")
            
        except Exception as e:
            logger.error(f"Error processing analytics for tenant {tenant_id}: {e}")
    
    def _calculate_message_rate(self, tenant_id: str) -> float:
        """Calculate current message rate (messages per second)"""
        # Implementation would calculate from recent messages
        return 0.0
    
    def _get_normal_message_rate(self, tenant_id: str) -> float:
        """Get normal message rate for anomaly detection"""
        # Implementation would use historical data
        return 1.0
    
    def _calculate_average_latency(self, tenant_id: str) -> float:
        """Calculate average message latency"""
        latencies = self.message_latencies.get(tenant_id)
        if latencies and len(latencies) > 0:
            return statistics.mean(latencies)
        return 0.0
    
    def _calculate_error_rate(self, tenant_id: str) -> float:
        """Calculate error rate"""
        errors = self.error_counts.get(tenant_id, {})
        total_errors = sum(errors.values())
        # Would need total message count for proper calculation
        return 0.0
    
    def _calculate_throughput(self, tenant_id: str) -> float:
        """Calculate throughput in Mbps"""
        history = self.throughput_history.get(tenant_id, deque())
        if len(history) < 2:
            return 0.0
        
        # Calculate bytes per second over recent history
        recent_bytes = sum(size for _, size in history)
        time_span = 60.0  # 60 seconds
        bytes_per_second = recent_bytes / time_span
        mbps = (bytes_per_second * 8) / 1_000_000
        return mbps
    
    def _extract_subject_pattern(self, subject: str) -> str:
        """Extract pattern from subject (replace IDs with wildcards)"""
        parts = subject.split(".")
        pattern_parts = []
        
        for part in parts:
            # Replace UUIDs and IDs with wildcards
            if len(part) > 20 or part.isdigit():
                pattern_parts.append("*")
            else:
                pattern_parts.append(part)
                
        return ".".join(pattern_parts)
    
    def _is_unusual_subject(self, tenant_id: str, subject: str) -> bool:
        """Check if subject is unusual for this tenant"""
        pattern = self._extract_subject_pattern(subject)
        patterns = self.message_patterns.get(tenant_id, {})
        
        if not patterns:
            return False
            
        # Check if this pattern is rare
        total_messages = sum(patterns.values())
        pattern_count = patterns.get(pattern, 0)
        
        if pattern_count == 0:
            return True
            
        pattern_ratio = pattern_count / total_messages
        return pattern_ratio < 0.01  # Less than 1% of messages
    
    async def _track_error(self, tenant_id: str, source: str, error: str):
        """Track error occurrence"""
        self.error_counts[tenant_id][f"{source}:{error}"] += 1
    
    async def _alert_anomaly(self, tenant_id: str, anomaly_type: str, details: Dict[str, Any]):
        """Alert about detected anomaly"""
        logger.warning(f"Anomaly detected for tenant {tenant_id}: {anomaly_type} - {details}")
        # Would send alerts to monitoring system
    
    async def _track_subject_distribution(self, tenant_id: str, subject: str):
        """Track subject distribution for professional tier"""
        # Implementation for subject analytics
        pass
    
    async def _track_message_flow(self, tenant_id: str, client_id: str, 
                                subject: str, data: Dict[str, Any]):
        """Track message flow patterns for enterprise tier"""
        # Implementation for flow analytics
        pass
    
    async def _analyze_payload(self, tenant_id: str, subject: str, data: Dict[str, Any]):
        """Analyze message payload for enterprise tier"""
        # Implementation for payload analytics
        pass
    
    async def _track_client_behavior(self, tenant_id: str, client_id: str, subject: str):
        """Track client behavior patterns for enterprise tier"""
        # Implementation for behavior analytics
        pass
    
    async def _handle_client_connect(self, tenant_id: str, msg: Msg):
        """Handle client connection event"""
        # Extract client ID from system message
        pass
    
    async def _handle_client_disconnect(self, tenant_id: str, msg: Msg):
        """Handle client disconnection event"""
        # Extract client ID and update status
        pass
    
    async def _handle_client_error(self, tenant_id: str, msg: Msg):
        """Handle client error event"""
        # Track client errors
        pass
    
    # Public API methods for retrieving metrics
    
    async def get_tenant_metrics(self, tenant_id: str, tier: str = MetricTier.BASIC) -> Dict[str, Any]:
        """Get metrics for a tenant based on their tier"""
        metrics = {
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tier": tier
        }
        
        # Basic metrics
        if tier in [MetricTier.BASIC, MetricTier.PROFESSIONAL, MetricTier.ENTERPRISE]:
            # Get from Redis tracker
            stats = await message_tracker.get_current_stats(tenant_id)
            metrics.update({
                "messages": stats.get("messages", 0),
                "bytes": stats.get("bytes", 0),
                "active_clients": len([c for c in self.client_presence.get(tenant_id, {}).values() 
                                     if c.get("status") == "online"]),
                "active_channels": stats.get("active_channels", 0)
            })
        
        # Professional metrics
        if tier in [MetricTier.PROFESSIONAL, MetricTier.ENTERPRISE]:
            metrics.update({
                "average_latency_ms": self._calculate_average_latency(tenant_id),
                "throughput_mbps": self._calculate_throughput(tenant_id),
                "subject_distribution": dict(self.message_patterns.get(tenant_id, {})),
                "message_rate_per_second": self._calculate_message_rate(tenant_id)
            })
        
        # Enterprise metrics
        if tier == MetricTier.ENTERPRISE:
            metrics.update({
                "error_rate": self._calculate_error_rate(tenant_id),
                "anomalies_detected": 0,  # Would track actual anomalies
                "client_analytics": self._get_client_analytics(tenant_id),
                "predictive_insights": self._get_predictive_insights(tenant_id)
            })
        
        return metrics
    
    def _get_client_analytics(self, tenant_id: str) -> Dict[str, Any]:
        """Get detailed client analytics for enterprise tier"""
        analytics = {}
        for client_id, presence in self.client_presence.get(tenant_id, {}).items():
            analytics[client_id] = {
                "status": presence.get("status"),
                "message_count": presence.get("message_count", 0),
                "last_seen": presence.get("last_seen").isoformat() if presence.get("last_seen") else None
            }
        return analytics
    
    def _get_predictive_insights(self, tenant_id: str) -> Dict[str, Any]:
        """Get predictive insights for enterprise tier"""
        return {
            "predicted_monthly_messages": 0,  # Would use ML model
            "capacity_recommendation": "current",
            "cost_optimization_tips": []
        }


# Global instance
nats_monitoring_service = NATSMonitoringService()

async def get_nats_monitoring_service() -> NATSMonitoringService:
    """Get the global NATS monitoring service instance"""
    return nats_monitoring_service