import os
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

# Imported at usage point to avoid circular import

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
                hashes.SHA256()  # Specify the hash algorithm
            )
            
            return True
        
        except InvalidSignature:
            logger.warning("Invalid signature")
            return False
        
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    async def generate_challenge(self, tenant_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a challenge for SSH key authentication.

        Args:
            tenant_id: Tenant ID
            agent_id: Optional agent ID

        Returns:
            Dict with challenge data
        """
        try:
            # Import here to avoid circular imports
            from infrastructure.challenge_store import challenge_store
            
            # Ensure challenge table exists
            await challenge_store.ensure_table_exists()
            
            # Generate a random challenge
            challenge = secrets.token_hex(32)
            
            # Store the challenge in DynamoDB with TTL
            challenge_data = await challenge_store.store_challenge(
                tenant_id=tenant_id,
                challenge=challenge,
                agent_id=agent_id
            )
            
            # Return challenge data to client
            return {
                "tenant_id": tenant_id,
                "challenge": challenge,
                "expires_at": challenge_data["expires_at"],
                "agent_id": agent_id
            }
            
        except Exception as e:
            logger.error(f"Error generating challenge: {e}")
            raise

    def _check_challenge_expiry(self, expires_at_str: str) -> bool:
        """
        Check if a challenge has expired.

        Args:
            expires_at_str: ISO formatted expiration time

        Returns:
            True if challenge is still valid, False if expired
        """
        try:
            # Parse the expiration time
            expires_at = datetime.fromisoformat(expires_at_str)
            
            # Check if challenge has expired
            now = datetime.utcnow()
            return now < expires_at
        except Exception as e:
            logger.error(f"Error checking challenge expiry: {e}")
            return False

    async def _retrieve_challenge(self, tenant_id: str, challenge: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve challenge data from the persistent store.
        
        Args:
            tenant_id: Tenant ID
            challenge: Challenge string
            
        Returns:
            Challenge data or None if not found
        """
        # Import here to avoid circular imports
        from infrastructure.challenge_store import challenge_store
        
        # Get the challenge from the store
        challenge_data = await challenge_store.get_challenge(tenant_id, challenge)
        
        # Return None if the challenge is not found or has expired
        if not challenge_data:
            logger.warning(f"Challenge not found or expired: tenant={tenant_id}, challenge={challenge}")
            return None
        
        return challenge_data

    async def verify_challenge_response(
        self,
        tenant_id: str,
        key_id: str,
        challenge: str,
        response: str,
        agent_id: Optional[str] = None
    ) -> bool:
        """
        Verify a challenge response.

        Args:
            tenant_id: Tenant ID
            key_id: SSH key ID
            challenge: Challenge string
            response: Signed challenge response
            agent_id: Optional agent ID

        Returns:
            True if response is valid, False otherwise
        """
        try:
            # Retrieve challenge from persistent store
            challenge_data = await self._retrieve_challenge(tenant_id, challenge)
            if not challenge_data:
                logger.warning(f"Challenge not found for tenant {tenant_id}")
                return False
            
            # Verify challenge expiry
            if not self._check_challenge_expiry(challenge_data["expires_at"]):
                logger.warning(f"Challenge has expired for tenant {tenant_id}")
                return False
            
            # Verify tenant matches
            if challenge_data["tenant_id"] != tenant_id:
                logger.warning(f"Challenge tenant ID mismatch: {challenge_data['tenant_id']} != {tenant_id}")
                return False
            
            # Verify agent ID if provided
            if agent_id and challenge_data.get("agent_id") and challenge_data["agent_id"] != agent_id:
                logger.warning(f"Challenge agent ID mismatch: {challenge_data.get('agent_id')} != {agent_id}")
                return False

            # Get the SSH key
            from api.services.ssh_key_service import ssh_key_service
            ssh_key = await ssh_key_service.get_ssh_key(tenant_id, key_id)
            if not ssh_key:
                logger.warning(f"SSH key {key_id} not found")
                return False

            # If agent_id is provided, verify it matches the key
            if agent_id and ssh_key.agent_id and ssh_key.agent_id != agent_id:
                logger.warning(f"SSH key {key_id} does not belong to agent {agent_id}")
                return False

            # Check if key is revoked
            if ssh_key.revoked:
                logger.warning(f"SSH key {key_id} is revoked")
                return False
            
            # Check if key is active
            if ssh_key.status != "active":
                logger.warning(f"SSH key {key_id} is not active: {ssh_key.status}")
                return False

            # Verify the signature
            message = challenge.encode('utf-8')
            
            valid = self.verify_signature(
                ssh_key.public_key,
                message,  # Pass the raw message, not the digest
                base64.b64decode(response)
            )

            if valid:
                # Import here to avoid circular imports
                from infrastructure.challenge_store import challenge_store
                
                # Delete the challenge after successful verification (one-time use)
                await challenge_store.delete_challenge(tenant_id, challenge)
                
                # Update last_used timestamp
                from api.services.ssh_key_service import ssh_key_service
                await ssh_key_service.update_ssh_key_usage(tenant_id, key_id)

            return valid

        except Exception as e:
            logger.error(f"Error verifying challenge response: {e}")
            return False


# Singleton instance
ssh_key_manager = SSHKeyManager()