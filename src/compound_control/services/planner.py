from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from compound_control.domain.models import Goal,GoalSnapshot,PositionSize,RiskContext,RiskDecision,TradeSetup,VolatilityRegime
from compound_control.goals.compound import build_goal_snapshot
from compound_control.risk.controller import RiskController
from compound_control.sizing.position import calculate_position_size

@dataclass(frozen=True)
class PlanningResult:
    goal: GoalSnapshot
    risk: RiskDecision
    position: PositionSize

class PlanningService:
    def __init__(self,*,risk_controller:RiskController,execution_config:dict)->None:
        self._risk_controller=risk_controller; self._execution_config=execution_config
    def plan_trade(self,*,goal:Goal,reporting_equity:float,trading_equity:float,as_of:date,drawdown_pct:float,volatility_regime:VolatilityRegime,open_risk_pct:float,setup:TradeSetup)->PlanningResult:
        snap=build_goal_snapshot(goal,reporting_equity,as_of)
        decision=self._risk_controller.decide(RiskContext(reporting_equity,drawdown_pct,snap.status,volatility_regime,open_risk_pct))
        position=calculate_position_size(trading_equity=trading_equity,effective_risk_pct=decision.effective_risk_pct,setup=setup,execution_config=self._execution_config)
        return PlanningResult(snap,decision,position)
