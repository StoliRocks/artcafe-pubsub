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
from nats import nats_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ArtCafe.ai PubSub API",
    description="API for ArtCafe.ai PubSub service",
    version="1.0.0",
)

# Set up middleware
setup_middleware(app)

# Include API routes
app.include_router(router)


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
    
    # Connect to NATS
    try:
        await nats_manager.connect()
        logger.info("Connected to NATS server")
    except Exception as e:
        logger.error(f"Failed to connect to NATS server: {e}")
        
    # Ensure DynamoDB tables exist
    try:
        await dynamodb.ensure_tables_exist()
        logger.info("DynamoDB tables ready")
    except Exception as e:
        logger.error(f"Failed to ensure DynamoDB tables: {e}")
        
    logger.info("ArtCafe.ai PubSub API started")


@app.on_event("shutdown")
async def shutdown_event():
    """Execute on application shutdown"""
    logger.info("Shutting down ArtCafe.ai PubSub API...")
    
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