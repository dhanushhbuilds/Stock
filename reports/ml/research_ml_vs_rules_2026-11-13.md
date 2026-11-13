# Research question: does ML beat rule-based strategies? (2026-11-13)

Model: Logistic Regression (best walk-forward IC). Universe: NIFTY 50 (trained on NIFTY 50 + Next 50 + Midcap 100). Long-only, top-10, turnover-based round-trip cost 0.39%. Rebalance every h sessions.

## Walk-forward 2020-01 → 2025-10 (out of sample)

| horizon | IC | IC t | ML top-10 | trend filter (no ML) | trend + ML top-10 | buy & hold |
|---|---|---|---|---|---|---|
| 5 sessions | 0.0187 | 3.60 | Sharpe 0.48 · DD -39.0% · total 50% | Sharpe 1.13 · DD -30.7% · total 209% | Sharpe 0.32 · DD -27.4% · total 22% | Sharpe 1.36 · DD -34.4% · total 282% |
| 20 sessions | 0.0168 | 2.97 | Sharpe 0.59 · DD -29.8% · total 62% | Sharpe 1.20 · DD -28.2% · total 211% | Sharpe 0.37 · DD -31.4% · total 28% | Sharpe 1.38 · DD -30.5% · total 285% |

## Locked holdout 2025-11-03 → 2026-10-14 (evaluated once, for the variant chosen on walk-forward: ml_top10, h=20)

| | IC | IC t | Sharpe | max DD | total |
|---|---|---|---|---|---|
| ml_top10 | -0.0263 | -2.12 | -1.48 | -21.4% | -17.1% |
| trend_equal_weight | — | — | -0.89 | -17.1% | -17.2% |
| buy_and_hold | — | — | -0.35 | -11.6% | -7.1% |

## Conclusion

- The ML ranking signal is statistically significant in walk-forward testing (IC ≈ 0.017–0.019, t ≈ 3–3.6) but **too weak to beat buy-and-hold after costs** in a concentrated top-10 long-only portfolio, and **adding it to a trend filter lowered the trend filter's Sharpe**.
- On the locked holdout year the ranking skill **reversed** (negative IC), i.e. the edge did not persist out of sample.
- Answer to the slide-4 research question on this data: **no** — ML did not improve risk-adjusted returns after costs over rule-based strategies. Trend rules mainly reduce drawdown; buy-and-hold had the best Sharpe 2020–2025 (flattered by survivorship bias).
- The holdout is now spent: any further model changes must be validated on new, unseen data (forward/paper testing), not on this year again.
