import logging
from typing import Optional, Dict, List
from datetime import datetime

from models.user_profile import UserProfile, UserProfileCreate, UserProfileUpdate
from api.db import dynamodb
from config.settings import settings

logger = logging.getLogger(__name__)

# Table name for user profiles
USER_PROFILE_TABLE = "artcafe-user-profiles"


class ProfileService:
    """Service for managing user profiles"""
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        Get user profile by user ID
        
        Args:
            user_id: User ID (Cognito sub)
            
        Returns:
            UserProfile if found, None otherwise
        """
        try:
            result = await dynamodb.get_item(
                table_name=USER_PROFILE_TABLE,
                key={"user_id": user_id}
            )
            
            if result:
                return UserProfile(**result)
            return None
            
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return None
    
    async def create_user_profile(self, profile_data: UserProfileCreate) -> UserProfile:
        """
        Create a new user profile
        
        Args:
            profile_data: Profile creation data
            
        Returns:
            Created UserProfile
        """
        try:
            # Create profile model
            profile = UserProfile(
                user_id=profile_data.user_id,
                email=profile_data.email,
                name=profile_data.name,
                greeting=profile_data.greeting,
                avatar_url=profile_data.avatar_url,
                timezone=profile_data.timezone,
                bio=profile_data.bio,
                phone=profile_data.phone,
                company=profile_data.company,
                title=profile_data.title,
                notifications_enabled=profile_data.notifications_enabled,
                theme=profile_data.theme,
                language=profile_data.language,
                metadata=profile_data.metadata,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Save to DynamoDB
            await dynamodb.put_item(
                table_name=USER_PROFILE_TABLE,
                item=profile.dict()
            )
            
            logger.info(f"Created user profile for {profile.user_id}")
            return profile
            
        except Exception as e:
            logger.error(f"Error creating user profile: {e}")
            raise
    
    async def update_user_profile(self, user_id: str, update_data: UserProfileUpdate) -> Optional[UserProfile]:
        """
        Update user profile
        
        Args:
            user_id: User ID to update
            update_data: Fields to update
            
        Returns:
            Updated UserProfile if successful
        """
        try:
            # Get current profile
            current_profile = await self.get_user_profile(user_id)
            if not current_profile:
                logger.warning(f"Profile not found for user {user_id}")
                return None
            
            # Prepare updates
            updates = update_data.dict(exclude_none=True)
            if not updates:
                return current_profile
            
            # Add updated timestamp
            updates["updated_at"] = datetime.utcnow()
            
            # Update in DynamoDB
            await dynamodb.update_item(
                table_name=USER_PROFILE_TABLE,
                key={"user_id": user_id},
                updates=updates
            )
            
            # Return updated profile
            updated_profile = await self.get_user_profile(user_id)
            logger.info(f"Updated profile for user {user_id}")
            return updated_profile
            
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            raise
    
    async def delete_user_profile(self, user_id: str) -> bool:
        """
        Delete user profile
        
        Args:
            user_id: User ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Check if profile exists
            profile = await self.get_user_profile(user_id)
            if not profile:
                return False
            
            # Delete from DynamoDB
            await dynamodb.delete_item(
                table_name=USER_PROFILE_TABLE,
                key={"user_id": user_id}
            )
            
            logger.info(f"Deleted profile for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting user profile: {e}")
            raise
    
    async def ensure_profile_exists(self, user_id: str, email: str, name: Optional[str] = None) -> UserProfile:
        """
        Ensure user profile exists, create if not
        
        Args:
            user_id: User ID
            email: User email
            name: User name (optional)
            
        Returns:
            UserProfile
        """
        try:
            # Check if profile exists
            profile = await self.get_user_profile(user_id)
            if profile:
                return profile
            
            # Create new profile
            profile_data = UserProfileCreate(
                user_id=user_id,
                email=email,
                name=name or email.split('@')[0]
            )
            
            return await self.create_user_profile(profile_data)
            
        except Exception as e:
            logger.error(f"Error ensuring profile exists: {e}")
            raise
    
    async def update_preferences(self, user_id: str, preferences: Dict) -> Optional[UserProfile]:
        """
        Update user preferences
        
        Args:
            user_id: User ID
            preferences: Preferences to update
            
        Returns:
            Updated UserProfile
        """
        try:
            # Validate preference keys
            allowed_keys = {
                "theme", "language", "email_notifications",
                "dashboard_layout", "default_view", "timezone",
                "date_format", "time_format", "notifications_enabled"
            }
            
            # Filter preferences
            filtered_prefs = {
                k: v for k, v in preferences.items() 
                if k in allowed_keys
            }
            
            if not filtered_prefs:
                return await self.get_user_profile(user_id)
            
            # Create update data
            update_data = UserProfileUpdate(**filtered_prefs)
            
            return await self.update_user_profile(user_id, update_data)
            
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            raise


# Create singleton instance
profile_service = ProfileService()