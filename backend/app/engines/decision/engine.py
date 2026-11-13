"""Decision engine (Engine 6): combines ML probabilities, news intelligence, market regime and data freshness,
then routes every candidate trade through the independent risk engine.

Outputs BUY / SELL / HOLD / NO_TRADE with signal contributions and reasons. NO_TRADE is the default: any
missing, stale or conflicting input, or any risk rejection, yields NO_TRADE. This module never places orders.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.engines.risk.engine import RiskEngine
from app.engines.risk.schemas import MarketSnapshot, OrderIntent, PortfolioState

Action = Literal["BUY", "SELL", "HOLD", "NO_TRADE"]


@dataclass(frozen=True)
class DecisionPolicy:
    min_direction_prob: float = 0.40  # p_up (or p_down) must be at least this AND the largest class
    min_edge: float = 0.08  # combined score threshold
    news_weight: float = 0.25  # weight of news sentiment (x its confidence) in the score
    news_veto: float = 0.5  # strongly opposing news (|sentiment*confidence|) vetoes the trade
    max_prediction_age: dict = field(
        default_factory=lambda: {"intraday": timedelta(minutes=10), "swing": timedelta(days=4)}
    )
    bearish_regime_blocks_longs: bool = True


@dataclass
class Inputs:
    instrument_key: str
    symbol: str
    pipeline: Literal["intraday", "swing"]
    now: datetime
    prediction: dict | None  # {p_down, p_neutral, p_up, as_of: datetime, model_version, promoted}
    news: dict | None  # news.service.signal_for output
    regime: dict | None  # {trend: "bull"|"bear"|"sideways", volatility: "high"|"normal"|"low"}
    market: MarketSnapshot | None
    portfolio: PortfolioState
    sector: str | None = None
    holding_qty: int = 0


@dataclass
class Decision:
    decision_id: str
    instrument_key: str
    symbol: str
    pipeline: str
    action: Action
    confidence: float
    score: float | None
    contributions: dict
    reasons: list[str]
    model_version: str | None
    market_conditions: dict | None
    risk: dict | None
    quantity: int
    created_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d


class DecisionEngine:
    def __init__(self, risk: RiskEngine, policy: DecisionPolicy | None = None) -> None:
        self.risk, self.policy = risk, policy or DecisionPolicy()

    def decide(self, x: Inputs) -> Decision:
        P = self.policy
        reasons: list[str] = []
        contrib: dict = {}

        def out(action: Action, conf=0.0, score=None, risk=None, qty=0) -> Decision:
            return Decision(
                str(uuid.uuid4()),
                x.instrument_key,
                x.symbol,
                x.pipeline,
                action,
                round(conf, 4),
                None if score is None else round(score, 4),
                contrib,
                reasons,
                (x.prediction or {}).get("model_version"),
                x.regime,
                risk,
                qty,
                x.now,
            )

        # 1. hard input requirements -> NO_TRADE
        if x.prediction is None:
            reasons.append("no model prediction available")
            return out("NO_TRADE")
        if not x.prediction.get("promoted", False):
            reasons.append("model has not passed the promotion gate")
            return out("NO_TRADE")
        age = x.now - x.prediction["as_of"]
        if age > P.max_prediction_age[x.pipeline] or age < timedelta(0):
            reasons.append(f"prediction is stale or future-dated (age {age})")
            return out("NO_TRADE")
        if x.market is None:
            reasons.append("no market snapshot (price/ATR) available")
            return out("NO_TRADE")

        p_up, p_dn, p_nu = x.prediction["p_up"], x.prediction["p_down"], x.prediction["p_neutral"]
        ml = p_up - p_dn
        contrib["ml"] = {
            "p_up": round(p_up, 4),
            "p_neutral": round(p_nu, 4),
            "p_down": round(p_dn, 4),
            "score": round(ml, 4),
        }
        news_term = 0.0
        if x.news and x.news.get("items"):
            news_term = P.news_weight * x.news["sentiment"] * x.news["confidence"]
            contrib["news"] = {
                "sentiment": round(x.news["sentiment"], 4),
                "confidence": round(x.news["confidence"], 4),
                "items": x.news["items"],
                "score": round(news_term, 4),
                "top": [t["title"] for t in x.news.get("top", [])[:3]],
            }
        else:
            contrib["news"] = {"items": 0, "score": 0.0, "note": "no usable news (neutral)"}
        score = ml + news_term
        contrib["total_score"] = round(score, 4)
        direction = "BUY" if score > 0 else "SELL"
        dir_prob = p_up if direction == "BUY" else p_dn
        conf = dir_prob

        # 2. holding management
        if x.holding_qty:
            long = x.holding_qty > 0
            if (
                long and direction == "SELL" and p_dn >= P.min_direction_prob and abs(score) >= P.min_edge
            ) or (
                not long and direction == "BUY" and p_up >= P.min_direction_prob and abs(score) >= P.min_edge
            ):
                reasons.append("signal reversed against the open position: exit")
                action: Action = "SELL" if long else "BUY"
                return out(action, conf, score)
            reasons.append("position open and no reversal signal: keep")
            return out("HOLD", conf, score)

        # 3. signal strength
        if dir_prob < P.min_direction_prob or dir_prob < max(p_up, p_dn, p_nu):
            reasons.append(
                f"directional probability {dir_prob:.3f} not dominant / below {P.min_direction_prob}"
            )
            return out("NO_TRADE", conf, score)
        if abs(score) < P.min_edge:
            reasons.append(f"edge {abs(score):.3f} below threshold {P.min_edge}")
            return out("NO_TRADE", conf, score)

        # 4. conflicts
        if x.news and x.news.get("items"):
            nv = x.news["sentiment"] * x.news["confidence"]
            if (direction == "BUY" and nv <= -P.news_veto) or (direction == "SELL" and nv >= P.news_veto):
                reasons.append(
                    f"conflicting signals: model says {direction}, news strongly opposite ({nv:+.2f})"
                )
                return out("NO_TRADE", conf, score)
        if (
            x.regime
            and P.bearish_regime_blocks_longs
            and direction == "BUY"
            and x.regime.get("trend") == "bear"
            and x.pipeline == "swing"
        ):
            reasons.append("bearish market regime: new swing longs blocked")
            return out("NO_TRADE", conf, score)
        if direction == "SELL" and x.pipeline == "swing":
            reasons.append("bearish swing signal but no holding: cash-market delivery shorts are not allowed")
            return out("NO_TRADE", conf, score)

        # 5. risk engine (independent veto + sizing)
        intent = OrderIntent(
            intent_id=str(uuid.uuid4()),
            instrument_key=x.instrument_key,
            sector=x.sector,
            side=direction,
            product="INTRADAY" if x.pipeline == "intraday" else "DELIVERY",
            entry_price=x.market.last_price,
            stop_price=None,
            confidence=conf,
            model_version=x.prediction.get("model_version"),
            created_at=x.now,
        )
        verdict = self.risk.evaluate(intent, x.market, x.portfolio, now=x.now)
        risk = {
            "approved": verdict.approved,
            "quantity": verdict.quantity,
            "stop": verdict.stop_price,
            "take_profit": verdict.take_profit,
            "reasons": verdict.reasons,
            "failed_checks": [c.name for c in verdict.checks if not c.passed],
        }
        if not verdict.approved:
            reasons.append("risk engine rejected: " + "; ".join(verdict.reasons))
            return out("NO_TRADE", conf, score, risk)
        reasons.append(
            f"{direction}: model edge {ml:+.3f}, news {news_term:+.3f}; risk approved {verdict.quantity} "
            f"shares, stop {verdict.stop_price}, target {verdict.take_profit}"
        )
        return out(direction, conf, score, risk, verdict.quantity)
