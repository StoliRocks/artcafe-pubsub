from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Optional
from pydantic import BaseModel, EmailStr

from auth.dependencies import get_current_user
from api.services.user_tenant_service import user_tenant_service
from api.services.tenant_service import tenant_service
from api.services.profile_service import profile_service
from models.user_profile import UserProfile, UserProfileCreate, UserProfileUpdate

router = APIRouter(prefix="/profile", tags=["profile"])


class UserProfileResponse(BaseModel):
    """User profile response"""
    profile: UserProfile
    organizations: list[Dict] = []
    current_organization: Optional[Dict] = None


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    user: Dict = Depends(get_current_user)
):
    """
    Get current user's profile
    
    Returns user profile data along with their organizations
    """
    try:
        # Get user ID and email from JWT
        user_id = user.get("user_id", user.get("sub"))
        email = user.get("email", "")
        name = user.get("name", "")
        
        # Ensure profile exists in database
        user_profile = await profile_service.ensure_profile_exists(
            user_id=user_id,
            email=email,
            name=name
        )
        
        # Update profile with latest Cognito attributes if they differ
        cognito_updates = {}
        if user.get("nickname") and user_profile.greeting != user.get("nickname"):
            cognito_updates["greeting"] = user.get("nickname")
        if user.get("picture") and user_profile.avatar_url != user.get("picture"):
            cognito_updates["avatar_url"] = user.get("picture")
        if user.get("zoneinfo") and user_profile.timezone != user.get("zoneinfo"):
            cognito_updates["timezone"] = user.get("zoneinfo")
            
        if cognito_updates:
            update_data = UserProfileUpdate(**cognito_updates)
            user_profile = await profile_service.update_user_profile(user_id, update_data)
        
        # Get user's organizations
        user_tenants = await tenant_service.get_user_tenants(user_profile.user_id)
        
        # Format organizations for response
        organizations = []
        for tenant in user_tenants:
            org_data = {
                "id": tenant.id,
                "name": tenant.name,
                "role": "admin",  # This would come from user_tenant mapping
                "created_at": tenant.created_at,
                "subscription_tier": tenant.subscription_tier,
                "logo_url": getattr(tenant, "logo_url", None),
                "primary_color": getattr(tenant, "primary_color", "#0284c7")
            }
            organizations.append(org_data)
        
        # Get current organization (first one or from session)
        current_org = organizations[0] if organizations else None
        
        return UserProfileResponse(
            profile=user_profile,
            organizations=organizations,
            current_organization=current_org
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user profile: {str(e)}"
        )


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    profile_data: UserProfileUpdate,
    user: Dict = Depends(get_current_user)
):
    """
    Update current user's profile
    
    Note: This endpoint updates profile metadata. Core attributes like
    email and name should be updated through AWS Cognito.
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        # Update user profile in database
        updated_profile = await profile_service.update_user_profile(user_id, profile_data)
        
        if not updated_profile:
            # Profile doesn't exist, create it first
            email = user.get("email", "")
            name = profile_data.name or user.get("name", "")
            
            # Create profile
            create_data = UserProfileCreate(
                user_id=user_id,
                email=email,
                name=name,
                greeting=profile_data.greeting,
                avatar_url=profile_data.avatar_url,
                timezone=profile_data.timezone or "UTC",
                bio=profile_data.bio,
                phone=profile_data.phone,
                company=profile_data.company,
                title=profile_data.title,
                notifications_enabled=profile_data.notifications_enabled if profile_data.notifications_enabled is not None else True
            )
            
            updated_profile = await profile_service.create_user_profile(create_data)
        
        return updated_profile
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user profile: {str(e)}"
        )


@router.get("/preferences", response_model=Dict)
async def get_user_preferences(
    user: Dict = Depends(get_current_user)
):
    """
    Get user preferences
    
    Returns user's application preferences like theme, notifications, etc.
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        # Get user profile
        profile = await profile_service.get_user_profile(user_id)
        
        if not profile:
            # Return default preferences if no profile exists
            preferences = {
                "theme": "light",
                "language": "en",
                "email_notifications": {
                    "agent_status": True,
                    "usage_alerts": True,
                    "billing_updates": True,
                    "security_alerts": True,
                    "newsletter": False
                },
                "dashboard_layout": "grid",
                "default_view": "overview",
                "timezone": user.get("zoneinfo", "UTC"),
                "date_format": "MM/DD/YYYY",
                "time_format": "12h"
            }
        else:
            # Return preferences from profile
            preferences = {
                "theme": profile.theme,
                "language": profile.language,
                "email_notifications": profile.email_notifications,
                "dashboard_layout": profile.dashboard_layout,
                "default_view": profile.default_view,
                "timezone": profile.timezone,
                "date_format": profile.date_format,
                "time_format": profile.time_format,
                "notifications_enabled": profile.notifications_enabled
            }
        
        return preferences
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user preferences: {str(e)}"
        )


@router.put("/preferences", response_model=Dict)
async def update_user_preferences(
    preferences: Dict,
    user: Dict = Depends(get_current_user)
):
    """
    Update user preferences
    
    Updates user's application preferences
    """
    try:
        user_id = user.get("user_id", user.get("sub"))
        
        # Update preferences using profile service
        updated_profile = await profile_service.update_preferences(user_id, preferences)
        
        if not updated_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Return updated preferences
        return {
            "theme": updated_profile.theme,
            "language": updated_profile.language,
            "email_notifications": updated_profile.email_notifications,
            "dashboard_layout": updated_profile.dashboard_layout,
            "default_view": updated_profile.default_view,
            "timezone": updated_profile.timezone,
            "date_format": updated_profile.date_format,
            "time_format": updated_profile.time_format,
            "notifications_enabled": updated_profile.notifications_enabled
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user preferences: {str(e)}"
        )