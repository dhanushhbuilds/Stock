"""Risk engine (Engine 5). Independent of the decision engine: it receives an OrderIntent and the current
portfolio/market state and returns a RiskVerdict. A signal can never bypass it.

Policy: every check is evaluated and recorded; the intent is approved only if ALL checks pass and the sized
quantity is >= 1. Missing or invalid inputs fail closed.
"""

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.engines.risk import metrics
from app.engines.risk.schemas import (
    MarketSnapshot,
    OrderIntent,
    PortfolioState,
    RiskCheck,
    RiskLimits,
    RiskVerdict,
)

MIN_PRICE = 0.01
EPS = 1e-9


def atr_stop(side: str, entry: float, atr: float, multiple: float) -> float:
    return entry - multiple * atr if side == "BUY" else entry + multiple * atr


def update_trailing_stop(
    side: str, current_stop: float, best_price: float, atr: float, multiple: float
) -> float:
    """Ratchet only in the trade's favour: never loosens."""
    if side == "BUY":
        return max(current_stop, best_price - multiple * atr)
    return min(current_stop, best_price + multiple * atr)


def position_size(equity: float, risk_pct: float, entry: float, stop: float) -> int:
    per_share = abs(entry - stop)
    if per_share <= 0 or not math.isfinite(per_share):
        return 0
    return int(math.floor(equity * risk_pct / per_share))


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None, kill_switch: bool = False) -> None:
        self.limits = limits or RiskLimits()
        self.kill_switch = kill_switch

    def evaluate(
        self,
        intent: OrderIntent,
        market: MarketSnapshot,
        pf: PortfolioState,
        returns: pd.DataFrame | None = None,
        now: datetime | None = None,
    ) -> RiskVerdict:
        L, now = self.limits, now or datetime.now(UTC)
        checks: list[RiskCheck] = []

        def add(name, passed, value=None, limit=None, detail=None):
            checks.append(RiskCheck(name=name, passed=bool(passed), value=value, limit=limit, detail=detail))

        add("kill_switch_off", not self.kill_switch, "ON" if self.kill_switch else "OFF", "OFF")
        add(
            "instrument_matches",
            intent.instrument_key == market.instrument_key,
            market.instrument_key,
            intent.instrument_key,
        )
        age = (now - market.data_ts).total_seconds()
        max_age = L.max_data_age_s if intent.product == "INTRADAY" else L.max_eod_data_age_s
        add(
            "market_data_fresh",
            0 <= age <= max_age,
            round(age, 1),
            max_age,
            "stale or future-dated market data" if not 0 <= age <= max_age else None,
        )
        add("feed_healthy", market.feed_healthy)
        # NSE's smallest tick is Rs 0.01; anything below is not a tradable price (and would explode sizing).
        prices_ok = all(math.isfinite(x) and x >= MIN_PRICE for x in (intent.entry_price, market.last_price))
        add("prices_valid", prices_ok, intent.entry_price, MIN_PRICE)
        dev = abs(intent.entry_price / market.last_price - 1) if prices_ok else float("inf")
        add("entry_near_market", dev <= 0.02, round(dev, 5), 0.02,
            None if dev <= 0.02 else "entry >2% away from last traded price")
        add("confidence", intent.confidence >= L.min_confidence, intent.confidence, L.min_confidence)

        # ---- stop / take-profit ----
        stop = intent.stop_price
        atr_ok = market.atr is not None and math.isfinite(market.atr) and market.atr > 0
        if stop is None and atr_ok:
            stop = atr_stop(intent.side, intent.entry_price, market.atr, L.atr_stop_multiple)
        stop_ok = (
            stop is not None
            and math.isfinite(stop)
            and stop > 0
            and (stop < intent.entry_price if intent.side == "BUY" else stop > intent.entry_price)
        )
        add(
            "stop_valid",
            stop_ok,
            stop,
            None,
            None if stop_ok else "stop missing or on the wrong side of entry",
        )
        risk_per_share = abs(intent.entry_price - stop) if stop_ok else None
        tp = None
        if stop_ok:
            tp = intent.entry_price + (1 if intent.side == "BUY" else -1) * L.take_profit_r * risk_per_share

        # ---- portfolio state limits ----
        # Breach at or beyond the limit; EPS absorbs float error (900000/1000000 - 1 = -0.09999999999999998).
        dd = pf.equity / pf.peak_equity - 1
        add("max_drawdown", dd > -L.max_drawdown_pct + EPS, round(dd, 5), -L.max_drawdown_pct)
        day = pf.equity / pf.start_of_day_equity - 1
        add("daily_loss_limit", day > -L.daily_loss_limit_pct + EPS, round(day, 5), -L.daily_loss_limit_pct)
        open_n = sum(1 for p in pf.positions if p.quantity != 0)
        existing = next(
            (p for p in pf.positions if p.instrument_key == intent.instrument_key and p.quantity), None
        )
        adds_position = existing is None
        add(
            "max_concurrent_positions",
            open_n + adds_position <= L.max_concurrent_positions,
            open_n + adds_position,
            L.max_concurrent_positions,
        )
        same_dir = existing is not None and (existing.quantity > 0) == (intent.side == "BUY")
        add(
            "no_duplicate_position",
            not same_dir,
            None,
            None,
            "already holding this instrument in the same direction" if same_dir else None,
        )

        # ---- sizing: fixed-fractional risk, then capped by every exposure limit ----
        qty = position_size(pf.equity, L.risk_per_trade_pct, intent.entry_price, stop) if stop_ok else 0
        caps = {"risk_based": qty}
        px = intent.entry_price if prices_ok else float("inf")
        caps["single_stock"] = int(L.max_single_stock_pct * pf.equity // px)
        caps["gross_exposure"] = int(max(L.max_gross_exposure_pct * pf.equity - pf.gross_exposure, 0) // px)
        sector_now = sum(
            abs(p.market_value) for p in pf.positions if intent.sector and p.sector == intent.sector
        )
        caps["sector"] = (
            int(max(L.max_sector_pct * pf.equity - sector_now, 0) // px) if intent.sector else qty
        )
        if intent.side == "BUY" and intent.product == "DELIVERY":
            caps["cash"] = int(max(pf.cash, 0) // px)
        qty = max(min(caps.values()), 0) if prices_ok else 0
        binding = min(caps, key=caps.get) if caps else None
        add("sized_quantity_positive", qty >= 1, qty, 1, f"binding cap: {binding}")

        # ---- correlation & VaR (need return history; fail closed when holdings exist but data is missing) ----
        held = [p.instrument_key for p in pf.positions if p.quantity]
        if held:
            if returns is None:
                add("correlation", False, None, L.max_avg_correlation, "no return history supplied")
                add("portfolio_var", False, None, L.max_portfolio_var_pct, "no return history supplied")
            else:
                rho = metrics.avg_correlation(intent.instrument_key, held, returns)
                add(
                    "correlation",
                    rho is None or rho <= L.max_avg_correlation,
                    None if rho is None else round(rho, 4),
                    L.max_avg_correlation,
                )
                self._var_check(add, intent, pf, returns, qty)
        else:
            add("correlation", True, None, L.max_avg_correlation, "no existing holdings")
            if returns is not None and intent.instrument_key in returns.columns and qty:
                self._var_check(add, intent, pf, returns, qty)

        failed = [c for c in checks if not c.passed]
        approved = not failed
        return RiskVerdict(
            intent_id=intent.intent_id,
            approved=approved,
            quantity=qty if approved else 0,
            stop_price=round(stop, 4) if stop_ok else None,
            take_profit=round(tp, 4) if tp else None,
            trailing_stop_distance=(L.trailing_atr_multiple * market.atr) if atr_ok else None,
            checks=checks,
            reasons=[f"{c.name}: {c.detail or f'{c.value} vs limit {c.limit}'}" for c in failed]
            or ["all checks passed"],
            evaluated_at=now,
        )

    def _var_check(self, add, intent, pf, returns, qty):
        L = self.limits
        values = {p.instrument_key: p.market_value for p in pf.positions if p.quantity}
        sign = 1 if intent.side == "BUY" else -1
        values[intent.instrument_key] = values.get(intent.instrument_key, 0) + sign * qty * intent.entry_price
        try:
            pnl = metrics.portfolio_pnl_series(values, returns)
            var = metrics.historical_var(pnl, L.var_confidence) / pf.equity
            add(
                "portfolio_var",
                var <= L.max_portfolio_var_pct,
                round(var, 5),
                L.max_portfolio_var_pct,
                f"1-day {int(L.var_confidence * 100)}% historical VaR after this trade",
            )
        except ValueError as exc:
            add("portfolio_var", False, None, L.max_portfolio_var_pct, str(exc))


def returns_matrix(closes: dict[str, pd.Series]) -> pd.DataFrame:
    return pd.DataFrame(closes).sort_index().pipe(lambda d: np.log(d / d.shift(1))).iloc[1:]
