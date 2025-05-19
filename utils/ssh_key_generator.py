"""
SSH Key Generator

Generates SSH keypairs for agent authentication
"""

import io
import logging
from typing import Tuple, Optional
from datetime import datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class SSHKeyGenerator:
    """Generates SSH keypairs for agents"""
    
    def generate_keypair(self, comment: str = "") -> Tuple[str, str]:
        """
        Generate an SSH keypair
        
        Args:
            comment: Optional comment for the key (e.g., agent name)
            
        Returns:
            Tuple of (private_key_pem, public_key_ssh)
        """
        try:
            # Generate RSA private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Generate private key in PEM format
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            # Generate public key in OpenSSH format
            public_key = private_key.public_key()
            public_ssh = public_key.public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH
            )
            
            # Add comment to public key if provided
            if comment:
                public_ssh_str = public_ssh.decode('utf-8')
                public_ssh = f"{public_ssh_str} {comment}".encode('utf-8')
            
            return private_pem.decode('utf-8'), public_ssh.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error generating SSH keypair: {e}")
            raise
    
    def generate_agent_keypair(self, agent_name: str, tenant_id: str) -> Tuple[str, str]:
        """
        Generate an SSH keypair specifically for an agent
        
        Args:
            agent_name: Name of the agent
            tenant_id: Tenant ID
            
        Returns:
            Tuple of (private_key_pem, public_key_ssh)
        """
        # Create a comment with agent info and timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        comment = f"artcafe_agent_{agent_name}_{tenant_id}_{timestamp}"
        
        return self.generate_keypair(comment)


# Global instance
ssh_key_generator = SSHKeyGenerator()