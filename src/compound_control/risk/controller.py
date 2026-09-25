from __future__ import annotations

from typing import Any
from compound_control.domain.models import RiskContext, RiskDecision


class RiskController:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def decide(self, context: RiskContext) -> RiskDecision:
        small = self._small_account_profile(context)
        if small:
            base = float(small["base_risk_pct"])
            minimum = float(small["absolute_min_risk_pct"])
            maximum = float(small["absolute_max_risk_pct"])
            max_open_risk = float(small["max_open_risk_pct"])
            equity_m = 1.0
        else:
            base = float(self._config["base_risk_pct"])
            minimum = float(self._config["absolute_min_risk_pct"])
            maximum = float(self._config["absolute_max_risk_pct"])
            max_open_risk = float(self._config["max_open_risk_pct"])
            equity_m = self._equity_multiplier(context.reporting_equity)

        target_m = float(self._config["target_multiplier"][context.target_status.value])
        dd_m = self._drawdown_multiplier(context.drawdown_pct)
        vol_m = float(self._config["volatility_multiplier"][context.volatility_regime.value])
        preservation_mode = context.drawdown_pct >= float(self._config["preservation_drawdown_pct"])

        effective = min(max(base * target_m * dd_m * vol_m * equity_m, minimum), maximum)
        remaining_open_capacity = max(max_open_risk - context.open_risk_pct, 0.0)
        capped_by_open_risk = effective > remaining_open_capacity
        effective = min(effective, remaining_open_capacity)
        if preservation_mode:
            effective = min(effective, base)

        return RiskDecision(
            base,
            max(effective, 0.0),
            target_m,
            dd_m,
            vol_m,
            equity_m,
            preservation_mode,
            capped_by_open_risk,
        )

    def _small_account_profile(self, context: RiskContext) -> dict[str, Any] | None:
        profile = self._config.get("small_account")
        if not profile or context.trading_equity is None:
            return None
        return profile if float(context.trading_equity) < float(profile["max_trading_equity"]) else None

    def _drawdown_multiplier(self, drawdown_pct: float) -> float:
        dd = max(drawdown_pct, 0.0)
        table = self._config["drawdown_multiplier"]
        if dd < 0.05: return float(table["dd_0_5"])
        if dd < 0.10: return float(table["dd_5_10"])
        if dd < 0.15: return float(table["dd_10_15"])
        return float(table["dd_15_plus"])

    def _equity_multiplier(self, equity: float) -> float:
        for tier in self._config["equity_tiers"]:
            maximum = tier["max_equity"]
            if maximum is None or equity <= float(maximum):
                return float(tier["multiplier"])
        return 1.0
