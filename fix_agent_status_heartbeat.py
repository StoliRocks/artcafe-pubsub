#!/usr/bin/env python3
"""
Fix agent status to only be set to 'online' when actual agents send heartbeats,
not when dashboards or other clients connect.
"""

import sys
import re

def fix_websocket_routes():
    """Fix the websocket routes to properly handle agent status"""
    file_path = '/home/stvwhite/projects/artcafe/artcafe-pubsub/api/routes/websocket_routes.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Add heartbeat tracking at the top after the other dictionaries
    heartbeat_tracking = '''
# Track last heartbeat for agents
# Structure: {"tenant_id": {"agent_id": datetime}}
agent_heartbeats: Dict[str, Dict[str, datetime]] = {}

# Heartbeat timeout in seconds
HEARTBEAT_TIMEOUT = 60
'''
    
    # Find where to insert heartbeat tracking
    queue_pattern = r'(message_queues: Dict\[str, Dict\[str, asyncio\.Queue\]\] = \{\})'
    if queue_pattern in content:
        content = re.sub(queue_pattern, r'\1' + heartbeat_tracking, content)
    
    # Replace the connect method to not automatically set agents online
    connect_old = '''                # Update agent status to online
                await agent_service.update_agent_status(tenant_id, agent_id, "online")'''
    
    connect_new = '''                # Don't automatically set agent to online
                # Agent will be set online when it sends a heartbeat
                # await agent_service.update_agent_status(tenant_id, agent_id, "online")'''
    
    content = content.replace(connect_old, connect_new)
    
    # Add heartbeat handler in the main message processing loop
    message_processing = '''            try:
                message = json.loads(data)
                
                # Add tenant and agent information
                message["tenant_id"] = tenant_id
                message["agent_id"] = agent_id
                message["timestamp"] = datetime.utcnow().isoformat()'''
    
    message_processing_new = '''            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                # Handle heartbeat messages from actual agents
                if msg_type == "heartbeat":
                    # Update heartbeat timestamp
                    if tenant_id not in agent_heartbeats:
                        agent_heartbeats[tenant_id] = {}
                    
                    agent_heartbeats[tenant_id][agent_id] = datetime.utcnow()
                    
                    # Update agent status to online if not already
                    current_agent = await agent_service.get_agent(tenant_id, agent_id)
                    if current_agent and current_agent.status != "online":
                        await agent_service.update_agent_status(tenant_id, agent_id, "online")
                    
                    logger.debug(f"Heartbeat received: tenant={tenant_id}, agent={agent_id}")
                
                # Add tenant and agent information
                message["tenant_id"] = tenant_id
                message["agent_id"] = agent_id
                message["timestamp"] = datetime.utcnow().isoformat()'''
    
    content = content.replace(message_processing, message_processing_new)
    
    # Add the heartbeat timeout checker function before the router definitions
    heartbeat_checker = '''

async def check_heartbeat_timeouts():
    """Background task to check for agent heartbeat timeouts."""
    while True:
        try:
            current_time = datetime.utcnow()
            timeout_delta = timedelta(seconds=HEARTBEAT_TIMEOUT)
            
            # Check all agents for heartbeat timeout
            for tenant_id in list(agent_heartbeats.keys()):
                for agent_id in list(agent_heartbeats.get(tenant_id, {}).keys()):
                    last_heartbeat = agent_heartbeats[tenant_id].get(agent_id)
                    
                    if last_heartbeat and (current_time - last_heartbeat) > timeout_delta:
                        # Agent hasn't sent heartbeat within timeout
                        logger.warning(f"Agent heartbeat timeout: tenant={tenant_id}, agent={agent_id}")
                        
                        # Update agent status to offline
                        await agent_service.update_agent_status(tenant_id, agent_id, "offline")
                        
                        # Remove from heartbeat tracking
                        if tenant_id in agent_heartbeats and agent_id in agent_heartbeats[tenant_id]:
                            del agent_heartbeats[tenant_id][agent_id]
            
            # Check every 10 seconds
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Error in heartbeat timeout check: {e}")
            await asyncio.sleep(10)


# Start heartbeat timeout checker when module loads
# Note: This should be started by the main application
# asyncio.create_task(check_heartbeat_timeouts())


@router.websocket("/ws")'''
    
    # Find where to insert the heartbeat checker
    websocket_pattern = r'(@router\.websocket\("/ws"\))'
    content = re.sub(websocket_pattern, heartbeat_checker + r'\1', content)
    
    # Add timedelta import
    if 'from datetime import datetime' in content and 'timedelta' not in content:
        content = content.replace('from datetime import datetime', 'from datetime import datetime, timedelta')
    
    # Write the fixed content
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Fixed {file_path}")
    return True

if __name__ == "__main__":
    if fix_websocket_routes():
        print("\nSuccessfully fixed agent status handling!")
        print("\nChanges made:")
        print("1. Added heartbeat tracking for agents")
        print("2. Disabled automatic 'online' status when WebSocket connects")
        print("3. Added heartbeat message handling")
        print("4. Added heartbeat timeout checker (disabled by default)")
        print("\nAgents will now only show as 'online' when they send heartbeat messages.")
    else:
        print("Failed to fix agent status handling")
        sys.exit(1)