import os
import json
import logging
import uuid
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)

def generate_id(prefix: str = "id") -> str:
    """
    Generate a unique ID with a prefix.
    
    Args:
        prefix: ID prefix
        
    Returns:
        Unique ID
    """
    return f"{prefix}-{uuid.uuid4()}"

def format_datetime(dt: Optional[Union[datetime, date]]) -> Optional[str]:
    """
    Format a datetime object as ISO string.
    
    Args:
        dt: Datetime object
        
    Returns:
        ISO formatted string or None
    """
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return None

def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO datetime string.
    
    Args:
        dt_str: ISO datetime string
        
    Returns:
        Datetime object or None
    """
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse datetime: {dt_str}")
        return None

def safe_get(obj: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safely get a nested value from a dict.
    
    Args:
        obj: Dict to get value from
        path: Dot-separated path to value
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    keys = path.split('.')
    result = obj
    
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    
    return result

def safe_update(obj: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """
    Safely update a nested value in a dict.
    
    Args:
        obj: Dict to update
        path: Dot-separated path to value
        value: New value
        
    Returns:
        Updated dict
    """
    keys = path.split('.')
    current = obj
    
    for i, key in enumerate(keys[:-1]):
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    return obj

def mask_sensitive_data(data: Dict[str, Any], sensitive_keys: List[str]) -> Dict[str, Any]:
    """
    Mask sensitive data in a dict.
    
    Args:
        data: Dict containing sensitive data
        sensitive_keys: List of sensitive keys to mask
        
    Returns:
        Dict with sensitive data masked
    """
    masked_data = data.copy()
    
    for key in sensitive_keys:
        if key in masked_data:
            masked_data[key] = "***MASKED***"
    
    return masked_data

def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize data for logging.
    
    Args:
        data: Data to sanitize
        
    Returns:
        Sanitized data
    """
    sensitive_keys = [
        "password", "token", "secret", "key", "auth",
        "jwt", "private", "credential", "api_key", "admin_token"
    ]
    
    return mask_sensitive_data(data, sensitive_keys)