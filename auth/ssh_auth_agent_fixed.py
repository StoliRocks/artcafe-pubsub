"""
SSH authentication for agents directly from agent records
"""
import logging
import base64
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from api.services.agent_service import agent_service

logger = logging.getLogger(__name__)


class AgentSSHAuth:
    """Direct agent SSH authentication without separate SSH key records"""
    
    def verify_signature(self, public_key: str, message: bytes, signature: bytes) -> bool:
        """
        Verify a signature using an SSH public key.
        
        Args:
            public_key: Public key in OpenSSH format
            message: Message that was signed
            signature: Signature to verify
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Import ssh_key_manager to reuse parsing logic
            from auth.ssh_auth import ssh_key_manager
            
            # Parse the public key
            key_type, public_key_obj, comment = ssh_key_manager.parse_public_key(public_key)
            
            # For RSA keys, verify with SHA256
            if isinstance(public_key_obj, rsa.RSAPublicKey):
                public_key_obj.verify(
                    signature,
                    message,
                    padding.PKCS1v15(),
                    hashes.SHA256()  # Specify the hash algorithm
                )
            else:
                # For other key types, use the appropriate algorithm
                public_key_obj.verify(
                    signature,
                    message,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
            
            return True
        
        except InvalidSignature:
            logger.warning("Invalid signature")
            return False
        
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
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
            
            # Use the local verify_signature method
            valid = self.verify_signature(
                agent.public_key,
                message,  # Pass raw message
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