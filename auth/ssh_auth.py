import os
import base64
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

class SSHKeyManager:
    """
    Manager for SSH key operations.
    """
    
    def __init__(self):
        """Initialize SSH key manager."""
        pass
    
    def parse_public_key(self, public_key: str) -> Tuple[str, RSAPublicKey, str]:
        """
        Parse an OpenSSH format public key.
        
        Args:
            public_key: Public key in OpenSSH format
            
        Returns:
            Tuple of (key_type, public_key_obj, comment)
            
        Raises:
            ValueError: If key format is invalid
        """
        try:
            # Split key into components
            parts = public_key.strip().split()
            if len(parts) < 2:
                raise ValueError("Invalid SSH public key format")
            
            # Get key type and data
            key_type = parts[0]
            key_data = parts[1]
            
            # Get optional comment
            comment = " ".join(parts[2:]) if len(parts) > 2 else ""
            
            # Decode base64 key data
            decoded_data = base64.b64decode(key_data)
            
            # Parse public key
            public_key_obj = serialization.load_ssh_public_key(
                (key_type + " " + key_data).encode('utf-8'),
                backend=default_backend()
            )
            
            return key_type, public_key_obj, comment
        
        except Exception as e:
            logger.error(f"Error parsing SSH public key: {e}")
            raise ValueError(f"Invalid SSH public key: {e}")
    
    def calculate_fingerprint(self, public_key: str) -> str:
        """
        Calculate the fingerprint of an SSH public key.
        
        Args:
            public_key: Public key in OpenSSH format
            
        Returns:
            Key fingerprint
        """
        try:
            # Parse public key
            key_type, public_key_obj, comment = self.parse_public_key(public_key)
            
            # Get key in DER format
            der_data = public_key_obj.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            # Calculate SHA256 hash
            digest = hashlib.sha256(der_data).digest()
            
            # Format fingerprint
            b64_digest = base64.b64encode(digest).decode('utf-8').rstrip('=')
            
            return f"SHA256:{b64_digest}"
        
        except Exception as e:
            logger.error(f"Error calculating key fingerprint: {e}")
            raise ValueError(f"Invalid SSH public key: {e}")
    
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
            # Parse public key
            key_type, public_key_obj, comment = self.parse_public_key(public_key)
            
            # Verify signature
            public_key_obj.verify(
                signature,
                message,
                padding.PKCS1v15(),
                None
            )
            
            return True
        
        except InvalidSignature:
            logger.warning("Invalid signature")
            return False
        
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False