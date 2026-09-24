from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compound_control.config import load_config
from compound_control.domain.models import Goal, TradeSetup, VolatilityRegime
from compound_control.exchange.binance.client import BinanceApiError, BinanceUsdMReadOnlyClient
from compound_control.goals.compound import baseline_equity, build_goal_snapshot
from compound_control.risk.controller import RiskController
from compound_control.services.planner import PlanningService

PLAN_KEYS = {"start_equity":"ps","target_equity":"pt","start_date":"pd0","target_date":"pd1"}


def money(value: float, currency: str) -> str:
    return f"Rp{value:,.0f}" if currency == "IDR" else f"{value:,.2f} {currency}"


@st.cache_data
def load_settings():
    return load_config(PROJECT_ROOT / "config/settings.yaml")


def streamlit_secrets() -> dict[str, str]:
    try:
        return {key: str(value) for key, value in st.secrets.items()}
    except Exception:
        return {}


@st.cache_resource(show_spinner=False)
def binance_client() -> BinanceUsdMReadOnlyClient:
    return BinanceUsdMReadOnlyClient.from_sources(streamlit_secrets())


def read_binance_equity() -> tuple[float, float, float]:
    account = binance_client().account()
    return float(account["totalMarginBalance"]), float(account["availableBalance"]), float(account["totalUnrealizedProfit"])


def query_float(key: str) -> float | None:
    raw = st.query_params.get(key)
    try:
        return None if raw is None else float(raw)
    except (TypeError, ValueError):
        return None


def query_date(key: str) -> date | None:
    raw = st.query_params.get(key)
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def load_plan_from_url() -> Goal | None:
    start_equity = query_float(PLAN_KEYS["start_equity"])
    target_equity = query_float(PLAN_KEYS["target_equity"])
    start_date = query_date(PLAN_KEYS["start_date"])
    target_date = query_date(PLAN_KEYS["target_date"])
    if not all((start_equity, target_equity, start_date, target_date)):
        return None
    if start_equity <= 0 or target_equity <= 0 or target_date <= start_date:
        return None
    return Goal(start_equity, target_equity, start_date, target_date, "IDR")


def save_plan_to_url(goal: Goal) -> None:
    st.query_params[PLAN_KEYS["start_equity"]] = f"{goal.start_equity:.8f}"
    st.query_params[PLAN_KEYS["target_equity"]] = f"{goal.target_equity:.8f}"
    st.query_params[PLAN_KEYS["start_date"]] = goal.start_date.isoformat()
    st.query_params[PLAN_KEYS["target_date"]] = goal.target_date.isoformat()


def clear_plan_from_url() -> None:
    for key in PLAN_KEYS.values():
        if key in st.query_params:
            del st.query_params[key]


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    lengths = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(start.day, lengths[month - 1]))


def build_curve(goal: Goal, current_equity: float, as_of: date) -> pd.DataFrame:
    total_days = (goal.target_date - goal.start_date).days
    step = max(total_days // 120, 1)
    dates = [goal.start_date + pd.Timedelta(days=i) for i in range(0, total_days + 1, step)]
    if dates[-1].date() != goal.target_date:
        dates.append(pd.Timestamp(goal.target_date))
    remaining_days = max((goal.target_date - as_of).days, 1)
    rows = []
    for timestamp in dates:
        d = timestamp.date()
        original = baseline_equity(goal, d)
        dynamic = None
        if d >= as_of:
            elapsed = (d - as_of).days
            dynamic = current_equity * ((goal.target_equity / current_equity) ** (elapsed / remaining_days))
        rows.append({"date": d, "Original": original, "Dynamic": dynamic})
    return pd.DataFrame(rows)


def render_create_plan(current_reporting_equity: float) -> None:
    st.subheader("Buat target")
    st.caption("Start equity otomatis memakai equity Binance saat Start Plan ditekan.")
    target = st.number_input("Target Equity (IDR)", min_value=1_000_000.0, value=10_000_000_000.0, step=10_000_000.0, format="%.0f")
    horizon = st.number_input("Horizon (bulan)", min_value=1, max_value=240, value=24, step=1)
    target_date = add_months(date.today(), int(horizon))
    c1,c2,c3 = st.columns(3)
    c1.metric("Start Equity", money(current_reporting_equity, "IDR"))
    c2.metric("Target", money(target, "IDR"))
    c3.metric("Target Date", target_date.strftime("%d %b %Y"))
    if st.button("Start Plan", type="primary", use_container_width=True):
        save_plan_to_url(Goal(current_reporting_equity, float(target), date.today(), target_date, "IDR"))
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Compound Target Control", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    cfg = load_settings()
    st.title("Compound Target Control")
    st.caption("Live Binance equity + compound target + adaptive risk + position sizing. Tidak membuat prediksi arah market.")

    with st.sidebar:
        st.header("Connection")
        usdt_to_idr = st.number_input("USDT → IDR", min_value=1.0, value=float(cfg.currency["usdt_to_idr"]), step=100.0)
        st.caption("FX manual agar perubahan kurs tidak dianggap trading PnL.")

    try:
        with st.spinner("Membaca Binance Futures..."):
            trading_equity, available_balance, unrealized_pnl = read_binance_equity()
    except BinanceApiError as exc:
        st.error(str(exc))
        st.info("Di Streamlit Cloud buka App settings → Secrets lalu isi BINANCE_API_KEY dan BINANCE_API_SECRET.")
        st.stop()
    except Exception as exc:
        st.error(f"Gagal membaca Binance: {exc}")
        st.stop()

    reporting_equity = trading_equity * usdt_to_idr
    status = st.columns(3)
    status[0].metric("Binance Futures Equity", f"{trading_equity:,.2f} USDT")
    status[1].metric("Approx. IDR", money(reporting_equity, "IDR"))
    status[2].metric("Available Balance", f"{available_balance:,.2f} USDT")
    st.caption(f"Unrealized PnL: {unrealized_pnl:,.2f} USDT · refreshed setiap page run")

    goal = load_plan_from_url()
    if goal is None:
        render_create_plan(reporting_equity)
        st.stop()

    snapshot = build_goal_snapshot(goal, reporting_equity, date.today())
    tabs = st.tabs(["Mission Control", "Trade Planner", "Plan"])

    with tabs[0]:
        top = st.columns(4)
        top[0].metric("Current Equity", money(reporting_equity, "IDR"))
        top[1].metric("Final Target", money(goal.target_equity, "IDR"))
        top[2].metric("Progress", f"{snapshot.progress_pct:.3%}")
        top[3].metric("Days Remaining", f"{snapshot.days_remaining:,}")
        second = st.columns(4)
        second[0].metric("Target Today", money(snapshot.baseline_equity, "IDR"))
        second[1].metric("Schedule Variance", f"{snapshot.schedule_variance_pct:.2%}")
        second[2].metric("Required Monthly", f"{snapshot.current_monthly_return:.2%}")
        second[3].metric("Target Pressure", f"{snapshot.target_pressure:.2f}×")
        curve = build_curve(goal, reporting_equity, date.today())
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=curve["date"], y=curve["Original"], mode="lines", name="Original baseline"))
        fig.add_trace(go.Scatter(x=curve["date"], y=curve["Dynamic"], mode="lines", name="Dynamic required", line={"dash":"dash"}))
        fig.add_trace(go.Scatter(x=[date.today()], y=[reporting_equity], mode="markers", name="Actual", marker={"size":12}))
        fig.update_layout(height=390, yaxis_title="IDR", margin=dict(l=10,r=10,t=20,b=10), legend_orientation="h")
        st.plotly_chart(fig, use_container_width=True)
        st.info("Required return adalah trajectory sisa horizon, bukan target PnL harian. Hari tanpa call tidak dianggap gagal.")

    with tabs[1]:
        st.subheader("Trade Planner")
        left,right = st.columns(2)
        with left:
            symbol = st.text_input("Symbol", "BTCUSDT").upper()
            side = st.selectbox("Side", ["LONG","SHORT"])
            entry = st.number_input("Entry", min_value=0.000001, value=100000.0)
            stop = st.number_input("Stop Loss", min_value=0.000001, value=98000.0)
            leverage = st.number_input("Leverage", min_value=1.0, max_value=125.0, value=5.0)
        with right:
            drawdown = st.slider("Current Drawdown", 0.0, 30.0, 0.0, 0.5) / 100
            open_risk = st.slider("Current Open Risk", 0.0, 3.0, 0.0, 0.1) / 100
            regime = st.selectbox("Volatility condition", [item.value for item in VolatilityRegime], index=1)
        result = PlanningService(risk_controller=RiskController(cfg.risk), execution_config=cfg.execution).plan_trade(goal=goal, reporting_equity=reporting_equity, trading_equity=trading_equity, as_of=date.today(), drawdown_pct=drawdown, volatility_regime=VolatilityRegime(regime), open_risk_pct=open_risk, setup=TradeSetup(symbol,side,entry,stop,leverage))
        size,risk = result.position,result.risk
        row = st.columns(4)
        row[0].metric("Effective R", f"{risk.effective_risk_pct:.3%}")
        row[1].metric("Risk Budget", f"{size.risk_budget:,.2f} USDT")
        row[2].metric("Recommended Notional", f"{size.recommended_notional:,.2f} USDT")
        row[3].metric("Required Margin", f"{size.required_margin:,.2f} USDT")
        row2 = st.columns(3)
        row2[0].metric("Stop Distance", f"{size.stop_distance_pct:.2%}")
        row2[1].metric("Est. loss at SL", f"{size.estimated_loss_at_stop:,.2f} USDT")
        row2[2].metric("Actual Account Risk", f"{size.account_risk_pct:.3%}")

    with tabs[2]:
        st.subheader("Current Plan")
        cols = st.columns(4)
        cols[0].metric("Start Equity", money(goal.start_equity,"IDR"))
        cols[1].metric("Start Date", goal.start_date.strftime("%d %b %Y"))
        cols[2].metric("Target", money(goal.target_equity,"IDR"))
        cols[3].metric("Target Date", goal.target_date.strftime("%d %b %Y"))
        st.caption("Plan disimpan di URL non-sensitif. Bookmark URL setelah membuat plan.")
        if st.button("Reset Plan"):
            clear_plan_from_url(); st.rerun()


if __name__ == "__main__":
    main()
