# Compound Target Control v0.2

Mobile-friendly compound target + risk + position sizing planner for Binance USD-M Futures.

## Deploy to Streamlit Cloud

Main file:

```text
src/compound_control/dashboard_app.py
```

Add these in **App settings → Secrets**:

```toml
BINANCE_API_KEY = "YOUR_READ_ONLY_KEY"
BINANCE_API_SECRET = "YOUR_SECRET"
BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
```

Do not commit `.env` or `.streamlit/secrets.toml`.

## How it works

- Current/start equity comes from live Binance Futures balance.
- Target equity and horizon are entered from the mobile UI.
- Start equity is locked when `Start Plan` is pressed.
- Current equity stays live.
- Plan state is stored in non-sensitive URL query parameters.
- Trade Planner converts effective R + Entry/SL into suggested USDT notional and margin.
- No ML, signal prediction, or order placement.

## Local

```bash
pip install -r requirements.txt
streamlit run src/compound_control/dashboard_app.py
```
