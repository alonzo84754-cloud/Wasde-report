#!/bin/bash
# WASDE Platform - AWS Deployment Script
# This script automates the setup of the WASDE platform on an Ubuntu/Debian EC2 instance.

set -e

echo "🚀 Starting WASDE Platform Setup on AWS (52.90.166.187)..."

# 1. Update System
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Dependencies
sudo apt-get install -y python3-pip python3-venv git nginx curl

# 3. Setup Project
cd ~
if [ ! -d "wande" ]; then
    echo "Directory 'wande' not found. Please ensure code is uploaded."
    exit 1
fi

cd wande

# 4. Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Initialize Database
make db-init
make run-all

# 6. Create Systemd Service for FastAPI Backend
echo "Creating WASDE API service..."
sudo bash -c 'cat << EOF > /etc/systemd/system/wasde-api.service
[Unit]
Description=WASDE FastAPI Backend
After=network.target

[Service]
User='$(whoami)'
WorkingDirectory='$(pwd)'
ExecStart='$(pwd)'/venv/bin/python api/index.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

# 7. Create Systemd Service for Streamlit Dashboard
echo "Creating WASDE Dashboard service..."
sudo bash -c 'cat << EOF > /etc/systemd/system/wasde-dashboard.service
[Unit]
Description=WASDE Streamlit Dashboard
After=network.target

[Service]
User='$(whoami)'
WorkingDirectory='$(pwd)'
ExecStart='$(pwd)'/venv/bin/streamlit run src/dashboard.py --server.port 8501 --server.address 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

# 8. Start Services
sudo systemctl daemon-reload
sudo systemctl enable wasde-api
sudo systemctl start wasde-api
sudo systemctl enable wasde-dashboard
sudo systemctl start wasde-dashboard

echo "✅ Services started!"
echo "📡 API: http://52.90.166.187:8000"
echo "🖥️ Dashboard: http://52.90.166.187:8501"
echo ""
echo "⚠️  Note: Ensure AWS Security Group allows inbound traffic on ports 8000 and 8501."
