import json
import logging

logger = logging.getLogger(__name__)

def fix_boolean_for_dynamodb(data: dict) -> dict:
    """Convert boolean values to numeric for DynamoDB"""
    logger.info(f"Before fix: {json.dumps(data, default=str)}")
    
    if 'active' in data and isinstance(data['active'], bool):
        data['active'] = 1 if data['active'] else 0
    
    # Check for other boolean fields
    for key, value in data.items():
        if isinstance(value, bool):
            logger.warning(f"Found boolean field '{key}' with value {value}")
            if key != 'active':  # Already handled above
                data[key] = 1 if value else 0
    
    logger.info(f"After fix: {json.dumps(data, default=str)}")
    return data