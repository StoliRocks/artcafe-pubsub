from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum

from .base import BaseSchema


class NotificationType(str, Enum):
    """Notification types"""
    # System notifications
    SYSTEM_UPDATE = "system.update"
    SYSTEM_MAINTENANCE = "system.maintenance"
    SYSTEM_ALERT = "system.alert"
    
    # Agent notifications
    AGENT_OFFLINE = "agent.offline"
    AGENT_ERROR = "agent.error"
    AGENT_RESOURCE_HIGH = "agent.resource_high"
    
    # Usage notifications
    USAGE_LIMIT_WARNING = "usage.limit_warning"
    USAGE_LIMIT_REACHED = "usage.limit_reached"
    USAGE_QUOTA_RESET = "usage.quota_reset"
    
    # Billing notifications
    PAYMENT_DUE = "billing.payment_due"
    PAYMENT_FAILED = "billing.payment_failed"
    PAYMENT_SUCCEEDED = "billing.payment_succeeded"
    SUBSCRIPTION_EXPIRING = "billing.subscription_expiring"
    
    # Security notifications
    SECURITY_LOGIN = "security.login"
    SECURITY_API_KEY_CREATED = "security.api_key_created"
    SECURITY_SUSPICIOUS_ACTIVITY = "security.suspicious_activity"
    
    # Collaboration notifications
    MEMBER_INVITED = "collab.member_invited"
    MEMBER_JOINED = "collab.member_joined"
    MEMBER_REMOVED = "collab.member_removed"


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, Enum):
    """Notification read status"""
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class Notification(BaseSchema):
    """Notification model"""
    user_id: str
    notification_id: str
    timestamp_notification_id: str  # Composite sort key
    
    # Notification details
    type: NotificationType
    priority: NotificationPriority = NotificationPriority.MEDIUM
    title: str
    message: str
    
    # Status
    read_status: NotificationStatus = NotificationStatus.UNREAD
    read_at: Optional[datetime] = None
    
    # Related entities
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    
    # Actions
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    actions: Optional[List[Dict[str, str]]] = []  # Multiple action buttons
    
    # Delivery
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    push_sent: bool = False
    push_sent_at: Optional[datetime] = None
    
    # Additional data
    metadata: Optional[Dict[str, Any]] = {}
    
    # TTL for auto-deletion (90 days)
    ttl: Optional[int] = None
    
    @validator('timestamp_notification_id', pre=True, always=True)
    def set_timestamp_notification_id(cls, v, values):
        """Set composite sort key"""
        if v:
            return v
        
        if 'created_at' in values and 'notification_id' in values:
            timestamp = values['created_at'].isoformat()
            return f"{timestamp}#{values['notification_id']}"
        return v
    
    @validator('ttl', pre=True, always=True)
    def set_ttl(cls, v, values):
        """Set TTL to 90 days from creation"""
        if v:
            return v
        
        if 'created_at' in values:
            # 90 days in seconds
            return int(values['created_at'].timestamp()) + (90 * 24 * 60 * 60)
        return int(datetime.utcnow().timestamp()) + (90 * 24 * 60 * 60)


class NotificationCreate(BaseModel):
    """Notification creation model"""
    user_id: str
    type: NotificationType
    priority: NotificationPriority = NotificationPriority.MEDIUM
    title: str
    message: str
    
    # Optional fields
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    actions: Optional[List[Dict[str, str]]] = []
    
    metadata: Optional[Dict[str, Any]] = {}
    
    # Delivery preferences
    send_email: bool = True
    send_push: bool = False


class NotificationUpdate(BaseModel):
    """Notification update model"""
    read_status: Optional[NotificationStatus] = None
    read_at: Optional[datetime] = None


class NotificationPreferences(BaseModel):
    """User notification preferences"""
    user_id: str
    
    # Email preferences
    email_enabled: bool = True
    email_types: Dict[str, bool] = {
        "system": True,
        "agent": True,
        "usage": True,
        "billing": True,
        "security": True,
        "collab": True
    }
    
    # Push preferences
    push_enabled: bool = False
    push_types: Dict[str, bool] = {
        "system": True,
        "agent": True,
        "usage": False,
        "billing": True,
        "security": True,
        "collab": False
    }
    
    # Digest preferences
    digest_enabled: bool = False
    digest_frequency: str = "daily"  # daily, weekly
    digest_time: str = "09:00"  # UTC time
    
    # Do not disturb
    dnd_enabled: bool = False
    dnd_start: Optional[str] = None  # HH:MM format
    dnd_end: Optional[str] = None    # HH:MM format
    dnd_timezone: str = "UTC"