import os
import jwt
import time
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.jwt_handler import decode_token, create_access_token, validate_cognito_token
from config.settings import settings

logger = logging.getLogger(__name__)


class JWTAuth:
    """
    JWT authentication service that supports both internal (HS256) and Cognito (RS256) tokens.
    """
    
    def __init__(self):
        """
        Initialize JWT authentication service using settings.
        """
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.algorithms = settings.JWT_ALGORITHMS
        self.token_expiration = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        self.audience = settings.COGNITO_CLIENT_ID
        self.issuer = settings.COGNITO_ISSUER
        
        # OAuth2 security scheme
        self.security = HTTPBearer()
    
    def create_token(self, subject: str, tenant_id: str, payload: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a JWT token (internal use).
        
        Args:
            subject: Token subject (usually user ID)
            tenant_id: Tenant ID
            payload: Additional payload data
            
        Returns:
            JWT token
        """
        # Create token payload
        token_data = {
            'sub': subject,
            'tenant_id': tenant_id,
            'user_id': subject,  # Add user_id for compatibility
        }
        
        # Add additional payload data
        if payload:
            token_data.update(payload)
        
        # Create token using the handler
        return create_access_token(
            data=token_data,
            expires_delta=timedelta(seconds=self.token_expiration)
        )
    
    def create_agent_token(
        self,
        agent_id: str,
        tenant_id: str,
        scopes: Optional[str] = None,
        expiration: Optional[int] = None
    ) -> str:
        """
        Create a JWT token for an agent.
        
        Args:
            agent_id: Agent ID
            tenant_id: Tenant ID
            scopes: Token scopes
            expiration: Token expiration time in seconds
            
        Returns:
            JWT token
        """
        # Create token payload
        payload = {
            'agent_id': agent_id,
            'scopes': scopes or 'agent:pubsub',
            'token_type': 'agent'
        }
        
        # Use custom expiration if provided
        expires_delta = None
        if expiration:
            expires_delta = timedelta(seconds=expiration)
        
        return create_access_token(
            data={
                'sub': agent_id,
                'tenant_id': tenant_id,
                **payload
            },
            expires_delta=expires_delta
        )
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a JWT token (supports both HS256 and RS256).
        
        Args:
            token: JWT token
            
        Returns:
            Token payload
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Use the centralized decode_token which handles both algorithms
            payload = decode_token(token)
            
            # For Cognito tokens, do additional validation
            header = jwt.get_unverified_header(token)
            if header.get('alg') == 'RS256':
                # This is a Cognito token, validate it fully
                payload = validate_cognito_token(token)
                
                # Map Cognito claims to our expected format
                payload['tenant_id'] = payload.get('custom:tenant_id') or payload.get('tenant_id')
                payload['user_id'] = payload.get('cognito:username') or payload.get('sub')
            
            return payload
        
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        
        except jwt.PyJWTError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail=str(e))
        
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
    
    async def verify_auth_header(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> Dict[str, Any]:
        """
        Verify JWT token from HTTP Authorization header.
        
        Args:
            credentials: HTTP Authorization credentials
            
        Returns:
            Token payload
            
        Raises:
            HTTPException: If token is missing or invalid
        """
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        
        return self.verify_token(credentials.credentials)
    
    async def get_tenant_id(self, request: Request, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> str:
        """
        Get tenant ID from request.
        
        Args:
            request: HTTP request
            credentials: HTTP Authorization credentials
            
        Returns:
            Tenant ID
            
        Raises:
            HTTPException: If tenant ID is missing or invalid
        """
        # First check for tenant ID in headers
        tenant_id = request.headers.get('x-tenant-id')
        
        # If not found in headers, check JWT token
        if not tenant_id:
            token_payload = self.verify_token(credentials.credentials)
            tenant_id = token_payload.get('tenant_id')
        
        # If still not found, raise error
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Missing tenant ID")
        
        return tenant_id
    
    async def verify_api_key(self, api_key: str, db_service) -> Dict[str, Any]:
        """
        Verify an API key.
        
        Args:
            api_key: API key
            db_service: Database service
            
        Returns:
            API key data
            
        Raises:
            HTTPException: If API key is invalid
        """
        # TODO: Implement API key verification using database service
        # This would check the API key in the database and return tenant info
        
        # For now, return mock data
        return {
            'tenant_id': 'tenant-123',
            'status': 'active',
            'created_at': datetime.utcnow().isoformat()
        }