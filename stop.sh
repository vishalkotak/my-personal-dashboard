#!/bin/bash

# Health App Stop Script
# Stops both the API server and React frontend

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_DIR="$SCRIPT_DIR/.pids"

echo "Stopping Health App..."

# Stop API server
if [ -f "$PID_DIR/api.pid" ]; then
    API_PID=$(cat "$PID_DIR/api.pid")
    if ps -p $API_PID > /dev/null 2>&1; then
        echo "Stopping API server (PID: $API_PID)..."
        kill $API_PID 2>/dev/null
        # Also kill any child processes (uvicorn workers)
        pkill -P $API_PID 2>/dev/null
        sleep 1
        # Force kill if still running
        if ps -p $API_PID > /dev/null 2>&1; then
            kill -9 $API_PID 2>/dev/null
        fi
        echo "API server stopped"
    else
        echo "API server not running"
    fi
    rm "$PID_DIR/api.pid"
else
    echo "API server not running (no PID file)"
fi

# Stop frontend
if [ -f "$PID_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PID_DIR/frontend.pid")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null
        # Also kill any child processes (vite/node)
        pkill -P $FRONTEND_PID 2>/dev/null
        sleep 1
        # Force kill if still running
        if ps -p $FRONTEND_PID > /dev/null 2>&1; then
            kill -9 $FRONTEND_PID 2>/dev/null
        fi
        echo "Frontend stopped"
    else
        echo "Frontend not running"
    fi
    rm "$PID_DIR/frontend.pid"
else
    echo "Frontend not running (no PID file)"
fi

# Clean up any orphaned processes on our ports
echo "Cleaning up ports..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null

echo ""
echo "========================================="
echo "Health App Stopped"
echo "========================================="
echo ""
