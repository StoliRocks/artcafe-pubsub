"""
Subject model for ArtCafe platform
Replaces the old channel model, aligned with NATS terminology
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from ulid import ULID


class RetentionPolicy(BaseModel):
    """JetStream retention policy"""
    age: int = Field(default=86400, description="Max age in seconds")
    messages: int = Field(default=10000, description="Max number of messages")
    bytes: int = Field(default=1048576, description="Max storage in bytes")


class Subject(BaseModel):
    """Subject configuration (formerly channel)"""
    
    subject_id: str = Field(default_factory=lambda: str(ULID()), description="Subject ID")
    account_id: str = Field(..., description="Parent account ID")
    name: str = Field(..., description="Human-readable name")
    pattern: str = Field(..., description="NATS subject pattern (e.g., events.security.*)")
    description: str = Field(default="", description="Subject description")
    
    # JetStream configuration
    stream: str = Field(..., description="JetStream stream name")
    retention: RetentionPolicy = Field(
        default_factory=RetentionPolicy,
        description="Message retention policy"
    )
    
    # Status and metadata
    status: str = Field(default="active", description="Subject status")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation timestamp"
    )
    
    # Additional configuration
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": "01HXYZ123456789ABCDEFGHIJ",
                "account_id": "01HXYZ000000000000000000",
                "name": "Security Events",
                "pattern": "cyberforge.events.security.*",
                "description": "Security event notifications",
                "stream": "SECURITY_EVENTS",
                "retention": {
                    "age": 604800,  # 7 days
                    "messages": 100000,
                    "bytes": 104857600  # 100MB
                },
                "status": "active"
            }
        }
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = self.model_dump(exclude_none=True)
        # Flatten retention for DynamoDB
        item['retention'] = {
            'age': item['retention']['age'],
            'messages': item['retention']['messages'],
            'bytes': item['retention']['bytes']
        }
        return item
    
    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "Subject":
        """Create from DynamoDB item"""
        # Ensure retention is properly structured
        if 'retention' in item and isinstance(item['retention'], dict):
            item['retention'] = RetentionPolicy(**item['retention'])
        return cls(**item)
    
    def to_jetstream_config(self) -> Dict[str, Any]:
        """Generate JetStream stream configuration"""
        return {
            "name": self.stream,
            "subjects": [self.pattern],
            "retention": "limits",
            "max_age": self.retention.age * 1_000_000_000,  # Convert to nanoseconds
            "max_msgs": self.retention.messages,
            "max_bytes": self.retention.bytes,
            "storage": "file",
            "replicas": 1,
            "discard": "old"
        }
    
    def validate_pattern(self) -> bool:
        """Validate NATS subject pattern"""
        # Must start with account ID
        if not self.pattern.startswith(self.account_id):
            return False
        
        # Check for valid characters
        valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_*>')
        return all(c in valid_chars for c in self.pattern)