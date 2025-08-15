#!/bin/bash

# IPO Scraper PM2 Deployment Script for Ubuntu Server
# This script sets up environment, deploys the application, and configures cron jobs

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
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons."
   print_status "Please run as a regular user with sudo privileges."
   exit 1
fi

# Check if required commands exist
print_status "Checking system requirements..."
command -v python3 >/dev/null 2>&1 || { print_error "Python3 is required but not installed. Aborting."; exit 1; }
command -v pip3 >/dev/null 2>&1 || { print_error "pip3 is required but not installed. Aborting."; exit 1; }

# Get the available Python3 version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
print_status "Using Python ${PYTHON_VERSION} ($(python3 --version))"

# Install only essential packages if not present
print_status "Installing essential packages (if needed)..."
sudo apt update
sudo apt install -y curl wget git cron python3-venv python3-pip

# Install Node.js and PM2 only if not present
if ! command -v node &> /dev/null; then
    print_status "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt install -y nodejs
else
    print_status "Node.js already installed: $(node --version)"
fi

if ! command -v pm2 &> /dev/null; then
    print_status "Installing PM2..."
    sudo npm install -g pm2
else
    print_status "PM2 already installed: $(pm2 --version)"
fi

# Install Redis only if not present
if ! command -v redis-server &> /dev/null; then
    print_status "Installing Redis server..."
    sudo apt install -y redis-server
    sudo systemctl enable redis-server
    sudo systemctl start redis-server
else
    print_status "Redis already installed"
    sudo systemctl enable redis-server
    sudo systemctl start redis-server
fi

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

# Create virtual environment using available Python3
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

# Create IPO_DATA directory if it doesn't exist
mkdir -p IPO_DATA

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

# Create cron job scripts
print_status "Creating cron job scripts..."

# Create data fetching script
sudo -u $APP_USER tee $APP_DIR/fetch_data.sh > /dev/null << 'EOF'
#!/bin/bash
cd /opt/ipo-scraper
source venv/bin/activate

# Log start time
echo "$(date): Starting data fetch process" >> logs/cron.log

# Run meta_data.py to fetch data
echo "$(date): Running meta_data.py" >> logs/cron.log
python3 meta_data.py >> logs/cron.log 2>&1

# Wait a moment then run parser.py
echo "$(date): Running parser.py" >> logs/cron.log
python3 parser.py >> logs/cron.log 2>&1

echo "$(date): Data fetch process completed" >> logs/cron.log
EOF

# Make the script executable
sudo chmod +x $APP_DIR/fetch_data.sh
sudo chown $APP_USER:$APP_USER $APP_DIR/fetch_data.sh

# Add cron job to run every hour
print_status "Setting up cron job to run data fetching every hour..."
sudo -u $APP_USER bash << EOF
# Remove any existing cron jobs for this application
crontab -l 2>/dev/null | grep -v "$APP_DIR/fetch_data.sh" | crontab -

# Add new cron job to run every hour
(crontab -l 2>/dev/null; echo "0 * * * * $APP_DIR/fetch_data.sh") | crontab -

# Verify cron job was added
echo "Current cron jobs for $APP_USER:"
crontab -l
EOF

# Ensure cron service is running
print_status "Ensuring cron service is running..."
sudo systemctl enable cron
sudo systemctl start cron

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

# Run initial data fetch
print_status "Running initial data fetch..."
sudo -u $APP_USER $APP_DIR/fetch_data.sh

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
echo -e "Python Version: ${BLUE}$PYTHON_VERSION${NC}"
echo -e "PM2 Status: ${BLUE}$(sudo -u $APP_USER pm2 list | grep $APP_NAME)${NC}"
echo -e "Redis Status: ${BLUE}$(sudo systemctl is-active redis-server)${NC}"
echo -e "Cron Status: ${BLUE}$(sudo systemctl is-active cron)${NC}"
echo -e "Application URL: ${BLUE}http://$(hostname -I | awk '{print $1}'):$PORT${NC}"

print_status "Cron job configured to run data fetching every hour"
print_status "Data fetching includes: meta_data.py -> parser.py"

print_status "Useful commands:"
echo -e "  View API logs: ${YELLOW}sudo -u $APP_USER pm2 logs $APP_NAME${NC}"
echo -e "  View cron logs: ${YELLOW}sudo -u $APP_USER tail -f $APP_DIR/logs/cron.log${NC}"
echo -e "  Restart app: ${YELLOW}sudo -u $APP_USER pm2 restart $APP_NAME${NC}"
echo -e "  Stop app: ${YELLOW}sudo -u $APP_USER pm2 stop $APP_NAME${NC}"
echo -e "  Monitor: ${YELLOW}sudo -u $APP_USER pm2 monit${NC}"
echo -e "  Redis CLI: ${YELLOW}redis-cli${NC}"
echo -e "  Check cron jobs: ${YELLOW}sudo -u $APP_USER crontab -l${NC}"
echo -e "  Manual data fetch: ${YELLOW}sudo -u $APP_USER $APP_DIR/fetch_data.sh${NC}"

print_status "Deployment script completed!"