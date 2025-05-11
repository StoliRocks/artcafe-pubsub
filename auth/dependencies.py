from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from .jwt_handler import decode_token
from config.settings import settings

# HTTP Bearer security scheme
security = HTTPBearer()


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
        tenant_id = payload.get("tenant_id")
        
        if not tenant_id:
            # If no tenant ID in token, use the default
            return settings.DEFAULT_TENANT_ID
            
        return tenant_id
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
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