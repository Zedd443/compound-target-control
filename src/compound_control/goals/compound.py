from __future__ import annotations

from datetime import date
import math

from compound_control.domain.models import Goal, GoalSnapshot, TargetStatus

AVERAGE_DAYS_PER_MONTH = 365.25 / 12.0


def _compound_rate(growth_multiple: float, periods: float) -> float:
    if growth_multiple <= 0:
        raise ValueError("growth_multiple must be positive")
    if periods <= 0:
        return 0.0 if math.isclose(growth_multiple, 1.0) else math.inf
    return math.exp(math.log(growth_multiple) / periods) - 1.0


def baseline_equity(goal: Goal, as_of: date) -> float:
    total_days = (goal.target_date - goal.start_date).days
    if total_days <= 0:
        raise ValueError("target_date must be after start_date")
    elapsed = min(max((as_of - goal.start_date).days, 0), total_days)
    fraction = elapsed / total_days
    growth_multiple = goal.target_equity / goal.start_equity
    return goal.start_equity * math.exp(math.log(growth_multiple) * fraction)


def classify_target_status(schedule_variance_pct: float) -> TargetStatus:
    if schedule_variance_pct >= 0.10:
        return TargetStatus.FAR_AHEAD
    if schedule_variance_pct >= 0.03:
        return TargetStatus.AHEAD
    if schedule_variance_pct > -0.03:
        return TargetStatus.ON_TRACK
    if schedule_variance_pct > -0.10:
        return TargetStatus.SLIGHTLY_BEHIND
    return TargetStatus.FAR_BEHIND


def build_goal_snapshot(goal: Goal, current_equity: float, as_of: date) -> GoalSnapshot:
    if current_equity <= 0:
        raise ValueError("current_equity must be positive")
    total_days = (goal.target_date - goal.start_date).days
    days_elapsed = min(max((as_of - goal.start_date).days, 0), total_days)
    days_remaining = max((goal.target_date - as_of).days, 0)
    baseline = baseline_equity(goal, as_of)
    schedule_variance = current_equity / baseline - 1.0
    total_months = total_days / AVERAGE_DAYS_PER_MONTH
    remaining_months = days_remaining / AVERAGE_DAYS_PER_MONTH
    original_daily = _compound_rate(goal.target_equity / goal.start_equity, total_days)
    original_monthly = _compound_rate(goal.target_equity / goal.start_equity, total_months)
    remaining_multiple = goal.target_equity / current_equity
    current_daily = _compound_rate(remaining_multiple, days_remaining) if days_remaining else 0.0
    current_monthly = _compound_rate(remaining_multiple, remaining_months) if remaining_months else 0.0
    if original_monthly <= 0 or not math.isfinite(current_monthly):
        pressure = math.inf if current_monthly > 0 else 1.0
    else:
        pressure = current_monthly / original_monthly
    return GoalSnapshot(as_of,current_equity,baseline,current_equity/goal.target_equity,schedule_variance,days_elapsed,days_remaining,original_daily,current_daily,original_monthly,current_monthly,pressure,classify_target_status(schedule_variance))
