from __future__ import annotations

import requests

import termux_app as appmod


def _mid_from_book(data: dict) -> float:
    bids = data.get("bids") or data.get("data", {}).get("bids")
    asks = data.get("asks") or data.get("data", {}).get("asks")
    if not bids or not asks:
        raise RuntimeError("order book kosong")
    return (float(bids[0][0]) + float(asks[0][0])) / 2


def get_usdt_idr_rate() -> tuple[float, str]:
    errors: list[str] = []

    # Tokocrypto migrated BTCIDR market-data route. Do not send unsupported `limit`.
    try:
        r = requests.get(
            "https://cloudme-toko.2meta.app/api/v1/depth",
            params={"symbol": "BTCIDR"},
            timeout=8,
        )
        r.raise_for_status()
        btc_idr = _mid_from_book(r.json())
        btc_usdt = appmod.client.mark_price("BTCUSDT")
        if btc_idr > 0 and btc_usdt > 0:
            return btc_idr / btc_usdt, "Tokocrypto BTCIDR ÷ Binance BTCUSDT"
    except Exception as exc:
        errors.append(f"Tokocrypto NextMe: {exc}")

    # Fallback: Tokocrypto public API route used by the legacy/public interface.
    for symbol in ("BTC_IDR", "BTCIDR"):
        try:
            r = requests.get(
                "https://www.tokocrypto.com/open/v1/market/depth",
                params={"symbol": symbol},
                timeout=8,
            )
            r.raise_for_status()
            btc_idr = _mid_from_book(r.json())
            btc_usdt = appmod.client.mark_price("BTCUSDT")
            if btc_idr > 0 and btc_usdt > 0:
                return btc_idr / btc_usdt, "Tokocrypto public BTCIDR ÷ Binance BTCUSDT"
        except Exception as exc:
            errors.append(f"Tokocrypto public {symbol}: {exc}")

    # Last-resort public quote. Good enough for reporting/target conversion; not used for order execution.
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "tether", "vs_currencies": "idr"},
            timeout=8,
            headers={"accept": "application/json", "user-agent": "compound-target-control/1.0"},
        )
        r.raise_for_status()
        rate = float(r.json()["tether"]["idr"])
        if rate > 0:
            return rate, "CoinGecko USDT/IDR"
    except Exception as exc:
        errors.append(f"CoinGecko: {exc}")

    raise RuntimeError("Semua sumber FX gagal: " + " | ".join(errors[-3:]))


# Override the FX function used by the existing Flask route without duplicating the app.
appmod.get_usdt_idr_rate = get_usdt_idr_rate


if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
