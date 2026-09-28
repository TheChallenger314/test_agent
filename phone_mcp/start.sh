#!/usr/bin/env bash
# Démarre le serveur MCP et le tunnel vers Internet, puis affiche l'URL à
# coller dans claude.ai (Paramètres > Connecteurs > Ajouter un connecteur personnalisé).
#
# - Si ngrok est configuré (./setup_ngrok.sh), l'URL est fixe.
# - Sinon, repli sur un tunnel Cloudflare temporaire (URL différente à chaque fois).
# Le tunnel est relancé automatiquement s'il tombe (perte de réseau…).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="$HOME/.config/phone-mcp"
TOKEN_FILE="$CONF_DIR/token"
DOMAIN_FILE="$CONF_DIR/ngrok_domain"
PID_FILE="$CONF_DIR/server.pid"
PORT="${PHONE_MCP_PORT:-8765}"

mkdir -p "$CONF_DIR"
if [ ! -s "$TOKEN_FILE" ]; then
  python -c 'import secrets; print(secrets.token_urlsafe(24))' > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
export PHONE_MCP_TOKEN="$(cat "$TOKEN_FILE")"
export PHONE_MCP_PORT="$PORT"

show_url() {
  echo
  echo "=============================================================="
  echo " URL du connecteur (à garder secrète) :"
  echo "   $1/$PHONE_MCP_TOKEN/mcp"
  echo "=============================================================="
  echo
}

# Déjà lancé (par exemple au démarrage du téléphone) ? On affiche juste l'URL.
old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -n "$old_pid" ] && grep -qs start.sh "/proc/$old_pid/cmdline"; then
  echo "Le service tourne déjà."
  [ -s "$DOMAIN_FILE" ] && show_url "https://$(cat "$DOMAIN_FILE")"
  exit 0
fi
echo $$ > "$PID_FILE"

# Option : empêcher la mise en veille du processeur (consomme plus de batterie).
if [ "${PHONE_MCP_WAKE_LOCK:-0}" = "1" ]; then
  termux-wake-lock 2>/dev/null || true
fi

python "$DIR/server.py" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null; rm -f "$PID_FILE"; termux-wake-unlock 2>/dev/null || true; exit' EXIT INT TERM

run_ngrok() {
  local domain; domain="$(cat "$DOMAIN_FILE")"
  show_url "https://$domain"
  # ngrok cherche /etc/resolv.conf (DNS) et des certificats qui n'existent pas
  # sur Android : proot lui présente ceux de Termux à ces emplacements.
  proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" \
        -b "$PREFIX/etc/tls/cert.pem:/etc/ssl/cert.pem" \
    ngrok http "$PORT" --url "https://$domain" --log stdout --log-level warn
}

run_cloudflared() {
  local shown=""
  cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" 2>&1 |
  while IFS= read -r line; do
    if [ -z "$shown" ]; then
      url="$(printf '%s' "$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' || true)"
      if [ -n "$url" ]; then
        shown=1
        show_url "$url"
        echo " (URL temporaire : lance ./setup_ngrok.sh pour une URL fixe)"
      fi
    fi
  done
}

while kill -0 "$SERVER_PID" 2>/dev/null; do
  if [ -s "$DOMAIN_FILE" ]; then
    run_ngrok
  else
    run_cloudflared
  fi
  echo "Tunnel arrêté, nouvelle tentative dans 5 s…"
  sleep 5
done
