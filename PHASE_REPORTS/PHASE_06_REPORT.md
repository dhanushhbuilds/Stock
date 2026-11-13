# Phase 6 — News Intelligence Engine

1. **Objective:** ingest legitimate news, map it to stocks, classify events, score sentiment with FinBERT, and expose point-in-time signals.

2. **Features implemented** (`app/engines/news/`)
   - **Sources (official public RSS, verified live 2026-11-13):** NSE corporate announcements (`nsearchives.nseindia.com/content/RSS/Online_announcements.xml`, ~640 filings per fetch), RBI press releases, SEBI updates. Bulk historical announcements are a **paid NSE product**, so no historical news is used for model training and none is fabricated.
   - Parsing of all three formats (incl. BOM, HTML in descriptions, three date formats; NSE symbol extracted from filing URLs).
   - Timestamp validation: `missing` → usable from ingestion time; > 5 min in the future → `future_rejected` (stored, never scored or used); `usable_from = max(published, ingested)` gates every consumer.
   - Dedup: exact content hash (unique key) + near-duplicate (token Jaccard ≥ 0.9, same source/symbols) linked via `duplicate_of` and excluded from scoring.
   - Entity mapping to Upstox-master instruments only: NSE filings by explicit issuer (URL symbol, then normalised legal name); RBI/SEBI by multi-word mentions with regulator names blanked; ambiguous aliases (Reliance, HDFC, Tata, …) deliberately excluded.
   - Event classification (20 types: earnings, profit warning, merger, acquisition, buyback, dividend, fund raising, management change, legal, regulatory, credit rating, contract, product launch, macro, geopolitical, corporate action, board meeting, press release, market activity, investor meet, routine disclosure) with importance weights.
   - **FinBERT** (`ProsusAI/finbert`, loaded **only from safetensors**, no pickle; on Apple MPS): probabilities + score = P(pos) − P(neg).
   - Signal: weighted by importance × relevance × freshness (24 h half-life, 72 h lookback); returns sentiment, impact, confidence (0 with no evidence) and top items.
   - API: `POST /news/ingest/{source}`, `GET /news`, `GET /news/signal/{instrument}?as_of=`.

3. **Files created:** `app/engines/news/{__init__,sources,nlp,service}.py`, `app/models/news.py`, `app/api/news.py`, migration `6e44083a6d8b`, `tests/test_news.py`.
4. **Files modified:** `app/main.py`, `app/models/__init__.py`, `tests/conftest.py`, `pyproject.toml` (slow marker).
5. **Dependencies added:** transformers 5.22.2 (+ tokenizers, safetensors, huggingface_hub).
6. **Commands executed:** live fetch + ingest of all three sources into the dev DB; FinBERT smoke checks.
7–9. **Tests:** `tests/test_news.py` — **30 passed, 0 failed**, including the real FinBERT model (schema + direction) and regressions for every live-found bug.

10. **Bugs discovered on live data**
    1. Every RBI release mapped to **Bank of India** ("Reserve Bank of India" ⊃ "Bank of India"; the normaliser also stripped "India").
    2. **Reliance Mutual Fund** NAV filings tagged as RELIANCE (fuzzy fallback for unknown filers).
    3. Near-duplicates were detected but still scored (link set before the original had a DB id).
    4. All 30 SEBI timestamps unparsed ("12 Nov, 2026 +0530").
    5. 490/637 NSE items classified "other".
11. **Bugs fixed:** only legal suffixes stripped + regulator names blanked; company-scope items map by explicit issuer only; flush before linking duplicates; SEBI date format; classifier extended (NAV, board meetings, corporate actions, press releases, KMP changes). Final live run: NSE 650 received / 645 new / 30 near-dups / 194 mapped / 615 scored; RBI 10 (0 mis-mapped); SEBI 30 (all timestamps valid).
12. **Performance:** fetch ~0.2 s per feed; FinBERT load 23 s (first, from cache afterwards); ingest + FinBERT for ~640 items 11.5 s on MPS (~55 items/s).
13. **Actual data verification:** live official feeds ingested and inspected row by row (samples in this report's bug list).
14. **Remaining limitations:** no legitimate free historical news → news-based backtests impossible; market-only models are evaluated separately (Phase 4). FinBERT licence is CC-BY-NC-SA-4.0 (non-commercial) — fine for the competition, must be replaced for commercial use. Classification is rule-based (transparent, but not learned). Most NSE filings are routine (NAV, compliance) and rightly get low importance.
15. **Security:** only allow-listed official URLs are fetched; model weights loaded from safetensors only (no arbitrary code execution); sources identified with an honest User-Agent.
16. **Acceptance gate:** **PASS** — three legitimate sources functioning and processed correctly; external limitation (no free historical news) documented.
17. **Next phase:** Phase 7 — Strategy engine.
