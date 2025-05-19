"""
SSH authentication for agents directly from agent records
"""
import logging
import base64
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from api.services.agent_service import agent_service

logger = logging.getLogger(__name__)


class AgentSSHAuth:
    """Direct agent SSH authentication without separate SSH key records"""
    
    async def verify_agent_challenge(
        self,
        tenant_id: str,
        agent_id: str,
        challenge: str,
        response: str
    ) -> bool:
        """
        Verify a challenge response for an agent using its public key.
        
        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            challenge: Challenge string
            response: Signed challenge response (base64)
            
        Returns:
            True if response is valid, False otherwise
        """
        try:
            # Import ssh_key_manager to reuse parsing logic
            from auth.ssh_auth import ssh_key_manager
            
            # Get the agent
            agent = await agent_service.get_agent(tenant_id, agent_id)
            if not agent:
                logger.warning(f"Agent {agent_id} not found")
                return False
            
            # Check if agent has a public key
            if not agent.public_key:
                logger.warning(f"Agent {agent_id} has no public key")
                return False
            
            # Verify the signature using the agent's public key
            message = challenge.encode('utf-8')
            
            # Use the existing verify_signature method
            valid = ssh_key_manager.verify_signature(
                agent.public_key,
                message,  # Pass raw message, not digest
                base64.b64decode(response)
            )
            
            if valid:
                logger.info(f"Successfully verified signature for agent {agent_id}")
            else:
                logger.warning(f"Invalid signature for agent {agent_id}")
                
            return valid
            
        except Exception as e:
            logger.error(f"Error verifying agent challenge: {e}")
            return False


# Singleton instance
agent_ssh_auth = AgentSSHAuth()