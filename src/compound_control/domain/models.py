from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class VolatilityRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class TargetStatus(str, Enum):
    FAR_AHEAD = "far_ahead"
    AHEAD = "ahead"
    ON_TRACK = "on_track"
    SLIGHTLY_BEHIND = "slightly_behind"
    FAR_BEHIND = "far_behind"


@dataclass(frozen=True)
class Goal:
    start_equity: float
    target_equity: float
    start_date: date
    target_date: date
    reporting_currency: str = "IDR"


@dataclass(frozen=True)
class GoalSnapshot:
    as_of: date
    current_equity: float
    baseline_equity: float
    progress_pct: float
    schedule_variance_pct: float
    days_elapsed: int
    days_remaining: int
    original_daily_return: float
    current_daily_return: float
    original_monthly_return: float
    current_monthly_return: float
    target_pressure: float
    status: TargetStatus


@dataclass(frozen=True)
class RiskContext:
    reporting_equity: float
    drawdown_pct: float
    target_status: TargetStatus
    volatility_regime: VolatilityRegime
    open_risk_pct: float = 0.0


@dataclass(frozen=True)
class RiskDecision:
    base_risk_pct: float
    effective_risk_pct: float
    target_multiplier: float
    drawdown_multiplier: float
    volatility_multiplier: float
    equity_multiplier: float
    preservation_mode: bool
    capped_by_open_risk: bool


@dataclass(frozen=True)
class TradeSetup:
    symbol: str
    side: str
    entry: float
    stop_loss: float
    leverage: float


@dataclass(frozen=True)
class PositionSize:
    risk_budget: float
    stop_distance_pct: float
    raw_notional: float
    recommended_notional: float
    required_margin: float
    estimated_cost: float
    estimated_loss_at_stop: float
    account_risk_pct: float
    capped_by_notional_limit: bool


@dataclass(frozen=True)
class PartialExit:
    fraction: float
    r_multiple: Optional[float]


@dataclass(frozen=True)
class PartialPlanResult:
    gross_r: float
    net_r: float
    gross_pnl: float
    net_pnl: float
    estimated_cost: float
