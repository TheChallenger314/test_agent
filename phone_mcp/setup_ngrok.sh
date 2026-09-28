#!/usr/bin/env bash
# Configure ngrok pour avoir une URL fixe (à lancer une seule fois).
# Prérequis : un compte gratuit sur https://ngrok.com
set -euo pipefail

CONF_DIR="$HOME/.config/phone-mcp"
mkdir -p "$CONF_DIR"

# proot et resolv-conf fournissent à ngrok le DNS qui manque sur Android.
pkg install -y proot resolv-conf wget

if ! command -v ngrok >/dev/null 2>&1; then
  case "$(uname -m)" in
    aarch64) arch=arm64 ;;
    armv7l|armv8l) arch=arm ;;
    x86_64) arch=amd64 ;;
    *) echo "Architecture non gérée : $(uname -m)"; exit 1 ;;
  esac
  echo "Téléchargement de ngrok ($arch)…"
  tmp="$(mktemp -d)"
  wget -q -O "$tmp/ngrok.tgz" "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-$arch.tgz"
  tar -xzf "$tmp/ngrok.tgz" -C "$PREFIX/bin"
  chmod +x "$PREFIX/bin/ngrok"
  rm -rf "$tmp"
fi

echo
echo "1. Sur https://dashboard.ngrok.com/get-started/your-authtoken, copie ton authtoken."
read -r -p "   Colle-le ici : " authtoken
ngrok config add-authtoken "$authtoken" >/dev/null

echo
echo "2. Sur https://dashboard.ngrok.com/domains, copie ton domaine gratuit"
echo "   (du type quelque-chose.ngrok-free.app)."
read -r -p "   Colle-le ici : " domain
domain="${domain#https://}"
domain="${domain%%/*}"
printf '%s\n' "$domain" > "$CONF_DIR/ngrok_domain"

echo
echo "ngrok est configuré. Relance le service : ./start.sh"
echo "Pense à mettre à jour l'URL du connecteur dans claude.ai (dernière fois !)."
