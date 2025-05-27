import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import statistics

from models.agent_metrics import (
    AgentMetrics, AgentMetricsCreate, AgentMetricsSummary,
    MetricsAggregation
)
from api.db import dynamodb
from config.settings import settings
from api.websocket import broadcast_to_tenant

logger = logging.getLogger(__name__)

# Table name
METRICS_TABLE = "artcafe-agent-metrics"


class MetricsService:
    """Service for managing agent metrics"""
    
    async def record_metrics(
        self,
        tenant_id: str,
        metrics_data: AgentMetricsCreate
    ) -> AgentMetrics:
        """
        Record agent metrics
        
        Args:
            tenant_id: Tenant ID
            metrics_data: Metrics data
            
        Returns:
            Created metrics record
        """
        try:
            # Create metrics record
            metrics = AgentMetrics(
                tenant_agent_id=f"{tenant_id}#{metrics_data.agent_id}",
                timestamp=int(datetime.utcnow().timestamp()),
                cpu_usage=metrics_data.cpu_usage,
                memory_usage=metrics_data.memory_usage,
                disk_usage=metrics_data.disk_usage,
                network_in=metrics_data.network_in,
                network_out=metrics_data.network_out,
                tasks_processed=metrics_data.tasks_processed,
                tasks_failed=metrics_data.tasks_failed,
                tasks_queued=metrics_data.tasks_queued,
                error_rate=metrics_data.error_rate,
                response_time=metrics_data.response_time,
                uptime=metrics_data.uptime,
                last_restart=metrics_data.last_restart,
                process_count=metrics_data.process_count,
                thread_count=metrics_data.thread_count,
                open_file_descriptors=metrics_data.open_file_descriptors,
                custom_metrics=metrics_data.custom_metrics or {},
                created_at=datetime.utcnow()
            )
            
            # Save to DynamoDB
            await dynamodb.put_item(
                table_name=METRICS_TABLE,
                item=metrics.dict()
            )
            
            # Broadcast to WebSocket subscribers
            await self._broadcast_metrics(tenant_id, metrics_data.agent_id, metrics)
            
            # Check for alerts
            await self._check_alerts(tenant_id, metrics_data.agent_id, metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error recording metrics: {e}")
            raise
    
    async def get_agent_metrics(
        self,
        tenant_id: str,
        agent_id: str,
        hours: int = 1,
        limit: int = 100
    ) -> List[AgentMetrics]:
        """
        Get metrics for an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            hours: Hours to look back
            limit: Maximum records
            
        Returns:
            List of metrics
        """
        try:
            # Calculate time range
            end_time = int(datetime.utcnow().timestamp())
            start_time = end_time - (hours * 3600)
            
            # Query DynamoDB
            result = await dynamodb.query(
                table_name=METRICS_TABLE,
                key_condition_expression="tenant_agent_id = :id AND #ts BETWEEN :start AND :end",
                expression_attribute_names={
                    "#ts": "timestamp"
                },
                expression_attribute_values={
                    ":id": f"{tenant_id}#{agent_id}",
                    ":start": start_time,
                    ":end": end_time
                },
                scan_index_forward=False,  # Most recent first
                limit=limit
            )
            
            # Convert to AgentMetrics objects
            metrics = [AgentMetrics(**item) for item in result.get("items", [])]
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting agent metrics: {e}")
            return []
    
    async def get_agent_metrics_summary(
        self,
        tenant_id: str,
        agent_id: str,
        hours: int = 24
    ) -> AgentMetricsSummary:
        """
        Get metrics summary for an agent
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            hours: Hours to analyze
            
        Returns:
            Metrics summary
        """
        try:
            # Get metrics data
            metrics = await self.get_agent_metrics(
                tenant_id=tenant_id,
                agent_id=agent_id,
                hours=hours,
                limit=1000
            )
            
            if not metrics:
                return AgentMetricsSummary(
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    data_points=0
                )
            
            # Calculate summary
            summary = AgentMetricsSummary(
                agent_id=agent_id,
                tenant_id=tenant_id,
                current_metrics=metrics[0] if metrics else None,
                data_points=len(metrics),
                start_time=datetime.fromtimestamp(metrics[-1].timestamp),
                end_time=datetime.fromtimestamp(metrics[0].timestamp)
            )
            
            # Calculate averages
            cpu_values = [m.cpu_usage for m in metrics if m.cpu_usage is not None]
            memory_values = [m.memory_usage for m in metrics if m.memory_usage is not None]
            disk_values = [m.disk_usage for m in metrics if m.disk_usage is not None]
            response_times = [m.response_time for m in metrics if m.response_time is not None]
            
            if cpu_values:
                summary.avg_cpu_usage = statistics.mean(cpu_values)
                summary.max_cpu_usage = max(cpu_values)
            
            if memory_values:
                summary.avg_memory_usage = statistics.mean(memory_values)
                summary.max_memory_usage = max(memory_values)
            
            if disk_values:
                summary.avg_disk_usage = statistics.mean(disk_values)
            
            if response_times:
                summary.avg_response_time = statistics.mean(response_times)
                summary.min_response_time = min(response_times)
                summary.max_response_time = max(response_times)
            
            # Calculate totals
            summary.total_tasks_processed = sum(m.tasks_processed or 0 for m in metrics)
            summary.total_tasks_failed = sum(m.tasks_failed or 0 for m in metrics)
            summary.total_network_in = sum(m.network_in or 0 for m in metrics)
            summary.total_network_out = sum(m.network_out or 0 for m in metrics)
            
            # Calculate health score (0-100)
            health_factors = []
            
            # CPU health (lower is better)
            if summary.avg_cpu_usage is not None:
                health_factors.append(100 - min(summary.avg_cpu_usage, 100))
            
            # Memory health (lower is better)
            if summary.avg_memory_usage is not None:
                health_factors.append(100 - min(summary.avg_memory_usage, 100))
            
            # Error rate health (lower is better)
            if summary.total_tasks_processed > 0:
                error_rate = (summary.total_tasks_failed / summary.total_tasks_processed) * 100
                summary.error_percentage = error_rate
                health_factors.append(100 - min(error_rate, 100))
            
            # Availability (based on data points vs expected)
            expected_points = hours * 60  # One per minute
            availability = (len(metrics) / expected_points) * 100
            summary.availability_percentage = min(availability, 100)
            health_factors.append(summary.availability_percentage)
            
            # Calculate overall health score
            if health_factors:
                summary.health_score = statistics.mean(health_factors)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return AgentMetricsSummary(
                agent_id=agent_id,
                tenant_id=tenant_id,
                data_points=0
            )
    
    async def get_tenant_metrics_aggregation(
        self,
        tenant_id: str,
        hours: int = 1
    ) -> MetricsAggregation:
        """
        Get aggregated metrics for all agents in a tenant
        
        Args:
            tenant_id: Tenant ID
            hours: Hours to analyze
            
        Returns:
            Aggregated metrics
        """
        try:
            # Get all agents for tenant
            from api.services.agent_service import agent_service
            agents = await agent_service.list_agents(tenant_id)
            
            aggregation = MetricsAggregation(
                tenant_id=tenant_id,
                total_agents=len(agents),
                period_start=datetime.utcnow() - timedelta(hours=hours),
                period_end=datetime.utcnow()
            )
            
            # Collect metrics for each agent
            for agent in agents:
                summary = await self.get_agent_metrics_summary(
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    hours=hours
                )
                
                if summary.current_metrics:
                    aggregation.active_agents += 1
                    
                    # Add to totals
                    if summary.current_metrics.cpu_usage:
                        aggregation.total_cpu_usage += summary.current_metrics.cpu_usage
                    if summary.current_metrics.memory_usage:
                        aggregation.total_memory_usage += summary.current_metrics.memory_usage
                    if summary.current_metrics.disk_usage:
                        aggregation.total_disk_usage += summary.current_metrics.disk_usage
                    
                    # Health categorization
                    if summary.health_score:
                        if summary.health_score >= 80:
                            aggregation.healthy_agents += 1
                        elif summary.health_score >= 60:
                            aggregation.warning_agents += 1
                        else:
                            aggregation.critical_agents += 1
                
                # Add totals
                aggregation.total_tasks_processed += summary.total_tasks_processed
                aggregation.total_tasks_failed += summary.total_tasks_failed
                aggregation.total_network_in += summary.total_network_in
                aggregation.total_network_out += summary.total_network_out
            
            # Calculate averages
            if aggregation.active_agents > 0:
                aggregation.avg_cpu_per_agent = aggregation.total_cpu_usage / aggregation.active_agents
                aggregation.avg_memory_per_agent = aggregation.total_memory_usage / aggregation.active_agents
            
            return aggregation
            
        except Exception as e:
            logger.error(f"Error getting tenant metrics: {e}")
            return MetricsAggregation(
                tenant_id=tenant_id,
                period_start=datetime.utcnow() - timedelta(hours=hours),
                period_end=datetime.utcnow()
            )
    
    async def _broadcast_metrics(self, tenant_id: str, agent_id: str, metrics: AgentMetrics):
        """Broadcast metrics to WebSocket subscribers"""
        try:
            await broadcast_to_tenant(
                tenant_id=tenant_id,
                event_type=f"agent.{agent_id}.metrics",
                data=metrics.dict()
            )
        except Exception as e:
            logger.error(f"Error broadcasting metrics: {e}")
    
    async def _check_alerts(self, tenant_id: str, agent_id: str, metrics: AgentMetrics):
        """Check metrics for alert conditions"""
        try:
            # Import here to avoid circular dependency
            from api.services.notification_service import notification_service
            from models.notification import NotificationCreate, NotificationType, NotificationPriority
            
            alerts = []
            
            # CPU alert
            if metrics.cpu_usage and metrics.cpu_usage > 90:
                alerts.append({
                    "type": NotificationType.AGENT_RESOURCE_HIGH,
                    "priority": NotificationPriority.HIGH,
                    "title": f"High CPU Usage on Agent {agent_id}",
                    "message": f"CPU usage is at {metrics.cpu_usage:.1f}%"
                })
            
            # Memory alert
            if metrics.memory_usage and metrics.memory_usage > 90:
                alerts.append({
                    "type": NotificationType.AGENT_RESOURCE_HIGH,
                    "priority": NotificationPriority.HIGH,
                    "title": f"High Memory Usage on Agent {agent_id}",
                    "message": f"Memory usage is at {metrics.memory_usage:.1f}%"
                })
            
            # Disk alert
            if metrics.disk_usage and metrics.disk_usage > 85:
                alerts.append({
                    "type": NotificationType.AGENT_RESOURCE_HIGH,
                    "priority": NotificationPriority.MEDIUM,
                    "title": f"High Disk Usage on Agent {agent_id}",
                    "message": f"Disk usage is at {metrics.disk_usage:.1f}%"
                })
            
            # Error rate alert
            if metrics.error_rate and metrics.error_rate > 10:
                alerts.append({
                    "type": NotificationType.AGENT_ERROR,
                    "priority": NotificationPriority.HIGH,
                    "title": f"High Error Rate on Agent {agent_id}",
                    "message": f"Error rate is at {metrics.error_rate:.1f}%"
                })
            
            # Create notifications for alerts
            for alert in alerts:
                # Get tenant admins
                from api.services.user_tenant_service import user_tenant_service
                tenant_users = await user_tenant_service.get_tenant_users(tenant_id)
                
                for user in tenant_users:
                    if user.is_admin:
                        notification_data = NotificationCreate(
                            user_id=user.user_id,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            resource_id=agent_id,
                            resource_type="agent",
                            action_url=f"/dashboard/agents/{agent_id}",
                            action_label="View Agent",
                            **alert
                        )
                        
                        await notification_service.create_notification(notification_data)
            
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")


# Create singleton instance
metrics_service = MetricsService()