#!/usr/bin/env bash
# Fait démarrer le service automatiquement quand le téléphone s'allume.
# Prérequis : l'application Termux:Boot (F-Droid), ouverte une fois.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BOOT_DIR="$HOME/.termux/boot"
mkdir -p "$BOOT_DIR"

cat > "$BOOT_DIR/phone-mcp.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
# Lancé par Termux:Boot au démarrage du téléphone.
exec "$DIR/start.sh" > "\$HOME/.config/phone-mcp/service.log" 2>&1
EOF
chmod +x "$BOOT_DIR/phone-mcp.sh"

echo "Démarrage automatique activé."
echo "Journal du service : ~/.config/phone-mcp/service.log"
