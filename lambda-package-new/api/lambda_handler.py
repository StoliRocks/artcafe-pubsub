import os
import json
import logging
from mangum import Mangum

from artcafe_pubsub.api.app import app

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create Mangum handler
handler = Mangum(app)

def lambda_function(event, context):
    """AWS Lambda handler function."""
    # Log the event for debugging
    logger.info(f"Event: {json.dumps(event)}")
    
    # Call the Mangum handler
    return handler(event, context)