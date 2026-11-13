# Phase 4 — ML/DL Training (swing; intraday deferred by owner)

1. **Objective:** compare six model families under one leakage-safe protocol for the swing task (daily bars → next 5
   sessions) and add volatility forecasting; promote a model only if it beats no-skill baselines out of sample.

2. **Implemented**
   - Trainer (`app/engines/ml/trainer.py`): expanding walk-forward 2020-01 → 2025-10 in 6-month windows (12 folds),
     purge = horizon before validation and test, early stopping + Platt (trees/linear) or temperature (RNN) calibration
     on the purged validation slice, locked holdout 2025-11 → 2026-10 evaluated once. Selection on walk-forward only.
   - Models: Logistic Regression, Random Forest, XGBoost, LightGBM, LSTM, GRU (PyTorch, Apple MPS).
   - Registry (`ml_datasets`, `ml_experiments`, `ml_models`) with content-hashed datasets and SHA-256 artifacts.
   - Strict promotion gate (log loss < prior on walk-forward AND holdout; walk-forward direction AUC ≥ 0.51;
     IC > 0 with t ≥ 2; holdout direction AUC > 0.5; walk-forward strategy Sharpe after costs > 0).
   - Volatility forecasting (`app/engines/ml/volatility.py`): log realised vol of the next 5 sessions; baselines
     persistence and HAR; candidates HAR-X and LightGBM.
   - Research comparison ML vs rule-based (`app/engines/ml/research.py`), 5- and 20-session horizons.

3. **Results — swing direction (run `20261113-144439-final-swing`, 118,639 NIFTY 50 labelled rows, 77 features)**

| model | WF log loss (prior 1.0659) | WF direction AUC | WF IC (t) | holdout log loss (prior 1.0640) | holdout direction AUC |
|---|---|---|---|---|---|
| GRU (selected) | 1.0461 | 0.516 | 0.0165 (3.08) | 1.0487 | 0.491 |
| LSTM | 1.0457 | 0.514 | 0.0134 (2.50) | 1.0475 | 0.495 |
| Logistic Regression | 1.0476 | 0.513 | 0.0190 (3.66) | 1.0491 | 0.494 |
| LightGBM | 1.0483 | 0.506 | 0.0058 (1.19) | 1.0497 | 0.498 |
| Random Forest | 1.0481 | 0.504 | 0.0082 (1.67) | 1.0487 | 0.500 |
| XGBoost | 1.0486 | 0.504 | 0.0045 (0.90) | 1.0494 | 0.498 |

   All six beat the no-skill baseline on probability quality in walk-forward and holdout; the recurrent models are
   best. **GRU was selected but NOT promoted**: it fails "holdout direction AUC > 0.5" — the directional edge seen in
   2020–2025 did not persist into the unseen year. No top-10 long-only ML portfolio beat equal-weight buy & hold after
   costs (walk-forward Sharpe 0.14–0.54 vs 1.36); adding ML to a trend filter lowered the trend filter's Sharpe
   (`reports/ml/research_ml_vs_rules_2026-11-13.md`).

4. **Results — volatility forecasting (run `20261113-145734-vol`) — PROMOTED**

| model | WF R² (log vol) | holdout R² | holdout RMSE |
|---|---|---|---|
| Persistence (vol20) | 0.060 | −0.074 | 0.5362 |
| HAR | 0.228 | 0.122 | 0.4848 |
| HAR-X | 0.281 | 0.166 | 0.4723 |
| **LightGBM (promoted)** | **0.292** | **0.184** | **0.4672** |

   LightGBM beats both baselines on walk-forward and the once-only holdout (holdout RMSE −12.9% vs persistence,
   rank correlation 0.424) and is above zero R² in every walk-forward window.

5. **Bugs found and fixed:** too-lenient first promotion gate (and a stale promoted model demoted); under-costed ML
   backtests (0.25%/0.10% → 0.39%/0.18% from the charge schedule); a backtest that only bought argmax-UP and charged
   full cost on unchanged holdings; macOS OpenMP conflicts — lightgbm→torch and torch→xgboost segfaults, torch deadlock
   after tree training, torch training segfault after xgboost load → two process modes (`AQ_ML_MODE=torch`), lazy
   tree-library imports, three-step training (`train_final.sh`: trees, RNNs, finalize), regression tests for each.

6. **Tests:** 204 backend + 19 frontend passing; ML-specific: features/leakage (19), volatility (3), end-to-end (1).
7. **Performance:** swing dataset build 3.2 s; trees 12 folds ≈ 20 min (Random Forest dominates); LSTM ≈ 5 s/fold on
   MPS; volatility run 280 s; inference via API on the latest session ≈ seconds (dataset rebuild dominates).
8. **Limitations:** intraday 6-model comparison deferred (pipeline, features, labels and leak tests are built; an
   earlier run showed log loss below baseline in 12/12 folds for LR); current-constituent universe (survivorship bias);
   no historical news; the direction holdout is now spent — further direction work needs new unseen data.
9. **Acceptance gate:** **PASS WITH LIMITATIONS** — real evaluation reports for six direction models and the
   volatility model exist; the direction model honestly fails promotion; the volatility model is promoted.
