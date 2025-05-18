import logging
import uuid
from typing import Optional, List, Dict
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models.terms_acceptance import TermsAcceptance

logger = logging.getLogger(__name__)


class TermsAcceptanceService:
    """Service for managing terms of service acceptance records"""
    
    async def create_acceptance(
        self,
        user_id: str,
        email: str,
        terms_version: str,
        privacy_version: str,
        ip_address: str,
        user_agent: str,
        tenant_id: Optional[str] = None
    ) -> TermsAcceptance:
        """
        Create a new terms acceptance record
        
        Args:
            user_id: User ID (from Cognito)
            email: User's email address
            terms_version: Version of terms accepted
            privacy_version: Version of privacy policy accepted
            ip_address: IP address of acceptance
            user_agent: User agent string
            tenant_id: Optional tenant ID
            
        Returns:
            Created TermsAcceptance record
        """
        try:
            # Generate acceptance ID
            acceptance_id = str(uuid.uuid4())
            
            # Create acceptance record
            acceptance_data = {
                "id": acceptance_id,
                "user_id": user_id,
                "email": email,
                "terms_version": terms_version,
                "privacy_version": privacy_version,
                "accepted_at": datetime.utcnow().isoformat(),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "tenant_id": tenant_id,
                "revoked": 0,  # Convert boolean to number for DynamoDB
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=settings.TERMS_ACCEPTANCE_TABLE_NAME,
                item=acceptance_data
            )
            
            logger.info(f"Created terms acceptance {acceptance_id} for user {user_id}")
            
            # Convert numeric back to boolean for the model
            acceptance_data["revoked"] = bool(acceptance_data["revoked"])
            return TermsAcceptance(**acceptance_data)
            
        except Exception as e:
            logger.error(f"Error creating terms acceptance: {e}")
            raise
    
    async def get_current_acceptance(
        self,
        user_id: str,
        terms_version: Optional[str] = None
    ) -> Optional[TermsAcceptance]:
        """
        Get the current (most recent) terms acceptance for a user
        
        Args:
            user_id: User ID
            terms_version: Optional specific version to check
            
        Returns:
            Most recent TermsAcceptance or None
        """
        try:
            # Query by user ID
            response = await dynamodb.query(
                table_name=settings.TERMS_ACCEPTANCE_TABLE_NAME,
                index_name="UserIndex",
                key_condition_expression="user_id = :user_id",
                expression_attribute_values={
                    ":user_id": user_id
                },
                scan_index_forward=False,  # Sort descending by ID (timestamp)
                limit=1
            )
            
            items = response.get("Items", [])
            if not items:
                return None
                
            # Check if specific version requested
            if terms_version:
                for item in items:
                    if item.get("terms_version") == terms_version:
                        # Convert numeric revoked to boolean
                        if 'revoked' in item:
                            item['revoked'] = bool(item['revoked'])
                        return TermsAcceptance(**item)
                return None
            
            # Return most recent
            # Convert numeric revoked to boolean
            item = items[0]
            if 'revoked' in item:
                item['revoked'] = bool(item['revoked'])
            return TermsAcceptance(**item)
            
        except Exception as e:
            logger.error(f"Error getting current acceptance for user {user_id}: {e}")
            return None
    
    async def get_acceptance_history(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[TermsAcceptance]:
        """
        Get acceptance history for a user
        
        Args:
            user_id: User ID
            limit: Maximum records to return
            
        Returns:
            List of TermsAcceptance records
        """
        try:
            response = await dynamodb.query(
                table_name=settings.TERMS_ACCEPTANCE_TABLE_NAME,
                index_name="UserIndex",
                key_condition_expression="user_id = :user_id",
                expression_attribute_values={
                    ":user_id": user_id
                },
                scan_index_forward=False,  # Sort descending
                limit=limit
            )
            
            items = response.get("Items", [])
            # Convert numeric revoked to boolean
            for item in items:
                if 'revoked' in item:
                    item['revoked'] = bool(item['revoked'])
            return [TermsAcceptance(**item) for item in items]
            
        except Exception as e:
            logger.error(f"Error getting acceptance history for user {user_id}: {e}")
            return []
    
    async def revoke_acceptance(
        self,
        acceptance_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Revoke a terms acceptance
        
        Args:
            acceptance_id: Acceptance ID to revoke
            reason: Optional reason for revocation
            
        Returns:
            Success status
        """
        try:
            update_expression = "SET revoked = :true, revoked_at = :now, updated_at = :now"
            expression_values = {
                ":true": 1,  # Convert boolean to number for DynamoDB
                ":now": datetime.utcnow().isoformat()
            }
            
            if reason:
                update_expression += ", revocation_reason = :reason"
                expression_values[":reason"] = reason
            
            await dynamodb.update_item(
                table_name=settings.TERMS_ACCEPTANCE_TABLE_NAME,
                key={"id": acceptance_id},
                update_expression=update_expression,
                expression_attribute_values=expression_values
            )
            
            logger.info(f"Revoked terms acceptance {acceptance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking acceptance {acceptance_id}: {e}")
            return False
    
    async def check_user_acceptance(
        self,
        user_id: str,
        required_terms_version: str,
        required_privacy_version: str
    ) -> Dict[str, bool]:
        """
        Check if user has accepted required versions
        
        Args:
            user_id: User ID
            required_terms_version: Required terms version
            required_privacy_version: Required privacy version
            
        Returns:
            Dict with acceptance status
        """
        try:
            current = await self.get_current_acceptance(user_id)
            
            if not current or current.revoked:
                return {
                    "accepted": False,
                    "current_terms_version": None,
                    "current_privacy_version": None,
                    "needs_acceptance": True
                }
            
            # Check versions
            terms_ok = current.terms_version == required_terms_version
            privacy_ok = current.privacy_version == required_privacy_version
            
            return {
                "accepted": terms_ok and privacy_ok,
                "current_terms_version": current.terms_version,
                "current_privacy_version": current.privacy_version,
                "needs_acceptance": not (terms_ok and privacy_ok),
                "terms_up_to_date": terms_ok,
                "privacy_up_to_date": privacy_ok
            }
            
        except Exception as e:
            logger.error(f"Error checking user acceptance: {e}")
            return {
                "accepted": False,
                "error": str(e)
            }


# Create singleton instance
terms_acceptance_service = TermsAcceptanceService()