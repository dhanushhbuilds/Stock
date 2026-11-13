"""Wires real data into the decision engine: promoted model -> latest predictions, news signals, market regime,
market snapshot, risk limits; persists every decision with its explanation and an audit event."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import Settings
from app.engines.data.global_data import load_global
from app.engines.data.service import universe_members
from app.engines.data.storage import CandleLake
from app.engines.decision.engine import DecisionEngine, Inputs
from app.engines.ml import indicators as ind
from app.engines.ml import inference, swing
from app.engines.ml import intraday as intr
from app.engines.news.service import signal_for
from app.engines.risk.engine import RiskEngine
from app.engines.risk.schemas import MarketSnapshot, PortfolioState, RiskLimits
from app.engines.risk.service import get_state
from app.models.decision import DecisionRecord
from app.models.ml import MLDataset

IST = ZoneInfo("Asia/Kolkata")


def default_portfolio() -> PortfolioState:
    """Paper trading is out of scope for now: decisions are sized against a flat SIMULATED Rs 10 lakh book."""
    return PortfolioState(
        equity=1_000_000, cash=1_000_000, start_of_day_equity=1_000_000, peak_equity=1_000_000
    )


def market_regime(lake: CandleLake, as_of: pd.Timestamp) -> dict:
    """Rule-based regime from NIFTY 50 (trend: close vs EMA200 and EMA50 slope) and India VIX percentile."""
    n = lake.read("1day", swing.NIFTY)
    n = n[n["ts"].dt.tz_localize(None).dt.normalize() <= as_of.normalize()]
    c = n["close"].reset_index(drop=True)
    e50, e200 = ind.ema(c, 50), ind.ema(c, 200)
    slope = e50.iloc[-1] / e50.iloc[-11] - 1
    if c.iloc[-1] > e200.iloc[-1] and slope > 0:
        trend = "bull"
    elif c.iloc[-1] < e200.iloc[-1] and slope < 0:
        trend = "bear"
    else:
        trend = "sideways"
    v = lake.read("1day", swing.VIX)
    v = v[v["ts"].dt.tz_localize(None).dt.normalize() <= as_of.normalize()]["close"].tail(252)
    pct = float((v < v.iloc[-1]).mean())
    vol = "high" if pct >= 0.8 else "low" if pct <= 0.2 else "normal"
    return {
        "trend": trend,
        "nifty_close": float(c.iloc[-1]),
        "nifty_ema200": float(e200.iloc[-1]),
        "ema50_10d_slope": round(float(slope), 5),
        "volatility": vol,
        "india_vix": float(v.iloc[-1]),
        "vix_1y_percentile": round(pct, 3),
        "as_of": str(n["ts"].iloc[-1].date()),
    }


def _persist(session: Session, d) -> None:
    session.add(
        DecisionRecord(
            decision_id=d.decision_id,
            instrument_key=d.instrument_key,
            symbol=d.symbol,
            pipeline=d.pipeline,
            action=d.action,
            confidence=d.confidence,
            score=d.score,
            quantity=d.quantity,
            model_version=d.model_version,
            explanation=d.to_dict(),
            decided_at=d.created_at,
        )
    )
    record(
        session,
        "decision",
        f"decision_{d.action.lower()}",
        {
            "decision_id": d.decision_id,
            "instrument_key": d.instrument_key,
            "pipeline": d.pipeline,
            "score": d.score,
            "reasons": d.reasons,
        },
    )


def run_swing(
    session: Session, settings: Settings, now: datetime | None = None, symbols: list[str] | None = None
):
    now = now or datetime.now(UTC)
    lake = CandleLake(settings.data_dir)
    st = get_state(session)
    engine = DecisionEngine(RiskEngine(RiskLimits(**st.limits), kill_switch=st.kill_switch))
    try:
        m = inference.promoted(session, "swing")
    except inference.ModelUnavailable as exc:
        return [], str(exc)
    art = inference.load_artifact(m)
    cfg_d = session.get(MLDataset, m.dataset_version).config
    cfg = swing.SwingConfig(
        **{
            k: (tuple(v) if k == "train_universes" else v)
            for k, v in cfg_d.items()
            if k in swing.SwingConfig.__dataclass_fields__
        }
    )
    mem, seen = [], set()
    for u in cfg.train_universes:
        for mm in universe_members(session, u):
            if mm.symbol not in seen:
                seen.add(mm.symbol)
                mem.append((mm.symbol, mm.instrument_key, mm.sector_index_key, u == "NIFTY50"))
    ds = swing.build_swing_dataset(lake, mem, load_global(settings.data_dir), cfg)
    ds = ds[ds["eval_universe"]] if "eval_universe" in ds else ds
    ds = ds[ds["date"] <= pd.Timestamp(now.astimezone(IST).date())]
    preds = inference.predict_latest(ds, art, "date")
    as_of = preds["date"].iloc[0]
    regime = market_regime(lake, as_of)
    sectors = {mm.instrument_key: mm.sector_index_key for mm in universe_members(session, "NIFTY50")}
    out = []
    for r in preds.itertuples():
        if symbols and r.symbol not in symbols:
            continue
        d = lake.read("1day", r.instrument_key)
        d = d[d["ts"].dt.tz_localize(None).dt.normalize() <= as_of]
        atr = float(ind.atr(d["high"], d["low"], d["close"]).iloc[-1])
        close_ts = datetime.combine(as_of.date(), time(15, 30), tzinfo=IST)
        snap = MarketSnapshot(
            instrument_key=r.instrument_key, last_price=float(r.close), atr=atr, data_ts=close_ts
        )
        x = Inputs(
            instrument_key=r.instrument_key,
            symbol=r.symbol,
            pipeline="swing",
            now=now,
            prediction={
                "p_up": r.p_up,
                "p_down": r.p_down,
                "p_neutral": r.p_neutral,
                "as_of": close_ts,
                "model_version": m.version,
                "promoted": m.promoted,
            },
            news=signal_for(session, r.instrument_key, now),
            regime=regime,
            market=snap,
            portfolio=default_portfolio(),
            sector=sectors.get(r.instrument_key),
        )
        dec = engine.decide(x)
        _persist(session, dec)
        out.append(dec)
    session.commit()
    return out, None


def run_intraday_replay(
    session: Session, settings: Settings, as_of: datetime, symbols: list[str] | None = None
):
    """Historical REPLAY: decisions as they would have been made at `as_of` using only data up to that bar.
    (Live intraday decisions need the Upstox live feed, which is blocked until credentials are provided.)"""
    lake = CandleLake(settings.data_dir)
    st = get_state(session)
    engine = DecisionEngine(RiskEngine(RiskLimits(**st.limits), kill_switch=st.kill_switch))
    try:
        m = inference.promoted(session, "intraday")
    except inference.ModelUnavailable as exc:
        return [], str(exc)
    art = inference.load_artifact(m)
    mem = [(mm.symbol, mm.instrument_key, mm.sector_index_key) for mm in universe_members(session)]
    if symbols:
        mem = [x for x in mem if x[0] in symbols]
    cfg = intr.IntradayConfig(start=str((as_of.astimezone(IST) - timedelta(days=60)).date()))
    ds = intr.build_intraday_dataset(lake, mem, load_global(settings.data_dir), cfg)
    cut = pd.Timestamp(as_of.astimezone(IST).replace(tzinfo=None)) - pd.Timedelta(minutes=5)
    ds = ds[ds["ts"] <= cut]  # decision bar must have CLOSED by as_of
    if ds.empty:
        return [], "no closed decision bar before as_of"
    preds = inference.predict_latest(ds, art, "ts")
    bar_close = (preds["ts"].iloc[0] + pd.Timedelta(minutes=5)).tz_localize(IST).to_pydatetime()
    regime = market_regime(lake, pd.Timestamp(preds["ts"].iloc[0]).normalize() - pd.Timedelta(days=1))
    sectors = {mm.instrument_key: mm.sector_index_key for mm in universe_members(session, "NIFTY50")}
    out = []
    for r in preds.itertuples():
        b = lake.read("5minute", r.instrument_key, end=preds["ts"].iloc[0].tz_localize(IST))
        atr = float(ind.atr(b["high"], b["low"], b["close"]).iloc[-1])
        snap = MarketSnapshot(
            instrument_key=r.instrument_key, last_price=float(r.close), atr=atr, data_ts=bar_close
        )
        x = Inputs(
            instrument_key=r.instrument_key,
            symbol=r.symbol,
            pipeline="intraday",
            now=as_of,
            prediction={
                "p_up": r.p_up,
                "p_down": r.p_down,
                "p_neutral": r.p_neutral,
                "as_of": bar_close,
                "model_version": m.version,
                "promoted": m.promoted,
            },
            news=signal_for(session, r.instrument_key, as_of),
            regime=regime,
            market=snap,
            portfolio=default_portfolio(),
            sector=sectors.get(r.instrument_key),
        )
        dec = engine.decide(x)
        dec.reasons.insert(0, "REPLAY (historical, simulated): not a live decision")
        _persist(session, dec)
        out.append(dec)
    session.commit()
    return out, None


def summarize(decisions) -> dict:
    acts = pd.Series([d.action for d in decisions]).value_counts().to_dict() if decisions else {}
    return {
        "count": len(decisions),
        "actions": acts,
        "mean_confidence": float(np.mean([d.confidence for d in decisions])) if decisions else None,
    }
