#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

git config core.fileMode false
git fetch origin main
git reset --hard origin/main

pkill -f termux_ui_v4.py 2>/dev/null || true
pkill -f termux_ui_v3.py 2>/dev/null || true
pkill -f termux_launcher.py 2>/dev/null || true
pkill -f termux_app.py 2>/dev/null || true

exec bash run-termux.sh
