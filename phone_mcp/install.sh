#!/usr/bin/env bash
# Installation des dépendances dans Termux (à lancer une seule fois).
set -euo pipefail

pkg update -y
pkg install -y python cloudflared termux-api

echo
echo "Installation terminée."
echo "Pense aussi à :"
echo "  1. Installer l'app « Termux:API » (même source que Termux : F-Droid ou GitHub)."
echo "  2. Autoriser Termux à « Afficher par-dessus les autres applis »"
echo "     (Paramètres Android > Applis > Termux)."
echo "  3. Désactiver l'optimisation de batterie pour Termux."
echo
echo "Ensuite : ./setup_ngrok.sh (URL fixe), ./enable_boot.sh (démarrage auto), puis ./start.sh"
