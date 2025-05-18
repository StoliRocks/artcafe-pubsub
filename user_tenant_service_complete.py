import logging
import uuid
from typing import List, Optional, Dict
from datetime import datetime

from ..db import dynamodb
from config.settings import settings
from models import UserTenant, UserTenantCreate, UserTenantUpdate, UserRole
from models.user_tenant import UserWithTenants, TenantWithUsers

logger = logging.getLogger(__name__)


def fix_boolean_for_dynamodb(data: dict) -> dict:
    """Convert boolean values to numeric for DynamoDB"""
    logger.info(f"[BOOLEAN_FIX] Starting fix_boolean_for_dynamodb with data: {data}")
    print(f"[BOOLEAN_FIX] Starting fix_boolean_for_dynamodb with data: {data}")
    
    # Create a new dict to avoid modifying the original
    fixed_data = {}
    
    for key, value in data.items():
        if isinstance(value, bool):
            fixed_data[key] = 1 if value else 0
            logger.info(f"[BOOLEAN_FIX] Converted {key}: {value} -> {fixed_data[key]}")
            print(f"[BOOLEAN_FIX] Converted {key}: {value} -> {fixed_data[key]}")
        else:
            fixed_data[key] = value
    
    logger.info(f"[BOOLEAN_FIX] Fixed data: {fixed_data}")
    print(f"[BOOLEAN_FIX] Fixed data: {fixed_data}")
    return fixed_data


class UserTenantService:
    """Service for managing user-tenant relationships"""
    
    async def create_user_tenant_mapping(
        self, 
        user_id: str,
        tenant_id: str,
        role: str = UserRole.MEMBER,
        invited_by: Optional[str] = None,
        user_email: Optional[str] = None,
        tenant_name: Optional[str] = None
    ) -> UserTenant:
        """
        Create a user-tenant mapping
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
            role: User role in the tenant
            invited_by: ID of user who invited this user
            user_email: User email (denormalized)
            tenant_name: Tenant name (denormalized)
            
        Returns:
            Created user-tenant mapping
        """
        try:
            logger.info(f"[CREATE_MAPPING] Starting with user_id={user_id}, tenant_id={tenant_id}, role={role}")
            print(f"[CREATE_MAPPING] Starting with user_id={user_id}, tenant_id={tenant_id}, role={role}")
            
            mapping_id = str(uuid.uuid4())
            
            # Create the mapping
            mapping_dict = {
                "id": mapping_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "role": role,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "active": 1  # Already using numeric value
            }
            
            logger.info(f"[CREATE_MAPPING] Initial mapping_dict: {mapping_dict}")
            print(f"[CREATE_MAPPING] Initial mapping_dict: {mapping_dict}")
            
            if invited_by:
                mapping_dict["invited_by"] = invited_by
                mapping_dict["invitation_date"] = datetime.utcnow().isoformat()
                
            if user_email:
                mapping_dict["user_email"] = user_email
                
            if tenant_name:
                mapping_dict["tenant_name"] = tenant_name
            
            # Fix boolean values for DynamoDB
            fixed_mapping_dict = fix_boolean_for_dynamodb(mapping_dict)
            
            logger.info(f"[CREATE_MAPPING] About to store to DynamoDB: {fixed_mapping_dict}")
            print(f"[CREATE_MAPPING] About to store to DynamoDB: {fixed_mapping_dict}")
            
            # Store in DynamoDB
            await dynamodb.put_item(
                table_name=settings.USER_TENANT_TABLE_NAME,
                item=fixed_mapping_dict
            )
            
            # Create indexes for efficient queries
            await self._create_user_index_entry(user_id, tenant_id, mapping_id)
            await self._create_tenant_index_entry(tenant_id, user_id, mapping_id)
            
            # Return using the fixed dict to avoid re-introducing boolean values
            return UserTenant(**fixed_mapping_dict)
            
        except Exception as e:
            logger.error(f"Error creating user-tenant mapping: {e}")
            raise
    
    async def _create_user_index_entry(self, user_id: str, tenant_id: str, mapping_id: str):
        """Create index entry for user -> tenants lookup"""
        await dynamodb.put_item(
            table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
            item={
                "pk": f"USER#{user_id}",
                "sk": f"TENANT#{tenant_id}",
                "mapping_id": mapping_id,
                "created_at": datetime.utcnow().isoformat()
            }
        )
    
    async def _create_tenant_index_entry(self, tenant_id: str, user_id: str, mapping_id: str):
        """Create index entry for tenant -> users lookup"""
        await dynamodb.put_item(
            table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
            item={
                "pk": f"TENANT#{tenant_id}",
                "sk": f"USER#{user_id}",
                "mapping_id": mapping_id,
                "created_at": datetime.utcnow().isoformat()
            }
        )
    
    async def get_user_tenants(self, user_id: str) -> List[UserTenant]:
        """
        Get all tenants for a user
        
        Args:
            user_id: User ID
            
        Returns:
            List of user-tenant mappings
        """
        try:
            # Query the index for user's tenants
            response = await dynamodb.query_items(
                table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
                key_condition_expression="pk = :pk",
                expression_attribute_values={
                    ":pk": f"USER#{user_id}"
                }
            )
            
            # Get full mapping details
            mappings = []
            for item in response.get("Items", []):
                mapping_id = item.get("mapping_id")
                if mapping_id:
                    mapping = await self.get_mapping_by_id(mapping_id)
                    if mapping:
                        mappings.append(mapping)
            
            return mappings
            
        except Exception as e:
            logger.error(f"Error getting user tenants: {e}")
            return []
    
    async def get_tenant_users(self, tenant_id: str) -> List[UserTenant]:
        """
        Get all users for a tenant
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of user-tenant mappings
        """
        try:
            # Query the index for tenant's users
            response = await dynamodb.query_items(
                table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
                key_condition_expression="pk = :pk",
                expression_attribute_values={
                    ":pk": f"TENANT#{tenant_id}"
                }
            )
            
            # Get full mapping details
            mappings = []
            for item in response.get("Items", []):
                mapping_id = item.get("mapping_id")
                if mapping_id:
                    mapping = await self.get_mapping_by_id(mapping_id)
                    if mapping:
                        mappings.append(mapping)
            
            return mappings
            
        except Exception as e:
            logger.error(f"Error getting tenant users: {e}")
            return []
    
    async def get_mapping_by_id(self, mapping_id: str) -> Optional[UserTenant]:
        """Get a specific user-tenant mapping by ID"""
        try:
            item = await dynamodb.get_item(
                table_name=settings.USER_TENANT_TABLE_NAME,
                key={"id": mapping_id}
            )
            
            if item:
                return UserTenant(**item)
            return None
            
        except Exception as e:
            logger.error(f"Error getting mapping: {e}")
            return None
    
    async def get_user_tenant_mapping(self, user_id: str, tenant_id: str) -> Optional[UserTenant]:
        """Get specific user-tenant mapping"""
        try:
            # Query the index
            response = await dynamodb.query_items(
                table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
                key_condition_expression="pk = :pk AND sk = :sk",
                expression_attribute_values={
                    ":pk": f"USER#{user_id}",
                    ":sk": f"TENANT#{tenant_id}"
                }
            )
            
            items = response.get("Items", [])
            if items:
                mapping_id = items[0].get("mapping_id")
                if mapping_id:
                    return await self.get_mapping_by_id(mapping_id)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user-tenant mapping: {e}")
            return None
    
    async def update_user_role(
        self,
        user_id: str,
        tenant_id: str,
        new_role: str
    ) -> Optional[UserTenant]:
        """Update user's role in a tenant"""
        try:
            mapping = await self.get_user_tenant_mapping(user_id, tenant_id)
            if not mapping:
                return None
            
            # Update the mapping
            mapping.role = new_role
            mapping.updated_at = datetime.utcnow()
            
            # Save to database
            await dynamodb.update_item(
                table_name=settings.USER_TENANT_TABLE_NAME,
                key={"id": mapping.id},
                update_expression="SET #role = :role, updated_at = :updated_at",
                expression_attribute_names={
                    "#role": "role"
                },
                expression_attribute_values={
                    ":role": new_role,
                    ":updated_at": mapping.updated_at.isoformat()
                }
            )
            
            return mapping
            
        except Exception as e:
            logger.error(f"Error updating user role: {e}")
            return None
    
    async def remove_user_from_tenant(self, user_id: str, tenant_id: str) -> bool:
        """Remove user from tenant (soft delete)"""
        try:
            mapping = await self.get_user_tenant_mapping(user_id, tenant_id)
            if not mapping:
                return False
            
            # Soft delete the mapping
            await dynamodb.update_item(
                table_name=settings.USER_TENANT_TABLE_NAME,
                key={"id": mapping.id},
                update_expression="SET active = :active, updated_at = :updated_at",
                expression_attribute_values={
                    ":active": 0,  # Convert boolean to number for DynamoDB
                    ":updated_at": datetime.utcnow().isoformat()
                }
            )
            
            # Remove from indexes
            await dynamodb.delete_item(
                table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
                key={
                    "pk": f"USER#{user_id}",
                    "sk": f"TENANT#{tenant_id}"
                }
            )
            
            await dynamodb.delete_item(
                table_name=settings.USER_TENANT_INDEX_TABLE_NAME,
                key={
                    "pk": f"TENANT#{tenant_id}",
                    "sk": f"USER#{user_id}"
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing user from tenant: {e}")
            return False
    
    async def get_user_with_tenants(self, user_id: str, user_email: str) -> UserWithTenants:
        """Get user with all their tenant associations"""
        try:
            tenants = await self.get_user_tenants(user_id)
            
            # Find default tenant (first owned tenant, or first admin tenant, or first tenant)
            default_tenant_id = None
            for tenant in tenants:
                if tenant.role == UserRole.OWNER:
                    default_tenant_id = tenant.tenant_id
                    break
            
            if not default_tenant_id and tenants:
                # Look for admin role
                for tenant in tenants:
                    if tenant.role == UserRole.ADMIN:
                        default_tenant_id = tenant.tenant_id
                        break
            
            if not default_tenant_id and tenants:
                # Just use the first tenant
                default_tenant_id = tenants[0].tenant_id
            
            return UserWithTenants(
                user_id=user_id,
                email=user_email,
                tenants=tenants,
                default_tenant_id=default_tenant_id
            )
            
        except Exception as e:
            logger.error(f"Error getting user with tenants: {e}")
            return UserWithTenants(user_id=user_id, email=user_email)
    
    async def check_user_access(
        self,
        user_id: str,
        tenant_id: str,
        required_role: Optional[str] = None
    ) -> bool:
        """
        Check if user has access to a tenant
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
            required_role: Required role (optional)
            
        Returns:
            True if user has access
        """
        try:
            mapping = await self.get_user_tenant_mapping(user_id, tenant_id)
            if not mapping or not mapping.active:
                return False
            
            if required_role:
                if required_role == UserRole.OWNER:
                    return mapping.is_owner
                elif required_role == UserRole.ADMIN:
                    return mapping.is_admin
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking user access: {e}")
            return False


# Create service singleton
user_tenant_service = UserTenantService()