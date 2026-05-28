#!/usr/bin/env bash
# Launch the Webull dashboard and expose it via a Cloudflare quick tunnel.
# Requires: cloudflared (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
set -euo pipefail

PORT="${PORT:-5000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed."
  echo "  macOS:  brew install cloudflared"
  echo "  other:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi

# Start the Flask app in the background and stop it when this script exits.
python app.py &
FLASK_PID=$!
trap 'kill "$FLASK_PID" 2>/dev/null || true' EXIT

# Wait for the app to start listening before opening the tunnel.
until curl -s -o /dev/null "http://localhost:${PORT}"; do sleep 1; done

echo ""
echo "App is up on http://localhost:${PORT}"
echo "Opening public tunnel — use the https://*.trycloudflare.com URL below on your phone/iPad:"
echo ""
cloudflared tunnel --url "http://localhost:${PORT}"
