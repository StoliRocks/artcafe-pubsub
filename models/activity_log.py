from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum

from .base import BaseSchema


class ActivityType(str, Enum):
    """Activity types"""
    # Agent activities
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"
    AGENT_CONNECTED = "agent.connected"
    AGENT_DISCONNECTED = "agent.disconnected"
    AGENT_ERROR = "agent.error"
    
    # Channel activities
    CHANNEL_CREATED = "channel.created"
    CHANNEL_UPDATED = "channel.updated"
    CHANNEL_DELETED = "channel.deleted"
    CHANNEL_SUBSCRIBED = "channel.subscribed"
    CHANNEL_UNSUBSCRIBED = "channel.unsubscribed"
    
    # Message activities
    MESSAGE_PUBLISHED = "message.published"
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_PROCESSED = "message.processed"
    MESSAGE_FAILED = "message.failed"
    
    # System activities
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_INFO = "system.info"
    
    # Billing activities
    BILLING_SUBSCRIPTION_CREATED = "billing.subscription_created"
    BILLING_SUBSCRIPTION_UPDATED = "billing.subscription_updated"
    BILLING_SUBSCRIPTION_CANCELLED = "billing.subscription_cancelled"
    BILLING_PAYMENT_SUCCEEDED = "billing.payment_succeeded"
    BILLING_PAYMENT_FAILED = "billing.payment_failed"
    BILLING_USAGE_ALERT = "billing.usage_alert"
    
    # User activities
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_INVITED = "user.invited"
    USER_REMOVED = "user.removed"


class ActivityStatus(str, Enum):
    """Activity status"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ActivityLog(BaseSchema):
    """Activity log model"""
    tenant_id: str
    activity_id: str
    timestamp_activity_id: str  # Composite sort key: timestamp#activity_id
    
    # Activity details
    activity_type: ActivityType
    status: ActivityStatus
    action: str  # Human-readable action description
    message: str  # Detailed message
    
    # Related entities
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    channel_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    
    # Additional context
    metadata: Optional[Dict[str, Any]] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # TTL for auto-deletion (30 days)
    ttl: Optional[int] = None
    
    @validator('timestamp_activity_id', pre=True, always=True)
    def set_timestamp_activity_id(cls, v, values):
        """Set composite sort key"""
        if v:
            return v
        
        if 'created_at' in values and 'activity_id' in values:
            timestamp = values['created_at'].isoformat()
            return f"{timestamp}#{values['activity_id']}"
        return v
    
    @validator('ttl', pre=True, always=True)
    def set_ttl(cls, v, values):
        """Set TTL to 30 days from creation"""
        if v:
            return v
        
        if 'created_at' in values:
            # 30 days in seconds
            return int(values['created_at'].timestamp()) + (30 * 24 * 60 * 60)
        return int(datetime.utcnow().timestamp()) + (30 * 24 * 60 * 60)


class ActivityLogCreate(BaseModel):
    """Activity log creation model"""
    activity_type: ActivityType
    status: ActivityStatus
    action: str
    message: str
    
    # Optional fields
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    channel_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ActivitySummary(BaseModel):
    """Activity summary for dashboard"""
    total_activities: int = 0
    activities_by_type: Dict[str, int] = {}
    activities_by_status: Dict[str, int] = {}
    recent_activities: List[ActivityLog] = []
    
    # Time-based summaries
    activities_last_hour: int = 0
    activities_last_24h: int = 0
    activities_last_7d: int = 0
    
    # Key metrics
    error_count: int = 0
    warning_count: int = 0
    active_agents: int = 0
    messages_processed: int = 0