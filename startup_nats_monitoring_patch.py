#!/usr/bin/env python3
"""
Patch to add NATS monitoring service to app startup
"""

# Add this import section after other imports
MONITORING_IMPORTS = '''
# NATS monitoring service
from api.services.nats_monitoring_service import nats_monitoring_service
from api.services.nats_heartbeat_handler import setup_heartbeat_subscription
'''

# Add this to the startup_event function after message tracker initialization
MONITORING_STARTUP = '''
    # Start NATS monitoring service
    try:
        logger.info("Starting NATS monitoring service...")
        await nats_monitoring_service.start()
        
        # Setup heartbeat subscription
        await setup_heartbeat_subscription(nats_monitoring_service, nats_manager)
        
        logger.info("NATS monitoring service started successfully")
    except Exception as e:
        logger.error(f"Failed to start NATS monitoring service: {e}")
        # Non-critical, continue startup
'''

# Add this to the shutdown_event function
MONITORING_SHUTDOWN = '''
    # Stop NATS monitoring service
    try:
        await nats_monitoring_service.stop()
        logger.info("NATS monitoring service stopped")
    except Exception as e:
        logger.error(f"Error stopping NATS monitoring service: {e}")
'''

# Print the patches
print("=== ADD IMPORTS ===")
print(MONITORING_IMPORTS)
print("\n=== ADD TO STARTUP ===")
print(MONITORING_STARTUP)
print("\n=== ADD TO SHUTDOWN ===")
print(MONITORING_SHUTDOWN)