# AstraQuant X-2026 — Architecture

Status (2026-11-13): implemented — foundation, data engine (historical), features, ML training/registry/inference, news, strategies + backtester, risk, decision. Not yet — live feed (blocked on credentials), paper trading (postponed), frontend pages, auth/hardening, broker adapter.

## 1. Shape of the system

A **modular monolith**: one FastAPI backend process plus background workers, sharing one PostgreSQL database.
The six engines are Python packages with explicit interfaces. They talk through typed function calls
and an in-process event bus (Redis pub/sub only where events need to leave the process, e.g. live ticks to WebSocket clients).
No microservices.

```
                   ┌──────────────────────── React terminal (Vite + TS) ────────────────────────┐
                   │ 10 pages · REST via typed client · WebSocket for ticks / decisions / orders │
                   └───────────────▲───────────────────────────────────────────▲───────────────┘
                                   │ REST                                      │ WS
┌──────────────────────────────────┴───────────── FastAPI app ─────────────────┴──────────────────┐
│  api/ (routers, auth, error handling)                                                          │
│                                                                                                │
│  E1 data ──bars──► E2 ml ──predictions──┐                                                      │
│     │                                   ▼                                                      │
│     ├──bars──► E4 strategy ──signals──► E6 decision ──order intent──► E5 risk ──approved──►    │
│     │                                   ▲                              (veto, sizing)  paper   │
│  E3 news ──scored events────────────────┘                                              broker  │
│                                                                                                │
│  core/ (config, logging, db session, event bus, clock, audit)                                  │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
        │ SQLAlchemy/Alembic                │ Parquet (pyarrow)            │ Redis
   PostgreSQL 18: metadata,           data/ lake: candles, features,   live LTP cache, feed
   orders, decisions, audit           datasets (versioned)             heartbeat, pub/sub
```

Rule that everything else depends on: **an order can only be created by the risk engine approving an order intent.**
The decision engine produces intents; it has no handle on the broker.

## 2. Repository layout (planned)

```
astraquant-x/
  backend/
    pyproject.toml
    alembic/                    migrations
    app/
      core/                     config (pydantic-settings), logging (structlog JSON), db, events, clock, audit
      api/                      FastAPI routers per engine + health + auth
      engines/
        data/                   E1: upstox client, oauth, instruments, historical downloader, live feed, validation, storage
        ml/                     E2: features, targets, splits (walk-forward, purge, embargo), models, registry, inference, drift
        news/                   E3: sources, dedup, entities, classifier, finbert sentiment, scoring
        strategy/               E4: 10 strategies, regime classifier, backtester, optimizer
        risk/                   E5: sizing, limits, VaR/CVaR, stress, kill switch
        decision/               E6: aggregator, explainer, decision log
        execution/              paper broker, charges, positions, P&L; upstox order adapter (disabled)
      models/                   SQLAlchemy ORM tables
      schemas/                  Pydantic API schemas
      workers/                  scheduled jobs (incremental download, feed, retrain, news poll)
    tests/                      unit / integration / fixtures (incl. protobuf + candle fixtures)
  frontend/                     React + TS + Vite + Tailwind + shadcn/ui + lightweight-charts + Recharts
  data/                         Parquet lake (gitignored)
  artifacts/                    model artifacts + registry files (gitignored, metadata in Postgres)
  docker-compose.yml            postgres, redis, backend, frontend
  PHASE_REPORTS/
```

## 3. Engine interfaces (contracts)

| Engine | Input | Output | Key guarantees |
|---|---|---|---|
| E1 Data | Upstox REST/WS | `Candle` rows (Parquet), `Tick` events, `Instrument` table, quality reports | No invented instrument keys (only from Upstox instrument master); no fabricated candles; every gap reported, never filled silently |
| E2 ML | Candles + context series | `Prediction{symbol, horizon, p_up, p_neutral, p_down, vol_forecast, regime, model_version, ts}` | Same feature code path for training and live; chronological walk-forward with purge + embargo; promotion only on out-of-sample metrics |
| E3 News | Legitimate sources (NSE/BSE announcements, RSS where permitted) | `NewsEvent{symbols, category, sentiment, relevance, importance, published_at, ingested_at}` | Point-in-time: an event is usable only at `max(published_at, ingested_at)`; no fabricated history |
| E4 Strategy | Candles | `Signal{strategy, symbol, side, strength, stop, target, ts}` + backtest reports | Signals computed on closed bars only; costs and slippage in every backtest |
| E5 Risk | `OrderIntent`, portfolio state, market freshness | `RiskVerdict{approved, qty, stop, take_profit, reasons[]}` | Independent of E6; blocks on stale data, broker down, limit breach, kill switch; every verdict logged |
| E6 Decision | Prediction, NewsEvents, Signals, regime, portfolio | `Decision{BUY/SELL/HOLD/NO_TRADE, confidence, contributions{}, reasons[], model_version, ts}` | NO_TRADE is the default when inputs are missing, stale or conflicting; every decision audited |
| Execution | Approved `OrderIntent` | Orders, fills, positions, P&L | Paper broker is the only enabled broker; simulated orders are labelled `SIMULATED` everywhere; Upstox order adapter gated by `LIVE_TRADING_ENABLED=false` + explicit authorization |

## 4. Data provider facts (from current Upstox V3 docs, read 2026-11-13)

Historical candles — `GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`
- Auth: `Authorization: Bearer <access_token>` (OAuth2 authorization-code flow; tokens expire daily).
- Units: `minutes` 1–300, `hours` 1–5, `days|weeks|months` 1.
- History: minutes/hours from **Jan 2022**; days from Jan 2000.
- Max range per request: **1 month** for 1–15 min; 1 quarter for >15 min and hours; 1 decade for days.
- Candle = `[ts_iso_ist, open, high, low, close, volume, oi]`.
- Rate limits are on a separate page — the downloader will read and respect them and back off on HTTP 429.

Consequences for the plan:
- Daily: 3–5 years is easily available (one request per symbol).
- Intraday: 1-minute data back to Jan 2022, fetched in **monthly batches** (~60 requests/symbol); 5-minute bars are aggregated locally from 1-minute bars, with a cross-check against Upstox's own 5-minute candles.

Live feed (Market Data Feed V3)
- Authorize via REST → 302 to a `wss://` URL; subscription requests are sent as **binary** JSON
  `{"guid","method":"sub|change_mode|unsub","data":{"mode","instrumentKeys"}}`.
- Modes `ltpc`, `option_greeks`, `full` (5-level depth), `full_d30`. Limits: 2 connections; Full 2,000 keys (individual).
- Messages are Protobuf (`MarketDataFeed.proto` from `assets.upstox.com`); first message `market_info`, then `live_feed` snapshots/updates.
- Server sends WS ping when idle → we track last-message time for stale-feed detection.

## 4a. Verified provider behaviour (measured against live Upstox responses, 2026-11-13)

| Observation | Evidence | How the platform handles it |
|---|---|---|
| V3 historical candles answer **without an access token** | HTTP 200 for daily and 1-minute requests with no `Authorization` header | Downloader works without OAuth; token is attached automatically once connected. OAuth still required for the live feed (Phase 5) and orders. |
| Range limit enforced | 1-minute request spanning 2.5 months → HTTP 400 `UDAPI1148 Invalid date range` | `plan_chunks()` uses calendar months for ≤15-min, quarters for >15-min/hours, ≤10 years for daily (2016-01-01→2025-12-31 accepted). |
| Prices are **corporate-action adjusted retroactively** | RELIANCE pre-bonus (Oct 2024) prices appear as ~₹1,340, not ~₹2,700, in both daily and 1-minute data | Incremental runs re-fetch a 7-day overlap; any price disagreement ⇒ full re-download of that series (`drift_detected`). |
| Older daily candles for some symbols are stamped 09:15 instead of 00:00 | 718 HDFCBANK / INFY daily candles 2016-01 → 2018-11 | `normalize_daily()` floors to the session date; count reported per download. |
| First 1-minute bar can have `open` outside the bar's high/low | HDFCBANK 2024-06-25 09:15: open 835.6, low 837.4 (identical in raw API response) | Kept as delivered; reported as `open_outside_range_at_session_open` warning (pre-open auction price). Same condition elsewhere = error. |
| **Closing-auction pattern from 2026-08-03** | Every session since: 15:15–15:28 bars flat with zero volume; 15:29 bar carries the closing print and volume (e.g. RELIANCE 1309.0 → 1319.0, 400k shares) | Reported as `closing_auction_pattern` in quality reports. Feature/label pipelines must treat 15:15–15:28 as non-trading placeholders and 15:29 as an auction print (Phase 3). |
| Special sessions exist | Sunday 2026-11-08 and 2025-10-21 (Diwali Muhurat), Saturday 2024-03-02 / 2024-05-18 (~105 bars) | Classified as `short_sessions` / `special_session_days`, not as missing data. |
| Some special sessions missing for some symbols | HDFCBANK/INFY lack Muhurat days 2016-10-30, 2017-10-19, 2018-11-07 that NIFTY 50 index has | `missing_trading_days` warning; never back-filled. |
| Missing 1-minute bars are rare | 0.006–0.016% of expected bars on normal sessions | `incomplete_days` warning with worst days listed; never filled. |
| Local 5-minute aggregation is exact | 9/9 symbol-days: identical OHLCV to Upstox's own 5-minute candles | 5-minute bars are built from 1-minute (`n_bars` column marks partial buckets). |

## 5. Storage

- **PostgreSQL** (Alembic-managed): instruments, candle_files (metadata + checksums), datasets, experiments, models, predictions,
  news, sentiment, strategies, signals, backtests, risk_assessments, decisions, orders, trades, positions, portfolios, audit_events.
- **Parquet** lake partitioned `data/candles/{timeframe}/{instrument_key with | → __}/{year}.parquet` (zstd), each file catalogued in `candle_files` with row count, first/last timestamp and SHA-256; feature datasets `data/datasets/{name}/{version}/`
  with a content hash recorded in Postgres (dataset version = hash of source files + feature config).
- **Redis**: latest tick per instrument, feed heartbeat, pub/sub fan-out to WebSocket clients, API rate limiting. Justified only by the live path; the rest works without it.

## 6. ML validation design

- Labels: forward return over horizon *h* (6 × 5-min bars intraday; 5 sessions swing) compared to ±k·σ (rolling volatility) plus round-trip cost → UP / NEUTRAL / DOWN.
- Splits: expanding-window walk-forward; **purge** training rows whose label window overlaps the test fold; **embargo** of ≥ *h* bars after each test fold. Never shuffled.
- Leakage tests: (1) shift-invariance — features at *t* unchanged when data after *t* is deleted; (2) permuted-label sanity check must collapse to chance; (3) timestamp audit that every feature input ≤ *t*.
- Candidates: LogisticRegression, RandomForest, XGBoost, LightGBM, LSTM, GRU. Same folds, same metrics, compared against majority-class and "always NEUTRAL" baselines and buy-and-hold.
- Calibration: isotonic/Platt on a held-out calibration slice; Brier score and reliability curves reported.
- Registry: every run records dataset version, feature config, model config, train/val/test periods, metrics, artifact hash.

## 7. Costs model (to verify in Phase 7 against current schedules)

Brokerage, STT, exchange transaction charges, SEBI fee, stamp duty, GST — implemented as a dated, configurable schedule
(intraday vs delivery) so backtests use the schedule valid on the trade date. Slippage: configurable bps + fraction of bar range.

## 8. Security and live-trading guardrails

- Secrets only via environment variables / `.env` (gitignored); `.env.example` committed. Tokens never logged (log redaction filter).
- API auth: JWT for the terminal user, role `viewer` / `trader` / `admin`; kill switch and settings require `admin`.
- `LIVE_TRADING_ENABLED=false` by default; live adapter additionally requires a signed authorization record and SEBI/NSE retail-algo checklist completion (researched in Phase 14).

## 9. Local environment decisions

- Python **3.12** (best wheel coverage for torch / xgboost / lightgbm / transformers); 3.14 is the system default and is not used for the backend.
- PostgreSQL 18 and Redis 8 run as **project-owned Docker containers** on host ports **5433** and **6380**
  (the machine's own Postgres on 5432 needs a password the build does not have, and is left untouched).
- Tests use a separate `astraquant_test` database (dropped/recreated per run) and Redis db 15.
- `docker compose --profile app up` runs the full stack; frontend nginx proxies `/api` (incl. WebSocket) to the backend.


## 10. Implemented engine map (2026-11-13)

| Engine | Package | Key entry points |
|---|---|---|
| E1 Data | `app/engines/data` | `cli instruments|download|quality|crosscheck5m`; `CandleLake.read(adjusted=True)`; `/api/v1/data/*`, `/api/v1/auth/upstox/*` |
| E2 ML | `app/engines/ml` | `swing.build_swing_dataset`, `intraday.build_intraday_dataset`, `trainer.run` (walk-forward + purge + holdout + registry), `inference.predict_latest`; `cli train --pipeline swing|intraday` |
| E3 News | `app/engines/news` | `sources.fetch` (NSE/RBI/SEBI RSS), `service.ingest`, `service.signal_for` (point-in-time); FinBERT via safetensors; `/api/v1/news/*` |
| E4 Strategy | `app/engines/strategy` | 10 strategies, `backtest.backtest_symbol`, `charges.ChargeSchedule`, `runner` → `reports/strategies` |
| E5 Risk | `app/engines/risk` | `RiskEngine.evaluate` (all checks recorded, fail-closed), VaR/CVaR/stress; `/api/v1/risk/*` |
| E6 Decision | `app/engines/decision` | `DecisionEngine.decide` → BUY/SELL/HOLD/NO_TRADE + explanation; `service.run_swing`, `service.run_intraday_replay`; `/api/v1/decisions/*` |

### Data corrections are data, not code
`app/engines/data/reference/price_discontinuities.csv` (reviewed unadjusted corporate actions / index rebases, with evidence)
and `data_quarantine.csv` (unrepairable periods) are applied on read for analytics; raw Parquet is never modified.
Validation always runs on raw data (`adjusted=False`) so provider issues stay visible.

### Model promotion gate (trainer.promotion_decision)
Out-of-sample only: walk-forward AND holdout log loss below the class-prior baseline; walk-forward direction AUC ≥ 0.51;
walk-forward mean daily IC > 0 with t ≥ 2; holdout direction AUC > 0.5; walk-forward strategy Sharpe after costs > 0.
Selection between candidates uses walk-forward results only; the holdout is evaluated once afterwards.
If no candidate passes, nothing is promoted and the decision engine returns no decisions.

### Native library load order (macOS)
`app/engines/ml/__init__.py` imports xgboost → torch → lightgbm. Other orders segfault (exit 139) because each ships its
own OpenMP runtime. The ruff import sorter is disabled for that file; a subprocess regression test trains all three.
