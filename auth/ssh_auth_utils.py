"""
SSH authentication utilities for agent WebSocket connections.
"""

from auth.ssh_auth import SSHKeyManager

# Create a global instance
ssh_key_manager = SSHKeyManager()


def verify_signed_challenge(challenge: str, signature: bytes, public_key: str) -> bool:
    """
    Verify a signed challenge using an agent's public key.
    
    Args:
        challenge: The challenge string that was signed
        signature: The signature bytes
        public_key: The agent's public SSH key
        
    Returns:
        True if the signature is valid
    """
    # Convert challenge to bytes for verification
    challenge_bytes = challenge.encode('utf-8')
    
    # Use the SSH key manager to verify
    return ssh_key_manager.verify_signature(public_key, challenge_bytes, signature)