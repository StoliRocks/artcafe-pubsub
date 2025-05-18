#!/bin/bash

# Script to set up Nginx with SSL for ArtCafe API including WebSocket support

set -e

echo "Setting up Nginx with SSL for ArtCafe API..."

# Update system packages
sudo apt update

# Install Nginx and Certbot
echo "Installing Nginx and Certbot..."
sudo apt install -y nginx certbot python3-certbot-nginx

# Stop Nginx temporarily
sudo systemctl stop nginx

# Get SSL certificate from Let's Encrypt
echo "Obtaining SSL certificate for api.artcafe.ai..."
sudo certbot certonly --standalone -d api.artcafe.ai \
    --non-interactive \
    --agree-tos \
    --email admin@artcafe.ai \
    --no-eff-email

# Copy Nginx configuration
echo "Installing Nginx configuration..."
sudo cp /opt/artcafe/artcafe-pubsub/infrastructure/nginx-websocket-config.conf \
    /etc/nginx/sites-available/artcafe-api

# Enable the site
sudo ln -s /etc/nginx/sites-available/artcafe-api /etc/nginx/sites-enabled/

# Remove default site if it exists
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
echo "Testing Nginx configuration..."
sudo nginx -t

# Start Nginx
echo "Starting Nginx..."
sudo systemctl start nginx
sudo systemctl enable nginx

# Set up auto-renewal for SSL certificates
echo "Setting up SSL certificate auto-renewal..."
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

echo "Setup complete!"
echo ""
echo "Testing endpoints:"
echo "  curl https://api.artcafe.ai/health"
echo "  wscat -c wss://api.artcafe.ai/api/v1/ws/dashboard"
echo ""
echo "To view Nginx logs:"
echo "  sudo tail -f /var/log/nginx/access.log"
echo "  sudo tail -f /var/log/nginx/error.log"