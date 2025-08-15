#!/bin/bash

# IPO Scraper PM2 Deployment Script for Ubuntu Server
# This script installs dependencies, sets up environment, and deploys the application

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="ipo-scraper-api"
APP_DIR="/opt/ipo-scraper"
APP_USER="ipo-user"
PORT=1234
NODE_VERSION="18"
PYTHON_VERSION="3.11"

echo -e "${BLUE}Starting IPO Scraper deployment...${NC}"

# Function to print status
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root


# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential packages
print_status "Installing essential packages..."
sudo apt install -y curl wget git build-essential software-properties-common

# Install Python 3.11 and pip
print_status "Installing Python ${PYTHON_VERSION}..."
sudo apt install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev python3-pip

# Install Node.js and npm (required for PM2)
print_status "Installing Node.js ${NODE_VERSION}..."
curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
print_status "Installing PM2..."
sudo npm install -g pm2

# Install Redis server
print_status "Installing Redis server..."
sudo apt install -y redis-server

# Configure Redis
print_status "Configuring Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Create application user if it doesn't exist
if ! id "$APP_USER" &>/dev/null; then
    print_status "Creating application user: $APP_USER"
    sudo useradd -m -s /bin/bash $APP_USER
fi

# Create application directory
print_status "Creating application directory: $APP_DIR"
sudo mkdir -p $APP_DIR
sudo chown $APP_USER:$APP_USER $APP_DIR

# Copy application files
print_status "Copying application files..."
sudo cp -r . $APP_DIR/
sudo chown -R $APP_USER:$APP_USER $APP_DIR

# Switch to application user for the rest of the setup
print_status "Setting up Python virtual environment..."
sudo -u $APP_USER bash << EOF
cd $APP_DIR

# Create virtual environment
python${PYTHON_VERSION} -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

EOF

# Create PM2 ecosystem file
print_status "Creating PM2 ecosystem configuration..."
sudo -u $APP_USER tee $APP_DIR/ecosystem.config.js > /dev/null << EOF
module.exports = {
  apps: [{
    name: '$APP_NAME',
    script: 'venv/bin/python',
    args: 'ipo_api.py',
    cwd: '$APP_DIR',
    instances: 'max',
    exec_mode: 'fork',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      FLASK_ENV: 'production',
      PYTHONPATH: '$APP_DIR',
      REDIS_URL: 'redis://localhost:6379/0'
    },
    error_file: '$APP_DIR/logs/err.log',
    out_file: '$APP_DIR/logs/out.log',
    log_file: '$APP_DIR/logs/combined.log',
    time: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};
EOF

# Create systemd service for PM2
print_status "Creating systemd service for PM2..."
sudo tee /etc/systemd/system/pm2-$APP_USER.service > /dev/null << EOF
[Unit]
Description=PM2 process manager for $APP_USER
Documentation=https://pm2.keymetrics.io/
After=network.target

[Service]
Type=forking
User=$APP_USER
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PM2_HOME=/home/$APP_USER/.pm2
PIDFile=/home/$APP_USER/.pm2/pm2.pid
ExecStart=/usr/bin/pm2 resurrect
ExecReload=/usr/bin/pm2 reload all
ExecStop=/usr/bin/pm2 kill

[Install]
WantedBy=multi-user.target
EOF

# Configure firewall
print_status "Configuring firewall..."
sudo ufw allow $PORT/tcp
sudo ufw allow ssh
sudo ufw --force enable

# Start the application with PM2
print_status "Starting application with PM2..."
sudo -u $APP_USER bash << EOF
cd $APP_DIR
export PM2_HOME=/home/$APP_USER/.pm2
pm2 start ecosystem.config.js
pm2 save
pm2 startup
EOF

# Enable and start PM2 service
sudo systemctl daemon-reload
sudo systemctl enable pm2-$APP_USER
sudo systemctl start pm2-$APP_USER

# Create nginx configuration (optional)
if command -v nginx &> /dev/null; then
    print_status "Creating Nginx reverse proxy configuration..."
    sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null << EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://localhost:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
    
    # Enable gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
}
EOF
    
    sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx
    print_status "Nginx reverse proxy configured"
else
    print_warning "Nginx not found. Skipping reverse proxy setup."
fi

# Display status
print_status "Deployment completed successfully!"
echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo -e "App Name: ${BLUE}$APP_NAME${NC}"
echo -e "App Directory: ${BLUE}$APP_DIR${NC}"
echo -e "App User: ${BLUE}$APP_USER${NC}"
echo -e "Port: ${BLUE}$PORT${NC}"
echo -e "PM2 Status: ${BLUE}$(sudo -u $APP_USER pm2 list | grep $APP_NAME)${NC}"
echo -e "Redis Status: ${BLUE}$(sudo systemctl is-active redis-server)${NC}"
echo -e "Application URL: ${BLUE}http://$(hostname -I | awk '{print $1}'):$PORT${NC}"

print_status "Useful commands:"
echo -e "  View logs: ${YELLOW}sudo -u $APP_USER pm2 logs $APP_NAME${NC}"
echo -e "  Restart app: ${YELLOW}sudo -u $APP_USER pm2 restart $APP_NAME${NC}"
echo -e "  Stop app: ${YELLOW}sudo -u $APP_USER pm2 stop $APP_NAME${NC}"
echo -e "  Monitor: ${YELLOW}sudo -u $APP_USER pm2 monit${NC}"
echo -e "  Redis CLI: ${YELLOW}redis-cli${NC}"

print_status "Deployment script completed!"