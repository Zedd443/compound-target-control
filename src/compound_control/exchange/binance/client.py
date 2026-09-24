from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from pathlib import Path
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
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": credentials.api_key})
        self._session.verify = self._resolve_ca_bundle()

    @staticmethod
    def _resolve_ca_bundle() -> str | bool:
        explicit = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
        if explicit and Path(explicit).is_file():
            return explicit

        termux_bundle = Path("/data/data/com.termux/files/usr/etc/tls/cert.pem")
        if termux_bundle.is_file():
            return str(termux_bundle)

        return True

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
            raise BinanceApiError("Binance credentials not found. Add them to .env or Streamlit Secrets.")

        return cls(BinanceCredentials(key, secret), base)

    def account(self) -> dict[str, Any]:
        return self._signed_get("/fapi/v3/account")

    def _signed_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = 5000
        query = urlencode(payload)
        signature = hmac.new(
            self._credentials.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()

        url = f"{self._base_url}{path}?{query}&signature={signature}"
        try:
            response = self._session.get(url, timeout=self._timeout)
        except requests.exceptions.SSLError as exc:
            raise BinanceApiError(f"TLS verification failed: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise BinanceApiError(f"Network error while contacting Binance: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise BinanceApiError(
                f"Binance returned non-JSON response: HTTP {response.status_code}"
            ) from exc

        if not response.ok:
            message = data.get("msg", "Unknown Binance API error") if isinstance(data, dict) else str(data)
            raise BinanceApiError(f"Binance API error {response.status_code}: {message}")

        return data
