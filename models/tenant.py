from typing import Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr

from .base import BaseSchema


class TenantBase(BaseModel):
    """Base tenant model"""
    name: str
    admin_email: EmailStr
    subscription_tier: str = "basic"  # basic, standard, premium


class TenantCreate(TenantBase):
    """Tenant creation model"""
    metadata: Optional[Dict] = None


class Tenant(TenantBase, BaseSchema):
    """Tenant model"""
    tenant_id: str = Field(..., alias="id")
    metadata: Optional[Dict] = None
    status: str = "active"
    
    class Config:
        allow_population_by_field_name = True


class TenantResponse(BaseModel):
    """Tenant response model"""
    tenant_id: str
    api_key: Optional[str] = None
    admin_token: Optional[str] = None
    success: bool = True