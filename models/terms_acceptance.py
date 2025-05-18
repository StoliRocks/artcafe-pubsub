from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class TermsAcceptance(BaseSchema):
    """Record of terms of service acceptance"""
    acceptance_id: str = Field(..., alias="id")
    user_id: str
    email: str
    terms_version: str
    privacy_version: str
    accepted_at: datetime
    ip_address: str
    user_agent: str
    tenant_id: Optional[str] = None
    
    # Tracking fields
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    
    class Config:
        allow_population_by_field_name = True