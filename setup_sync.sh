#!/bin/bash

# WHOOP Sync Setup Script
# This script sets up the database, loads initial data, and configures the daily sync job

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "WHOOP Sync Setup"
echo "========================================"

# Create logs directory
mkdir -p logs

# Check if Python dependencies are installed
echo ""
echo "Checking dependencies..."
pip3 install -q requests python-dotenv

# Initialize database
echo ""
echo "Initializing database..."
python3 backend/database.py

# Check if authenticated
echo ""
echo "Checking WHOOP authentication..."
if [ ! -f ".whoop_token.json" ]; then
    echo "ERROR: Not authenticated with WHOOP."
    echo "Please run the API first and authenticate:"
    echo "  python3 api.py"
    echo "Then visit http://localhost:8000/auth/login"
    exit 1
fi

echo "Authentication found!"

# Load initial 30 days of data
echo ""
echo "Loading last 30 days of data..."
python3 backend/sync_service.py --full-sync 30

# Show stats
echo ""
python3 backend/sync_service.py --stats

# Setup launchd job
echo ""
echo "========================================"
echo "Setting up daily sync job..."
echo "========================================"

PLIST_NAME="com.health.whoop-sync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Unload if already loaded
if launchctl list | grep -q "com.health.whoop-sync"; then
    echo "Unloading existing job..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
cp "$SCRIPT_DIR/$PLIST_NAME" "$PLIST_DEST"

# Load the job
echo "Loading sync job..."
launchctl load "$PLIST_DEST"

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Daily sync is now scheduled to run at 12:30 AM"
echo ""
echo "The sync will:"
echo "  - Fetch yesterday's data"
echo "  - Backfill any missing days (handles laptop sleep)"
echo "  - Send email alerts on failures"
echo ""
echo "Useful commands:"
echo "  python3 backend/sync_service.py --stats      # View sync statistics"
echo "  python3 backend/sync_service.py --backfill   # Manually backfill missing days"
echo "  python3 backend/sync_service.py --daily      # Run daily sync manually"
echo ""
echo "Logs are stored in: $SCRIPT_DIR/logs/"
echo ""
echo "To configure email alerts, add to .env file:"
echo "  SMTP_USER=your-email@gmail.com"
echo "  SMTP_PASSWORD=your-app-password"
echo ""
