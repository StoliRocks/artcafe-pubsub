import time
import json
import requests
from typing import Dict, Optional, List
import jwt
from datetime import datetime, timedelta
from jwt.algorithms import RSAAlgorithm
from functools import lru_cache

from config.settings import settings


# Cache for Cognito public keys
_cognito_keys_cache = {}
_cache_timestamp = 0
CACHE_TTL = 3600  # 1 hour


@lru_cache(maxsize=1)
def get_cognito_keys() -> Dict[str, any]:
    """
    Fetch public keys from AWS Cognito JWKS endpoint
    
    Returns:
        Dictionary of kid -> public key
    """
    global _cognito_keys_cache, _cache_timestamp
    
    # Check cache
    if _cognito_keys_cache and (time.time() - _cache_timestamp) < CACHE_TTL:
        return _cognito_keys_cache
    
    try:
        # Fetch JWKS from Cognito
        response = requests.get(settings.COGNITO_JWKS_URL, timeout=5)
        response.raise_for_status()
        jwks = response.json()
        
        # Convert JWKS to dictionary of kid -> public key
        keys = {}
        for key_data in jwks.get('keys', []):
            kid = key_data.get('kid')
            if kid:
                # Convert JWK to PEM format for RS256 verification
                public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                keys[kid] = public_key
        
        # Update cache
        _cognito_keys_cache = keys
        _cache_timestamp = time.time()
        
        return keys
    except Exception as e:
        # If we have cached keys and fetch fails, use cache
        if _cognito_keys_cache:
            return _cognito_keys_cache
        raise Exception(f"Failed to fetch Cognito public keys: {str(e)}")


def create_access_token(*, data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT token (for internal use, not Cognito)
    
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
    Decode and validate JWT token (supports both HS256 and RS256)
    
    Args:
        token: JWT token
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.PyJWTError: If token is invalid
    """
    # Decode header to check algorithm
    try:
        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get('alg', '')
        
        # Handle RS256 (Cognito) tokens
        if algorithm == 'RS256':
            # Get kid from header
            kid = unverified_header.get('kid')
            if not kid:
                raise jwt.PyJWTError("No 'kid' in token header")
            
            # Get public keys from Cognito
            public_keys = get_cognito_keys()
            public_key = public_keys.get(kid)
            
            if not public_key:
                raise jwt.PyJWTError(f"Public key not found for kid: {kid}")
            
            # Decode with RS256 and Cognito public key
            return jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                options={"verify_aud": False}  # Skip audience verification for now
            )
            
        # Handle HS256 (internal) tokens
        elif algorithm == 'HS256':
            return jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=['HS256']
            )
        else:
            raise jwt.PyJWTError(f"Unsupported algorithm: {algorithm}")
            
    except jwt.PyJWTError:
        raise
    except Exception as e:
        raise jwt.PyJWTError(f"Token decode error: {str(e)}")


def validate_cognito_token(token: str) -> Dict:
    """
    Validate a Cognito token with additional checks
    
    Args:
        token: JWT token from Cognito
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.PyJWTError: If token is invalid
    """
    # First decode the token
    payload = decode_token(token)
    
    # Validate issuer
    if payload.get('iss') != settings.COGNITO_ISSUER:
        raise jwt.PyJWTError(f"Invalid issuer: {payload.get('iss')}")
    
    # Validate token use (should be 'id' for ID tokens)
    token_use = payload.get('token_use')
    if token_use not in ['id', 'access']:
        raise jwt.PyJWTError(f"Invalid token_use: {token_use}")
    
    # Validate expiration
    exp = payload.get('exp')
    if exp and exp < time.time():
        raise jwt.ExpiredSignatureError("Token has expired")
    
    return payload