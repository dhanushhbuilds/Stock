# Phase 7 — Strategy Engine

1. **Objective:** ten rule-based strategies with explicit rules, reproducible cost-aware backtests, regime breakdown, and a benchmark for the research question on slide 4 ("can ML + news beat rule-based strategies?").

2. **Features implemented** (`app/engines/strategy/`)
   - Strategies (textbook parameters fixed **before** testing — no optimisation): EMA 20/50 crossover, MACD momentum, RSI-14 mean reversion with SMA200 filter, Bollinger mean reversion, Donchian 20/10 breakout, SMA50/200 trend following, 1.5×ATR breakout (10-day time exit), cross-sectional 120-day relative-strength momentum, intraday VWAP reclaim, intraday 30-min opening-range breakout.
   - Backtester: signal at close t → execution at open t+1; 2×ATR stop on every trade (gap-through fills at the open); intraday flat by the 15:10 bar; whole shares; equal capital per stock.
   - Charges (`charges.py`): dated, configurable NSE/Upstox schedule (brokerage, STT, exchange, SEBI, stamp, GST, DP) + 5 bp slippage per side. Round trip on ₹1 lakh: **delivery 0.39%, intraday 0.18%**; on ₹20,000: delivery 0.68% (fixed fees dominate small positions).
   - Regime classification (NIFTY trend vs EMA200 + EMA50 slope; India VIX 1-year percentile) and per-regime trade statistics.
   - Runner + markdown report: `reports/strategies/strategies_2026-11-13.{json,md}`.

3. **Files created:** `app/engines/strategy/{__init__,charges,strategies,backtest,runner,report}.py`, `tests/test_strategy.py`.
4. **Files modified:** `app/engines/ml/{swing,intraday}.py` — ML cost assumptions aligned to the schedule (swing 0.25% → 0.39%, intraday 0.10% → 0.18%).
5. **Dependencies added:** none.
6. **Commands executed:** `python -m app.engines.strategy.runner` (50 stocks, 10 strategies, 54 s total).
7–9. **Tests:** `tests/test_strategy.py` — **8 passed**: next-open execution, stop-loss and gap fills, time exit, intraday flat-by-15:10 and no overnight carry of signals, hand-computed charges (₹20k delivery round trip = ₹135.368), rule behaviour on constructed series, signals unchanged when future bars are removed (all daily strategies), determinism.

10. **Bugs discovered:** operator-precedence bug in my own trend-following entry rule (`|` binds tighter than `<=`) caught in review before running; test bound on delivery costs was wrong (0.68% on ₹20k is correct) — this exposed the under-costed ML assumptions.
11. **Bugs fixed:** rule rewritten as "condition turns true"; ML costs derived from the schedule.
12. **Performance:** daily strategies ~0.1 s each over 50 stocks × ~2,700 days; intraday 14–20 s each over 50 stocks × ~86,000 bars.
13. **Results on genuine data (out of sample 2020-01-01 → 2026-11-12, ₹50 lakh, ₹1 lakh per stock)**

| strategy | total | Sharpe | max DD | trades | costs / gross profit |
|---|---|---|---|---|---|
| EMA crossover | 110.4% | 1.23 | −12.2% | 774 | 0.05 |
| Trend following | 141.3% | 1.14 | −14.1% | 896 | 0.05 |
| Donchian breakout | 73.5% | 1.08 | −14.1% | 1,508 | 0.08 |
| Relative-strength momentum | 69.6% | 0.99 | −13.0% | 568 | 0.04 |
| ATR breakout | 11.3% | 0.46 | −8.5% | 1,569 | 0.14 |
| MACD momentum | 6.6% | 0.30 | −11.3% | 1,534 | 0.16 |
| RSI mean reversion | 1.1% | 0.19 | −2.2% | 128 | 0.12 |
| Bollinger mean reversion | −9.1% | −0.14 | −26.2% | 2,004 | 0.15 |
| Opening-range breakout (intraday) | −64.0% | −7.99 | −64.1% | 27,839 | 0.59 |
| VWAP trend (intraday) | −82.2% | −20.95 | −82.2% | 38,101 | 1.57 |
| *Equal-weight buy & hold (benchmark)* | 291.7% | 1.21 | −39.1% | — | — |
| *NIFTY 50 index (benchmark)* | 107.9% | 0.70 | −38.4% | — | — |

   Reading: trend strategies match buy-and-hold's Sharpe with roughly a third of its drawdown but lower total return; mean-reversion adds little; the intraday rules lose money mainly through costs (VWAP's costs are 1.57× its gross profit; both are also slightly negative before costs).
14. **Remaining limitations:** current-constituent universe → survivorship bias (flatters all long strategies and the benchmark); long-only; no controlled parameter optimisation yet (deliberately — avoids snooping); intraday uses 5-minute bars, so intrabar stop ordering is approximated.
15. **Security:** none (offline analytics).
16. **Acceptance gate:** **PASS** — ten strategies produce reproducible, cost-inclusive reports with benchmarks and regime breakdowns.
17. **Next phase:** Phase 8 — Risk engine.
