from fastapi import APIRouter

from .agent_routes import router as agent_router
from .agent_auth_routes import router as agent_auth_router
from .ssh_key_routes import router as ssh_key_router
from .channel_routes import router as channel_router
from .tenant_routes import router as tenant_router
from .usage_routes import router as usage_router
from .auth_routes import router as auth_router
from .legal_routes import router as legal_router
from .billing_routes import router as billing_router
from .subscription_routes import router as subscription_router
# from .websocket_routes import router as websocket_router
from .agent_websocket import router as agent_websocket_router
from .dashboard_websocket_routes import router as dashboard_websocket_router

# Create main router
router = APIRouter(prefix="/api/v1")

# Include all routers
router.include_router(agent_router)
router.include_router(agent_auth_router)
router.include_router(ssh_key_router)
router.include_router(channel_router)
router.include_router(tenant_router)
router.include_router(usage_router)
router.include_router(auth_router)
router.include_router(legal_router)
router.include_router(billing_router)
router.include_router(subscription_router)

# Include WebSocket routers
router.include_router(agent_websocket_router)
router.include_router(dashboard_websocket_router)

__all__ = ["router"]