from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class UserRole(str):
    """User role within a tenant"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserTenantBase(BaseModel):
    """Base user-tenant mapping model"""
    user_id: str
    tenant_id: str
    role: str = UserRole.MEMBER
    
    @property
    def is_owner(self) -> bool:
        """Check if user is owner of the tenant"""
        return self.role == UserRole.OWNER
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        return self.role in [UserRole.OWNER, UserRole.ADMIN]
    
    @property
    def can_manage_members(self) -> bool:
        """Check if user can manage tenant members"""
        return self.role in [UserRole.OWNER, UserRole.ADMIN]
    
    @property
    def can_view(self) -> bool:
        """Check if user can view tenant resources"""
        return True  # All roles can view


class UserTenantCreate(UserTenantBase):
    """User-tenant mapping creation model"""
    invited_by: Optional[str] = None
    invitation_email: Optional[str] = None


class UserTenant(UserTenantBase, BaseSchema):
    """User-tenant mapping model"""
    user_email: Optional[str] = None  # Denormalized for easier queries
    tenant_name: Optional[str] = None  # Denormalized for easier queries
    invited_by: Optional[str] = None
    invitation_date: Optional[datetime] = None
    accepted_date: Optional[datetime] = None
    active: int = Field(default=1)  # 1 for active, 0 for inactive
    
    def dict(self, *args, **kwargs):
        """Override dict method to convert boolean values to numeric"""
        data = super().dict(*args, **kwargs)
        # Convert boolean values to numeric for DynamoDB
        if 'active' in data and isinstance(data['active'], bool):
            data['active'] = 1 if data['active'] else 0
        return data
    
    
class UserTenantUpdate(BaseModel):
    """User-tenant mapping update model"""
    role: Optional[str] = None
    active: Optional[int] = None  # 1 for active, 0 for inactive


class UserWithTenants(BaseModel):
    """User with their tenant associations"""
    user_id: str
    email: str
    tenants: List[UserTenant] = []
    default_tenant_id: Optional[str] = None
    
    
class TenantWithUsers(BaseModel):
    """Tenant with its user associations"""
    tenant_id: str
    tenant_name: str
    users: List[UserTenant] = []
    owner_id: str