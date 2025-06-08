"""
Monkey patch to add the missing nkeys functions
This adds compatibility for code expecting create_user_seed() and create_account_seed()
"""

import nkeys
import secrets
import base64

def _encode_raw_seed(prefix_byte):
    """Generate a proper nkeys seed with the correct format"""
    # Generate 32-byte random seed
    raw_seed = secrets.token_bytes(32)
    
    # Create the full seed with proper prefix encoding
    # First byte is PREFIX_BYTE_SEED (144)
    # Second byte encodes the key type in a special format
    b1 = nkeys.PREFIX_BYTE_SEED
    b2 = prefix_byte >> 5
    b3 = (prefix_byte & 31) << 3
    
    # Combine prefix and raw seed
    full_seed = bytes([b1, b2 | b3]) + raw_seed
    
    # Calculate CRC16 checksum
    checksum = nkeys.crc16_checksum(full_seed)
    
    # Append checksum
    full_seed_with_checksum = full_seed + checksum
    
    # Base32 encode
    encoded = base64.b32encode(full_seed_with_checksum).decode('ascii')
    
    # Remove padding
    return encoded.rstrip('=').encode('utf-8')

def create_user_seed():
    """Generate a new user NKey seed"""
    return _encode_raw_seed(nkeys.PREFIX_BYTE_USER)

def create_account_seed():
    """Generate a new account NKey seed"""
    return _encode_raw_seed(nkeys.PREFIX_BYTE_ACCOUNT)

# Add these functions to the nkeys module
nkeys.create_user_seed = create_user_seed
nkeys.create_account_seed = create_account_seed