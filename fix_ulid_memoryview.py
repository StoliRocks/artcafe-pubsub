#!/usr/bin/env python3
"""
Fix for ULID MemoryView issue. This script patches the tenant service to use
UUID instead of ULID if ULID is having compatibility issues.
"""

import os
import sys

tenant_service_path = sys.argv[1] if len(sys.argv) > 1 else '/opt/artcafe/artcafe-pubsub/api/services/tenant_service.py'

# Read the current tenant service
with open(tenant_service_path, 'r') as f:
    content = f.read()

# Replace ULID imports and usage with UUID
replacements = [
    ('import ulid', 'import uuid'),
    ('str(ulid.new())', 'str(uuid.uuid4())'),
    ('ulid.new().str.lower()', 'str(uuid.uuid4()).lower()')
]

for old, new in replacements:
    content = content.replace(old, new)

# Write the patched version
with open(tenant_service_path + '.patched', 'w') as f:
    f.write(content)

print(f"Created patched version at {tenant_service_path}.patched")
print("File has been patched to use UUID instead of ULID")