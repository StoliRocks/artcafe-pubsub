import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import uuid
import asyncio
import boto3
from botocore.exceptions import ClientError

from models.notification import (
    Notification, NotificationCreate, NotificationUpdate,
    NotificationType, NotificationPriority, NotificationStatus,
    NotificationPreferences
)
from api.db import dynamodb
from config.settings import settings
from api.websocket import send_to_user
from api.services.profile_service import profile_service

logger = logging.getLogger(__name__)

# Table names
NOTIFICATION_TABLE = "artcafe-notifications"
NOTIFICATION_PREFS_TABLE = "artcafe-notification-preferences"

# SNS client for email notifications
sns_client = boto3.client('sns', region_name=settings.AWS_REGION)


class NotificationService:
    """Service for managing notifications"""
    
    async def create_notification(
        self,
        notification_data: NotificationCreate
    ) -> Notification:
        """
        Create a new notification
        
        Args:
            notification_data: Notification data
            
        Returns:
            Created notification
        """
        try:
            # Create notification
            notification = Notification(
                user_id=notification_data.user_id,
                notification_id=str(uuid.uuid4()),
                type=notification_data.type,
                priority=notification_data.priority,
                title=notification_data.title,
                message=notification_data.message,
                tenant_id=notification_data.tenant_id,
                agent_id=notification_data.agent_id,
                resource_id=notification_data.resource_id,
                resource_type=notification_data.resource_type,
                action_url=notification_data.action_url,
                action_label=notification_data.action_label,
                actions=notification_data.actions or [],
                metadata=notification_data.metadata or {},
                created_at=datetime.utcnow()
            )
            
            # Save to DynamoDB
            await dynamodb.put_item(
                table_name=NOTIFICATION_TABLE,
                item=notification.dict()
            )
            
            # Get user preferences
            prefs = await self.get_user_preferences(notification_data.user_id)
            
            # Send real-time notification via WebSocket
            await self._send_realtime_notification(notification)
            
            # Send email if enabled
            if notification_data.send_email and prefs.email_enabled:
                asyncio.create_task(self._send_email_notification(notification, prefs))
            
            # Send push if enabled (future implementation)
            if notification_data.send_push and prefs.push_enabled:
                asyncio.create_task(self._send_push_notification(notification, prefs))
            
            logger.info(f"Created notification {notification.notification_id} for user {notification.user_id}")
            return notification
            
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            raise
    
    async def get_notifications(
        self,
        user_id: str,
        limit: int = 50,
        status: Optional[NotificationStatus] = None,
        notification_type: Optional[NotificationType] = None,
        start_date: Optional[datetime] = None
    ) -> List[Notification]:
        """
        Get notifications for a user
        
        Args:
            user_id: User ID
            limit: Maximum number of notifications
            status: Filter by status
            notification_type: Filter by type
            start_date: Filter by date
            
        Returns:
            List of notifications
        """
        try:
            # Build query
            key_condition = "user_id = :user_id"
            expression_values = {":user_id": user_id}
            
            if start_date:
                start_key = start_date.isoformat()
                key_condition += " AND timestamp_notification_id >= :start"
                expression_values[":start"] = start_key
            
            # Add filters
            filter_expressions = []
            if status:
                filter_expressions.append("read_status = :status")
                expression_values[":status"] = status
            
            if notification_type:
                filter_expressions.append("#type = :type")
                expression_values[":type"] = notification_type
            
            # Query DynamoDB
            query_params = {
                "table_name": NOTIFICATION_TABLE,
                "key_condition_expression": key_condition,
                "expression_attribute_values": expression_values,
                "scan_index_forward": False,  # Most recent first
                "limit": limit
            }
            
            if filter_expressions:
                query_params["filter_expression"] = " AND ".join(filter_expressions)
                if notification_type:
                    query_params["expression_attribute_names"] = {"#type": "type"}
            
            result = await dynamodb.query(**query_params)
            
            # Convert to Notification objects
            notifications = [Notification(**item) for item in result.get("items", [])]
            return notifications
            
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []
    
    async def mark_as_read(
        self,
        user_id: str,
        notification_id: str
    ) -> Optional[Notification]:
        """
        Mark notification as read
        
        Args:
            user_id: User ID
            notification_id: Notification ID
            
        Returns:
            Updated notification
        """
        try:
            # Get notification first to get the sort key
            notifications = await self.get_notifications(user_id, limit=100)
            notification = next((n for n in notifications if n.notification_id == notification_id), None)
            
            if not notification:
                return None
            
            # Update notification
            updates = {
                "read_status": NotificationStatus.READ,
                "read_at": datetime.utcnow()
            }
            
            await dynamodb.update_item(
                table_name=NOTIFICATION_TABLE,
                key={
                    "user_id": user_id,
                    "timestamp_notification_id": notification.timestamp_notification_id
                },
                updates=updates
            )
            
            # Update local object
            notification.read_status = NotificationStatus.READ
            notification.read_at = updates["read_at"]
            
            # Send update via WebSocket
            await self._send_notification_update(user_id, notification_id, "read")
            
            return notification
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return None
    
    async def mark_all_as_read(self, user_id: str) -> int:
        """
        Mark all notifications as read for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Number of notifications marked as read
        """
        try:
            # Get unread notifications
            notifications = await self.get_notifications(
                user_id=user_id,
                status=NotificationStatus.UNREAD,
                limit=1000
            )
            
            # Update each notification
            count = 0
            for notification in notifications:
                await self.mark_as_read(user_id, notification.notification_id)
                count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"Error marking all as read: {e}")
            return 0
    
    async def delete_notification(
        self,
        user_id: str,
        notification_id: str
    ) -> bool:
        """
        Delete a notification
        
        Args:
            user_id: User ID
            notification_id: Notification ID
            
        Returns:
            True if deleted
        """
        try:
            # Get notification to find sort key
            notifications = await self.get_notifications(user_id, limit=100)
            notification = next((n for n in notifications if n.notification_id == notification_id), None)
            
            if not notification:
                return False
            
            # Delete from DynamoDB
            await dynamodb.delete_item(
                table_name=NOTIFICATION_TABLE,
                key={
                    "user_id": user_id,
                    "timestamp_notification_id": notification.timestamp_notification_id
                }
            )
            
            # Send update via WebSocket
            await self._send_notification_update(user_id, notification_id, "deleted")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return False
    
    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications"""
        notifications = await self.get_notifications(
            user_id=user_id,
            status=NotificationStatus.UNREAD,
            limit=1000
        )
        return len(notifications)
    
    # Preference management
    
    async def get_user_preferences(self, user_id: str) -> NotificationPreferences:
        """Get user notification preferences"""
        try:
            result = await dynamodb.get_item(
                table_name=NOTIFICATION_PREFS_TABLE,
                key={"user_id": user_id}
            )
            
            if result:
                return NotificationPreferences(**result)
            
            # Return defaults
            return NotificationPreferences(user_id=user_id)
            
        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            return NotificationPreferences(user_id=user_id)
    
    async def update_user_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> NotificationPreferences:
        """Update user notification preferences"""
        try:
            # Get current preferences
            current = await self.get_user_preferences(user_id)
            
            # Update with new values
            for key, value in preferences.items():
                if hasattr(current, key):
                    setattr(current, key, value)
            
            # Save to DynamoDB
            await dynamodb.put_item(
                table_name=NOTIFICATION_PREFS_TABLE,
                item=current.dict()
            )
            
            return current
            
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            raise
    
    # Private helper methods
    
    async def _send_realtime_notification(self, notification: Notification):
        """Send notification via WebSocket"""
        try:
            await send_to_user(
                user_id=notification.user_id,
                event_type="notification.new",
                data={
                    "notification": notification.dict(),
                    "unread_count": await self.get_unread_count(notification.user_id)
                }
            )
        except Exception as e:
            logger.error(f"Error sending realtime notification: {e}")
    
    async def _send_notification_update(self, user_id: str, notification_id: str, action: str):
        """Send notification update via WebSocket"""
        try:
            await send_to_user(
                user_id=user_id,
                event_type="notification.update",
                data={
                    "notification_id": notification_id,
                    "action": action,
                    "unread_count": await self.get_unread_count(user_id)
                }
            )
        except Exception as e:
            logger.error(f"Error sending notification update: {e}")
    
    async def _send_email_notification(self, notification: Notification, prefs: NotificationPreferences):
        """Send email notification via AWS SNS"""
        try:
            # Check if this type is enabled for email
            type_category = notification.type.value.split('.')[0]
            if not prefs.email_types.get(type_category, True):
                return
            
            # Get user profile for email
            profile = await profile_service.get_user_profile(notification.user_id)
            if not profile or not profile.email:
                return
            
            # Create email content
            subject = f"[ArtCafe.ai] {notification.title}"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #0284c7;">{notification.title}</h2>
                    <p>{notification.message}</p>
                    
                    {f'<a href="{notification.action_url}" style="display: inline-block; padding: 10px 20px; background-color: #0284c7; color: white; text-decoration: none; border-radius: 5px; margin-top: 10px;">{notification.action_label or "View Details"}</a>' if notification.action_url else ''}
                    
                    <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
                    <p style="font-size: 12px; color: #666;">
                        You received this email because you have notifications enabled for your ArtCafe.ai account.
                        <a href="https://www.artcafe.ai/dashboard/settings">Manage preferences</a>
                    </p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            {notification.title}
            
            {notification.message}
            
            {f'View details: {notification.action_url}' if notification.action_url else ''}
            
            ---
            You received this email because you have notifications enabled for your ArtCafe.ai account.
            Manage preferences: https://www.artcafe.ai/dashboard/settings
            """
            
            # Send via SNS
            response = await asyncio.to_thread(
                sns_client.publish,
                TopicArn=settings.SNS_NOTIFICATION_TOPIC_ARN,
                Subject=subject,
                Message=text_body,
                MessageAttributes={
                    'email': {'DataType': 'String', 'StringValue': profile.email},
                    'html': {'DataType': 'String', 'StringValue': html_body}
                }
            )
            
            # Update notification
            await dynamodb.update_item(
                table_name=NOTIFICATION_TABLE,
                key={
                    "user_id": notification.user_id,
                    "timestamp_notification_id": notification.timestamp_notification_id
                },
                updates={
                    "email_sent": True,
                    "email_sent_at": datetime.utcnow()
                }
            )
            
            logger.info(f"Email sent for notification {notification.notification_id}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
    
    async def _send_push_notification(self, notification: Notification, prefs: NotificationPreferences):
        """Send push notification (future implementation)"""
        # TODO: Implement push notifications via FCM or similar
        pass


# Create singleton instance
notification_service = NotificationService()