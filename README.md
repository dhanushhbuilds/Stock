# AstraQuant X — Institutional Quantitative Trading & AI Research Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue.svg)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-6.0-646cff.svg)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-8.0-dc382d.svg)](https://redis.io/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.4-38bdf8.svg)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Tests-237%20Passed-success.svg)](#testing--verification)

> **AstraQuant X** is an institutional-grade quantitative trading, machine learning research, and risk management platform engineered specifically for the Indian equity market (NSE NIFTY 50 & liquid equities). Built as a high-performance modular monolith with an Apple-inspired dark aesthetic, the platform combines audited historical data pipelines, 77 quantitative features, purged walk-forward machine learning models, regulatory NLP intelligence, 10 systematic trading strategies, and an independent, fail-closed risk management engine.

---

## Table of Contents

1. [Executive Overview & Philosophy](#executive-overview--philosophy)
2. [System Architecture](#system-architecture)
3. [Core Engines: A-to-Z Deep Dive](#core-engines-a-to-z-deep-dive)
   - [Engine 1: Historical & Market Data Engine](#engine-1-historical--market-data-engine)
   - [Engine 2: Feature Engineering & Machine Learning Engine](#engine-2-feature-engineering--machine-learning-engine)
   - [Engine 3: Regulatory News Intelligence & FinBERT Engine](#engine-3-regulatory-news-intelligence--finbert-engine)
   - [Engine 4: Quantitative Strategy & Backtesting Engine](#engine-4-quantitative-strategy--backtesting-engine)
   - [Engine 5: Independent Risk Management Engine](#engine-5-independent-risk-management-engine)
   - [Engine 6: Decision Aggregation & Execution Intent Engine](#engine-6-decision-aggregation--execution-intent-engine)
4. [Frontend Terminal: Page-by-Page Feature Tour](#frontend-terminal-page-by-page-feature-tour)
   - [1. Overview Dashboard (`/`)](#1-overview-dashboard-)
   - [2. Signal Lab (`/signal-lab`)](#2-signal-lab-signal-lab)
   - [3. Market Data Browser (`/market`)](#3-market-data-browser-market)
   - [4. AI Research Lab (`/research`)](#4-ai-research-lab-research)
   - [5. News Intelligence (`/news`)](#5-news-intelligence-news)
   - [6. Strategy Lab (`/strategy`)](#6-strategy-lab-strategy)
   - [7. Risk Centre (`/risk`)](#7-risk-centre-risk)
   - [8. System Monitor (`/system`)](#8-system-monitor-system)
   - [9. Settings & Risk Limits (`/settings`)](#9-settings--risk-limits-settings)
5. [Indian Statutory Transaction Cost Schedule](#indian-statutory-transaction-cost-schedule)
6. [Technology Stack](#technology-stack)
7. [Repository Structure](#repository-structure)
8. [Installation & Getting Started](#installation--getting-started)
9. [Testing & Verification](#testing--verification)
10. [Safety, Guardrails & Compliance](#safety-guardrails--compliance)

---

## Executive Overview & Philosophy

AstraQuant X is designed around several non-negotiable principles of quantitative finance and software reliability:

1. **Zero Hallucination / Strictly Point-in-Time Causality**: No historical data point is ever backfilled, interpolated, or peeked from the future. News events are strictly usable only after `max(published_at, ingested_at)`.
2. **The Golden Separation Rule**: The **Decision Engine** produces *Order Intents*. The **Risk Engine** acts as an autonomous veto and sizing gate. An order or execution intent can *only* become an actionable trade if approved and sized by the Risk Engine. The Decision Engine has zero handle on broker adapters.
3. **Fail-Closed by Design**: If any market feed is stale, volatility spikes past thresholds, data is missing, or correlation limits breach, the platform halts new trades (`NO_TRADE`).
4. **Honest Out-of-Sample Machine Learning**: Models are evaluated using Marcos López de Prado's **Purged Walk-Forward Cross-Validation with Embargo** windows. Models must beat baseline zero-intelligence priors and survive statutory transaction costs on a locked holdout test period to achieve promotion.
5. **Real-World Indian Market Mechanics**: Full statutory charges (STT, GST, Exchange charges, Stamp duty, SEBI fees, brokerage, and bid-ask slippage) are calculated on every single simulated backtest trade.

---

## System Architecture

The platform is designed as a **modular monolith** with clean package contracts, backed by PostgreSQL 18 for transactional metadata and audit logs, a local Parquet Lake for high-speed time-series analytics, and Redis for caching and pub/sub.

```
                   ┌──────────────────────── React Terminal (Vite + TypeScript) ────────────────────────┐
                   │ 10 Pages · REST Client via TanStack Query · Lightweight Charts · Recharts Bento UI   │
                   └───────────────▲───────────────────────────────────────────▲────────────────────────┘
                                   │ REST API                                  │ WebSockets (Ticks / Logs)
┌──────────────────────────────────┴───────────── FastAPI Backend ─────────────┴────────────────────────┐
│  app/api/ (Routers: Signal Lab, Decisions, Risk, ML, Data, News, Health, Settings)                    │
│                                                                                                       │
│  ┌──────────────┐     bars     ┌───────────────────┐  predictions  ┌──────────────────────────────┐    │
│  │   E1 DATA    ├─────────────►│       E2 ML       ├──────────────►│         E6 DECISION          │    │
│  └──────┬───────┘              └───────────────────┘               │   (Aggregates ML, Strategy,  │    │
│         │                      ┌───────────────────┐    signals    │    News, & Market Regime)    │    │
│         ├─────────────────────►│    E4 STRATEGY    ├──────────────►│              │               │    │
│         │       bars           └───────────────────┘               └──────────────┼───────────────┘    │
│  ┌──────┴───────┐              scored events                                      │ order intent      │
│  │   E3 NEWS    ├─────────────────────────────────────────────────────────────────┘                   │
│  └──────────────┘                                                                 ▼                   │
│                                                                    ┌──────────────────────────────┐    │
│                                                                    │           E5 RISK            │    │
│                                                                    │ (Autonomous Sizing, Limits,  │    │
│                                                                    │  VaR, Drawdown & Veto Engine)│    │
│                                                                    └──────────────┬───────────────┘    │
│                                                                                   │ approved order    │
│  Core Services: Config (Pydantic), Structured Logging, Clock, Audit Trail         ▼ intent            │
│                                                                           [ Execution Gateway ]       │
└───────────────────────────────────────┬───────────────────┬───────────────────────────────────────────┘
                                        │                   │
                  ┌─────────────────────┴───────┐   ┌───────┴─────────────────────┐
                  │   PostgreSQL 18 Database    │   │     Parquet Data Lake       │
                  │  Instruments, Models, Runs, │   │   data/candles/{tf}/{sym}   │
                  │  Decisions, Risk Assessments│   │   data/datasets/{name}/{v}  │
                  └─────────────────────────────┘   └─────────────────────────────┘
```

---

## Core Engines: A-to-Z Deep Dive

### Engine 1: Historical & Market Data Engine
*Location: `backend/app/engines/data/`*

The Data Engine manages the ingestion, normalization, quality auditing, and local storage of tick, 1-minute, 5-minute, and daily candles.
- **Upstox V3 API Provider**: Fully integrated historical downloader. Connects to Upstox historical endpoints supporting daily data (back to 2000) and 1-minute data (back to Jan 2022).
- **Intelligent Batch Planning (`plan_chunks`)**: Overcomes Upstox date range limits (1-month limits for intraday data) by chunking requests into calendar months with backoff and jitter for rate-limiting (HTTP 429).
- **Local 5-Minute Bar Aggregation**: Aggregates 1-minute ticks into exact 5-minute bars locally, maintaining exact synchronization verified against Upstox's native 5-minute feeds.
- **Data Quality & Integrity Auditing**:
  - Validates relational OHLC constraints (`high >= max(open, close)`, `low <= min(open, close)`, `volume >= 0`).
  - Detects duplicate timestamps, chronological misorderings, and weekend/holiday anomalies.
  - Corrects and flags special trading sessions (e.g., Diwali Muhurat trading).
  - Handles the NSE closing auction pattern introduced since August 2026 (15:15–15:28 flat zero-volume placeholders followed by the 15:29 cumulative auction print).
- **Corporate Action Adjustments**: Detects bonus splits and stock dividends. Uses reference table adjustments (`price_discontinuities.csv`) while leaving raw Parquet files intact for auditability.
- **Partitioned Parquet Storage**: Saves time-series data to disk using Zstandard compression: `data/candles/{timeframe}/{instrument_key}/{year}.parquet`.

---

### Engine 2: Feature Engineering & Machine Learning Engine
*Location: `backend/app/engines/ml/`*

A comprehensive quantitative research and machine learning framework designed to eliminate lookahead bias and evaluate predictive edge.
- **77 Quantitative Features**:
  1. *Momentum & Returns*: 1-day, 5-day, 20-day, and 60-day logarithmic returns, volatility-adjusted momentum.
  2. *Trend Indicators*: Exponential Moving Averages (EMA 10, 20, 50, 200), SMA ratios, moving average convergence.
  3. *Oscillators*: Relative Strength Index (RSI 14), Stochastic oscillator, MACD signal and histogram, Rate of Change (ROC).
  4. *Volatility & Range*: Average True Range (ATR 14), Bollinger Bands (bandwidth and %B), Parkinson historical volatility, Garman-Klass volatility, rolling standard deviations.
  5. *Market Regime & Macro Context*: Beta to NIFTY 50 index, relative strength vs benchmark, India VIX level and 1-year percentile.
  6. *Cross-Sectional Rank Features*: Daily cross-sectional percentiles across the NIFTY 50 universe (volume rank, momentum rank).
- **Triple-Barrier & Excess Return Labeling**:
  - Swing pipeline: 5-session forward return vs cross-sectional universe median. Labeled into ternary classes: `UP` ($> +k\sigma$), `NEUTRAL`, and `DOWN` ($< -k\sigma$).
  - Intraday pipeline: 30-minute forward return (6 bars $\times$ 5 minutes) vs rolling volatility bands after transaction costs.
- **Walk-Forward Cross-Validation with Purge & Embargo**:
  - Expanding-window walk-forward splits.
  - **Purging**: Removes training samples whose forward label evaluation overlaps test fold horizons.
  - **Embargo**: Adds a cooldown buffer immediately following test folds to eliminate serial correlation leakage.
- **Model Architectures Compared**:
  - Logistic Regression (L2 regularization baseline)
  - Random Forest Classifier
  - XGBoost (Extreme Gradient Boosting)
  - LightGBM (Gradient Boosting Decision Tree)
  - LSTM (Long Short-Term Memory Neural Network)
  - GRU (Gated Recurrent Unit Neural Network)
- **Model Promotion Gate**:
  - Strict out-of-sample criteria: Holdout Log Loss < No-Skill baseline, Direction AUC $\ge 0.51$, Information Coefficient (IC) with $t$-stat $\ge 2.0$, and positive post-cost Sharpe ratio.
- **Promoted AI Volatility Forecasting Model**:
  - GBDT volatility forecaster achieving a **Holdout $R^2 = 0.184$** on unseen data, beating both standard HAR (Heterogeneous Autoregressive) and EWMA baselines.

---

### Engine 3: Regulatory News Intelligence & FinBERT Engine
*Location: `backend/app/engines/news/`*

Real-time Natural Language Processing (NLP) pipeline parsing regulatory filings and financial announcements.
- **Legitimate Official Sources**: Consumes RSS and structured announcement feeds directly from the **National Stock Exchange (NSE)**, **Reserve Bank of India (RBI)**, and **SEBI**.
- **Entity & Ticker Extraction**: Resolves corporate filings to NSE stock symbols and instrument keys using fuzzy entity matching and regex ticker extraction.
- **Event Categorization**: Automatically categorizes filings into:
  - *Earnings & Financial Results*
  - *Dividends & Corporate Actions*
  - *Mergers, Acquisitions & Restructuring*
  - *Executive & Board Management Changes*
  - *Regulatory Penalties & Investigations*
  - *Routine Disclosures*
- **FinBERT Sentiment Analysis**:
  - Runs a local HuggingFace `ProsusAI/finbert` model via native safetensors weights.
  - Yields high-precision sentiment probability scores: `positive`, `negative`, and `neutral`.
- **Point-in-Time Constraint**: Every news item is stamped with `usable_at = max(published_at, ingested_at)`, ensuring backtests cannot use announcements prior to ingestion.

---

### Engine 4: Quantitative Strategy & Backtesting Engine
*Location: `backend/app/engines/strategy/`*

Hosts 10 systematic, rule-based quantitative trading strategies evaluated across 2017–2026 data.
1. **Trend Following**: Dual moving average crossover (EMA 50 / 200) with ATR volatility stop.
2. **Mean Reversion**: Bollinger Band ($2\sigma$) bounce coupled with RSI divergence.
3. **Volatility Breakout**: Donchian Channel 20-day high/low breakout with volume surge confirmation.
4. **Momentum Cross-Sectional**: Top decile 12-month minus 1-month momentum ranking.
5. **Statistical Arbitrage**: Cointegration-tested pair spread mean reversion.
6. **Volatility Squeeze**: Bollinger Band contraction inside Keltner Channels followed by directional expansion.
7. **Opening Range Breakout (ORB)**: First 15-minute high/low breakout with VWAP filter.
8. **VWAP Mean Reversion**: Intraday stretch from Volume Weighted Average Price with reversion targets.
9. **Macro Regime Conditional**: Shifts allocation based on NIFTY 50 200 EMA and India VIX regime.
10. **Multi-Factor Quantitative Blend**: Composite score combining value, quality, momentum, and low-volatility factors.

---

### Engine 5: Independent Risk Management Engine
*Location: `backend/app/engines/risk/`*

The autonomous gatekeeper of the platform. Evaluates every Order Intent against real-time portfolio state and market limits.
- **Position Sizing Algorithm**:
  - Standard trade allocation: Risks exactly **2.0%** of total portfolio equity.
  - Dynamic Stop-Loss: Placed at $2 \times \max(\text{ATR}_{14}, \text{forecast volatility})$.
  - Profit Target: Fixed at $2R$ (2:1 reward-to-risk ratio).
- **Deterministic Risk Veto Checks**:
  1. *Single Stock Concentration Limit*: Maximum 15% of portfolio equity in any single stock.
  2. *Gross Exposure Limit*: Maximum 100% total invested capital (zero unhedged leverage).
  3. *Sector Exposure Cap*: Maximum 30% concentration in any single industry sector.
  4. *Concurrent Positions Limit*: Caps open simultaneous trades to prevent portfolio over-fragmentation.
  5. *Daily Loss Circuit Breaker*: Halts new buying if daily portfolio equity drops by 3.0%.
  6. *Maximum Portfolio Drawdown*: Triggers de-risking if peak-to-trough drawdown reaches 10.0%.
  7. *Market Data Freshness Gate*: Vetoes orders if candles or tick feeds are older than 15 minutes (intraday) or 24 hours (daily).
  8. *Circuit Limit Proximity Check*: Blocks buying within 1.5% of upper circuit limits.
- **Portfolio Value at Risk (VaR & CVaR)**:
  - 1-Day 95% and 99% Parametric and Historical VaR calculations.
  - Conditional Value at Risk (CVaR / Expected Shortfall) to assess extreme tail risk.
- **Emergency Kill Switch**:
  - Instant administrative kill switch accessible via UI or API.
  - Persists state in Postgres with mandatory reason audit logging.

---

### Engine 6: Decision Aggregation & Execution Intent Engine
*Location: `backend/app/engines/decision/`*

Combines inputs from all specialized engines to produce an actionable market stance.
- **Decision Matrix**:
  - Synthesizes direction probabilities from the ML Engine, signals from Strategy Lab, sentiment from FinBERT, and broad market regime (Bull / Bear / High Volatility / Low Volatility).
  - Outputs one of four deterministic actions: `BUY`, `SELL`, `HOLD`, or `NO_TRADE`.
- **Default to Safety**: If inputs are conflicting, market regime is hostile, or confidence is below threshold ($< 0.55$), the engine defaults to `NO_TRADE`.
- **Audit Logging**: Every single decision is written to PostgreSQL with its full factor decomposition, feature snapshots, model version hash, and plain-language explanation.

---

## Frontend Terminal: Page-by-Page Feature Tour

Built in React 19 and TypeScript with an Apple-inspired dark aesthetic featuring a pure black canvas (`#000`), graphite bento tiles (`#1d1d1f`), translucent glass top navigation, and white highlight cards.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  ASTRAQUANT X      Overview   Signal Lab   Market Data   AI Research   News   Strategy   Risk   System │
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                        │
│   OVERVIEW                                                                                             │
│   Markets, understood.                                                 [ NIFTY 50 : 24,180.80 ▲ 1.4% ] │
│   AI forecasts, tested strategies, and risk limits.                    [ Interactive Candle Chart    ] │
│                                                                                                        │
│   ┌──────────────────────────┐ ┌──────────────────────────┐ ┌────────────────────────────────────────┐ │
│   │ MARKET REGIME: BULL      │ │ AI VOLATILITY MODEL      │ │ DATA LAKE                              │ │
│   │ Trend: Above 200 EMA     │ │ Promoted: R² = 0.184     │ │ 2.4M Candles · 50 Instruments          │ │
│   │ India VIX: 13.4 (32%ile) │ │ Beats HAR & EWMA on hold │ │ 100% Quality Checks Passed             │ │
│   └──────────────────────────┘ └──────────────────────────┘ └────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1. Overview Dashboard (`/`)
- **Hero Section**: Clean typography with CSS chrome art rendering and quick-action links.
- **NIFTY 50 1-Year Interactive Chart**: Real-time candlestick/line chart with 1-year performance delta badge.
- **Market Regime Bento Tile**: Shows current market trend (`BULL` / `BEAR`), NIFTY vs 200-day EMA, India VIX value, and 1-year historical percentile.
- **Promoted AI Volatility Tile**: High-contrast white card highlighting the promoted volatility model's holdout $R^2$ score.
- **Data Lake & Model Registry Status**: Real-time row counts, instrument tracking stats, and model promotion counts.
- **Recent Decisions Feed**: Shows the latest 50 algorithmic decisions with symbol, action badge (`BUY`, `SELL`, `HOLD`, `NO_TRADE`), confidence, and timestamps.
- **One-Click Decision Pass**: Trigger an automated swing decision pass across all tracked instruments directly from the UI.

---

### 2. Signal Lab (`/signal-lab`)
The flagship interactive analytics and dataset diagnostic center:
- **Universal Dataset Dropzone**: Drag and drop **any** daily OHLCV dataset directly into the page (supports CSV, TSV, semicolon, pipe-delimited, Excel `.xlsx`, `.xls`, and multi-encoding formats including UTF-8, UTF-16, and cp1252), or choose any stored stock symbol (e.g., RELIANCE, TCS, INFY).
- **Automated Processing Pipeline**:
  1. *Dataset Validation*: Verifies dates, OHLC bounds, and volume integrity.
  2. *77 Quantitative Features*: Computes complete institutional feature set on the fly.
  3. *AI Model Inference*: Runs the direction model and promoted volatility forecaster.
  4. *Risk Evaluation*: Sizes and validates position against portfolio equity.
- **Big-Typography Verdict Card**: High-contrast white card displaying the clear verdict (`BUY`, `SELL`, `HOLD`, `NO_TRADE`), entry close, position sizing, exact stop-loss level, and $2R$ target price.
- **Probability Distribution Bar**: Visual breakdown of model confidence across `Down`, `Neutral`, and `Up`.
- **Interactive LightWeight Chart**: Candlestick / line chart with trade markers and 200-day moving average.
- **Equity Growth vs Buy & Hold**: Full out-of-sample backtest simulation accounting for statutory transaction fees and slippage.
- **Risk Audit Checklist Table**: Transparent table listing all 8 risk engine rules, required limit values, actual candidate values, and pass/fail indicators.
- **Trade Log & CSV Export**: Detailed ledger of every simulated historical trade and one-click export of complete daily signal datasets.

---

### 3. Market Data Browser (`/market`)
- **NIFTY 50 Universe Navigator**: Sidebar listing all 50 constituent companies with sector categorization.
- **Multi-Timeframe Charts**: Switch between **Daily** and **5-Minute** historical candles.
- **Data Quality Audit Panel**: Inspect raw data health, including total trading days, missing bars, split adjustments, and auction prints.

---

### 4. AI Research Lab (`/research`)
- **Model Comparison Table**: Compares 6 model families (Logistic Regression, Random Forest, XGBoost, LightGBM, LSTM, GRU) across:
  - *Out-of-sample Log Loss vs Zero-Intelligence Baseline*
  - *Directional AUC*
  - *Information Coefficient (Mean IC & $t$-statistic)*
  - *Accuracy & Macro-F1*
  - *Brier Score Calibration*
- **Fold-by-Fold Walk-Forward Performance**: Visual bar chart of information coefficient and log-loss improvement across walk-forward test folds.
- **Volatility Forecasting Deep Dive**: Side-by-side comparison of the AI volatility model vs classic HAR-RV (Heterogeneous Autoregressive Realized Volatility) and GARCH models.

---

### 5. News Intelligence (`/news`)
- **Live Feed Ingest Buttons**: Fetch latest regulatory updates on demand from NSE Announcements, RBI Press Releases, and SEBI Circulars.
- **FinBERT Sentiment Scoring**: Each article displays confidence scores for positive, negative, and neutral sentiment.
- **Interactive Filtering**: Filter news events by stock ticker symbol or event category (earnings, dividend, penalty, etc.).
- **Point-in-Time Causality Note**: Explicit tracking of publication vs ingestion timestamps.

---

### 6. Strategy Lab (`/strategy`)
- **10 Quantitative Strategies**: Comprehensive benchmark table comparing all 10 rule-based strategies.
- **In-Sample vs Out-of-Sample Toggle**: Compare strategy performance before 2020 vs post-2020 unseen market regimes.
- **Key Metrics Table**: Total return, annualized return, Sharpe ratio, Sortino ratio, Maximum Drawdown, Profit Factor, Win Rate, and Fee-to-Gross-Profit drag.
- **Interactive Growth of ₹1 Chart**: Multi-line equity curve comparison against Equal-Weight Buy & Hold and the NIFTY 50 Index.

---

### 7. Risk Centre (`/risk`)
- **Emergency Kill Switch**: Large toggle button to halt all algorithmic trading instantly with mandatory audit justification.
- **Single-Order Risk Simulator**: Interactive testing form to submit hypothetical orders (Symbol, Side, Product, Confidence, Equity) and review the Risk Engine's exact sizing, stop-loss calculations, and veto decisions.
- **Assessment Audit Log**: Live audit table showing the latest 30 risk assessments with approval statuses and veto reasons.

---

### 8. System Monitor (`/system`)
- **Real-Time Health Status**: Live status indicators for PostgreSQL database, Redis connection, Parquet data lake, and ML models.
- **Latency Monitoring**: Millisecond response latencies for critical system dependencies.
- **Live Trading Safety Indicator**: High-visibility indicator confirming `LIVE_TRADING_ENABLED = false` to guarantee safety.

---

### 9. Settings & Risk Limits (`/settings`)
- **Dynamic Parameter Tuning**: Configure risk parameters including capital risk per trade, ATR stop multiples, take-profit ratios, sector caps, and maximum drawdown limits.
- **Server-Side Validation**: All modifications are validated against hard safety ranges (e.g., risk per trade $\le 5\%$) and written to the immutable audit log.

---

## Indian Statutory Transaction Cost Schedule

Every backtest, Signal Lab run, and decision simulation in AstraQuant X computes authentic transaction costs matching the current Indian statutory framework:

| Charge Component | Delivery (Equity Cash) | Intraday (Equity Cash) |
|---|---|---|
| **Brokerage** | ₹20 flat or 0.1% (whichever is lower) | ₹20 flat or 0.03% (whichever is lower) |
| **STT (Securities Transaction Tax)** | 0.1% on Buy + 0.1% on Sell | 0.025% on Sell only |
| **Exchange Transaction Charges** | 0.00297% (NSE) | 0.00297% (NSE) |
| **GST** | 18% on (Brokerage + Exchange charges + SEBI) | 18% on (Brokerage + Exchange charges + SEBI) |
| **SEBI Turnover Charges** | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) |
| **Stamp Duty** | 0.015% on Buy side | 0.003% on Buy side |
| **Execution Slippage** | Configurable (Default: 5 bps + 5% of bar range) | Configurable (Default: 5 bps + 5% of bar range) |

---

## Technology Stack

### Backend
- **Core Runtime**: Python 3.12 (Selected for stable PyTorch, XGBoost, LightGBM, and Transformers support)
- **API Framework**: FastAPI 0.115+ with Pydantic v2 data validation
- **Database & ORM**: PostgreSQL 18 with SQLAlchemy 2.0 (async/sync) and Alembic migrations
- **Time-Series Storage**: Apache Arrow / PyArrow (Zstandard compressed Parquet)
- **Cache & Pub/Sub**: Redis 8.0
- **Machine Learning & NLP**:
  - PyTorch 2.4+ (LSTM & GRU deep learning models)
  - XGBoost & LightGBM (Gradient boosted decision trees)
  - Scikit-Learn (Pipelines, preprocessing, metrics)
  - HuggingFace Transformers (FinBERT sentiment analysis via safetensors)
- **Structured Logging**: Structlog (JSON formatted logs with secret redaction)

### Frontend
- **Framework**: React 19 (TypeScript)
- **Build Tool**: Vite 6.0
- **Styling**: Tailwind CSS 3.4 with custom Apple-style glassmorphism design system
- **UI Components**: Radix UI primitives & Lucide React icons
- **Data Fetching**: TanStack React Query v5
- **Charts & Visualizations**:
  - TradingView Lightweight Charts (Financial candlestick and volume charts)
  - Recharts (Bento statistics and equity growth curves)

---

## Repository Structure

```
astraquant-x/
├── backend/
│   ├── alembic/                # Database migrations
│   ├── app/
│   │   ├── api/                # FastAPI endpoint routers
│   │   │   ├── data.py         # Candles, universe, coverage API
│   │   │   ├── decisions.py    # Algorithmic decisions & regime API
│   │   │   ├── health.py       # Readiness & health probes
│   │   │   ├── ml.py           # Model registry & experiment API
│   │   │   ├── news.py         # News ingestion & sentiment API
│   │   │   ├── risk.py         # Risk state, evaluate, kill-switch API
│   │   │   └── signal_lab.py   # Signal Lab dataset analysis API
│   │   ├── core/               # App configuration, DB session, logging, audit
│   │   ├── engines/            # Core business engines
│   │   │   ├── data/           # E1: Ingestion, Upstox API, validation, Parquet lake
│   │   │   ├── ml/             # E2: 77 features, walk-forward trainer, inference
│   │   │   ├── news/           # E3: RSS fetchers, FinBERT NLP scoring
│   │   │   ├── strategy/       # E4: 10 systematic strategies & backtester
│   │   │   ├── risk/           # E5: Position sizing, veto checks, VaR, limits
│   │   │   └── decision/       # E6: Aggregator & explanation generator
│   │   └── models/             # SQLAlchemy ORM database models
│   ├── pyproject.toml          # Python dependencies & build config
│   └── tests/                  # 215 backend unit and integration tests
├── frontend/
│   ├── src/
│   │   ├── components/         # CandleChart, PageHeader, Bento Panels, UI widgets
│   │   ├── pages/              # 10 application pages
│   │   │   ├── Overview.tsx    # Executive dashboard & regime monitor
│   │   │   ├── SignalLab.tsx   # Universal dataset analysis lab
│   │   │   ├── Market.tsx      # NIFTY 50 candle browser
│   │   │   ├── Research.tsx    # ML model walk-forward evaluation
│   │   │   ├── News.tsx        # News intelligence & FinBERT panel
│   │   │   ├── StrategyLab.tsx # Strategy backtesting reports
│   │   │   ├── Risk.tsx        # Risk Centre & order simulator
│   │   │   ├── SystemMonitor.tsx # System health monitor
│   │   │   └── Settings.tsx    # Risk limit configuration
│   │   ├── lib/                # API client, formatting utilities, cn helper
│   │   └── routes.ts           # Route definitions
│   └── package.json            # Frontend dependencies
├── data/                       # Parquet data lake (gitignored)
├── artifacts/                  # Serialized ML model binaries (gitignored)
├── docker-compose.yml          # PostgreSQL & Redis container definitions
├── Makefile                    # Unified developer CLI tasks
└── README.md                   # Complete platform documentation
```

---

## Installation & Getting Started

### Prerequisites
- **macOS** or **Linux**
- **Python 3.12**
- **Node.js 20+** and **npm**
- **Docker** and **Docker Compose**

### 1. Clone the Repository
```bash
git clone https://github.com/dhanushhbuilds/Stock.git
cd Stock
```

### 2. Configure Environment
Copy the sample environment file:
```bash
cp .env.example .env
```
*(The defaults are pre-configured for local development. Upstox API keys are optional for historical data, required only for live streaming).*

### 3. Start Database & Redis Services
Launch the dedicated PostgreSQL 18 (port 5433) and Redis 8 (port 6380) containers:
```bash
make services
```

### 4. Setup Backend Environment
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
```

### 5. Populate Data & Train Models
```bash
# 1. Download NIFTY 50 instrument master and sector data
python -m app.engines.data.cli instruments

# 2. Download historical daily and 1-minute candles
python -m app.engines.data.cli download --all --indices --timeframes 1day,1minute

# 3. Train swing and volatility machine learning models
python -m app.engines.ml.cli train --pipeline swing

# 4. Run strategy backtest suite
python -m app.engines.strategy.runner
```

### 6. Start the Backend API
```bash
make backend
# FastAPI will start at http://localhost:8000
# Interactive Swagger API documentation: http://localhost:8000/api/docs
```

### 7. Start the Frontend Terminal
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
# The web terminal will open at http://localhost:5173
```

---

## Testing & Verification

AstraQuant X enforces strict quality standards with comprehensive test suites across both backend and frontend:

```bash
# Run all backend tests (215 tests)
cd backend && .venv/bin/pytest

# Run frontend tests (22 tests)
cd frontend && npm test

# Full system linting & formatting checks
cd backend && .venv/bin/ruff check .
cd frontend && npm run lint
```

**Latest Test Suite Results**:
- **Backend Tests**: **215 passed** (100% passing across data, ml, news, strategy, risk, decision, and API endpoints).
- **Frontend Tests**: **22 passed** (UI components, Signal Lab parsing, page renders).
- **Alembic Migrations**: Fully up-to-date and clean.

---

## Safety, Guardrails & Compliance

- **Hard-Coded Safe Default**: `LIVE_TRADING_ENABLED=false` is enforced by config validation. Live order placement cannot be triggered accidentally.
- **Paper Broker Isolation**: Paper trading simulates orders against simulated execution queues labeled `SIMULATED`.
- **Immutable Audit Trail**: All risk evaluations, kill-switch toggles, and parameter modifications are committed to the `audit_events` database table with timestamps, IP addresses, and explicit reasons.
- **Zero Credentials Leakage**: Secrets and API tokens are redacted by logging filters and excluded via `.gitignore`.

---

*Engineered with precision for quantitative equity research.*
