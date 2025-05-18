"""
NATS authorization and permission handling for tenant isolation.

This module provides tenant-based authorization checking for NATS subject access.
It ensures that tenants can only publish to or subscribe to their own subjects.
"""

import logging
from typing import Optional, Dict, Any, List

from nats.errors import AuthError, TimeoutError

logger = logging.getLogger(__name__)

class TenantNATSAuth:
    """
    NATS authorization helper for tenant isolation.
    
    This class helps enforce tenant boundaries by providing methods to check
    if a subject is allowed for a specific tenant.
    """
    
    def __init__(self):
        """Initialize the NATS authorization helper."""
        self.tenant_permissions = {}
    
    def register_tenant(self, tenant_id: str, permissions: Optional[Dict[str, Any]] = None) -> None:
        """
        Register a tenant and its permissions.
        
        Args:
            tenant_id: The tenant ID
            permissions: Optional permissions dictionary. If None, default permissions will be used.
        """
        if not permissions:
            # Default permissions allow access only to the tenant's subjects
            permissions = {
                "publish": {
                    "allow": [f"tenant.{tenant_id}.>"]
                },
                "subscribe": {
                    "allow": [f"tenant.{tenant_id}.>"]
                }
            }
        
        self.tenant_permissions[tenant_id] = permissions
        logger.debug(f"Registered tenant {tenant_id} with permissions: {permissions}")
    
    def check_publish_permission(self, tenant_id: str, subject: str) -> bool:
        """
        Check if a tenant is allowed to publish to a subject.
        
        Args:
            tenant_id: The tenant ID
            subject: The subject to check
            
        Returns:
            bool: True if allowed, False otherwise
        """
        return self._check_permission(tenant_id, subject, "publish")
    
    def check_subscribe_permission(self, tenant_id: str, subject: str) -> bool:
        """
        Check if a tenant is allowed to subscribe to a subject.
        
        Args:
            tenant_id: The tenant ID
            subject: The subject to check
            
        Returns:
            bool: True if allowed, False otherwise
        """
        return self._check_permission(tenant_id, subject, "subscribe")
    
    def _check_permission(self, tenant_id: str, subject: str, action: str) -> bool:
        """
        Check if a tenant is allowed to perform an action on a subject.
        
        Args:
            tenant_id: The tenant ID
            subject: The subject to check
            action: The action to check ("publish" or "subscribe")
            
        Returns:
            bool: True if allowed, False otherwise
        """
        # Register tenant if not already registered
        if tenant_id not in self.tenant_permissions:
            self.register_tenant(tenant_id)
        
        # Get tenant permissions
        permissions = self.tenant_permissions.get(tenant_id, {})
        action_perms = permissions.get(action, {})
        
        # Check against allow patterns
        allow_patterns = action_perms.get("allow", [])
        for pattern in allow_patterns:
            # Convert NATS wildcard pattern to a prefix check
            # - '>' is a wildcard that matches one or more tokens
            # - '*' is a wildcard that matches exactly one token
            if pattern.endswith(".>"):
                prefix = pattern[:-2]
                if subject.startswith(prefix):
                    return True
            elif "*" in pattern:
                # For simplicity, we're not implementing full * wildcard matching here
                # In a production system, you'd want a proper wildcard pattern matcher
                parts = pattern.split(".")
                subject_parts = subject.split(".")
                
                if len(parts) != len(subject_parts):
                    continue
                
                match = True
                for i, part in enumerate(parts):
                    if part == "*":
                        continue
                    if part != subject_parts[i]:
                        match = False
                        break
                
                if match:
                    return True
            else:
                # Exact match
                if subject == pattern:
                    return True
        
        return False

    def validate_publish(self, tenant_id: str, subject: str) -> None:
        """
        Validate if a tenant can publish to a subject, raising an error if not allowed.
        
        Args:
            tenant_id: The tenant ID
            subject: The subject to publish to
            
        Raises:
            AuthError: If the tenant is not allowed to publish to the subject
        """
        if not self.check_publish_permission(tenant_id, subject):
            error_msg = f"Tenant {tenant_id} not authorized to publish to {subject}"
            logger.warning(error_msg)
            raise AuthError(error_msg)
    
    def validate_subscribe(self, tenant_id: str, subject: str) -> None:
        """
        Validate if a tenant can subscribe to a subject, raising an error if not allowed.
        
        Args:
            tenant_id: The tenant ID
            subject: The subject to subscribe to
            
        Raises:
            AuthError: If the tenant is not allowed to subscribe to the subject
        """
        if not self.check_subscribe_permission(tenant_id, subject):
            error_msg = f"Tenant {tenant_id} not authorized to subscribe to {subject}"
            logger.warning(error_msg)
            raise AuthError(error_msg)

# Global instance for convenience
nats_auth = TenantNATSAuth()