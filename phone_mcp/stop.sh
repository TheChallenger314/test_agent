#!/usr/bin/env bash
# Arrête le service (serveur + tunnel).
PID_FILE="$HOME/.config/phone-mcp/server.pid"
pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -n "$pid" ] && grep -qs start.sh "/proc/$pid/cmdline"; then
  pkill -TERM -P "$pid"   # tunnel et serveur, sinon bash attend la fin du tunnel
  kill "$pid" && echo "Service arrêté."
else
  echo "Le service ne tourne pas."
fi
