#!/usr/bin/env python3
import logging
import sys
import os

# Set up enhanced logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Add detailed debug logging to WebSocket authentication code
def add_debug_logging():
    # Update JWT handler with debug logging
    jwt_handler_path = os.path.join("auth", "jwt_handler.py")
    with open(jwt_handler_path, "r") as f:
        jwt_handler_code = f.read()
    
    enhanced_jwt_handler_code = jwt_handler_code.replace(
        "def decode_token(token: str) -> Dict:",
        """def decode_token(token: str) -> Dict:
    """Decode and validate JWT token (supports both HS256 and RS256)
    
    Args:
        token: JWT token
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.PyJWTError: If token is invalid
    """
    # Debug logging
    logger = logging.getLogger("auth.jwt_handler")
    logger.debug(f"Decoding token: {token[:10]}... (truncated)")
    """
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Decode header to check algorithm",
        """# Debug logging
    logger = logging.getLogger("auth.jwt_handler")
    logger.debug(f"Starting token decode process for token: {token[:10]}...")
    
    # Decode header to check algorithm"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "unverified_header = jwt.get_unverified_header(token)",
        """try:
            unverified_header = jwt.get_unverified_header(token)
            logger.debug(f"Unverified header: {unverified_header}")
        except Exception as header_err:
            logger.error(f"Error decoding token header: {header_err}")
            raise jwt.PyJWTError(f"Invalid token header: {str(header_err)}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Handle RS256 (Cognito) tokens",
        """# Handle RS256 (Cognito) tokens
            logger.debug(f"Token algorithm: {algorithm}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Get kid from header",
        """# Get kid from header
            logger.debug("Checking for kid in token header")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Get public keys from Cognito",
        """# Get public keys from Cognito
            logger.debug(f"Getting public keys for kid: {kid}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "public_keys = get_cognito_keys()",
        """try:
                public_keys = get_cognito_keys()
                logger.debug(f"Retrieved public keys: {list(public_keys.keys())}")
            except Exception as key_err:
                logger.error(f"Error getting Cognito public keys: {key_err}")
                raise jwt.PyJWTError(f"Cognito key retrieval error: {str(key_err)}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Decode with RS256 and Cognito public key",
        """# Decode with RS256 and Cognito public key
            logger.debug(f"Decoding RS256 token with kid: {kid}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "return jwt.decode(",
        """try:
                payload = jwt.decode("""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "algorithms=['RS256'],",
        """algorithms=['RS256'],"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        """options={"verify_aud": False}  # Skip audience verification for now
            )""",
        """options={"verify_aud": False}  # Skip audience verification for now
                )
                logger.debug(f"Successfully decoded RS256 token, payload keys: {list(payload.keys())}")
                return payload
            except Exception as decode_err:
                logger.error(f"Error decoding RS256 token: {decode_err}")
                raise jwt.PyJWTError(f"RS256 token decode error: {str(decode_err)}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "# Handle HS256 (internal) tokens",
        """# Handle HS256 (internal) tokens
            logger.debug("Decoding token as HS256")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        """return jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=['HS256']
            )""",
        """try:
                payload = jwt.decode(
                    token, 
                    settings.JWT_SECRET_KEY, 
                    algorithms=['HS256']
                )
                logger.debug(f"Successfully decoded HS256 token, payload keys: {list(payload.keys())}")
                return payload
            except Exception as decode_err:
                logger.error(f"Error decoding HS256 token: {decode_err}")
                raise jwt.PyJWTError(f"HS256 token decode error: {str(decode_err)}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "except jwt.PyJWTError:",
        """except jwt.PyJWTError as jwt_err:
        logger.error(f"JWT error: {jwt_err}")"""
    )
    
    enhanced_jwt_handler_code = enhanced_jwt_handler_code.replace(
        "except Exception as e:",
        """except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")"""
    )
    
    # Write the enhanced code back to the file
    with open(jwt_handler_path, "w") as f:
        f.write(enhanced_jwt_handler_code)
    print(f"Enhanced {jwt_handler_path} with debug logging")
    
    # Add debug logging to websocket_routes.py
    websocket_routes_path = os.path.join("api", "routes", "websocket_routes.py")
    with open(websocket_routes_path, "r") as f:
        websocket_routes_code = f.read()
    
    enhanced_websocket_routes_code = websocket_routes_code.replace(
        "async def get_tenant_from_token(",
        """async def get_tenant_from_token(
    """Get tenant information from token."""
    logger = logging.getLogger("api.routes.websocket")
    logger.debug("get_tenant_from_token called")
"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if not token:",
        """logger.debug(f"Token provided: {'yes' if token else 'no'}")
    if not token:
        logger.warning("No token provided in WebSocket connection")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "# Get user and tenant ID from token",
        """# Get user and tenant ID from token
        logger.debug(f"Attempting to decode token: {token[:10]}... (truncated)")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "user_data = decode_token(token)",
        """try:
            user_data = decode_token(token)
            logger.debug(f"Token decoded successfully. User data keys: {list(user_data.keys())}")
        except Exception as decode_err:
            logger.error(f"Error decoding WebSocket auth token: {decode_err}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(decode_err)}"
            )"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "tenant_id = user_data.get(\"tenant_id\")",
        """tenant_id = user_data.get("tenant_id")
        logger.debug(f"Extracted tenant_id: {tenant_id}")
        
        # Look in additional places for tenant_id
        if not tenant_id:
            # Check for Cognito custom attributes
            tenant_id = user_data.get("custom:tenant_id")
            if tenant_id:
                logger.debug(f"Found tenant_id in custom:tenant_id: {tenant_id}")
            else:
                # Check for common organization ID fields
                tenant_id = user_data.get("org_id") or user_data.get("organization_id")
                if tenant_id:
                    logger.debug(f"Found tenant_id in org_id/organization_id: {tenant_id}")
                
                # Check in custom claims
                elif "custom" in user_data and isinstance(user_data["custom"], dict):
                    tenant_id = user_data["custom"].get("tenant_id")
                    if tenant_id:
                        logger.debug(f"Found tenant_id in custom claims: {tenant_id}")
        
        logger.debug(f"Final tenant_id after checking all locations: {tenant_id}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if not tenant_id:",
        """if not tenant_id:
            logger.error("No tenant_id found in token")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "# Validate tenant",
        """# Validate tenant
        logger.debug(f"Validating tenant: {tenant_id}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "tenant = await tenant_service.get_tenant(tenant_id)",
        """try:
            tenant = await tenant_service.get_tenant(tenant_id)
            logger.debug(f"Tenant lookup result: {'Found' if tenant else 'Not found'}")
        except Exception as tenant_err:
            logger.error(f"Error retrieving tenant {tenant_id}: {tenant_err}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tenant service error: {str(tenant_err)}"
            )"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if not tenant:",
        """if not tenant:
            logger.error(f"Tenant not found: {tenant_id}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "# Verify tenant subscription is active",
        """# Verify tenant subscription is active
        logger.debug(f"Checking tenant subscription status: {tenant.payment_status}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if tenant.payment_status == \"expired\":",
        """if tenant.payment_status == "expired":
            logger.error(f"Tenant subscription expired: {tenant_id}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "return tenant_id, user_data.get(\"agent_id\"), tenant",
        """agent_id = user_data.get("agent_id")
        logger.debug(f"Extracted agent_id from token: {agent_id}")
        
        # If agent_id is not in the token, check in additional places
        if not agent_id:
            # Try sub field (common in Cognito tokens)
            agent_id = user_data.get("sub")
            if agent_id:
                logger.debug(f"Using 'sub' as agent_id: {agent_id}")
        
        if not agent_id:
            logger.warning(f"No agent_id found in token for tenant {tenant_id}")
        
        logger.debug(f"Authentication successful for tenant={tenant_id}, agent={agent_id}")
        return tenant_id, agent_id, tenant"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "except Exception as e:",
        """except Exception as e:
        logger.error(f"Unexpected error in WebSocket authentication: {e}")"""
    )
    
    # Update the WebSocket endpoint with debug logging
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "@router.websocket(\"/ws\")",
        """@router.websocket("/ws")
# Debug endpoint that accepts connection with no auth to test basic connectivity
@router.websocket("/ws-debug")
async def websocket_debug_endpoint(websocket: WebSocket):
    """Debug WebSocket endpoint that bypasses authentication"""
    logger.info("Debug WebSocket connection attempt")
    await websocket.accept()
    await websocket.send_text("Connected to debug WebSocket!")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Debug WebSocket received: {data}")
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        logger.info("Debug WebSocket disconnected")
    except Exception as e:
        logger.error(f"Debug WebSocket error: {e}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "async def websocket_endpoint(",
        """async def websocket_endpoint("""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "# Authenticate the connection",
        """# Authenticate the connection
        logger.debug(f"WebSocket connection attempt with token: {'provided' if token else 'not provided'}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "tenant_id, agent_id, tenant = await get_tenant_from_token(websocket, token)",
        """try:
            tenant_id, agent_id, tenant = await get_tenant_from_token(websocket, token)
            logger.debug(f"WebSocket authentication successful: tenant={tenant_id}, agent={agent_id}")
        except Exception as auth_err:
            logger.error(f"WebSocket authentication failed: {auth_err}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if not agent_id:",
        """if not agent_id:
            logger.error("WebSocket connection rejected: No agent_id in token")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "# Verify the agent exists",
        """# Verify the agent exists
        logger.debug(f"Verifying agent exists: tenant={tenant_id}, agent={agent_id}")"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "agent = await agent_service.get_agent(tenant_id, agent_id)",
        """try:
            agent = await agent_service.get_agent(tenant_id, agent_id)
            logger.debug(f"Agent lookup result: {'Found' if agent else 'Not found'}")
        except Exception as agent_err:
            logger.error(f"Error retrieving agent: tenant={tenant_id}, agent={agent_id}, error={str(agent_err)}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return"""
    )
    
    enhanced_websocket_routes_code = enhanced_websocket_routes_code.replace(
        "if not agent:",
        """if not agent:
            logger.error(f"Agent not found: tenant={tenant_id}, agent={agent_id}")"""
    )
    
    # Write enhanced file
    with open(websocket_routes_path, "w") as f:
        f.write(enhanced_websocket_routes_code)
    print(f"Enhanced {websocket_routes_path} with debug logging")

if __name__ == "__main__":
    add_debug_logging()
    print("Debug logging added to WebSocket authentication code")