from typing import List, Optional
from pydantic import BaseModel, Field

from .base import BaseSchema


class SSHKeyBase(BaseModel):
    """Base SSH key model"""
    name: str
    public_key: str


class SSHKeyCreate(SSHKeyBase):
    """SSH key creation model"""
    pass


class SSHKey(SSHKeyBase, BaseSchema):
    """SSH key model"""
    key_id: str = Field(..., alias="id")
    tenant_id: str
    status: str = "active"
    
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