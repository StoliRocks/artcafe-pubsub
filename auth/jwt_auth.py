import os
import jwt
import time
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

class JWTAuth:
    """
    JWT authentication service.
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = 'HS256',
        token_expiration: int = 86400,  # 24 hours in seconds
        audience: Optional[str] = None,
        issuer: Optional[str] = None
    ):
        """
        Initialize JWT authentication service.
        
        Args:
            secret_key: Secret key for JWT signing
            algorithm: JWT algorithm
            token_expiration: Token expiration time in seconds
            audience: Token audience
            issuer: Token issuer
        """
        self.secret_key = secret_key or os.getenv('JWT_SECRET_KEY')
        if not self.secret_key:
            raise ValueError("JWT secret key must be provided")
        
        self.algorithm = algorithm
        self.token_expiration = token_expiration
        self.audience = audience or os.getenv('JWT_AUDIENCE', 'artcafe-api')
        self.issuer = issuer or os.getenv('JWT_ISSUER', 'artcafe-auth')
        
        # OAuth2 security scheme
        self.security = HTTPBearer()
    
    def create_token(self, subject: str, tenant_id: str, payload: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a JWT token.
        
        Args:
            subject: Token subject (usually user ID)
            tenant_id: Tenant ID
            payload: Additional payload data
            
        Returns:
            JWT token
        """
        now = int(time.time())
        
        # Create token payload
        token_payload = {
            'sub': subject,
            'tenant_id': tenant_id,
            'iat': now,
            'exp': now + self.token_expiration,
            'aud': self.audience,
            'iss': self.issuer
        }
        
        # Add additional payload data
        if payload:
            token_payload.update(payload)
        
        # Create token
        token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
        
        return token
    
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
            'scopes': scopes or 'agent:pubsub'
        }
        
        # Use custom expiration if provided
        if expiration:
            now = int(time.time())
            payload['exp'] = now + expiration
        
        return self.create_token(agent_id, tenant_id, payload)
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a JWT token.
        
        Args:
            token: JWT token
            
        Returns:
            Token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        try:
            # Decode and verify token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer
            )
            
            return payload
        
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
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