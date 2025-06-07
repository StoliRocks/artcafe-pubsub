"""
API Routes initialization.

This module consolidates all API routes into a single router.
"""

from fastapi import APIRouter

# Import NEW route modules (NKey-based)
from .account_routes import router as account_router
from .client_routes import router as client_router

# Import EXISTING route modules (to be migrated)
from .agent_routes import router as agent_router
from .ssh_key_routes import router as ssh_key_router
from .channel_routes import router as channel_router
from .tenant_routes import router as tenant_router
from .usage_routes import router as usage_router
from .usage_routes_local import router as usage_local_router
from .auth_routes import router as auth_router
from .legal_routes import router as legal_router
from .billing_routes import router as billing_router
from .profile_routes import router as profile_router
from .activity_routes import router as activity_router

# Import WebSocket routers from the new consolidated module
from ..websocket import agent_router as agent_websocket_router
from ..websocket import dashboard_router as dashboard_websocket_router

# Create main router
router = APIRouter(prefix="/api/v1")

# Include NEW NKey-based routers
router.include_router(account_router)
router.include_router(client_router)

# Include EXISTING routers (for compatibility during migration)
router.include_router(agent_router)
router.include_router(ssh_key_router)
router.include_router(channel_router)
router.include_router(tenant_router)
router.include_router(usage_router)
router.include_router(usage_local_router)
router.include_router(auth_router)
router.include_router(legal_router)
router.include_router(billing_router)
router.include_router(profile_router)
router.include_router(activity_router)

# Include WebSocket routers (they already have /api/v1 prefix)
agent_websocket_router.prefix = ""  # Remove prefix since it's already in the route
dashboard_websocket_router.prefix = ""  # Remove prefix since it's already in the route
router.include_router(agent_websocket_router)
router.include_router(dashboard_websocket_router)

__all__ = ["router"]