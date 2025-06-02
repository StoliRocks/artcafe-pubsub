#!/bin/bash

echo "Fixing SSH signature verification error..."

# Check if the fix was applied correctly
echo "Checking ssh_auth.py..."
if grep -q "hashes.SHA256()" /home/stvwhite/projects/artcafe/artcafe-pubsub/auth/ssh_auth.py; then
    echo "✓ ssh_auth.py has been fixed"
else
    echo "✗ ssh_auth.py fix not applied correctly"
    exit 1
fi

# Check that we're not passing pre-hashed digest
if grep -q "digest_bytes" /home/stvwhite/projects/artcafe/artcafe-pubsub/auth/ssh_auth.py; then
    echo "✗ ssh_auth.py still has digest_bytes reference"
    exit 1
else
    echo "✓ ssh_auth.py no longer uses pre-hashed digest"
fi

echo "Checking ssh_auth.py.fixed..."
if grep -q "hashes.SHA256()" /home/stvwhite/projects/artcafe/artcafe-pubsub/auth/ssh_auth.py.fixed; then
    echo "✓ ssh_auth.py.fixed has been fixed"
else
    echo "✗ ssh_auth.py.fixed fix not applied correctly"
    exit 1
fi

echo ""
echo "SSH signature verification fix has been applied successfully!"
echo ""
echo "The changes made:"
echo "1. Fixed verify_signature() to pass hashes.SHA256() instead of None"
echo "2. Fixed verify_challenge_response() to pass raw message instead of pre-hashed digest"
echo ""
echo "To deploy these changes:"
echo "1. Restart the artcafe-pubsub service: sudo systemctl restart artcafe-pubsub"
echo "2. Or if running locally: restart the application"