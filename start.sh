#!/bin/bash

# Health App Start Script
# Starts both the API server and React frontend

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

echo "Starting Health App..."

# Check if already running
if [ -f "$PID_DIR/api.pid" ]; then
    API_PID=$(cat "$PID_DIR/api.pid")
    if ps -p $API_PID > /dev/null 2>&1; then
        echo "API server already running (PID: $API_PID)"
    else
        rm "$PID_DIR/api.pid"
    fi
fi

if [ -f "$PID_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PID_DIR/frontend.pid")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo "Frontend already running (PID: $FRONTEND_PID)"
    else
        rm "$PID_DIR/frontend.pid"
    fi
fi

# Start API server if not running
if [ ! -f "$PID_DIR/api.pid" ]; then
    echo "Starting API server on http://localhost:8000..."
    cd "$SCRIPT_DIR/backend"
    nohup python3 -m uvicorn api:app --reload --host 0.0.0.0 --port 8000 > ../logs/api.log 2>&1 &
    echo $! > "$PID_DIR/api.pid"
    echo "API server started (PID: $!)"
    cd "$SCRIPT_DIR"
fi

# Start frontend if not running
if [ ! -f "$PID_DIR/frontend.pid" ]; then
    echo "Starting frontend on http://localhost:5173..."
    cd "$SCRIPT_DIR/frontend"
    nohup npm run dev > ../logs/frontend.log 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
    echo "Frontend started (PID: $!)"
fi

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

echo ""
echo "========================================="
echo "Health App Started!"
echo "========================================="
echo ""
echo "API Server:  http://localhost:8000"
echo "API Docs:    http://localhost:8000/docs"
echo "Frontend:    http://localhost:5173"
echo ""
echo "Logs:"
echo "  API:      $SCRIPT_DIR/logs/api.log"
echo "  Frontend: $SCRIPT_DIR/logs/frontend.log"
echo ""
echo "Run ./stop.sh to stop all services"
echo ""
