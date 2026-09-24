from __future__ import annotations

from typing import Any
from compound_control.domain.models import PositionSize, TradeSetup


def calculate_position_size(*, trading_equity: float, effective_risk_pct: float, setup: TradeSetup, execution_config: dict[str, Any]) -> PositionSize:
    if trading_equity <= 0: raise ValueError("trading_equity must be positive")
    if effective_risk_pct < 0: raise ValueError("effective_risk_pct cannot be negative")
    if setup.entry <= 0 or setup.stop_loss <= 0: raise ValueError("entry and stop_loss must be positive")
    if setup.leverage <= 0: raise ValueError("leverage must be positive")
    if setup.entry == setup.stop_loss: raise ValueError("entry and stop_loss cannot be equal")
    stop_distance_pct = abs(setup.entry - setup.stop_loss) / setup.entry
    risk_budget = trading_equity * effective_risk_pct
    cost_rate = float(execution_config["estimated_round_trip_fee_pct"]) + float(execution_config["estimated_slippage_pct"])
    raw_notional = risk_budget / (stop_distance_pct + cost_rate)
    max_notional = trading_equity * float(execution_config["max_notional_to_equity"])
    recommended = min(raw_notional, max_notional)
    estimated_cost = recommended * cost_rate
    estimated_loss = recommended * stop_distance_pct + estimated_cost
    return PositionSize(risk_budget,stop_distance_pct,raw_notional,recommended,recommended/setup.leverage,estimated_cost,estimated_loss,estimated_loss/trading_equity,recommended < raw_notional)
