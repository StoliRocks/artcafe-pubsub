"""
Metrics and monitoring service for PubSub.

This module provides a metrics collection and monitoring service for the PubSub service.
It collects and aggregates metrics for usage tracking, monitoring, and billing purposes.
"""

import logging
import time
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple, Set

from config.settings import settings
from api.db.dynamodb import dynamodb
from models.usage import UsageMetrics, UsageTotals

logger = logging.getLogger(__name__)

# Table name for usage metrics
METRICS_TABLE_NAME = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"

# Metrics collection interval in seconds
METRICS_COLLECTION_INTERVAL = 60  # 1 minute

# Metrics flush interval in seconds (how often to write to DynamoDB)
METRICS_FLUSH_INTERVAL = 300  # 5 minutes


class MetricsService:
    """
    Metrics and monitoring service.
    
    This class provides methods for collecting, aggregating, and storing metrics
    for usage tracking, monitoring, and billing purposes.
    """
    
    def __init__(self):
        """Initialize metrics service."""
        # Current in-memory metrics storage (tenant_id -> category -> metric -> value)
        # Example: {"tenant-123": {"agents": {"count": 5, "active": 3}, "messages": {"count": 100}}}
        self.metrics: Dict[str, Dict[str, Dict[str, int]]] = {}
        
        # Set of active tenants, agents, and channels
        self.active_tenants: Set[str] = set()
        self.active_agents: Dict[str, Set[str]] = {}  # tenant_id -> set of agent_ids
        self.active_channels: Dict[str, Set[str]] = {}  # tenant_id -> set of channel_ids
        
        # Background tasks
        self.collection_task = None
        self.flush_task = None
        
        # Status
        self.running = False
    
    async def ensure_table_exists(self):
        """
        Ensure the metrics table exists in DynamoDB.
        
        This method checks if the metrics table exists and creates it if not.
        The table has tenant_id as the hash key and date as the range key.
        """
        try:
            # Check if the table exists
            exists = await dynamodb.table_exists(METRICS_TABLE_NAME)
            
            if not exists:
                # Create the table
                await dynamodb.create_table(
                    table_name=METRICS_TABLE_NAME,
                    key_schema=[
                        {"AttributeName": "tenant_id", "KeyType": "HASH"},
                        {"AttributeName": "date", "KeyType": "RANGE"}
                    ],
                    attribute_definitions=[
                        {"AttributeName": "tenant_id", "AttributeType": "S"},
                        {"AttributeName": "date", "AttributeType": "S"}
                    ],
                    provisioned_throughput={
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5
                    }
                )
                
                # Wait for the table to be created
                logger.info(f"Waiting for table {METRICS_TABLE_NAME} to be created...")
                await dynamodb.wait_for_table(METRICS_TABLE_NAME)
                
                logger.info(f"Created table {METRICS_TABLE_NAME}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error ensuring metrics table exists: {e}")
            return False
    
    async def start(self):
        """Start the metrics service."""
        if self.running:
            return
        
        # Ensure the metrics table exists
        await self.ensure_table_exists()
        
        # Start background tasks
        self.running = True
        self.collection_task = asyncio.create_task(self._collect_metrics_loop())
        self.flush_task = asyncio.create_task(self._flush_metrics_loop())
        
        logger.info("Metrics service started")
    
    async def stop(self):
        """Stop the metrics service."""
        if not self.running:
            return
        
        # Stop background tasks
        self.running = False
        
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
            self.collection_task = None
        
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
            self.flush_task = None
        
        # Flush any remaining metrics
        await self._flush_metrics()
        
        logger.info("Metrics service stopped")
    
    async def _collect_metrics_loop(self):
        """
        Metrics collection loop.
        
        This method runs in the background and collects metrics at a regular interval.
        """
        try:
            while self.running:
                # Collect metrics
                await self._collect_metrics()
                
                # Wait for the next collection interval
                await asyncio.sleep(METRICS_COLLECTION_INTERVAL)
        
        except asyncio.CancelledError:
            logger.info("Metrics collection task cancelled")
            raise
        
        except Exception as e:
            logger.error(f"Error in metrics collection loop: {e}")
            if self.running:
                # Restart the collection task
                self.collection_task = asyncio.create_task(self._collect_metrics_loop())
    
    async def _flush_metrics_loop(self):
        """
        Metrics flush loop.
        
        This method runs in the background and flushes metrics to DynamoDB at a regular interval.
        """
        try:
            while self.running:
                # Wait for the next flush interval
                await asyncio.sleep(METRICS_FLUSH_INTERVAL)
                
                # Flush metrics
                await self._flush_metrics()
        
        except asyncio.CancelledError:
            logger.info("Metrics flush task cancelled")
            raise
        
        except Exception as e:
            logger.error(f"Error in metrics flush loop: {e}")
            if self.running:
                # Restart the flush task
                self.flush_task = asyncio.create_task(self._flush_metrics_loop())
    
    async def _collect_metrics(self):
        """
        Collect current metrics.
        
        This method collects metrics from various sources and updates the in-memory metrics.
        """
        try:
            # Get active clients count from WebSocket connections
            from api.routes.websocket_routes import connected_clients
            
            # Update active tenants
            self.active_tenants = set(connected_clients.keys())
            
            # Update active agents and channels
            for tenant_id, agents in connected_clients.items():
                # Initialize if necessary
                if tenant_id not in self.active_agents:
                    self.active_agents[tenant_id] = set()
                if tenant_id not in self.active_channels:
                    self.active_channels[tenant_id] = set()
                
                # Update active agents
                self.active_agents[tenant_id] = set(agents.keys())
                
                # Update active channels
                active_channels = set()
                for agent_id, channels in agents.items():
                    active_channels.update(channels.keys())
                self.active_channels[tenant_id] = active_channels
            
            # Update metrics
            for tenant_id in self.active_tenants:
                # Initialize if necessary
                if tenant_id not in self.metrics:
                    self.metrics[tenant_id] = {}
                
                # Get tenant metrics
                tenant_metrics = self.metrics[tenant_id]
                
                # Initialize categories if necessary
                if "tenants" not in tenant_metrics:
                    tenant_metrics["tenants"] = {"active": 0}
                if "agents" not in tenant_metrics:
                    tenant_metrics["agents"] = {"active": 0}
                if "channels" not in tenant_metrics:
                    tenant_metrics["channels"] = {"active": 0}
                
                # Update metrics
                tenant_metrics["tenants"]["active"] = 1  # If the tenant is in active_tenants, it's active
                tenant_metrics["agents"]["active"] = len(self.active_agents.get(tenant_id, set()))
                tenant_metrics["channels"]["active"] = len(self.active_channels.get(tenant_id, set()))
            
            # Get NATS message stats
            from nats import nats_manager
            
            stats = await nats_manager.get_stats()
            if stats:
                for tenant_id in self.active_tenants:
                    # Initialize if necessary
                    if tenant_id not in self.metrics:
                        self.metrics[tenant_id] = {}
                    
                    # Get tenant metrics
                    tenant_metrics = self.metrics[tenant_id]
                    
                    # Initialize message metrics if necessary
                    if "messages" not in tenant_metrics:
                        tenant_metrics["messages"] = {"in": 0, "out": 0}
                    
                    # Update message metrics (use tenant's subjects)
                    tenant_subjects = f"tenant.{tenant_id}."
                    
                    # Get messages for this tenant
                    in_count = stats.get(f"in_msgs_{tenant_subjects}", 0)
                    out_count = stats.get(f"out_msgs_{tenant_subjects}", 0)
                    
                    # Update message metrics
                    tenant_metrics["messages"]["in"] += in_count
                    tenant_metrics["messages"]["out"] += out_count
            
            # Get system metrics (CPU, memory, etc.)
            import psutil
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage('/').percent
            
            # Add system metrics to a special "system" tenant
            if "system" not in self.metrics:
                self.metrics["system"] = {}
            
            # Initialize system metrics if necessary
            if "resources" not in self.metrics["system"]:
                self.metrics["system"]["resources"] = {"cpu": 0, "memory": 0, "disk": 0}
            
            # Update system metrics
            self.metrics["system"]["resources"]["cpu"] = cpu_percent
            self.metrics["system"]["resources"]["memory"] = memory_percent
            self.metrics["system"]["resources"]["disk"] = disk_percent
        
        except ImportError:
            # psutil may not be available
            logger.warning("psutil not available, system metrics will not be collected")
        
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def _flush_metrics(self):
        """
        Flush metrics to DynamoDB.
        
        This method flushes the in-memory metrics to DynamoDB for persistence.
        """
        try:
            # Get the current date in ISO format (YYYY-MM-DD)
            today = date.today().isoformat()
            
            # Get the current timestamp
            now = datetime.utcnow().isoformat()
            
            # For each tenant
            for tenant_id, tenant_metrics in self.metrics.items():
                # Skip the system tenant
                if tenant_id == "system":
                    continue
                
                # Create a metrics object
                metrics = {
                    "tenant_id": tenant_id,
                    "date": today,
                    "timestamp": now
                }
                
                # Add metrics
                for category, category_metrics in tenant_metrics.items():
                    metrics[category] = category_metrics
                
                # Store in DynamoDB
                try:
                    await dynamodb.put_item(
                        table_name=METRICS_TABLE_NAME,
                        item=metrics
                    )
                except Exception as e:
                    logger.error(f"Error storing metrics for tenant {tenant_id}: {e}")
            
            # Store system metrics
            if "system" in self.metrics:
                system_metrics = {
                    "tenant_id": "system",
                    "date": today,
                    "timestamp": now,
                    "resources": self.metrics["system"].get("resources", {})
                }
                
                try:
                    await dynamodb.put_item(
                        table_name=METRICS_TABLE_NAME,
                        item=system_metrics
                    )
                except Exception as e:
                    logger.error(f"Error storing system metrics: {e}")
            
            # Clear metrics
            self.metrics = {}
        
        except Exception as e:
            logger.error(f"Error flushing metrics: {e}")
    
    def increment_metric(self, tenant_id: str, category: str, metric: str, value: int = 1):
        """
        Increment a metric.
        
        Args:
            tenant_id: Tenant ID
            category: Metric category (e.g., "messages", "agents")
            metric: Metric name (e.g., "in", "out", "count")
            value: Value to increment by (default: 1)
        """
        try:
            # Initialize if necessary
            if tenant_id not in self.metrics:
                self.metrics[tenant_id] = {}
            if category not in self.metrics[tenant_id]:
                self.metrics[tenant_id][category] = {}
            if metric not in self.metrics[tenant_id][category]:
                self.metrics[tenant_id][category][metric] = 0
            
            # Increment metric
            self.metrics[tenant_id][category][metric] += value
        
        except Exception as e:
            logger.error(f"Error incrementing metric: {e}")
    
    def set_metric(self, tenant_id: str, category: str, metric: str, value: int):
        """
        Set a metric.
        
        Args:
            tenant_id: Tenant ID
            category: Metric category (e.g., "messages", "agents")
            metric: Metric name (e.g., "in", "out", "count")
            value: Value to set
        """
        try:
            # Initialize if necessary
            if tenant_id not in self.metrics:
                self.metrics[tenant_id] = {}
            if category not in self.metrics[tenant_id]:
                self.metrics[tenant_id][category] = {}
            
            # Set metric
            self.metrics[tenant_id][category][metric] = value
        
        except Exception as e:
            logger.error(f"Error setting metric: {e}")
    
    async def get_metrics(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get metrics for a tenant.
        
        Args:
            tenant_id: Tenant ID
            start_date: Start date (ISO format: YYYY-MM-DD)
            end_date: End date (ISO format: YYYY-MM-DD)
            
        Returns:
            List of metrics objects
        """
        try:
            # Set defaults if not provided
            if not end_date:
                end_date = date.today().isoformat()
            if not start_date:
                # Default to 7 days ago
                start_date = (date.today() - timedelta(days=6)).isoformat()
            
            # Query DynamoDB
            filter_expression = "tenant_id = :tenant_id AND #date BETWEEN :start_date AND :end_date"
            expression_values = {
                ":tenant_id": tenant_id,
                ":start_date": start_date,
                ":end_date": end_date
            }
            expression_names = {
                "#date": "date"
            }
            
            result = await dynamodb.query(
                table_name=METRICS_TABLE_NAME,
                key_condition_expression=filter_expression,
                expression_attribute_values=expression_values,
                expression_attribute_names=expression_names
            )
            
            return result["items"]
        
        except Exception as e:
            logger.error(f"Error getting metrics for tenant {tenant_id}: {e}")
            return []
    
    async def get_usage_totals(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> UsageTotals:
        """
        Get usage totals for a tenant.
        
        Args:
            tenant_id: Tenant ID
            start_date: Start date (ISO format: YYYY-MM-DD)
            end_date: End date (ISO format: YYYY-MM-DD)
            
        Returns:
            UsageTotals object
        """
        try:
            # Get metrics
            metrics = await self.get_metrics(tenant_id, start_date, end_date)
            
            # Calculate totals
            agents_total = 0
            active_agents_total = 0
            channels_total = 0
            active_channels_total = 0
            messages_in_total = 0
            messages_out_total = 0
            
            for metric in metrics:
                # Agents
                if "agents" in metric:
                    if "count" in metric["agents"]:
                        agents_total = max(agents_total, metric["agents"]["count"])
                    if "active" in metric["agents"]:
                        active_agents_total = max(active_agents_total, metric["agents"]["active"])
                
                # Channels
                if "channels" in metric:
                    if "count" in metric["channels"]:
                        channels_total = max(channels_total, metric["channels"]["count"])
                    if "active" in metric["channels"]:
                        active_channels_total = max(active_channels_total, metric["channels"]["active"])
                
                # Messages
                if "messages" in metric:
                    if "in" in metric["messages"]:
                        messages_in_total += metric["messages"]["in"]
                    if "out" in metric["messages"]:
                        messages_out_total += metric["messages"]["out"]
            
            # Create usage totals
            return UsageTotals(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                agents_total=agents_total,
                active_agents_total=active_agents_total,
                channels_total=channels_total,
                active_channels_total=active_channels_total,
                messages_in_total=messages_in_total,
                messages_out_total=messages_out_total,
                timestamp=datetime.utcnow().isoformat()
            )
        
        except Exception as e:
            logger.error(f"Error getting usage totals for tenant {tenant_id}: {e}")
            
            # Return empty usage totals on error
            return UsageTotals(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                agents_total=0,
                active_agents_total=0,
                channels_total=0,
                active_channels_total=0,
                messages_in_total=0,
                messages_out_total=0,
                timestamp=datetime.utcnow().isoformat()
            )


# Create a singleton instance
metrics_service = MetricsService()