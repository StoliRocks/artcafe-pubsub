from fastapi import APIRouter

from .agent_routes import router as agent_router
from .ssh_key_routes import router as ssh_key_router
from .channel_routes import router as channel_router
from .tenant_routes import router as tenant_router
from .usage_routes import router as usage_router
from .auth_routes import router as auth_router
from .legal_routes import router as legal_router
from .websocket_routes import router as websocket_router
from .dashboard_websocket_routes import router as dashboard_websocket_router

# Create main router
router = APIRouter(prefix="/api/v1")

# Include all routers
router.include_router(agent_router)
router.include_router(ssh_key_router)
router.include_router(channel_router)
router.include_router(tenant_router)
router.include_router(usage_router)
router.include_router(auth_router)
router.include_router(legal_router)

# Include WebSocket routers with /ws prefix
router.include_router(websocket_router, prefix="/ws")
router.include_router(dashboard_websocket_router, prefix="/ws")

__all__ = ["router"]