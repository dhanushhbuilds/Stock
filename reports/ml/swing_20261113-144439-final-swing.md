# Swing model evaluation — run 20261113-144439-final-swing

Dataset `4ceaf7e8c5f17d00`: 429,970 rows (118,639 labelled), 197 symbols, 2016-10-26 → 2026-11-12, 77 features.
Label distribution [DOWN, NEUTRAL, UP]: [0.2914, 0.4527, 0.2559]. Config: `{"horizon": 5, "label_c": 0.5, "cost": 0.0039, "start": "2016-01-01", "min_history": 200, "label_mode": "excess", "train_universes": ["NIFTY50", "NIFTYNEXT50", "NIFTYMIDCAP100"], "xs_rank_features": false}`.
Protocol: walk-forward from 2020-01-01 in 6-month test windows, purged; locked holdout from 2025-11-01.

**Selected on walk-forward results only:** `gru` (ranking: gru, lstm, logreg, lightgbm, random_forest, xgboost).
**Registry:** `swing-gru-20261113-144439-final-swing` — promoted: **False**

- PASS: walk-forward log loss < prior baseline
- PASS: holdout log loss < prior baseline
- PASS: walk-forward direction AUC >= 0.51
- PASS: walk-forward mean IC > 0 with t-stat >= 2
- FAIL: holdout direction AUC > 0.5
- PASS: walk-forward strategy Sharpe after costs > 0

## Walk-forward (out-of-sample, all folds pooled)

| model | acc | macro-F1 | log loss | prior log loss | Brier | ROC-AUC (OvR) | direction AUC | IC mean | IC t |
|---|---|---|---|---|---|---|---|---|---|
| logreg | 0.4589 | 0.2843 | 1.0476 | 1.0659 | 0.6302 | 0.5810 | 0.5128 | 0.0190 | 3.66 |
| random_forest | 0.4582 | 0.3291 | 1.0481 | 1.0659 | 0.6310 | 0.5776 | 0.5044 | 0.0082 | 1.67 |
| xgboost | 0.4570 | 0.3246 | 1.0486 | 1.0659 | 0.6312 | 0.5759 | 0.5036 | 0.0045 | 0.90 |
| lightgbm | 0.4595 | 0.3162 | 1.0483 | 1.0659 | 0.6309 | 0.5762 | 0.5057 | 0.0058 | 1.19 |
| lstm | 0.4604 | 0.3121 | 1.0457 | 1.0659 | 0.6294 | 0.5814 | 0.5143 | 0.0134 | 2.50 |
| gru | 0.4603 | 0.2946 | 1.0461 | 1.0659 | 0.6296 | 0.5811 | 0.5161 | 0.0165 | 3.08 |

Trading after costs:

| model | total return | ann. return | Sharpe | Sortino | max DD | profit factor | win rate | trades |
|---|---|---|---|---|---|---|---|---|
| logreg | 49.53% | 7.22% | 0.48 | 0.54 | -39.03% | 1.26 | 50.70% | 968 |
| random_forest | 50.35% | 7.32% | 0.47 | 0.48 | -43.83% | 1.30 | 52.21% | 846 |
| xgboost | 52.75% | 7.61% | 0.49 | 0.54 | -44.14% | 1.30 | 49.12% | 940 |
| lightgbm | 59.70% | 8.45% | 0.54 | 0.60 | -41.61% | 1.33 | 48.94% | 1048 |
| lstm | 5.31% | 0.90% | 0.14 | 0.15 | -36.64% | 1.08 | 48.11% | 871 |
| gru | 20.13% | 3.23% | 0.27 | 0.27 | -42.72% | 1.16 | 46.99% | 860 |

Ranking diagnostic — top-10 minus bottom-10, gross, needs shorting (not a tradable cash strategy):

| model | total | ann. | Sharpe | max DD |
|---|---|---|---|---|
| logreg | 72.07% | 9.86% | 0.67 | -30.39% |
| random_forest | -22.88% | -4.40% | -0.21 | -42.51% |
| xgboost | -21.82% | -4.17% | -0.19 | -43.58% |
| lightgbm | 3.64% | 0.62% | 0.12 | -32.38% |
| lstm | 6.01% | 1.02% | 0.15 | -29.82% |
| gru | -4.18% | -0.74% | 0.05 | -38.92% |

| *benchmark: equal-weight universe* | 282.00% | 26.13% | 1.36 | 1.63 | -34.41% | 1.73 | 59.45% | — |

## Locked holdout

| model | acc | macro-F1 | log loss | prior log loss | Brier | ROC-AUC (OvR) | direction AUC | IC mean | IC t |
|---|---|---|---|---|---|---|---|---|---|
| logreg | 0.4641 | 0.2489 | 1.0491 | 1.0640 | 0.6309 | 0.5705 | 0.4939 | -0.0141 | -1.16 |
| random_forest | 0.4568 | 0.3146 | 1.0487 | 1.0640 | 0.6310 | 0.5744 | 0.4998 | -0.0002 | -0.02 |
| xgboost | 0.4563 | 0.3030 | 1.0494 | 1.0640 | 0.6314 | 0.5746 | 0.4978 | -0.0003 | -0.03 |
| lightgbm | 0.4574 | 0.2993 | 1.0497 | 1.0640 | 0.6314 | 0.5737 | 0.4980 | -0.0034 | -0.33 |
| lstm | 0.4592 | 0.2998 | 1.0475 | 1.0640 | 0.6300 | 0.5786 | 0.4947 | 0.0152 | 1.12 |
| gru | 0.4614 | 0.2986 | 1.0487 | 1.0640 | 0.6308 | 0.5758 | 0.4907 | 0.0115 | 0.84 |

Trading after costs:

| model | total return | ann. return | Sharpe | Sortino | max DD | profit factor | win rate | trades |
|---|---|---|---|---|---|---|---|---|
| logreg | -14.44% | -14.55% | -1.13 | -1.37 | -19.16% | 0.61 | 38.00% | 196 |
| random_forest | 2.83% | 2.85% | 0.25 | 0.48 | -12.84% | 1.13 | 44.90% | 196 |
| xgboost | 8.17% | 8.24% | 0.55 | 0.96 | -11.43% | 1.29 | 47.83% | 219 |
| lightgbm | -1.26% | -1.27% | 0.01 | 0.01 | -11.34% | 1.00 | 40.82% | 238 |
| lstm | 3.57% | 3.60% | 0.46 | 0.92 | -4.53% | 1.36 | 32.43% | 64 |
| gru | -0.16% | -0.16% | -0.02 | -0.03 | -3.61% | 0.99 | 33.33% | 40 |

Ranking diagnostic — top-10 minus bottom-10, gross, needs shorting (not a tradable cash strategy):

| model | total | ann. | Sharpe | max DD |
|---|---|---|---|---|
| logreg | -6.52% | -6.58% | -0.48 | -12.07% |
| random_forest | 0.97% | 0.98% | 0.14 | -9.14% |
| xgboost | 6.11% | 6.16% | 0.63 | -7.65% |
| lightgbm | 8.75% | 8.82% | 0.86 | -5.79% |
| lstm | 13.10% | 13.21% | 0.74 | -11.07% |
| gru | 5.32% | 5.37% | 0.36 | -10.02% |

| *benchmark: equal-weight universe* | 1.87% | 1.89% | 0.19 | 0.38 | -12.14% | 1.08 | 52.00% | — |

## Selected model per fold (gru)

| test window | n | log loss | prior | direction AUC | best iter |
|---|---|---|---|---|---|
| 2020-01-01 → 2020-06-30 | 5781 | 1.0306 | 1.0479 | 0.5284 | 6 |
| 2020-07-01 → 2020-12-31 | 6063 | 1.0672 | 1.0818 | 0.5226 | 5 |
| 2021-01-01 → 2021-06-30 | 5748 | 1.0558 | 1.0660 | 0.5290 | 13 |
| 2021-07-01 → 2021-12-31 | 6048 | 1.0501 | 1.0744 | 0.4839 | 6 |
| 2022-01-03 → 2022-06-30 | 5938 | 1.0330 | 1.0522 | 0.5087 | 5 |
| 2022-07-01 → 2022-12-30 | 6125 | 1.0360 | 1.0507 | 0.5330 | 1 |
| 2023-01-02 → 2023-06-30 | 5978 | 1.0545 | 1.0690 | 0.5087 | 5 |
| 2023-07-03 → 2023-12-29 | 6076 | 1.0525 | 1.0768 | 0.4924 | 4 |
| 2024-01-01 → 2024-06-28 | 6040 | 1.0203 | 1.0646 | 0.5191 | 5 |
| 2024-07-01 → 2024-12-31 | 6300 | 1.0450 | 1.0613 | 0.4797 | 3 |
| 2025-01-01 → 2025-06-30 | 6150 | 1.0493 | 1.0715 | 0.5442 | 10 |
| 2025-07-01 → 2025-10-31 | 4250 | 1.0636 | 1.0748 | 0.5288 | 5 |

Holdout confusion matrix (rows = true DOWN/NEUTRAL/UP, cols = predicted):

```
[772, 2647, 1]
[780, 4995, 0]
[697, 2608, 0]
```
