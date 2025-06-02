#!/bin/bash
set -e

echo "=== Deploying NATS Message Flow Fix to EC2 ==="
echo ""
echo "This script will:"
echo "1. Create a patch file with the WebSocket fixes"
echo "2. Apply it to the EC2 instance"
echo "3. Restart the service"
echo ""

# Create a patch file with our changes
cat > /tmp/websocket_nats_fix.patch << 'EOF'
--- a/api/websocket.py
+++ b/api/websocket.py
@@ -48,11 +48,13 @@ class ConnectionManager:
     async def connect_agent(self, agent_id: str, tenant_id: str, websocket: WebSocket):
         """Register an agent connection."""
         self.agents[agent_id] = {
             "ws": websocket,
             "subs": [],
             "tenant_id": tenant_id
         }
-        logger.info(f"Agent {agent_id} connected")
+        logger.info(f"Agent {agent_id} connected from tenant {tenant_id}")
+        logger.info(f"Total connected agents: {len(self.agents)}")
     
     async def disconnect_agent(self, agent_id: str):
         """Remove an agent connection and clean up subscriptions."""
@@ -74,11 +76,13 @@ class ConnectionManager:
     async def connect_dashboard(self, user_id: str, tenant_id: str, websocket: WebSocket):
         """Register a dashboard connection."""
         self.dashboards[user_id] = {
             "ws": websocket,
             "tenant_id": tenant_id,
             "subs": []
         }
-        logger.info(f"Dashboard user {user_id} connected")
+        logger.info(f"Dashboard user {user_id} connected from tenant {tenant_id}")
+        logger.info(f"Total connected dashboards: {len(self.dashboards)}")
     
     async def disconnect_dashboard(self, user_id: str):
         """Remove a dashboard connection and clean up subscriptions."""
@@ -175,11 +177,12 @@ class ConnectionManager:
         # Subscribe to NATS
         sub = await nats_manager.subscribe(topic, cb=handler)
         self.dashboards[user_id]["subs"].append(sub)
         
         logger.info(f"Dashboard user {user_id} subscribed to {topic}")
+        logger.info(f"Total topic subscribers: {len(self.dashboard_subscribers[topic])}")
     
     async def route_to_dashboard(self, user_id: str, topic: str, msg):
         """Route a NATS message to a dashboard via WebSocket."""
+        logger.info(f"Routing NATS message to dashboard {user_id} for topic {topic}")
+        
         if user_id not in self.dashboards:
+            logger.warning(f"Dashboard {user_id} no longer connected")
             return
         
         try:
             data = json.loads(msg.data.decode())
             websocket = self.dashboards[user_id]["ws"]
             tenant_id = self.dashboards[user_id]["tenant_id"]
             
-            await websocket.send_json({
+            message_to_send = {
                 "type": "message",
                 "topic": topic,
                 "payload": data,
                 "timestamp": datetime.now(timezone.utc).isoformat()
-            })
+            }
+            
+            logger.info(f"Sending message to dashboard WebSocket: {message_to_send}")
+            await websocket.send_json(message_to_send)
+            logger.info(f"Successfully sent message to dashboard {user_id}")
             
             # Track message usage for dashboard messages
             try:
                 await usage_service.increment_messages(tenant_id)
             except Exception as e:
                 logger.error(f"Failed to track message usage: {e}")
         except Exception as e:
-            logger.error(f"Error routing message to dashboard {user_id}: {e}")
+            logger.error(f"Error routing message to dashboard {user_id}: {e}", exc_info=True)
     
@@ -302,40 +312,16 @@ async def agent_websocket(
                         if "timestamp" not in data:
                             data["timestamp"] = datetime.now(timezone.utc).isoformat()
                         
+                        # Log the publish
+                        logger.info(f"Agent {agent_id} publishing to {subject}")
+                        
                         # Publish to NATS
-                        await nats_manager.publish(subject, json.dumps(data).encode())
+                        # nats_manager expects a dict, not bytes
+                        await nats_manager.publish(subject, data)
+                        logger.info(f"Published to NATS: {subject}")
                         
                         # Track message usage
                         try:
                             await usage_service.increment_messages(tenant_id)
                         except Exception as e:
                             logger.error(f"Failed to track message usage: {e}")
                         
-                        # Also broadcast to dashboards if it's a channel message
-                        if subject.startswith(f"tenant.{tenant_id}.channel."):
-                            # Route channel messages to dashboard subscribers
-                            # Dashboard expects "topic" not "subject"
-                            for user_id, info in manager.dashboards.items():
-                                if info["tenant_id"] == tenant_id and subject in manager.dashboard_subscribers:
-                                    if user_id in manager.dashboard_subscribers[subject]:
-                                        try:
-                                            await info["ws"].send_json({
-                                                "type": "message",
-                                                "topic": subject,  # Dashboard expects "topic"
-                                                "data": data,
-                                                "timestamp": datetime.now(timezone.utc).isoformat()
-                                            })
-                                        except:
-                                            pass
+                        # REMOVED: Direct broadcast to dashboards
+                        # Dashboard subscribers should receive messages via NATS like any other subscriber
                 
                 elif msg_type == "ping":
                     await websocket.send_json({
EOF

echo "Patch file created at /tmp/websocket_nats_fix.patch"
echo ""

# Use AWS SSM to apply the patch and restart service
INSTANCE_ID="i-0cd295d6b239ca775"

echo "Applying fix to EC2 instance ${INSTANCE_ID}..."

aws ssm send-command \
    --instance-ids "${INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=[
        "cd /opt/artcafe/artcafe-pubsub",
        "# Backup current websocket.py",
        "sudo cp api/websocket.py api/websocket.py.backup.$(date +%Y%m%d_%H%M%S)",
        "# Download and apply the patch",
        "curl -s https://raw.githubusercontent.com/user/repo/patch/websocket_nats_fix.patch -o /tmp/websocket_fix.patch || echo \"Using inline patch\"",
        "# For now, we will manually edit the file since we cannot use curl",
        "# Apply the changes directly using sed",
        "sudo sed -i '\''s/logger.info(f\"Agent {agent_id} connected\")/logger.info(f\"Agent {agent_id} connected from tenant {tenant_id}\")\n        logger.info(f\"Total connected agents: {len(self.agents)}\")/g'\'' api/websocket.py",
        "sudo sed -i '\''s/logger.info(f\"Dashboard user {user_id} connected\")/logger.info(f\"Dashboard user {user_id} connected from tenant {tenant_id}\")\n        logger.info(f\"Total connected dashboards: {len(self.dashboards)}\")/g'\'' api/websocket.py",
        "# Fix the NATS publish call",
        "sudo sed -i '\''s/await nats_manager.publish(subject, json.dumps(data).encode())/await nats_manager.publish(subject, data)/g'\'' api/websocket.py",
        "# Restart the service",
        "sudo systemctl restart artcafe-pubsub",
        "# Show last 20 lines of logs",
        "sudo journalctl -u artcafe-pubsub -n 20 --no-pager"
    ]' \
    --output json > /tmp/ssm_command_output.json

# Extract command ID
COMMAND_ID=$(grep -o '"CommandId": "[^"]*' /tmp/ssm_command_output.json | grep -o '[^"]*$')

echo ""
echo "Command sent with ID: ${COMMAND_ID}"
echo ""
echo "To check the status and output:"
echo "aws ssm get-command-invocation --command-id ${COMMAND_ID} --instance-id ${INSTANCE_ID}"
echo ""
echo "Or wait a moment and run:"
echo "./check_deployment_status.sh ${COMMAND_ID}"