# AstraQuant X-2026 — Build Status

Last updated: 2026-11-13 · Owner priority (13 Nov): **ML model first, then risk, news, strategies/decision; paper trading postponed; prove it works with tests.**

## Master checklist

| Phase | Name | Status | Report |
|---|---|---|---|
| 0 | Repository audit | **PASSED** | [PHASE_00](PHASE_REPORTS/PHASE_00_REPORT.md) |
| 1 | Foundation | **PASSED** | [PHASE_01](PHASE_REPORTS/PHASE_01_REPORT.md) |
| 2 | Historical data | **PASSED WITH LIMITATIONS** (OAuth live login BLOCKED: no Upstox keys; historical data works without them) | [PHASE_02](PHASE_REPORTS/PHASE_02_REPORT.md) |
| 3 | Feature engineering | **PASSED** | [PHASE_03](PHASE_REPORTS/PHASE_03_REPORT.md) |
| 4 | ML/DL training | **PASSED WITH LIMITATIONS** — swing 6-model comparison done (GRU best, not promoted: edge did not persist in holdout); volatility model promoted (holdout R² 0.184 vs 0.122 HAR); intraday comparison deferred | [PHASE_04](PHASE_REPORTS/PHASE_04_REPORT.md) |
| 5 | Live market data | Not started — BLOCKED on Upstox credentials | |
| 6 | News engine | **PASSED** (no free historical news → market-only models) | [PHASE_06](PHASE_REPORTS/PHASE_06_REPORT.md) |
| 7 | Strategy engine | **PASSED** | [PHASE_07](PHASE_REPORTS/PHASE_07_REPORT.md) |
| 8 | Risk engine | **PASSED** | [PHASE_08](PHASE_REPORTS/PHASE_08_REPORT.md) |
| 9 | Decision engine | **PASSED** (sized against a simulated book; never places orders) | [PHASE_09](PHASE_REPORTS/PHASE_09_REPORT.md) |
| 10 | Paper trading | Postponed by owner | |
| 11 | Frontend integration | **Mostly done** — Overview, Market Data, AI Research (swing/intraday/volatility), News, Strategy Lab, Risk Centre, Settings, System Monitor on real data; Paper/Portfolio postponed | |
| 12 | System integration | Partial — end-to-end automated test (data → model → news → decision → risk → audit) passes | |
| 13 | Security & hardening | Not started — **API authentication missing: keep the backend on localhost** | |
| 14 | Broker execution readiness | Not started (live execution disabled by config validator) | |

## Test status (latest full run)

204 backend tests passing, 19 frontend tests passing, ruff + oxlint clean, `alembic check` clean.

## Outstanding external blockers

| Blocker | Needed for | What is required from the owner |
|---|---|---|
| Upstox developer app | OAuth live verification, Phase 5 live feed, live intraday decisions | Put `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI` in the root `.env` (never in chat/git) and complete the browser login. |
| Licensed historical news | News-assisted backtests | NSE's historical corporate-announcement data is a paid product; without it, news is used live only. |

## How to run

```bash
make services                                                    # Postgres :5433 + Redis :6380
cd backend && .venv/bin/python -m app.engines.data.cli instruments # instrument master + 3 universes
.venv/bin/python -m app.engines.data.cli download --all --indices --timeframes 1day,1minute
.venv/bin/python -m app.engines.ml.cli train --pipeline swing      # also: --pipeline intraday
.venv/bin/python -m app.engines.strategy.runner                    # strategy backtests -> reports/strategies
make backend                                                      # API + /api/docs on :8000
make test
```

## Exact next task

Collect final Phase 4 results (reports/ml), write PHASE_04_REPORT with the honest comparison against the rule-based strategies, run a real end-to-end decision pass (swing on the latest session; intraday replay), then commit.
