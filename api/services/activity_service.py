import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import uuid

from models.activity_log import (
    ActivityLog, ActivityLogCreate, ActivityType, 
    ActivityStatus, ActivitySummary
)
from api.db import dynamodb
from config.settings import settings
from api.websocket import broadcast_to_tenant

logger = logging.getLogger(__name__)

# Table name for activity logs
ACTIVITY_TABLE = "artcafe-activity-logs"


class ActivityService:
    """Service for managing activity logs"""
    
    async def log_activity(
        self, 
        tenant_id: str,
        activity_data: ActivityLogCreate,
        request_context: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log an activity
        
        Args:
            tenant_id: Tenant ID
            activity_data: Activity data
            request_context: Optional request context (IP, user agent, etc.)
            
        Returns:
            Created activity log
        """
        try:
            # Create activity log
            activity = ActivityLog(
                tenant_id=tenant_id,
                activity_id=str(uuid.uuid4()),
                activity_type=activity_data.activity_type,
                status=activity_data.status,
                action=activity_data.action,
                message=activity_data.message,
                user_id=activity_data.user_id,
                agent_id=activity_data.agent_id,
                channel_id=activity_data.channel_id,
                resource_id=activity_data.resource_id,
                resource_type=activity_data.resource_type,
                metadata=activity_data.metadata or {},
                ip_address=activity_data.ip_address or request_context.get('ip_address') if request_context else None,
                user_agent=activity_data.user_agent or request_context.get('user_agent') if request_context else None,
                created_at=datetime.utcnow()
            )
            
            # Save to DynamoDB
            await dynamodb.put_item(
                table_name=ACTIVITY_TABLE,
                item=activity.dict()
            )
            
            # Broadcast to WebSocket subscribers
            await self._broadcast_activity(tenant_id, activity)
            
            logger.info(f"Logged activity: {activity.activity_type} for tenant {tenant_id}")
            return activity
            
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            raise
    
    async def get_activities(
        self,
        tenant_id: str,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        activity_type: Optional[ActivityType] = None,
        status: Optional[ActivityStatus] = None
    ) -> List[ActivityLog]:
        """
        Get activities for a tenant
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of activities to return
            start_date: Filter by start date
            end_date: Filter by end date
            activity_type: Filter by activity type
            status: Filter by status
            
        Returns:
            List of activities
        """
        try:
            # Build query
            key_condition = "tenant_id = :tenant_id"
            expression_values = {":tenant_id": tenant_id}
            
            if start_date and end_date:
                start_key = start_date.isoformat()
                end_key = end_date.isoformat()
                key_condition += " AND timestamp_activity_id BETWEEN :start AND :end"
                expression_values[":start"] = start_key
                expression_values[":end"] = end_key + "~"  # ~ ensures we get all activities on end date
            
            # Add filters
            filter_expressions = []
            if activity_type:
                filter_expressions.append("activity_type = :activity_type")
                expression_values[":activity_type"] = activity_type
            
            if status:
                filter_expressions.append("#status = :status")
                expression_values[":status"] = status
            
            # Query DynamoDB
            query_params = {
                "table_name": ACTIVITY_TABLE,
                "key_condition_expression": key_condition,
                "expression_attribute_values": expression_values,
                "scan_index_forward": False,  # Most recent first
                "limit": limit
            }
            
            if filter_expressions:
                query_params["filter_expression"] = " AND ".join(filter_expressions)
                if status:
                    query_params["expression_attribute_names"] = {"#status": "status"}
            
            result = await dynamodb.query(**query_params)
            
            # Convert to ActivityLog objects
            activities = [ActivityLog(**item) for item in result.get("items", [])]
            return activities
            
        except Exception as e:
            logger.error(f"Error getting activities: {e}")
            return []
    
    async def get_activity_summary(
        self,
        tenant_id: str,
        hours: int = 24
    ) -> ActivitySummary:
        """
        Get activity summary for dashboard
        
        Args:
            tenant_id: Tenant ID
            hours: Number of hours to look back (default 24)
            
        Returns:
            Activity summary
        """
        try:
            # Calculate time ranges
            now = datetime.utcnow()
            start_24h = now - timedelta(hours=24)
            start_7d = now - timedelta(days=7)
            start_1h = now - timedelta(hours=1)
            
            # Get recent activities
            recent_activities = await self.get_activities(
                tenant_id=tenant_id,
                limit=100,
                start_date=start_24h,
                end_date=now
            )
            
            # Calculate summaries
            summary = ActivitySummary()
            summary.recent_activities = recent_activities[:10]  # Last 10 for display
            
            for activity in recent_activities:
                # Count by type
                activity_type = activity.activity_type.value
                summary.activities_by_type[activity_type] = \
                    summary.activities_by_type.get(activity_type, 0) + 1
                
                # Count by status
                status = activity.status.value
                summary.activities_by_status[status] = \
                    summary.activities_by_status.get(status, 0) + 1
                
                # Time-based counts
                if activity.created_at >= start_1h:
                    summary.activities_last_hour += 1
                if activity.created_at >= start_24h:
                    summary.activities_last_24h += 1
                
                # Error/warning counts
                if activity.status == ActivityStatus.ERROR:
                    summary.error_count += 1
                elif activity.status == ActivityStatus.WARNING:
                    summary.warning_count += 1
                
                # Active agents
                if activity.activity_type == ActivityType.AGENT_CONNECTED:
                    summary.active_agents += 1
                elif activity.activity_type == ActivityType.AGENT_DISCONNECTED:
                    summary.active_agents = max(0, summary.active_agents - 1)
                
                # Messages processed
                if activity.activity_type == ActivityType.MESSAGE_PROCESSED:
                    summary.messages_processed += 1
            
            summary.total_activities = len(recent_activities)
            
            # Get 7-day count (separate query for efficiency)
            activities_7d = await self.get_activities(
                tenant_id=tenant_id,
                limit=1000,
                start_date=start_7d,
                end_date=now
            )
            summary.activities_last_7d = len(activities_7d)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting activity summary: {e}")
            return ActivitySummary()
    
    async def _broadcast_activity(self, tenant_id: str, activity: ActivityLog):
        """Broadcast activity to WebSocket subscribers"""
        try:
            await broadcast_to_tenant(
                tenant_id=tenant_id,
                event_type="activity.new",
                data={
                    "activity": activity.dict()
                }
            )
        except Exception as e:
            logger.error(f"Error broadcasting activity: {e}")
    
    # Helper methods for common activity logging
    
    async def log_agent_activity(
        self,
        tenant_id: str,
        agent_id: str,
        activity_type: ActivityType,
        message: str,
        status: ActivityStatus = ActivityStatus.INFO,
        metadata: Optional[Dict] = None
    ):
        """Log agent-related activity"""
        action_map = {
            ActivityType.AGENT_CREATED: "Agent created",
            ActivityType.AGENT_UPDATED: "Agent updated",
            ActivityType.AGENT_DELETED: "Agent deleted",
            ActivityType.AGENT_CONNECTED: "Agent connected",
            ActivityType.AGENT_DISCONNECTED: "Agent disconnected",
            ActivityType.AGENT_ERROR: "Agent error"
        }
        
        activity_data = ActivityLogCreate(
            activity_type=activity_type,
            status=status,
            action=action_map.get(activity_type, "Agent activity"),
            message=message,
            agent_id=agent_id,
            resource_id=agent_id,
            resource_type="agent",
            metadata=metadata or {}
        )
        
        return await self.log_activity(tenant_id, activity_data)
    
    async def log_channel_activity(
        self,
        tenant_id: str,
        channel_id: str,
        activity_type: ActivityType,
        message: str,
        agent_id: Optional[str] = None,
        status: ActivityStatus = ActivityStatus.INFO,
        metadata: Optional[Dict] = None
    ):
        """Log channel-related activity"""
        action_map = {
            ActivityType.CHANNEL_CREATED: "Channel created",
            ActivityType.CHANNEL_UPDATED: "Channel updated",
            ActivityType.CHANNEL_DELETED: "Channel deleted",
            ActivityType.CHANNEL_SUBSCRIBED: "Channel subscription",
            ActivityType.CHANNEL_UNSUBSCRIBED: "Channel unsubscription"
        }
        
        activity_data = ActivityLogCreate(
            activity_type=activity_type,
            status=status,
            action=action_map.get(activity_type, "Channel activity"),
            message=message,
            channel_id=channel_id,
            agent_id=agent_id,
            resource_id=channel_id,
            resource_type="channel",
            metadata=metadata or {}
        )
        
        return await self.log_activity(tenant_id, activity_data)
    
    async def log_message_activity(
        self,
        tenant_id: str,
        channel_id: str,
        activity_type: ActivityType,
        message: str,
        agent_id: Optional[str] = None,
        status: ActivityStatus = ActivityStatus.INFO,
        metadata: Optional[Dict] = None
    ):
        """Log message-related activity"""
        action_map = {
            ActivityType.MESSAGE_PUBLISHED: "Message published",
            ActivityType.MESSAGE_RECEIVED: "Message received",
            ActivityType.MESSAGE_PROCESSED: "Message processed",
            ActivityType.MESSAGE_FAILED: "Message failed"
        }
        
        activity_data = ActivityLogCreate(
            activity_type=activity_type,
            status=status,
            action=action_map.get(activity_type, "Message activity"),
            message=message,
            channel_id=channel_id,
            agent_id=agent_id,
            metadata=metadata or {}
        )
        
        return await self.log_activity(tenant_id, activity_data)


# Create singleton instance
activity_service = ActivityService()