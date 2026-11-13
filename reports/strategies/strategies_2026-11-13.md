# Strategy backtests — 2026-11-13

Universe: 50 current NIFTY 50 stocks, Rs 5,000,000 split equally (Rs 100,000 per stock). Long-only. Signals at close, executed next open; 2xATR stop on every trade; intraday flat by 15:10.
Costs: full NSE/Upstox charge schedule + 5 bp slippage per side (round trip on Rs 1 lakh: delivery ~0.39%, intraday ~0.18%). Parameters are textbook defaults chosen before testing (no optimisation).

## in-sample (2017-01-01 → 2019-12-31)

| strategy | tf | total | ann. | Sharpe | Sortino | max DD | PF | win | trades | avg net/trade | costs / gross profit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| relative_strength_momentum | 1day | 14.1% | 4.6% | 0.92 | 1.36 | -6.4% | 1.17 | 54.3% | 192 | 1.0% | 0.08 |
| trend_following | 1day | 15.7% | 5.1% | 0.87 | 1.28 | -7.2% | 1.15 | 54.9% | 372 | 0.8% | 0.13 |
| ema_crossover | 1day | 16.5% | 5.3% | 0.86 | 1.27 | -10.4% | 1.15 | 53.5% | 335 | 1.3% | 0.08 |
| atr_breakout | 1day | -0.2% | -0.1% | -0.01 | -0.02 | -3.4% | 1.00 | 48.7% | 541 | 0.0% | 0.17 |
| donchian_breakout | 1day | -0.9% | -0.3% | -0.03 | -0.05 | -9.4% | 0.99 | 51.6% | 619 | -0.2% | 0.14 |
| rsi_mean_reversion | 1day | -0.1% | -0.0% | -0.05 | -0.04 | -1.2% | 0.99 | 48.7% | 42 | 0.1% | 0.11 |
| bollinger_mean_reversion | 1day | -4.6% | -1.6% | -0.36 | -0.43 | -11.6% | 0.93 | 48.8% | 784 | -0.3% | 0.16 |
| macd_momentum | 1day | -5.2% | -1.8% | -0.76 | -1.03 | -6.9% | 0.87 | 49.2% | 649 | -0.5% | 0.25 |
| *benchmark equal weight buy hold* | 1day | 59.2% | 17.2% | 1.27 | 2.03 | -15.5% | 1.23 | — | — | — | — |
| *benchmark nifty50 index* | 1day | 48.7% | 14.5% | 1.18 | 1.88 | -14.6% | 1.22 | — | — | — | — |

## out-of-sample (2020-01-01 → 2026-12-31)

| strategy | tf | total | ann. | Sharpe | Sortino | max DD | PF | win | trades | avg net/trade | costs / gross profit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ema_crossover | 1day | 110.2% | 11.6% | 1.22 | 1.51 | -12.2% | 1.25 | 57.7% | 775 | 6.2% | 0.05 |
| trend_following | 1day | 141.1% | 13.9% | 1.14 | 1.42 | -14.1% | 1.23 | 57.2% | 897 | 5.3% | 0.05 |
| donchian_breakout | 1day | 73.5% | 8.5% | 1.08 | 1.30 | -14.1% | 1.23 | 55.9% | 1508 | 1.8% | 0.08 |
| relative_strength_momentum | 1day | 70.4% | 8.2% | 1.00 | 1.29 | -13.0% | 1.19 | 57.1% | 568 | 6.0% | 0.04 |
| atr_breakout | 1day | 11.3% | 1.6% | 0.46 | 0.58 | -8.5% | 1.10 | 52.0% | 1569 | 0.3% | 0.14 |
| macd_momentum | 1day | 6.6% | 1.0% | 0.30 | 0.35 | -11.3% | 1.06 | 51.2% | 1534 | 0.2% | 0.16 |
| rsi_mean_reversion | 1day | 1.1% | 0.2% | 0.19 | 0.16 | -2.2% | 1.06 | 51.3% | 128 | 0.6% | 0.12 |
| bollinger_mean_reversion | 1day | -9.1% | -1.4% | -0.14 | -0.13 | -26.2% | 0.96 | 51.5% | 2004 | -0.1% | 0.15 |
| opening_range_breakout | 5minute | -64.0% | -19.4% | -7.99 | -13.31 | -64.1% | 0.27 | 21.8% | 27839 | -0.2% | 0.59 |
| vwap_trend | 5minute | -82.2% | -30.5% | -20.96 | -28.56 | -82.2% | 0.05 | 7.4% | 38101 | -0.2% | 1.57 |
| *benchmark equal weight buy hold* | 1day | 294.8% | 22.5% | 1.22 | 1.38 | -39.1% | 1.26 | — | — | — | — |
| *benchmark nifty50 index* | 1day | 107.9% | 11.4% | 0.70 | 0.82 | -38.4% | 1.14 | — | — | — | — |

## Out-of-sample trades by market regime at entry (trend / India VIX percentile)

| strategy | regime | trades | win rate | avg net return |
|---|---|---|---|---|
| ema_crossover | bear/high_vol | 57 | 40.4% | 5.34% |
| ema_crossover | bear/low_vol | 10 | 40.0% | 14.26% |
| ema_crossover | bear/normal_vol | 64 | 40.6% | 4.48% |
| ema_crossover | bull/high_vol | 50 | 30.0% | 0.28% |
| ema_crossover | bull/low_vol | 161 | 39.1% | 9.61% |
| ema_crossover | bull/normal_vol | 261 | 34.5% | 5.56% |
| ema_crossover | sideways/high_vol | 20 | 45.0% | 18.35% |
| ema_crossover | sideways/low_vol | 38 | 39.5% | 18.85% |
| ema_crossover | sideways/normal_vol | 114 | 17.5% | -0.09% |
| macd_momentum | bear/high_vol | 51 | 33.3% | -0.03% |
| macd_momentum | bear/low_vol | 4 | 25.0% | -1.76% |
| macd_momentum | bear/normal_vol | 72 | 29.2% | -1.21% |
| macd_momentum | bull/high_vol | 129 | 34.9% | 0.38% |
| macd_momentum | bull/low_vol | 416 | 32.7% | 0.47% |
| macd_momentum | bull/normal_vol | 635 | 33.9% | 0.42% |
| macd_momentum | sideways/high_vol | 10 | 30.0% | -1.36% |
| macd_momentum | sideways/low_vol | 61 | 29.5% | -0.62% |
| macd_momentum | sideways/normal_vol | 156 | 35.9% | -0.08% |
| rsi_mean_reversion | bear/high_vol | 15 | 13.3% | -5.25% |
| rsi_mean_reversion | bear/low_vol | 2 | 100.0% | 2.32% |
| rsi_mean_reversion | bear/normal_vol | 12 | 50.0% | 3.39% |
| rsi_mean_reversion | bull/high_vol | 7 | 57.1% | 3.78% |
| rsi_mean_reversion | bull/low_vol | 16 | 62.5% | 1.81% |
| rsi_mean_reversion | bull/normal_vol | 43 | 60.5% | 1.77% |
| rsi_mean_reversion | sideways/high_vol | 3 | 66.7% | 1.53% |
| rsi_mean_reversion | sideways/low_vol | 7 | 42.9% | -0.59% |
| rsi_mean_reversion | sideways/normal_vol | 23 | 39.1% | -0.94% |
| bollinger_mean_reversion | bear/high_vol | 451 | 43.5% | -1.59% |
| bollinger_mean_reversion | bear/low_vol | 16 | 43.8% | -1.91% |
| bollinger_mean_reversion | bear/normal_vol | 272 | 53.7% | 0.04% |
| bollinger_mean_reversion | bull/high_vol | 115 | 68.7% | 1.31% |
| bollinger_mean_reversion | bull/low_vol | 266 | 58.6% | 0.02% |
| bollinger_mean_reversion | bull/normal_vol | 494 | 58.1% | 0.27% |
| bollinger_mean_reversion | sideways/high_vol | 37 | 70.3% | 4.15% |
| bollinger_mean_reversion | sideways/low_vol | 91 | 59.3% | 0.34% |
| bollinger_mean_reversion | sideways/normal_vol | 262 | 55.7% | -0.04% |
| donchian_breakout | bear/high_vol | 100 | 34.0% | 1.33% |
| donchian_breakout | bear/low_vol | 19 | 36.8% | -1.55% |
| donchian_breakout | bear/normal_vol | 142 | 50.7% | 3.01% |
| donchian_breakout | bull/high_vol | 103 | 31.1% | 0.16% |
| donchian_breakout | bull/low_vol | 328 | 38.1% | 2.50% |
| donchian_breakout | bull/normal_vol | 545 | 37.8% | 2.43% |
| donchian_breakout | sideways/high_vol | 19 | 26.3% | -1.37% |
| donchian_breakout | sideways/low_vol | 85 | 25.9% | 1.00% |
| donchian_breakout | sideways/normal_vol | 167 | 29.3% | -0.28% |
| trend_following | bear/high_vol | 99 | 30.3% | 3.72% |
| trend_following | bear/low_vol | 10 | 20.0% | -1.15% |
| trend_following | bear/normal_vol | 101 | 26.7% | 3.34% |
| trend_following | bull/high_vol | 33 | 42.4% | 3.82% |
| trend_following | bull/low_vol | 156 | 25.6% | 10.64% |
| trend_following | bull/normal_vol | 265 | 21.1% | 9.44% |
| trend_following | sideways/high_vol | 24 | 33.3% | 2.49% |
| trend_following | sideways/low_vol | 77 | 11.7% | 0.56% |
| trend_following | sideways/normal_vol | 132 | 10.6% | -2.23% |
| atr_breakout | bear/high_vol | 112 | 52.7% | 0.74% |
| atr_breakout | bear/low_vol | 11 | 72.7% | -0.88% |
| atr_breakout | bear/normal_vol | 132 | 39.4% | -0.60% |
| atr_breakout | bull/high_vol | 147 | 52.4% | 0.31% |
| atr_breakout | bull/low_vol | 337 | 47.5% | 0.12% |
| atr_breakout | bull/normal_vol | 534 | 47.4% | 0.89% |
| atr_breakout | sideways/high_vol | 21 | 42.9% | -0.16% |
| atr_breakout | sideways/low_vol | 89 | 48.3% | -0.01% |
| atr_breakout | sideways/normal_vol | 186 | 44.6% | -0.22% |
| relative_strength_momentum | bear/high_vol | 84 | 44.0% | 8.43% |
| relative_strength_momentum | bear/low_vol | 8 | 25.0% | 2.49% |
| relative_strength_momentum | bear/normal_vol | 73 | 38.4% | 0.91% |
| relative_strength_momentum | bull/high_vol | 30 | 33.3% | -1.40% |
| relative_strength_momentum | bull/low_vol | 97 | 29.9% | 11.06% |
| relative_strength_momentum | bull/normal_vol | 143 | 30.1% | 10.95% |
| relative_strength_momentum | sideways/high_vol | 15 | 26.7% | 1.73% |
| relative_strength_momentum | sideways/low_vol | 45 | 33.3% | 2.11% |
| relative_strength_momentum | sideways/normal_vol | 73 | 13.7% | -1.60% |
| vwap_trend | bear/high_vol | 3087 | 14.6% | -0.26% |
| vwap_trend | bear/low_vol | 462 | 15.2% | -0.24% |
| vwap_trend | bear/normal_vol | 4963 | 12.7% | -0.28% |
| vwap_trend | bull/high_vol | 3481 | 13.8% | -0.22% |
| vwap_trend | bull/low_vol | 7851 | 13.2% | -0.23% |
| vwap_trend | bull/normal_vol | 9921 | 13.3% | -0.23% |
| vwap_trend | sideways/high_vol | 795 | 15.1% | -0.20% |
| vwap_trend | sideways/low_vol | 2777 | 12.4% | -0.25% |
| vwap_trend | sideways/normal_vol | 4764 | 13.3% | -0.26% |
| opening_range_breakout | bear/high_vol | 2397 | 31.8% | -0.24% |
| opening_range_breakout | bear/low_vol | 351 | 31.3% | -0.19% |
| opening_range_breakout | bear/normal_vol | 3495 | 30.2% | -0.24% |
| opening_range_breakout | bull/high_vol | 2651 | 31.8% | -0.19% |
| opening_range_breakout | bull/low_vol | 5517 | 30.2% | -0.19% |
| opening_range_breakout | bull/normal_vol | 7482 | 31.8% | -0.18% |
| opening_range_breakout | sideways/high_vol | 689 | 34.0% | -0.12% |
| opening_range_breakout | sideways/low_vol | 1935 | 31.1% | -0.19% |
| opening_range_breakout | sideways/normal_vol | 3322 | 30.3% | -0.19% |

## Caveats

- Parameters are textbook defaults chosen before testing (no optimisation).
- Universe = current NIFTY 50 constituents: survivorship bias inflates results.
- Long-only; signals at close t executed at open t+1.
- Intraday results include every order's brokerage and STT; high-turnover rules are dominated by costs.
