# AstraQuant X-2026 — Build Status

Last updated: 2026-11-13 · Current phase: **Phase 2 — Historical data (next)**

## Master checklist

| Phase | Name | Status | Report |
|---|---|---|---|
| 0 | Repository audit | **PASSED** | [PHASE_00](PHASE_REPORTS/PHASE_00_REPORT.md) |
| 1 | Foundation | **PASSED** | [PHASE_01](PHASE_REPORTS/PHASE_01_REPORT.md) |
| 2 | Historical data | Not started (live verification will be BLOCKED: no Upstox credentials yet) | |
| 3 | Feature engineering | Not started | |
| 4 | ML/DL training | Not started (depends on genuine data from Phase 2) | |
| 5 | Live market data | Not started (live verification will be BLOCKED: no Upstox credentials yet) | |
| 6 | News engine | Not started | |
| 7 | Strategy engine | Not started | |
| 8 | Risk engine | Not started | |
| 9 | Decision engine | Not started | |
| 10 | Paper trading | Not started | |
| 11 | Frontend integration | Not started | |
| 12 | System integration | Not started | |
| 13 | Security & hardening | Not started | |
| 14 | Broker execution readiness | Not started (live execution stays disabled) | |

## Outstanding external blockers

| Blocker | Needed for | What is required from the owner |
|---|---|---|
| Upstox developer app | Phase 2 live verification, Phase 5, Phase 10 with real data | Create an app at Upstox Developer Console; put `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI` in the root `.env` (never in chat or git); complete the browser OAuth login when prompted. |

**Important for Phase 4:** models must be trained on genuine data. Without Upstox credentials, Phases 3–4 can be built and tested on deterministic fixtures, but no model metrics will be reported as real results until genuine candles exist.

## How to run

```bash
make services      # Postgres :5433 + Redis :6380 in Docker
make backend       # API on :8000 (applies migrations)
make frontend      # terminal UI on :5173
make test          # backend 17 + frontend 8 tests
make up            # or: whole stack in Docker
```

## Exact next task

Phase 2: read the Upstox rate-limit, OAuth (authorization + token) and instrument-master docs; implement `engines/data/upstox/` (OAuth flow with token stored server-side, instrument master download + NSE symbol mapping for the configured NIFTY 50 list), historical downloader (monthly batches for 1-min, decade batches for daily, rate-limit + retry + checkpoint), validation (OHLC consistency, duplicates, gaps vs NSE session calendar), Parquet storage + Postgres metadata. Test with recorded-shape fixtures; mark live verification BLOCKED until credentials exist.
