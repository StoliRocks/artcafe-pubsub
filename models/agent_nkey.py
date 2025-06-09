"""
Client model for ArtCafe platform
Replaces the old agent model
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from ulid import ULID


class AgentPermissions(BaseModel):
    """Permissions for NATS subjects"""
    publish: List[str] = Field(default_factory=list, description="Subjects client can publish to")
    subscribe: List[str] = Field(default_factory=list, description="Subjects client can subscribe to")


class Agent(BaseModel):
    """Client (formerly agent)"""
    
    agent_id: str = Field(default_factory=lambda: str(ULID()), description="Client ID")
    tenant_id: str = Field(..., description="Parent tenant/organization ID")
    name: str = Field(..., description="Client name")
    nkey_public: str = Field(..., description="Client's public NKey")
    
    # Permissions replacing capabilities
    permissions: AgentPermissions = Field(
        default_factory=AgentPermissions,
        description="NATS subject permissions"
    )
    
    # Status tracking
    status: str = Field(default="offline", description="Client status")
    last_seen: Optional[str] = Field(None, description="Last activity timestamp")
    
    # Timestamps
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation timestamp"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Last update timestamp"
    )
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "01HXYZ123456789ABCDEFGHIJ",
                "tenant_id": "01HXYZ000000000000000000",
                "name": "Security Scanner",
                "nkey_public": "UAQZV3QFXKMS5JPVDWTSYLU4BBSXBN2WBPGWVMQWBPB2XMT2BYFUSER",
                "permissions": {
                    "publish": ["cyberforge.events.*", "cyberforge.alerts.*"],
                    "subscribe": ["cyberforge.commands.*", "cyberforge._sys.*"]
                },
                "status": "online",
                "metadata": {
                    "version": "1.0.0",
                    "type": "scanner"
                }
            }
        }
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        item = self.model_dump(exclude_none=True)
        # Flatten permissions for DynamoDB
        item['permissions'] = {
            'publish': item['permissions']['publish'],
            'subscribe': item['permissions']['subscribe']
        }
        item['updated_at'] = datetime.now(timezone.utc).isoformat()
        return item
    
    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "Agent":
        """Create Agent from DynamoDB item"""
        # Ensure permissions is properly structured
        if 'permissions' in item and isinstance(item['permissions'], dict):
            item['permissions'] = AgentPermissions(**item['permissions'])
        return cls(**item)
    
    def generate_jwt_claims(self) -> Dict[str, Any]:
        """Generate JWT claims for this client"""
        return {
            "sub": self.agent_id,
            "name": self.name,
            "type": "client",
            "tenant": self.tenant_id,
            "nkey": self.nkey_public,
            "permissions": {
                "pub": self.permissions.publish,
                "sub": self.permissions.subscribe
            },
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int(datetime.now(timezone.utc).timestamp()) + 3600  # 1 hour
        }
    
    def update_status(self, status: str) -> None:
        """Update client status and last seen timestamp"""
        self.status = status
        if status == "online":
            self.last_seen = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()