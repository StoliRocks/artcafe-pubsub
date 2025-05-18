from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field, validator

from .base import BaseSchema


class KeyType(str):
    """SSH key type enum"""
    ACCESS = "access"     # For general access (user login)
    AGENT = "agent"       # For agent authentication
    DEPLOYMENT = "deployment"  # For deployment tasks


class SSHKeyBase(BaseModel):
    """Base SSH key model"""
    name: str
    public_key: str
    key_type: str = KeyType.ACCESS
    agent_id: Optional[str] = None
    fingerprint: Optional[str] = None

    @validator('key_type')
    def validate_key_type(cls, v):
        """Validate key type"""
        allowed_types = [KeyType.ACCESS, KeyType.AGENT, KeyType.DEPLOYMENT]
        if v not in allowed_types:
            raise ValueError(f"Key type must be one of: {', '.join(allowed_types)}")
        return v


class SSHKeyCreate(SSHKeyBase):
    """SSH key creation model"""
    metadata: Optional[Dict] = None


class SSHKey(SSHKeyBase, BaseSchema):
    """SSH key model"""
    key_id: str = Field(..., alias="id")
    tenant_id: str
    status: str = "active"
    last_used: Optional[datetime] = None
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None

    class Config:
        allow_population_by_field_name = True


class SSHKeyResponse(BaseModel):
    """SSH key response model"""
    key: SSHKey
    success: bool = True


class SSHKeysResponse(BaseModel):
    """SSH keys list response model"""
    keys: List[SSHKey]
    next_token: Optional[str] = None