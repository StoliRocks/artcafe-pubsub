#!/bin/bash

# Setup HTTPS for api.artcafe.ai

echo "Setting up HTTPS for api.artcafe.ai..."

# Install certbot
echo "Installing certbot..."
sudo yum install -y certbot python3-certbot-nginx

# Install nginx if not present
echo "Installing nginx..."
sudo yum install -y nginx

# Create nginx configuration for API
echo "Creating nginx configuration..."
sudo tee /etc/nginx/conf.d/api.artcafe.ai.conf > /dev/null <<EOF
server {
    listen 80;
    server_name api.artcafe.ai;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Start nginx
echo "Starting nginx..."
sudo systemctl enable nginx
sudo systemctl start nginx

# Get SSL certificate
echo "Getting SSL certificate..."
sudo certbot --nginx -d api.artcafe.ai --non-interactive --agree-tos --email admin@artcafe.ai

# Restart nginx
echo "Restarting nginx..."
sudo systemctl restart nginx

echo "HTTPS setup complete!"
echo "API is now available at https://api.artcafe.ai"