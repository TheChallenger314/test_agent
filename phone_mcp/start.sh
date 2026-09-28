#!/usr/bin/env bash
# Démarre le serveur MCP et un tunnel Cloudflare, puis affiche l'URL à
# coller dans claude.ai (Paramètres > Connecteurs > Ajouter un connecteur personnalisé).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="$HOME/.config/phone-mcp"
TOKEN_FILE="$CONF_DIR/token"
PORT="${PHONE_MCP_PORT:-8765}"

mkdir -p "$CONF_DIR"
if [ ! -s "$TOKEN_FILE" ]; then
  python -c 'import secrets; print(secrets.token_urlsafe(24))' > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
export PHONE_MCP_TOKEN="$(cat "$TOKEN_FILE")"
export PHONE_MCP_PORT="$PORT"

# Empêche Android d'endormir Termux pendant que le serveur tourne.
termux-wake-lock 2>/dev/null || true

python "$DIR/server.py" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null; termux-wake-unlock 2>/dev/null || true' EXIT

echo "Ouverture du tunnel Cloudflare…"
shown=""
cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" 2>&1 |
while IFS= read -r line; do
  if [ -z "$shown" ]; then
    url="$(printf '%s' "$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' || true)"
    if [ -n "$url" ]; then
      shown=1
      echo
      echo "=============================================================="
      echo " URL du connecteur (à garder secrète) :"
      echo "   $url/$PHONE_MCP_TOKEN/mcp"
      echo "=============================================================="
      echo " claude.ai > Paramètres > Connecteurs > Ajouter un connecteur"
      echo " personnalisé, puis colle cette URL."
      echo
    fi
  fi
done
