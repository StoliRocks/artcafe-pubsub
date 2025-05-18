from typing import Optional, Dict
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from .jwt_handler import decode_token, validate_cognito_token
from config.settings import settings
from api.services.user_tenant_service import user_tenant_service
from models.user_tenant import UserWithTenants

# HTTP Bearer security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict:
    """
    Extract and verify user from JWT token (supports both HS256 and Cognito RS256)
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        User data from token
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        # Decode token (automatically handles both HS256 and RS256)
        payload = decode_token(credentials.credentials)
        
        # Check if this is a Cognito token
        header = jwt.get_unverified_header(credentials.credentials)
        if header.get('alg') == 'RS256':
            # This is a Cognito token, use the Cognito validator for extra checks
            payload = validate_cognito_token(credentials.credentials)
            
            # Map Cognito claims to our expected format
            user_id = payload.get("sub")  # Cognito uses 'sub' for user ID
            user_email = payload.get("email")
            
            # Also check for custom claims
            if not user_id:
                user_id = payload.get("cognito:username")
            
            # Map the payload to our standard format
            payload['user_id'] = user_id
            payload['email'] = user_email
        else:
            # Standard token format
            user_id = payload.get("user_id")
            user_email = payload.get("email")
        
        if not user_id or not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return {
            "user_id": user_id,
            "email": user_email,
            "token_data": payload
        }
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_with_tenants(
    user_data: Dict = Depends(get_current_user)
) -> UserWithTenants:
    """
    Get current user with their tenant associations
    
    Args:
        user_data: User data from token
        
    Returns:
        User with tenants
    """
    user_id = user_data["user_id"]
    email = user_data["email"]
    
    return await user_tenant_service.get_user_with_tenants(user_id, email)


async def get_current_tenant_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_tenant_id: Optional[str] = Header(None, alias=settings.TENANT_ID_HEADER_NAME)
) -> str:
    """
    Extract and verify tenant ID from JWT token or header
    
    Args:
        credentials: HTTP Bearer credentials
        x_tenant_id: Optional tenant ID from header
        
    Returns:
        Tenant ID
        
    Raises:
        HTTPException: If tenant ID is missing or token is invalid
    """
    # First try to get tenant ID from the header
    if x_tenant_id:
        return x_tenant_id
        
    # Otherwise extract it from the JWT token
    try:
        payload = decode_token(credentials.credentials)
        
        # Check multiple possible locations for tenant ID
        tenant_id = (
            payload.get("tenant_id") or
            payload.get("custom:tenant_id") or  # Cognito custom attribute
            payload.get("org_id") or  # Alternative naming
            payload.get("organization_id")  # Alternative naming
        )
        
        if not tenant_id:
            # If no tenant ID in token, check if we can get it from user's default tenant
            user_id = payload.get("sub") or payload.get("user_id")
            if user_id:
                # Try to get user's default tenant
                user_tenants = await user_tenant_service.get_user_tenants(user_id)
                if user_tenants:
                    # Use the first tenant as default
                    tenant_id = user_tenants[0].tenant_id
            
            if not tenant_id:
                # Last resort: use the default tenant ID
                return settings.DEFAULT_TENANT_ID
            
        return tenant_id
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_tenant_access(
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    tenant_id: str = Depends(get_current_tenant_id)
) -> str:
    """
    Verify user has access to the requested tenant
    
    Args:
        user: Current user with tenants
        tenant_id: Requested tenant ID
        
    Returns:
        Tenant ID if user has access
        
    Raises:
        HTTPException: If user doesn't have access
    """
    # Check if user has access to this tenant
    if await user_tenant_service.check_user_access(user.user_id, tenant_id):
        return tenant_id
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this organization"
    )


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias=settings.API_KEY_HEADER_NAME)
) -> str:
    """
    Verify API key header
    
    Args:
        x_api_key: API key from header
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
        )
    
    # TODO: Implement API key validation against database
    # For now, we'll just return the key
    return x_api_key


async def get_authorization_headers(
    tenant_id: str = Depends(get_current_tenant_id),
    api_key: str = Depends(verify_api_key),
) -> dict:
    """
    Get authorization headers for upstream services
    
    Args:
        tenant_id: Tenant ID
        api_key: API key
        
    Returns:
        Headers dict with tenant ID and API key
    """
    return {
        settings.TENANT_ID_HEADER_NAME: tenant_id,
        settings.API_KEY_HEADER_NAME: api_key,
    }