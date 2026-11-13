# Review 2: AI/ML/DL Model Development (35 Marks)
## Presentation Slide-by-Slide Content Guide

**Institution**: Koneru Lakshmaiah Education Foundation (KL University), Aziz Nagar Campus, Hyderabad  
**Department**: Department of Mathematics  
**Project Title**: AstraQuant X: Institutional-Grade AI/ML Quantitative Trading & Risk Engine for Indian Equities (NSE)  
**Target**: Maximum 10 Slides (Mapped 1:1 to Review 2 Rubrics)

---

### Slide 1: Title Slide & Project Overview
* **Header / Title**: AstraQuant X — Institutional AI/ML Quantitative Trading & Risk Management Engine for Indian Equities (NSE)
* **Subtitle**: Review 2: AI/ML/DL Model Development & Systematic Execution Pipeline
* **Student Details**:
  * Name: Putrevu Naga Venkata Sai Dhanush
  * Department: Department of Mathematics, KL University
* **Project Scope**:
  * Asset Class: Indian Equities (NSE NIFTY 50, NIFTY Next 50, NIFTY Midcap 100)
  * Timeframes: Daily Swing Trading (5-session horizon) & Intraday (5-minute bars)
  * Core Philosophy: Modular Monolith, Point-in-Time Causality, Purged Walk-Forward ML Validation, Autonomous Fail-Closed Risk Engine.

---

### Slide 2: Problem Statement & Architecture Design
* **The Challenges in Financial Machine Learning**:
  * Severe noise-to-signal ratio and non-stationarity in equity returns.
  * Lookahead bias and data leakage from standard random cross-validation.
  * Naive backtests ignoring Indian statutory transaction costs (STT, GST, stamp duty, slippage) leading to false alpha.
* **AstraQuant X Architecture (The Golden Separation Rule)**:
  * **Data Engine (E1)**: Automated Upstox V3 ingestion, quality audit, and Parquet data lake.
  * **Feature Engine & ML/DL Engine (E2)**: 77 institutional quantitative features; 6-model ML/DL comparison.
  * **News Intelligence (E3)**: Regulatory feed ingestion (NSE/RBI/SEBI) with FinBERT NLP sentiment.
  * **Strategy Engine (E4)**: 10 systematic quantitative rule-based strategies.
  * **Decision Aggregator (E6)**: Combines ML, strategies, news, and market regimes into *Order Intents*.
  * **Independent Risk Engine (E5)**: Autonomous sizing and deterministic veto gate. *The Decision Engine cannot execute trades directly.*

---

### Slide 3: Data Preprocessing & Quality Audits (Evaluation Criteria 1 - 5 Marks)
* **Dataset Scope**:
  * Source: Upstox V3 Market API (historical daily candles from 2016 to 2026).
  * Universe: 197 instruments (NIFTY 50, NIFTY Next 50, NIFTY Midcap 100) + NIFTY 50 Index & India VIX.
  * Total Volume: 429,970 candle rows; 118,639 labeled samples for training.
* **Data Cleaning & Normalization**:
  * Timestamp standardization: session date flooring (00:00:00 IST) for daily bars.
  * Non-trading days & special sessions handling (Diwali Muhurat trading sessions classified properly).
  * Corporate actions: Price discontinuities (bonus/splits) handled via reference mapping (`price_discontinuities.csv`) while preserving raw Parquet data.
  * Closing auction anomaly: Flagged post-August 2026 NSE pattern (15:15–15:28 placeholders vs 15:29 print).
* **Automated Data Quality Audit**:
  * Hard relational constraints enforced: `High >= max(Open, Close)` and `Low <= min(Open, Close)`.
  * `Volume >= 0` check; zero-tolerance for silent interpolation or synthetic filling.

---

### Slide 4: Feature Engineering: 77 Quantitative Features (Evaluation Criteria 1 - 5 Marks)
* **Zero-Leakage Feature Pipeline**: All features computed strictly at close of session $t$ (shift-invariance tested).
* **Feature Categorization (77 Features Total)**:
  1. **Returns & Momentum (8)**: Log returns over 1, 2, 5, 10, 20, 60 days; Rate of Change (ROC-10); volatility-adjusted returns.
  2. **Trend & Moving Average Distances (10)**: Normalized distances from EMA (9, 20, 50, 200) and SMA (20, 50); EMA 20/50 regime; EMA 9/20 Golden/Death cross indicators.
  3. **Oscillators (6)**: RSI-14, RSI-2, Stochastic %K & %D, MACD line, signal, and normalized histogram.
  4. **Volatility & Range (11)**: ATR-14 / Close; Bollinger Bands (%B and Bandwidth); 20d & 60d Realized Volatility; Parkinson & Garman-Klass Volatility; Open-to-Previous-Close gap.
  5. **Volume Dynamics (3)**: Relative Volume ($V / \text{SMA}_{20}(V)$), Close Location Value (CLV).
  6. **Macro & Market Context (9)**: NIFTY 50 returns (1d, 5d, 20d); NIFTY vs 50/200 EMA; India VIX level, return, 1-year percentile rank, and VIX $> 20$ indicator.
  7. **Systematic Sensitivity (2)**: 60-day rolling Beta to NIFTY ($\beta_{60}$), 60-day Relative Strength ($RS_{60}$).
  8. **Calendar Features (2)**: Day of week, Month of year.

---

### Slide 5: Mathematical & Statistical Modeling (Evaluation Criteria 2 - 5 Marks)
* **Target Variable Formulation (Triple Barrier / Excess Return)**:
  * Multi-session horizon: $h = 5$ trading sessions ($t+1$ to $t+5$).
  * Cross-Sectional Excess Return:
    $$\text{Excess Return}_{i, t \rightarrow t+5} = R_{i, t \rightarrow t+5} - \text{Median}(R_{\text{universe}, t \rightarrow t+5})$$
  * Ternary Target Classification:
    * $\text{Class UP} \; (25.6\%): \text{Excess Return} > +0.5\sigma \text{ and } > \text{Round-trip Cost } (0.39\%)$
    * $\text{Class DOWN} \; (29.1\%): \text{Excess Return} < -0.5\sigma$
    * $\text{Class NEUTRAL} \; (45.3\%): \text{Within } [-0.5\sigma, +0.5\sigma]$
* **Statistical Volatility Modeling**:
  * Log Realized Volatility: $\ln(\sigma_{t \rightarrow t+5})$ modeled via non-linear GBDT vs Heterogeneous Autoregressive benchmark (HAR-RV).
* **Probability Calibration**:
  * Platt Scaling (logistic calibration for tree ensembles) and Temperature Scaling (for RNNs) on held-out validation slices; Brier score minimization to ensure reliable probabilities.

---

### Slide 6: AI / ML / DL Model Architectures (Evaluation Criteria 3 - 10 Marks)
* **6 Model Architectures Implemented & Compared**:
  1. **GRU (Gated Recurrent Unit)**: 2-layer recurrent network modeling sequential dependencies across temporal bar windows; optimized via PyTorch with AdamW.
  2. **LSTM (Long Short-Term Memory)**: 2-layer recurrent network capturing multi-week memory dynamics.
  3. **LightGBM Classifier**: Fast gradient-boosted decision trees with histogram binning and early stopping on validation loss.
  4. **XGBoost Classifier**: Exact gradient boosting with column subsampling and depth regularization.
  5. **Random Forest Classifier**: Non-linear ensemble baseline (300 estimators, min samples leaf 20).
  6. **Logistic Regression**: L2-penalized linear baseline with standard scaling.
* **NLP Sentiment Model**:
  * HuggingFace `ProsusAI/finbert` running locally via safetensors. Classifies regulatory disclosures into Positive, Negative, or Neutral probabilities.
* **Hardware & Compute Setup**:
  * Apple Silicon Metal Performance Shaders (MPS) for PyTorch neural nets + parallelized CPU threads for GBDTs.

---

### Slide 7: Training Protocol, Testing & Validation Results (Evaluation Criteria 5 - 5 Marks)
* **Validation Methodology: Purged Walk-Forward Cross-Validation**:
  * 12 sequential 6-month expanding walk-forward test folds (2020–2025).
  * **Purging**: 5-day window deleted before test folds to eliminate label overlap.
  * **Embargo**: 5-day post-test quarantine to kill serial correlation leakage.
  * **Locked Holdout Set**: 2025-11-01 to 2026-10-31 (evaluated strictly once).
* **Walk-Forward Performance (Out-of-Sample Results)**:
  * Prior / No-Skill Baseline Log Loss: **1.0659**
  * **GRU**: Log Loss **1.0461** (Best), Direction AUC **0.5161**, IC Mean **0.0165** ($t = 3.08$).
  * **LSTM**: Log Loss **1.0457**, Direction AUC **0.5143**, IC Mean **0.0134** ($t = 2.50$).
  * **Logistic Regression**: Log Loss **1.0476**, Direction AUC **0.5128**, IC Mean **0.0190** ($t = 3.66$).
* **Strict Academic Promotion Gate**:
  * **Direction Models**: Despite beating baselines in walk-forward, holdout AUC dipped to 0.491. *Honest academic decision: Direction models demoted to research status.*
  * **Volatility Forecaster (PROMOTED)**: LightGBM Volatility model achieved **Holdout $R^2 = 0.184$** (beating HAR benchmark of $0.122$ and persistence baseline of $-0.074$). Officially promoted to production.

---

### Slide 8: Trading Strategy & Signal Generation (Evaluation Criteria 4 - 5 Marks)
* **Decision Engine Ensemble (E6)**:
  * Combines ML probability scores, rule-based indicators, FinBERT sentiment, and Market Regime (NIFTY 200 EMA + VIX).
  * Outputs discrete deterministic actions: `BUY`, `SELL`, `HOLD`, or `NO_TRADE`.
  * *Fail-Closed Safety*: Defaults to `NO_TRADE` when confidence $< 0.55$, market regime is hostile, or data is stale.
* **Strategy Lab (E4) — 10 Systematic Strategies Benchmarked**:
  * Trend Following (EMA cross + breakout), Mean Reversion (Bollinger + RSI), Donchian Breakout, Volatility Squeeze, Statistical Arbitrage, etc.
* **Authentic Indian Statutory Transaction Cost Schedule**:
  * Securities Transaction Tax (STT): 0.1% delivery, 0.025% intraday.
  * GST (18%), NSE transaction charges (0.00297%), SEBI turnover fees, Stamp Duty (0.015%), Zerodha-style flat brokerage (₹20), and bid-ask slippage.

---

### Slide 9: Independent Risk Management Engine (Evaluation Criteria 4 & 6 - 5 Marks)
* **The Risk Gatekeeper (E5)**:
  * Operates completely independently of the decision engine.
  * Evaluates every order intent against portfolio margin, equity, and market state.
* **Position Sizing Algorithm**:
  * Fixed Fractional Risk: Risks exactly **2.0%** of total capital per trade.
  * Dynamic Stop-Loss: $\text{Stop Distance} = 2 \times \max(\text{ATR}_{14}, \text{Forecast Volatility})$.
  * Profit Target: Fixed at $2R$ ($2:1$ reward-to-risk ratio).
* **8 Deterministic Autonomous Veto Checks**:
  1. *Single Stock Concentration Limit*: Max 15% of total equity.
  2. *Gross Portfolio Exposure*: Max 100% (zero unhedged leverage).
  3. *Sector Exposure Cap*: Max 30% per sector.
  4. *Daily Loss Circuit Breaker*: 3% daily drawdown halts all new buy orders.
  5. *Max Drawdown Limit*: 10% peak drawdown triggers de-risking.
  6. *Market Data Freshness Gate*: Vetoes trades if feeds are $> 15$ min old.
  7. *Upper Circuit Filter*: Blocks buying within 1.5% of upper circuit limits.
  8. *Emergency Kill Switch*: Immediate one-click trading halt with audit logging.

---

### Slide 10: Code Implementation, Live Demo & Verification (Evaluation Criteria 6 - 5 Marks)
* **Full-Stack Implementation**:
  * Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 18, Redis 8, PyArrow.
  * Frontend: React 19, TypeScript, Vite, Tailwind CSS, Lightweight Charts, Recharts.
* **Flagship Feature — Signal Lab (`/signal-lab`)**:
  * Universal dropzone: Drag-and-drop ANY CSV/Excel OHLCV dataset or pick any NSE symbol.
  * Instant automated pipeline: Validation $\rightarrow$ 77 features $\rightarrow$ AI models $\rightarrow$ Risk evaluation.
  * Outputs clear Verdict card (`BUY`/`SELL`/`HOLD`/`NO_TRADE`), interactive chart with trade markers, post-cost backtest equity curve, and CSV signal export.
* **System Testing & Verification**:
  * **215 Backend Unit & Integration Tests Passing** (`pytest`).
  * **22 Frontend Tests Passing** (`vitest`).
  * Strict security: `LIVE_TRADING_ENABLED=false` hard-coded guardrail.
  * GitHub Repository: Fully committed and reproducible at [https://github.com/dhanushhbuilds/Stock](https://github.com/dhanushhbuilds/Stock).
