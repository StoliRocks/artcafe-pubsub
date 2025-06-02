import logging
import uvicorn
import asyncio
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from .routes import router
from .middleware import setup_middleware
from .db import dynamodb
from nats_client import nats_manager
from .websocket import agent_router, dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Apply runtime boolean fix for DynamoDB
try:
    import complete_boolean_fix
    logger.info("Applied complete boolean fix for DynamoDB")
except Exception as e:
    logger.warning(f"Could not apply complete boolean fix: {e}")

# Create FastAPI app
app = FastAPI(
    title="ArtCafe.ai PubSub API",
    description="API for ArtCafe.ai PubSub service powering agent communication",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {"name": "Authentication", "description": "Authentication endpoints"},
        {"name": "Agents", "description": "Agent management endpoints"},
        {"name": "SSH Keys", "description": "SSH key management endpoints"},
        {"name": "Channels", "description": "Channel management endpoints"},
        {"name": "Tenant", "description": "Tenant management endpoints"},
        {"name": "Usage", "description": "Usage metrics and billing endpoints"},
    ],
)

# Set up middleware
setup_middleware(app)

# Include API routes
app.include_router(router)

# Include WebSocket routes with API prefix
app.include_router(agent_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")

# Add a simple test WebSocket for debugging
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

@app.websocket("/ws-test")
async def test_websocket(websocket: WebSocket):
    """Simple test WebSocket endpoint"""
    logger.info("[TEST] WebSocket connection attempt")
    
    try:
        await websocket.accept()
        logger.info("[TEST] WebSocket accepted")
        await websocket.send_text("Connected to test WebSocket!")
        
        while True:
            data = await websocket.receive_text()
            logger.info(f"[TEST] Received: {data}")
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        logger.error(f"[TEST] WebSocket error: {e}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ArtCafe.ai PubSub API",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "nats_connected": nats_manager._client is not None and nats_manager._client.is_connected
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Global exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


@app.on_event("startup")
async def startup_event():
    """Execute on application startup"""
    logger.info("Starting ArtCafe.ai PubSub API...")

    # Connect to NATS if enabled
    if settings.NATS_ENABLED:
        try:
            await nats_manager.connect()
            logger.info("Connected to NATS server")
        except Exception as e:
            logger.error(f"Failed to connect to NATS server: {e}")
    else:
        logger.info("NATS is disabled, skipping connection")

    # Ensure DynamoDB tables exist
    try:
        await dynamodb.ensure_tables_exist()
        logger.info("DynamoDB tables ready")
    except Exception as e:
        logger.error(f"Failed to ensure DynamoDB tables: {e}")

    # Start metrics service
    try:
        from infrastructure.metrics_service import metrics_service
        await metrics_service.start()
        logger.info("Metrics service started")
    except Exception as e:
        logger.error(f"Failed to start metrics service: {e}")

    # Initialize challenge store
    try:
        from infrastructure.challenge_store import challenge_store
        await challenge_store.ensure_table_exists()
        logger.info("Challenge store initialized")
    except Exception as e:
        logger.error(f"Failed to initialize challenge store: {e}")
    
    # Heartbeat checking is now handled internally by the websocket module
    
    # Start channel bridge service (for AWS WebSocket integration)
    try:
        from .services.channel_bridge_service import channel_bridge
        await channel_bridge.start()
        logger.info("Channel bridge service started")
    except Exception as e:
        logger.error(f"Failed to start channel bridge service: {e}")

    logger.info("ArtCafe.ai PubSub API started")


@app.on_event("shutdown")
async def shutdown_event():
    """Execute on application shutdown"""
    logger.info("Shutting down ArtCafe.ai PubSub API...")

    # Stop metrics service
    try:
        from infrastructure.metrics_service import metrics_service
        await metrics_service.stop()
        logger.info("Metrics service stopped")
    except Exception as e:
        logger.error(f"Failed to stop metrics service: {e}")
    
    # Stop channel bridge service
    try:
        from .services.channel_bridge_service import channel_bridge
        await channel_bridge.stop()
        logger.info("Channel bridge service stopped")
    except Exception as e:
        logger.error(f"Failed to stop channel bridge service: {e}")

    # Close NATS connection
    await nats_manager.close()

    logger.info("ArtCafe.ai PubSub API shutdown completed")


if __name__ == "__main__":
    # Run with uvicorn
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )