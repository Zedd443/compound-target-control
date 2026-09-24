#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

git config core.fileMode false
git fetch origin main
git reset --hard origin/main

pkill -f 'python .*termux_.*\.py' 2>/dev/null || true
sleep 1

exec bash run-termux.sh
