# Phase 2 — Historical Data

1. **Objective:** genuine NSE historical data for the NIFTY 50 universe (plus indices and context), validated, versioned and stored.

2. **Features implemented**
   - Upstox V3 historical client (rate limiter at 80% of the documented 50/s · 500/min · 2000/30 min; retries with jittered backoff and Retry-After; typed errors; no retry on 4xx/auth).
   - OAuth 2 authorization-code flow (CSRF state in Redis, single use), token exchange per docs, Fernet-encrypted token store, expiry at the next 03:30 IST.
   - Instrument master ingestion (NSE_EQ + NSE_INDEX, 2,890 rows) and universe mapping by ISIN for **NIFTY 50, NIFTY Next 50, NIFTY Midcap 100** (200 stocks) — every symbol verified against the master; 18 sector indices mapped and validated.
   - Request planner (calendar-month chunks for 1-minute, quarters for >15-min, ≤10 years for daily), checkpointed downloads (`download_chunks`), failed-chunk retry on resume, incremental updates with a 7-day overlap and **adjustment-drift detection** (full re-download when stored prices disagree).
   - Parquet lake (zstd, yearly files, atomic writes) catalogued in Postgres with SHA-256; 5-minute bars aggregated from 1-minute with `n_bars`.
   - Data-quality validator and reports (Postgres `data_quality_reports` + JSON files); daily timestamp normalisation.
   - **Discontinuity registry** (`reference/price_discontinuities.csv`) and **quarantine** (`reference/data_quarantine.csv`): reviewed corrections applied on read for analytics; raw files never modified.
   - Global context (S&P 500, Nasdaq, US VIX, USD/INR, Brent, US 10Y, Nikkei, Hang Seng) via yfinance, used only with a strict one-session lag.
   - Data API: universe, instrument search, candles, coverage, quality; Upstox auth status/login/callback.

3–5. **Files / dependencies:** see git history; added pandas 3.1.1, pyarrow 26.0.1, cryptography 50.0.2, yfinance 1.8.0.

6. **Commands executed (key)**
   - `cli instruments` → 2,890 instruments; NIFTY50 50, NIFTYNEXT50 50, NIFTYMIDCAP100 100 members mapped.
   - `cli download --all --indices --timeframes 1day,1minute` (NIFTY 50 + 16 indices) and `--universes NIFTYNEXT50,NIFTYMIDCAP100 --timeframes 1day` (separate low rate limit).
   - `cli quality --all --indices --timeframes 1day,1minute,5minute`; `cli crosscheck5m` on 9 symbol-days.

7–9. **Tests:** data-engine unit + integration + API tests — **48 + 16 + 8 = 72 passed** (planner, limiter, client retry/auth/validation, parsing, 20+ validation rules, lake round-trip/merge/atomicity, aggregation, discontinuity adjustment and quarantine, OAuth state/token store/expiry, checkpoint resume, incremental overlap, drift full-refresh, API endpoints). Mutation checks: disabling failed-chunk retry or drift detection makes the corresponding test fail.

10–11. **Bugs found → fixed**
    - pandas-settings CSV parsing (Phase 1), tz-aware timestamp crash in incremental reads, Docker data path → fixed earlier.
    - 718 + 78,328 daily candles stamped 09:15 instead of 00:00 → normalised.
    - First-bar open outside high/low (pre-open auction print) → warning, not error.
    - **Closing-auction regime from 2026-08-03** (15:15–15:28 flat zero-volume placeholders) → detected and reported; pipelines use 09:15–15:10 only.
    - Index pre-open (09:00–09:08) and post-close (15:30+) disseminated values flagged as errors → reclassified as info for indices only (still errors for stocks / other times).
    - **Unadjusted corporate actions in Upstox data:** Tata Motors demerger 2025-10-14 (−40% fake move), Nifty Commodities level discontinuity 2018-04-16 (−23%), and in training-only stocks CG Power 2016, Max Financial 2016, Tata Communications 2019, Vedanta 2026 → registry with evidence; Mazagon Dock (zero close before listing), 360 ONE (listing jump), NMDC (inconsistent pre-Dec-2022 series) → quarantined.

12. **Performance:** daily download 8 requests / 2.3 s for 4 instruments; 1-minute ≈ 59 requests and ~11 s per stock (~40k rows/s); full NIFTY 50 + indices run ≈ 4,000 requests, paced by the 30-minute cap; candle API p50 12–15 ms on real data; quality run over 35.6 M rows in a few minutes.

13. **Actual data verification**
    - Stored: **29.5 M 1-minute, 5.9 M 5-minute, 0.52 M daily candles across 218 instruments** (daily 2016→2026-11-12; 1-minute 2022-01→2026-11-12).
    - **Quality: 200/200 reports pass** (NIFTY 50 stocks + indices × 3 timeframes). Missing 1-minute bars on regular sessions: median 0.0055%, max 0.0157% per stock.
    - Independent cross-checks: local 5-min = Upstox 5-min exactly (9/9 symbol-days); Upstox vs the team's Yahoo archive: NIFTY 50 close median relative difference 2e-8 over 1,234 days, India VIX max 0.1%.

14. **Remaining limitations**
    - **Upstox OAuth live login BLOCKED** (no API key/secret yet). Historical data did not need it (verified: V3 historical works without a token).
    - Universe = current constituents → survivorship bias; historical index membership not sourced.
    - Discontinuity factors are open/prev-close approximations for entries marked "inferred"; replace with NSE's official adjustment factors when available.
15. **Security:** tokens encrypted at rest, never logged; OAuth state single-use; no credentials in repo.
16. **Acceptance gate:** **PASS WITH LIMITATIONS** — genuine data for the full universe retrieved, validated and stored; OAuth live verification BLOCKED on credentials (not needed for historical data).
17. **Next phase:** Phase 3 — Feature engineering.
