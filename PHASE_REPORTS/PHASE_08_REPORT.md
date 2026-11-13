# Phase 8 — Risk Engine

1. **Objective:** an independent risk engine that sizes positions and blocks unsafe orders; no signal may bypass it.

2. **Features implemented** (`app/engines/risk/`)
   - Contracts (`schemas.py`): `OrderIntent`, `MarketSnapshot`, `PortfolioState`, `RiskLimits` (validated bounds), `RiskVerdict` with every check recorded.
   - Sizing: fixed-fractional risk to the stop (default 0.5% of equity), ATR stop (2×ATR) when the intent has none, take-profit at 2R, trailing stop that only tightens.
   - Caps: single stock 10%, sector 25%, gross exposure 100%, cash (delivery buys); binding cap reported.
   - Blocks: kill switch, instrument mismatch, stale or future-dated data (intraday 120 s; delivery uses last completed session ≤ 4 days), unhealthy feed, invalid prices (< ₹0.01 tick / non-finite), entry > 2% from market, low confidence, invalid stop side, max drawdown (10%), daily loss limit (2%), max concurrent positions (10), duplicate same-direction position, average correlation with holdings > 0.8, portfolio 1-day 95% historical VaR > 3% after the trade. Missing return history with open holdings **fails closed**.
   - Metrics (`metrics.py`): historical VaR/CVaR, parametric VaR, correlation, full-revaluation P&L replay, stress scenarios (NIFTY ±5%, a 23-Mar-2020-like −13% day, financials −10%, IT −10%) via beta and sector shocks.
   - Persistence (`service.py`, tables `risk_state`, `risk_assessments`): kill switch and limits with audit events; every verdict (approved or rejected) stored with intent and reasons.
   - API (`app/api/risk.py`): `GET /risk/state`, `POST /risk/kill-switch`, `PUT /risk/limits`, `POST /risk/evaluate`, `POST /risk/portfolio`, `GET /risk/assessments`.

3. **Files created:** `app/engines/risk/{__init__,schemas,engine,metrics,service}.py`, `app/models/risk.py`, `app/api/risk.py`, migration `a780368c1a64`, `tests/test_risk.py`, `tests/test_api_risk.py`.
4. **Files modified:** `app/main.py` (router; 422 handler fix), `app/models/__init__.py`, `tests/conftest.py`, `tests/test_health.py`.
5. **Dependencies added:** none.
6. **Commands executed:** `pytest tests/test_risk.py tests/test_api_risk.py tests/test_health.py`.
7–9. **Tests:** **35 risk tests + 1 regression, all passing** (happy path, each of 12 blocking conditions parametrised, exact boundaries, concurrency/duplicates, sector/gross/cash caps, fail-closed without history, correlation block, VaR budget block, NaN rejection, every check recorded on rejection, hand-computed VaR/CVaR, parametric VaR, CVaR ≥ VaR, stress maths, delivery vs intraday freshness, API logging, kill switch block/release with audit, limits validation, invalid payloads → 422).

10. **Bugs discovered by tests**
    1. A ₹0.0001 price was **approved for 100,000,000 shares** (no tick floor).
    2. A drawdown of exactly −10% passed: `900000/1000000 − 1 = −0.09999999999999998` (float boundary).
    3. **Phase 1 bug:** the 422 handler crashed with HTTP 500 when a validator raised `ValueError` (exception object in `errors()` not JSON-serialisable).
    4. Test expectation error: sector cap (25%) was the binding cap, not the risk-based size.
11. **Bugs fixed:** price floor `MIN_PRICE = ₹0.01` with `prices_valid` check; `EPS = 1e-9` tolerance on limit comparisons; `jsonable_encoder(..., custom_encoder={Exception: str})` in the handler + regression test; test corrected (and both caps now asserted).
12. **Performance:** risk unit suite 31 tests in 1.6 s; a single evaluation is sub-millisecond (pure Python, no I/O) — VaR adds one matrix product over ≤ 500 days.
13. **Actual data verification:** `/risk/evaluate` and `/risk/portfolio` pull return history from the genuine Upstox daily lake.
14. **Remaining limitations:** no paper/live positions yet (paper trading postponed by the owner), so the decision engine sizes against a flat simulated ₹10 lakh book; correlation/VaR use daily data only; limits are global (not per strategy).
15. **Security:** limit changes and kill-switch toggles are audited; API authentication is still pending (Phase 13) — the risk endpoints must not be exposed beyond localhost until then.
16. **Acceptance gate:** **PASS** — risk controls block unsafe orders in automated tests.
17. **Next phase:** Phase 9 — Decision engine.
