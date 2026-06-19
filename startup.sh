#!/bin/bash

# Configuration variables
FRONTEND_FOLDER="mohini-app-frontend"
FRONTEND_START_CMD="serve -s build -p 3005"

HOME_FOLDER="/home/ubuntu" # Change this to your home folder (/home/ubuntu)

# Log file setup
LOG_FILE="$HOME_FOLDER/startup.log"
echo "Starting application components at $(date)" > "$LOG_FILE"

# Function to log timing information
log_timing() {
    local component=$1
    local start_time=$2
    local end_time=$3
    local duration=$((end_time - start_time))
    echo "$component startup took $duration seconds" >> "$LOG_FILE"
}

# Function to check if a tmux session exists
tmux_session_exists() {
    tmux has-session -t "$1" 2>/dev/null
}

# Function to check and export environment variables
export_env_vars() {
    if [ -f ".env" ]; then
        export $(cat .env | xargs)
    else
        echo "Warning: .env file not found in $(pwd)" >> "$LOG_FILE"
    fi
}

# Start timing for Docker containers
docker_start_time=$(date +%s)

# Build and start Docker containers
echo "Building Docker containers..." >> "$LOG_FILE"
# Stop existing containers if any
if [ -f "docker-compose.yml" ]; then
    echo "Stopping existing Docker containers..." >> "$LOG_FILE"
    docker compose down >> "$LOG_FILE" 2>&1
    
    # Build containers
    echo "Building Docker images..." >> "$LOG_FILE"
    docker compose build >> "$LOG_FILE" 2>&1
    
    # Start containers in detached mode
    echo "Starting Docker containers..." >> "$LOG_FILE"
    docker compose up -d >> "$LOG_FILE" 2>&1
    
    # Wait for containers to be healthy
    echo "Waiting for containers to be healthy..." >> "$LOG_FILE"
    sleep 10
else
    echo "Warning: docker-compose.yml not found" >> "$LOG_FILE"
fi

# Log Docker timing
docker_end_time=$(date +%s)
log_timing "Docker containers" $docker_start_time $docker_end_time

cd $HOME_FOLDER

# Start timing for frontend
frontend_start_time=$(date +%s)

# Setup frontend
if [ ! -d "$HOME_FOLDER/$FRONTEND_FOLDER" ]; then
    echo "Warning: Frontend folder $FRONTEND_FOLDER not found in $HOME_FOLDER" >> "$LOG_FILE"
    exit 1
fi

cd "$HOME_FOLDER/$FRONTEND_FOLDER"

# Install pm2 globally if not already installed
if ! command -v pm2 &> /dev/null; then
    echo "Installing PM2 globally..." >> "$LOG_FILE"
    npm install -g pm2
fi

if ! command -v serve &> /dev/null; then
    echo "Installing serve globally..." >> "$LOG_FILE"
    npm install -g serve
fi

# Build and start frontend
echo "Building frontend..." >> "$LOG_FILE"

# Check if frontend is already running in pm2
if pm2 list | grep -q "$FRONTEND_FOLDER"; then
    echo "Stopping existing frontend PM2 process..." >> "$LOG_FILE"
    pm2 delete $FRONTEND_FOLDER
fi

# Start new frontend process
pm2 start "$FRONTEND_START_CMD" --name $FRONTEND_FOLDER

# Log frontend timing
frontend_end_time=$(date +%s)
log_timing "Frontend" $frontend_start_time $frontend_end_time

# Final status check
echo "Final Status Check at $(date):" >> "$LOG_FILE"
echo "Docker Containers:" >> "$LOG_FILE"
docker-compose ps >> "$LOG_FILE" 2>&1
echo "PM2 Status:" >> "$LOG_FILE"
pm2 list >> "$LOG_FILE"
echo "TMux Sessions:" >> "$LOG_FILE"
tmux ls >> "$LOG_FILE" 2>&1

echo "Startup completed at $(date)" >> "$LOG_FILE" 