from __future__ import annotations

from typing import Any
from compound_control.domain.models import RiskContext, RiskDecision


class RiskController:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def decide(self, context: RiskContext) -> RiskDecision:
        base = float(self._config["base_risk_pct"])
        minimum = float(self._config["absolute_min_risk_pct"])
        maximum = float(self._config["absolute_max_risk_pct"])
        target_m = float(self._config["target_multiplier"][context.target_status.value])
        dd_m = self._drawdown_multiplier(context.drawdown_pct)
        vol_m = float(self._config["volatility_multiplier"][context.volatility_regime.value])
        equity_m = self._equity_multiplier(context.reporting_equity)
        preservation_mode = context.drawdown_pct >= float(self._config["preservation_drawdown_pct"])
        effective = min(max(base * target_m * dd_m * vol_m * equity_m, minimum), maximum)
        remaining_open_capacity = max(float(self._config["max_open_risk_pct"]) - context.open_risk_pct, 0.0)
        capped_by_open_risk = effective > remaining_open_capacity
        effective = min(effective, remaining_open_capacity)
        if preservation_mode:
            effective = min(effective, base)
        return RiskDecision(base,max(effective,0.0),target_m,dd_m,vol_m,equity_m,preservation_mode,capped_by_open_risk)

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
