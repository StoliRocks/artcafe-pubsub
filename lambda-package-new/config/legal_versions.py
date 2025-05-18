"""Legal document version tracking"""

from datetime import datetime

# Current versions - update these when terms change
CURRENT_TERMS_VERSION = "1.0"
CURRENT_PRIVACY_VERSION = "1.0"

# Version history for reference
VERSION_HISTORY = {
    "terms": {
        "1.0": {
            "effective_date": datetime(2025, 1, 15),
            "changes": "Initial terms of service"
        }
    },
    "privacy": {
        "1.0": {
            "effective_date": datetime(2025, 1, 15),
            "changes": "Initial privacy policy"
        }
    }
}

# Minimum required versions (for enforcement)
MINIMUM_REQUIRED_TERMS_VERSION = "1.0"
MINIMUM_REQUIRED_PRIVACY_VERSION = "1.0"

def is_version_current(doc_type: str, version: str) -> bool:
    """Check if a version is current"""
    if doc_type == "terms":
        return version == CURRENT_TERMS_VERSION
    elif doc_type == "privacy":
        return version == CURRENT_PRIVACY_VERSION
    return False

def is_version_acceptable(doc_type: str, version: str) -> bool:
    """Check if a version meets minimum requirements"""
    if doc_type == "terms":
        return version >= MINIMUM_REQUIRED_TERMS_VERSION
    elif doc_type == "privacy":
        return version >= MINIMUM_REQUIRED_PRIVACY_VERSION
    return False