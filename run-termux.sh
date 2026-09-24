#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"
. .venv/bin/activate

if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

python termux_app.py &
APP_PID=$!

sleep 2
if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url http://127.0.0.1:8501 >/dev/null 2>&1 || true
fi

printf '\nCompound Target Control berjalan di:\n  http://127.0.0.1:8501\n\nTekan Ctrl+C untuk berhenti.\n'
wait $APP_PID
