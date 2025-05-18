#!/usr/bin/env python3
"""
Direct boolean fix - modifies the tenant service directly
"""

# Find and replace the problematic permissions dictionary in tenant_service.py
import fileinput
import sys
import re

def apply_fix():
    file_path = "/opt/artcafe/artcafe-pubsub/api/services/tenant_service.py"
    
    # Pattern to find permissions dictionary with boolean values
    pattern1 = r'"permissions": {\s*"read": True'
    replacement1 = '"permissions": {\n                "read": 1'
    
    pattern2 = r'"write": True'
    replacement2 = '"write": 1'
    
    pattern3 = r'"publish": True'
    replacement3 = '"publish": 1'
    
    pattern4 = r'"subscribe": True'
    replacement4 = '"subscribe": 1'
    
    pattern5 = r'"manage": True'
    replacement5 = '"manage": 1'
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Apply all replacements
        content = re.sub(pattern1, replacement1, content)
        content = re.sub(pattern2, replacement2, content)
        content = re.sub(pattern3, replacement3, content)
        content = re.sub(pattern4, replacement4, content)
        content = re.sub(pattern5, replacement5, content)
        
        # Also fix False values
        content = content.replace('"read": False', '"read": 0')
        content = content.replace('"write": False', '"write": 0')
        content = content.replace('"publish": False', '"publish": 0')
        content = content.replace('"subscribe": False', '"subscribe": 0')
        content = content.replace('"manage": False', '"manage": 0')
        
        # Fix other boolean values
        content = content.replace(' True,', ' 1,')
        content = content.replace(' False,', ' 0,')
        content = content.replace(':True,', ':1,')
        content = content.replace(':False,', ':0,')
        content = content.replace(': True,', ': 1,')
        content = content.replace(': False,', ': 0,')
        content = content.replace(' True}', ' 1}')
        content = content.replace(' False}', ' 0}')
        content = content.replace(':True}', ':1}')
        content = content.replace(':False}', ':0}')
        content = content.replace(': True}', ': 1}')
        content = content.replace(': False}', ': 0}')
        
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f"Fixed boolean values in {file_path}")
        return True
    except Exception as e:
        print(f"Error applying fix: {e}")
        return False

if __name__ == "__main__":
    apply_fix()