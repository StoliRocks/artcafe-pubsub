import os
import fileinput

# Add OPTIONS method to WebSocket routes
route_file = "/opt/artcafe/artcafe-pubsub/api/routes/dashboard_websocket_routes.py"

# Read the file and find the websocket decorator
with open(route_file, 'r') as f:
    content = f.read()

# Add OPTIONS handling before the websocket endpoint
updated_content = content.replace(
    '@router.websocket("/dashboard")',
    '''@router.options("/dashboard")
async def websocket_options():
    """Handle OPTIONS request for WebSocket endpoint"""
    return {"message": "OK"}

@router.websocket("/dashboard")'''
)

# Also ensure we handle proxy headers
updated_content = updated_content.replace(
    'async def websocket_endpoint(',
    '''async def websocket_endpoint('''
)

# Write back the file
with open(route_file, 'w') as f:
    f.write(updated_content)

print("Updated WebSocket route to handle OPTIONS")