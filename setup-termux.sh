#!/data/data/com.termux/files/usr/bin/bash
set -e

printf '\nCompound Target Control - Termux setup\n\n'

pkg update -y
pkg install -y python git

if [ ! -d .venv ]; then
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-termux.txt

if [ ! -f .env ]; then
  printf '\nBinance API key (read-only): '
  read -r API_KEY
  printf 'Binance API secret: '
  read -r API_SECRET
  cat > .env <<EOF
BINANCE_API_KEY=$API_KEY
BINANCE_API_SECRET=$API_SECRET
BINANCE_FUTURES_BASE_URL=https://fapi.binance.com
EOF
  chmod 600 .env
  printf '\n.env dibuat dan permission diset 600.\n'
else
  printf '\n.env sudah ada, tidak ditimpa.\n'
fi

chmod +x run-termux.sh
printf '\nSetup selesai. Jalankan:\n\n  ./run-termux.sh\n\n'
