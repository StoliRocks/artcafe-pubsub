import time
from typing import Dict, Optional
import jwt
from datetime import datetime, timedelta

from config.settings import settings


def create_access_token(*, data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT token
    
    Args:
        data: Token payload data
        expires_delta: Optional token expiration time
        
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode.update({"exp": expire})
    
    # Create JWT token
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def decode_token(token: str) -> Dict:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.PyJWTError: If token is invalid
    """
    return jwt.decode(
        token, 
        settings.JWT_SECRET_KEY, 
        algorithms=[settings.JWT_ALGORITHM]
    )