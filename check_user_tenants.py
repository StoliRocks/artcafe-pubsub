#!/usr/bin/env python3
"""Check if a user has tenant associations."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.services.user_tenant_service import user_tenant_service

async def check_user_tenants(user_id: str):
    """Check user tenant associations."""
    print(f"Checking tenants for user: {user_id}")
    
    try:
        # Get user's tenants
        tenants = await user_tenant_service.get_user_tenants(user_id)
        
        if tenants:
            print(f"Found {len(tenants)} tenant(s):")
            for tenant in tenants:
                print(f"  - Tenant ID: {tenant.tenant_id}")
                print(f"    Role: {tenant.role}")
                print(f"    Status: {tenant.status}")
                print(f"    Created: {tenant.created_at}")
        else:
            print("No tenants found for this user")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # The user ID from the JWT token
    user_id = "f45854d8-20a1-70b8-a608-0d8bfd5f2cfc"
    asyncio.run(check_user_tenants(user_id))