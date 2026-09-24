from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


class BinanceApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class BinanceCredentials:
    api_key: str
    api_secret: str


class BinanceUsdMReadOnlyClient:
    def __init__(
        self,
        credentials: BinanceCredentials,
        base_url: str = "https://fapi.binance.com",
        timeout: float = 10.0,
    ) -> None:
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._spot_base_url = os.getenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com").rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": credentials.api_key})

        termux_ca = "/data/data/com.termux/files/usr/etc/tls/cert.pem"
        if os.path.exists(termux_ca):
            self._session.verify = termux_ca

    @classmethod
    def from_sources(cls, secrets: Mapping[str, Any] | None = None):
        load_dotenv()
        secrets = secrets or {}
        key = str(secrets.get("BINANCE_API_KEY") or os.getenv("BINANCE_API_KEY", "")).strip()
        secret = str(secrets.get("BINANCE_API_SECRET") or os.getenv("BINANCE_API_SECRET", "")).strip()
        base = str(
            secrets.get("BINANCE_FUTURES_BASE_URL")
            or os.getenv("BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com")
        ).strip()
        if not key or not secret:
            raise BinanceApiError("Binance credentials not found. Add BINANCE_API_KEY and BINANCE_API_SECRET to .env.")
        return cls(BinanceCredentials(key, secret), base)

    def account(self) -> dict[str, Any]:
        return self._signed_get("/fapi/v3/account")

    def positions(self) -> list[dict[str, Any]]:
        data = self._signed_get("/fapi/v3/positionRisk")
        return data if isinstance(data, list) else []

    def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        data = self._signed_get("/fapi/v1/openOrders", params)
        return data if isinstance(data, list) else []

    def klines(self, symbol: str, interval: str = "1h", limit: int = 120) -> list[list[Any]]:
        data = self._public_get(
            "/fapi/v1/klines",
            {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        )
        return data if isinstance(data, list) else []

    def ticker_price(self, symbol: str) -> float:
        data = self._public_get("/fapi/v1/ticker/price", {"symbol": symbol.upper()})
        if not isinstance(data, dict) or "price" not in data:
            raise BinanceApiError("Unexpected ticker response from Binance.")
        return float(data["price"])

    def mark_price(self, symbol: str) -> float:
        data = self._public_get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        if not isinstance(data, dict) or "markPrice" not in data:
            raise BinanceApiError("Unexpected mark-price response from Binance.")
        return float(data["markPrice"])

    # Spot/Funding are intentionally exposed only to the backend so the UI can
    # reconcile Binance Overview without cluttering the dashboard with wallet details.
    def spot_account(self) -> dict[str, Any]:
        data = self._signed_request("GET", self._spot_base_url, "/api/v3/account")
        return data if isinstance(data, dict) else {}

    def funding_assets(self) -> list[dict[str, Any]]:
        data = self._signed_request("POST", self._spot_base_url, "/sapi/v1/asset/get-funding-asset")
        return data if isinstance(data, list) else []

    def spot_ticker_price(self, symbol: str) -> float:
        data = self._public_request(
            self._spot_base_url,
            "/api/v3/ticker/price",
            {"symbol": symbol.upper()},
        )
        if not isinstance(data, dict) or "price" not in data:
            raise BinanceApiError(f"No Spot ticker for {symbol}.")
        return float(data["price"])

    def _public_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._public_request(self._base_url, path, params)

    def _public_request(
        self,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._session.get(
                f"{base_url}{path}", params=params or {}, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise BinanceApiError(f"Binance connection error: {exc}") from exc
        return self._decode_response(response)

    def _signed_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._signed_request("GET", self._base_url, path, params)

    def _signed_request(
        self,
        method: str,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = 5000
        query = urlencode(payload)
        signature = hmac.new(
            self._credentials.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        signed = f"{query}&signature={signature}"
        url = f"{base_url}{path}"
        try:
            if method.upper() == "POST":
                response = self._session.post(
                    url,
                    data=signed,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self._timeout,
                )
            else:
                response = self._session.get(f"{url}?{signed}", timeout=self._timeout)
        except requests.RequestException as exc:
            raise BinanceApiError(f"Binance connection error: {exc}") from exc
        return self._decode_response(response)

    @staticmethod
    def _decode_response(response: requests.Response) -> Any:
        try:
            data = response.json()
        except ValueError as exc:
            raise BinanceApiError(
                f"Binance returned non-JSON response: HTTP {response.status_code}"
            ) from exc
        if not response.ok:
            msg = data.get("msg", "Unknown Binance API error") if isinstance(data, dict) else str(data)
            raise BinanceApiError(f"Binance API error {response.status_code}: {msg}")
        return data
