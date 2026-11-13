# Phase 3 — Feature Engineering

1. **Objective:** leakage-free, reproducible feature + label pipelines for intraday (5-min → next 30 min) and swing (daily → next 5 sessions), as specified in the Review-1 deck (slides 6–8).

2. **Features implemented**
   - `app/engines/ml/indicators.py`: EMA, SMA, Wilder RSI, ATR (Wilder), MACD, stochastic, Bollinger (%B, bandwidth), ROC, log returns, realised volatility — all causal.
   - **Swing** (`swing.py`, 77 features): returns 1/2/5/10/20/60d; distance to EMA 9/20/50/200 and SMA 20/50; EMA crossovers; RSI 14/2; MACD (line/signal/hist, price-normalised); ROC; stochastic; ATR; Bollinger; realised vol 20/60 and ratio; range, close-location value, gap; distance to 20-day high/low; relative volume, volume momentum, price–volume divergence, OBV slope; NIFTY context (returns, EMA50 distance, vol, RSI); India VIX level / 5-day change / 60-day z-score; relative strength vs NIFTY and vs sector index; 60-day beta; day of week; 7 cross-sectional percentile ranks; **8 global series** (S&P 500, Nasdaq, Nikkei, Hang Seng, Brent, USD/INR returns, US VIX, US 10Y change) joined **strictly before** the NSE session date.
   - **Intraday** (`intraday.py`, 48 features): 5-min returns 1/3/6/12 bars; EMA 9/20 distance; RSI; MACD hist; ATR; Bollinger; range; session VWAP distance; time-of-day relative volume (same slot, previous 20 sessions); volume momentum; return since open; opening-range (09:15–09:40) distances; intraday vol so far; time of day; gap; previous-day high/low distance; previous-session daily RSI/return/EMA20 distance/vol; NIFTY 5-min returns and relative strength; VIX and global context (previous session); 5 cross-sectional ranks.
   - **Labels** (`labels.py`): R = P(t+h)/P(t) − 1, τ = max(c·σ·√h, round-trip cost), UP/NEUTRAL/DOWN. c = 0.5 fixed a priori. Swing default `label_mode="excess"` (return minus same-date universe mean) — see Phase 4 for why.
   - **Closing-auction handling:** intraday uses only bars starting 09:15–15:10; decisions every 15 min from the 09:40 bar to the 14:40 bar so the 30-minute label always ends by 15:15 (never in the post-2026-08-03 auction placeholders).
   - **Dataset versioning:** content hash of (config + data) → `data/datasets/{pipeline}/{hash}.parquet` + `ml_datasets` table.

3. **Files created:** `app/engines/ml/{__init__,indicators,labels,swing,intraday}.py`, `app/engines/data/global_data.py`, `tests/test_ml_features.py`.
4. **Files modified:** `app/engines/data/{instruments,service,cli}.py` (multi-universe support).
5. **Dependencies added:** yfinance 1.8.0 (global context download), scikit-learn/xgboost/lightgbm/torch (Phase 4). System: Homebrew `libomp` (LightGBM runtime).
6. **Commands executed:** dataset builds for swing (431,698 rows / 197 symbols incl. training-only universes; 118,639 labelled NIFTY 50 rows) and intraday (1,250,481 rows / 50 symbols); leak-planting experiments (below).
7–9. **Tests:** `tests/test_ml_features.py` — **17 passed, 0 failed** (indicators vs independent loop implementations for EMA/RSI/ATR at rtol ≤ 1e-10, MACD/Bollinger/stochastic reference values, label rules incl. cost floor and missing-future → no label, chronological purged splits, swing and intraday truncation-invariance leak tests, exact 30-min label alignment, global data strictly-before join, special-session exclusion, missing-volume handling, VWAP session reset, torch/xgboost/lightgbm coexistence).

10. **Bugs discovered (all by tests)**
    1. Intraday leak test initially cut data at day end and **missed a planted look-ahead** (decisions stop at 14:40). Test strengthened to cut mid-session (12:00); it now catches the planted leak.
    2. Strengthened test then found a **real leak in row selection**: special sessions were removed using the whole day's bar count (unknown at noon).
    3. Found a **live/historical parity bug**: previous-day daily features were attached via `shift(1)` on the daily table, which needs today's daily row — absent in live trading → features would be NaN in production.
    4. Fixture bug: minute data window depended on truncation length.
    5. Native crash: `import lightgbm` before `import torch` segfaults (exit 139); later `torch` before `xgboost` also segfaults.
11. **Bugs fixed:** (2) causal regular-session rule (weekday AND first bar 09:15); (3) `_asof_before()` as-of join strictly before the session date — identical in history and live; (5) package import guard xgboost → torch → lightgbm with a subprocess regression test that trains all three.
12. **Performance:** swing dataset build 3.3 s (431k rows); intraday build ~10 s (1.25M rows, 358 MB float32).
13. **Actual data verification:** built entirely from the genuine Upstox lake (Phase 2) and Yahoo global series; Yahoo NIFTY 50 / India VIX from the team's archive agree with Upstox to median 2e-8 relative difference over 1,234 common days.
14. **Remaining limitations:** universe = current constituents (survivorship bias); global series via Yahoo Finance (personal/research terms); no fundamentals or historical news features (no legitimate free history).
15. **Security:** none new (read-only analytics).
16. **Acceptance gate:** **PASS** — valid, reproducible (content-hashed) datasets; leakage tests pass and are proven to fail on planted leaks.
17. **Next phase:** Phase 4 — ML/DL training.
