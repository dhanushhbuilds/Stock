"""Indian equity transaction charges (NSE), as a dated, configurable schedule.

Sources consulted 2026-11-13 (where they disagree, the higher figure is used):
- Upstox pricing / help centre: brokerage Rs 20 per executed order (intraday: min(Rs 20, 0.1%)), NSE exchange
  transaction charge 0.00322%, SEBI fee Rs 10/crore, DP charge Rs 20 + GST per scrip on delivery sells.
- STT: delivery 0.1% on buy and sell; intraday 0.025% on sell (unchanged by Budget 2026, which only revised F&O).
- Stamp duty (buy side): delivery 0.015%, intraday 0.003%.  GST 18% on brokerage + exchange + SEBI charges.
Verify against the broker's live rate card before relying on exact rupee figures.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChargeSchedule:
    as_of: str = "2026-11-13"
    brokerage_per_order: float = 20.0
    intraday_brokerage_pct_cap: float = 0.001  # min(Rs 20, 0.1%)
    exchange_pct: float = 0.0000322
    sebi_pct: float = 0.000001
    gst_pct: float = 0.18
    stt_delivery_pct: float = 0.001  # buy and sell
    stt_intraday_sell_pct: float = 0.00025
    stamp_delivery_buy_pct: float = 0.00015
    stamp_intraday_buy_pct: float = 0.00003
    dp_charge_per_sell: float = 20.0
    slippage_pct: float = 0.0005  # 5 bp per side for liquid NIFTY 50 names (assumption)

    def costs(self, notional: float, side: str, product: str) -> dict[str, float]:
        """Rupee costs for ONE order (one side). side: BUY|SELL, product: DELIVERY|INTRADAY."""
        if notional <= 0:
            return {"total": 0.0}
        if product == "INTRADAY":
            brokerage = min(self.brokerage_per_order, self.intraday_brokerage_pct_cap * notional)
            stt = self.stt_intraday_sell_pct * notional if side == "SELL" else 0.0
            stamp = self.stamp_intraday_buy_pct * notional if side == "BUY" else 0.0
            dp = 0.0
        else:
            brokerage = self.brokerage_per_order
            stt = self.stt_delivery_pct * notional
            stamp = self.stamp_delivery_buy_pct * notional if side == "BUY" else 0.0
            dp = self.dp_charge_per_sell * (1 + self.gst_pct) if side == "SELL" else 0.0
        exch, sebi = self.exchange_pct * notional, self.sebi_pct * notional
        gst = self.gst_pct * (brokerage + exch + sebi)
        slip = self.slippage_pct * notional
        parts = {
            "brokerage": brokerage,
            "stt": stt,
            "exchange": exch,
            "sebi": sebi,
            "stamp": stamp,
            "gst": gst,
            "dp": dp,
            "slippage": slip,
        }
        parts["total"] = sum(parts.values())
        return parts

    def round_trip_pct(self, notional: float, product: str) -> float:
        return (
            self.costs(notional, "BUY", product)["total"] + self.costs(notional, "SELL", product)["total"]
        ) / notional
