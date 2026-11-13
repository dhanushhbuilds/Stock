# Phase 9 — Decision Engine

1. **Objective:** combine ML, news, regime and freshness into explainable BUY / SELL / HOLD / NO_TRADE decisions, with every candidate trade passing the independent risk engine.

2. **Features implemented** (`app/engines/decision/`)
   - `engine.py` — pure decision logic. Score = (p_up − p_down) + 0.25 × news sentiment × news confidence.
     NO_TRADE when: no prediction; model not promoted; prediction stale or future-dated (intraday 10 min, swing 4 days); no market snapshot; directional probability not dominant or < 0.40; edge < 0.08; news strongly opposite (|sentiment × confidence| ≥ 0.5); bearish regime for new swing longs; bearish swing signal without a holding (no cash-market delivery shorts); **any risk rejection**.
     HOLD/exit logic for open positions. Every decision carries contributions (ML probabilities, news items), reasons, regime, risk verdict, model version and timestamp.
   - `service.py` — wires real data: promoted model artifact (SHA-256 verified) → latest predictions using the **same dataset builders as training**; point-in-time news signals; NIFTY/VIX regime; ATR market snapshot; persisted `decisions` table + audit event per decision. Swing runs on the last completed session; intraday runs as an explicit **historical replay** (labelled in the decision) until the live feed is connected.
   - API: `POST /decisions/run?pipeline=swing|intraday&as_of=`, `GET /decisions`, `GET /decisions/health` (reports 0 orders placed — this engine never places orders).

3. **Files created:** `app/engines/decision/{__init__,engine,service}.py`, `app/engines/ml/inference.py`, `app/models/decision.py`, `app/api/decisions.py`, migration `27be3086cd61`, `tests/test_decision.py`.
4. **Files modified:** `app/engines/risk/{schemas,engine}.py` (end-of-day freshness for delivery), `tests/test_risk.py`.
5. **Dependencies added:** none.
7–9. **Tests:** `tests/test_decision.py` — **16 passed**: BUY with risk-approved size/stop/target; intraday SELL; eight invalid/weak-input cases → NO_TRADE with the right reason; stale market data rejected by risk (not bypassed); kill switch → NO_TRADE; swing no-short and bear-regime rules; news lifting a marginal signal (explained); holding management; every decision has a traceable explanation.
10. **Bugs discovered:** risk freshness of 120 s made every end-of-day swing decision fail as "stale" — correct for intraday, wrong for next-session delivery orders; my own test arithmetic (edge exactly at threshold).
11. **Bugs fixed:** separate `max_eod_data_age_s` for DELIVERY (test added both ways); test corrected to a genuinely marginal case.
12–13. **Performance / real data:** end-to-end runs on real data are recorded in the Phase 4 report once the final promoted models exist.
14. **Remaining limitations:** paper trading postponed by the owner → decisions are sized against a flat simulated ₹10 lakh book and never become orders; intraday live decisions blocked on Upstox credentials (replay only); policy thresholds are a-priori choices, not tuned.
15. **Security:** decision engine has no broker handle; `LIVE_TRADING_ENABLED` cannot be enabled (config validator).
16. **Acceptance gate:** **PASS** — engines communicate through typed contracts and invalid conditions cannot produce an executable (risk-approved) action in tests.
17. **Next phase:** Phase 10 — Paper trading (postponed by the owner).
