import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from config.settings import settings


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging request/response information"""
    
    async def dispatch(self, request: Request, call_next):
        """Process request and log information"""
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Extract request info
        method = request.method
        path = request.url.path
        status_code = response.status_code
        
        # Log request info
        print(f"{method} {path} {status_code} {process_time:.3f}s")
        
        return response


def setup_middleware(app):
    """Set up middleware for the application"""
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins in development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Request logging
    app.add_middleware(RequestLoggingMiddleware)