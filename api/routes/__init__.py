"""
API Routes initialization.

This module consolidates all API routes into a single router.
"""

from fastapi import APIRouter

# Import route modules
from .agent_routes import router as agent_router
from .ssh_key_routes import router as ssh_key_router
from .channel_routes import router as channel_router
from .tenant_routes import router as tenant_router
from .usage_routes import router as usage_router
from .auth_routes import router as auth_router
from .legal_routes import router as legal_router
from .billing_routes import router as billing_router

# Import WebSocket routers from the new consolidated module
from ..websocket import agent_router as agent_websocket_router
from ..websocket import dashboard_router as dashboard_websocket_router

# Create main router
router = APIRouter(prefix="/api/v1")

# Include all REST API routers
router.include_router(agent_router)
router.include_router(ssh_key_router)
router.include_router(channel_router)
router.include_router(tenant_router)
router.include_router(usage_router)
router.include_router(auth_router)
router.include_router(legal_router)
router.include_router(billing_router)

# Include WebSocket routers (they already have /api/v1 prefix)
agent_websocket_router.prefix = ""  # Remove prefix since it's already in the route
dashboard_websocket_router.prefix = ""  # Remove prefix since it's already in the route
router.include_router(agent_websocket_router)
router.include_router(dashboard_websocket_router)

__all__ = ["router"]