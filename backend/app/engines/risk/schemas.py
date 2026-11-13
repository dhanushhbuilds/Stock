"""Risk engine contracts. The decision engine sends an OrderIntent; only an approved RiskVerdict may become an order."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RiskLimits(BaseModel):
    risk_per_trade_pct: float = Field(0.005, gt=0, le=0.05)  # capital at risk to the stop (0.5%)
    atr_stop_multiple: float = Field(2.0, gt=0)
    take_profit_r: float = Field(2.0, gt=0)  # take-profit at 2R
    trailing_atr_multiple: float = Field(2.0, gt=0)
    max_single_stock_pct: float = Field(0.10, gt=0, le=1)
    max_gross_exposure_pct: float = Field(1.0, gt=0, le=5)
    max_sector_pct: float = Field(0.25, gt=0, le=1)
    max_concurrent_positions: int = Field(10, ge=1)
    daily_loss_limit_pct: float = Field(0.02, gt=0, le=1)
    max_drawdown_pct: float = Field(0.10, gt=0, le=1)
    max_data_age_s: float = Field(120.0, gt=0)  # INTRADAY: live data required
    # DELIVERY (swing) decisions use the last completed daily close and are placed for the next session.
    max_eod_data_age_s: float = Field(4 * 86400.0, gt=0)
    min_confidence: float = Field(0.40, ge=0, le=1)
    max_avg_correlation: float = Field(0.80, gt=-1, le=1)
    var_confidence: float = Field(0.95, gt=0.5, lt=1)
    max_portfolio_var_pct: float = Field(0.03, gt=0, le=1)  # 1-day 95% VaR budget


class Position(BaseModel):
    instrument_key: str
    sector: str | None = None
    quantity: int  # signed: + long, - short
    avg_price: float = Field(gt=0)
    last_price: float = Field(gt=0)

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price


class PortfolioState(BaseModel):
    equity: float = Field(gt=0)
    cash: float
    start_of_day_equity: float = Field(gt=0)
    peak_equity: float = Field(gt=0)
    positions: list[Position] = Field(default_factory=list)

    @property
    def gross_exposure(self) -> float:
        return sum(abs(p.market_value) for p in self.positions)


class MarketSnapshot(BaseModel):
    instrument_key: str
    last_price: float
    atr: float | None = None  # same timeframe as the strategy
    data_ts: datetime
    feed_healthy: bool = True

    @field_validator("last_price")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not (v == v) or v in (float("inf"), float("-inf")):
            raise ValueError("price must be finite")
        return v


class OrderIntent(BaseModel):
    intent_id: str
    instrument_key: str
    sector: str | None = None
    side: Literal["BUY", "SELL"]
    product: Literal["INTRADAY", "DELIVERY"]
    entry_price: float
    stop_price: float | None = None  # if omitted, the risk engine sets an ATR stop
    confidence: float = Field(ge=0, le=1)
    model_version: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _no_naked_delivery_short(self) -> "OrderIntent":
        if self.side == "SELL" and self.product == "DELIVERY":
            raise ValueError(
                "short selling is only modelled for INTRADAY (cash-market delivery shorts not allowed)"
            )
        return self


class RiskCheck(BaseModel):
    name: str
    passed: bool
    value: float | str | None = None
    limit: float | str | None = None
    detail: str | None = None


class RiskVerdict(BaseModel):
    intent_id: str
    approved: bool
    quantity: int = 0
    stop_price: float | None = None
    take_profit: float | None = None
    trailing_stop_distance: float | None = None
    checks: list[RiskCheck]
    reasons: list[str]
    evaluated_at: datetime
