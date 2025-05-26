#!/bin/bash
# Cleanup old WebSocket implementations

echo "Backing up old WebSocket files..."
mkdir -p /tmp/artcafe_websocket_backup
cp api/routes/websocket_routes.py /tmp/artcafe_websocket_backup/ 2>/dev/null || true
cp api/routes/agent_websocket_routes.py /tmp/artcafe_websocket_backup/ 2>/dev/null || true
cp api/routes/dashboard_websocket_routes.py /tmp/artcafe_websocket_backup/ 2>/dev/null || true
cp api/routes/agent_websocket.py /tmp/artcafe_websocket_backup/ 2>/dev/null || true

echo "Removing old WebSocket implementations..."
rm -f api/routes/websocket_routes.py
rm -f api/routes/agent_websocket_routes.py
rm -f api/routes/dashboard_websocket_routes.py
rm -f api/routes/agent_websocket.py
rm -f api/routes/websocket_routes_*.py
rm -f api/routes/agent_websocket_routes_*.py

echo "Cleanup complete. Backups saved to /tmp/artcafe_websocket_backup/"