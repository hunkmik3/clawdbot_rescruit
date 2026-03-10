#!/bin/bash
# ClawdBot Server + Named Tunnel auto-restart script
# URL: https://clawdbot.otsulabstoolkit.io.vn
# Usage: ./start_server.sh

cd "$(dirname "$0")"

trap "kill $CAFE_PID $SERVER_PID 2>/dev/null; exit" SIGINT SIGTERM

# Prevent Mac from sleeping (requires power adapter)
caffeinate -d -i -s &
CAFE_PID=$!
echo "✓ caffeinate PID: $CAFE_PID"

# Start FastAPI server
source venv/bin/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
echo "✓ FastAPI server PID: $SERVER_PID (port 8000)"
sleep 2

# Named tunnel auto-restart loop
while true; do
    echo "[$(date)] Starting Cloudflare Named Tunnel (clawdbot)..."
    cloudflared tunnel run clawdbot 2>&1 &
    TUNNEL_PID=$!
    echo "✓ Tunnel PID: $TUNNEL_PID → https://clawdbot.otsulabstoolkit.io.vn"

    # Wait for tunnel process to exit (means it crashed or lost connection)
    wait $TUNNEL_PID
    echo "[$(date)] Tunnel disconnected. Retrying in 5s..."
    sleep 5
done
