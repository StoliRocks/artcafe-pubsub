from typing import Optional, Dict
from datetime import datetime
from pydantic import BaseModel, EmailStr, validator

from .base import BaseSchema


class UserProfile(BaseSchema):
    """User profile model for storing extended user information"""
    user_id: str  # Primary key - matches Cognito sub
    email: EmailStr
    
    # Basic profile info
    name: Optional[str] = None
    greeting: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: str = "UTC"
    
    # Extended profile info
    bio: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    
    # Preferences
    notifications_enabled: bool = True
    theme: str = "light"
    language: str = "en"
    dashboard_layout: str = "grid"
    default_view: str = "overview"
    date_format: str = "MM/DD/YYYY"
    time_format: str = "12h"
    
    # Email notification preferences
    email_notifications: Dict[str, bool] = {
        "agent_status": True,
        "usage_alerts": True,
        "billing_updates": True,
        "security_alerts": True,
        "newsletter": False
    }
    
    # Metadata
    metadata: Optional[Dict] = None
    
    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone"""
        valid_timezones = [
            "UTC", "America/New_York", "America/Chicago", 
            "America/Denver", "America/Los_Angeles",
            "Europe/London", "Europe/Paris", 
            "Asia/Tokyo", "Australia/Sydney"
        ]
        if v not in valid_timezones:
            # Allow any timezone string for flexibility
            pass
        return v
    
    @validator('theme')
    def validate_theme(cls, v):
        """Validate theme"""
        if v not in ["light", "dark", "auto"]:
            raise ValueError("Theme must be light, dark, or auto")
        return v
    
    @validator('language')
    def validate_language(cls, v):
        """Validate language code"""
        # Basic validation for ISO 639-1 codes
        if len(v) != 2:
            raise ValueError("Language must be a 2-letter ISO code")
        return v.lower()


class UserProfileCreate(BaseModel):
    """User profile creation model"""
    user_id: str
    email: EmailStr
    name: Optional[str] = None
    greeting: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: str = "UTC"
    
    # Extended profile info
    bio: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    
    # Preferences can be set on creation
    notifications_enabled: Optional[bool] = True
    theme: Optional[str] = "light"
    language: Optional[str] = "en"
    
    metadata: Optional[Dict] = None


class UserProfileUpdate(BaseModel):
    """User profile update model"""
    name: Optional[str] = None
    greeting: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    
    # Extended profile info
    bio: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    
    # Preferences
    notifications_enabled: Optional[bool] = None
    theme: Optional[str] = None
    language: Optional[str] = None
    dashboard_layout: Optional[str] = None
    default_view: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    
    # Email notification preferences
    email_notifications: Optional[Dict[str, bool]] = None
    
    metadata: Optional[Dict] = None