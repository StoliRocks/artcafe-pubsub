"""
Agent API Key Authentication

Provides authentication using agent API keys (ak_* format)
"""

import logging
from typing import Optional, Dict
from datetime import timedelta

from api.db import dynamodb
from config.settings import settings
from auth.jwt_handler import create_access_token

logger = logging.getLogger(__name__)


class AgentKeyAuth:
    """Handler for agent API key authentication"""
    
    async def authenticate_agent_key(self, api_key: str) -> Optional[Dict]:
        """
        Authenticate an agent using API key
        
        Args:
            api_key: Agent API key (format: ak_*)
            
        Returns:
            Dict with agent info and JWT token, or None if authentication fails
        """
        try:
            if not api_key or not api_key.startswith("ak_"):
                logger.warning(f"Invalid API key format: {api_key[:8]}...")
                return None
            
            # Query agents by public_key (which stores the ak_ key)
            # Note: This requires a GSI on public_key or a scan operation
            result = await dynamodb.scan_items(
                table_name=settings.AGENT_TABLE_NAME,
                filter_expression="public_key = :key",
                expression_values={":key": api_key}
            )
            
            if not result["items"]:
                logger.warning(f"No agent found for key: {api_key[:8]}...")
                return None
            
            agent = result["items"][0]
            
            # Create JWT token for the agent
            token_data = {
                "sub": agent["id"],
                "tenant_id": agent["tenant_id"],
                "agent_id": agent["id"],
                "scopes": "agent:pubsub",
                "token_type": "agent"
            }
            
            # Create JWT token with 24 hour expiration
            token = create_access_token(
                data=token_data,
                expires_delta=timedelta(hours=24)
            )
            
            return {
                "agent_id": agent["id"],
                "tenant_id": agent["tenant_id"],
                "token": token,
                "token_type": "bearer"
            }
            
        except Exception as e:
            logger.error(f"Error authenticating agent key: {e}")
            return None


# Global instance
agent_key_auth = AgentKeyAuth()