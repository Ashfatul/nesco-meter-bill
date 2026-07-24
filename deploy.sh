#!/bin/bash

# ==============================================================================
# NESCO Tracker - Automated Master Deployment Script (Ubuntu 22.04 / 24.04)
# ==============================================================================
# WARNING: Run this script with 'sudo' or as the root user.
# Usage: sudo bash deploy.sh
# ==============================================================================

set -e # Exit immediately if a command exits with a non-zero status

echo "🚀 Starting NESCO Tracker Deployment..."

# 1. Update system and install dependencies
echo "📦 Installing system dependencies (Python, Nginx, Git)..."
apt-get update
apt-get install -y python3-pip python3-venv git nginx cron

# 2. Get the current directory (assuming script is run from project root)
PROJECT_DIR=$(pwd)
USER_NAME=$SUDO_USER
if [ -z "$USER_NAME" ]; then
    USER_NAME=$(whoami)
fi

echo "📂 Project Directory: $PROJECT_DIR"
echo "👤 System User: $USER_NAME"

# 3. Setup Python Virtual Environment
echo "🐍 Setting up Python Virtual Environment..."
python3 -m venv venv
source venv/bin/activate
pip install Flask Flask-SQLAlchemy Flask-Login Flask-Bcrypt requests beautifulsoup4 gunicorn

# 4. Initialize Database
echo "🗄️ Initializing SQLite Database..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"
# Ensure the instance folder and db have correct permissions
chown -R $USER_NAME:www-data $PROJECT_DIR/instance || true
chmod -R 775 $PROJECT_DIR/instance || true

# 5. Setup Gunicorn Systemd Service
echo "⚙️ Configuring Gunicorn Systemd Service..."
SERVICE_FILE=/etc/systemd/system/nesco.service

cat <<EOF > $SERVICE_FILE
[Unit]
Description=Gunicorn instance to serve NESCO Tracker
After=network.target

[Service]
User=$USER_NAME
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --workers 3 --bind unix:nesco.sock -m 007 app:app

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl start nesco
systemctl enable nesco
echo "✅ Gunicorn Service Started!"

# 6. Setup Nginx Reverse Proxy
echo "🌐 Configuring Nginx..."
NGINX_FILE=/etc/nginx/sites-available/nesco

cat <<EOF > $NGINX_FILE
server {
    listen 80;
    server_name _; # Accepts any IP/Domain

    location / {
        include proxy_params;
        proxy_pass http://unix:$PROJECT_DIR/nesco.sock;
    }
}
EOF

# Remove default nginx site if exists
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/nesco /etc/nginx/sites-enabled/nesco

systemctl restart nginx
echo "✅ Nginx Configured!"

# 7. Setup the Daily Cron Job for 4:00 AM
echo "🕒 Setting up Daily Fetch Cron Job (Runs at 4:00 AM)..."
CRON_CMD="0 4 * * * cd $PROJECT_DIR && $PROJECT_DIR/venv/bin/python fetch_daily.py >> $PROJECT_DIR/cron.log 2>&1"

# Check if cron job already exists to avoid duplicates
if ! crontab -u $USER_NAME -l 2>/dev/null | grep -q "fetch_daily.py"; then
    (crontab -u $USER_NAME -l 2>/dev/null; echo "$CRON_CMD") | crontab -u $USER_NAME -
    echo "✅ Cron Job Added!"
else
    echo "⚠️ Cron Job already exists. Skipping."
fi

echo "=============================================================================="
echo "🎉 DEPLOYMENT COMPLETE! 🎉"
echo "Your NESCO Tracker is now live and hosted on this server."
echo "You can access it by typing this server's Public IP Address into your browser."
echo "The automated daily fetch is scheduled for 4:00 AM every day."
echo "=============================================================================="
