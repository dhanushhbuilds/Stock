"""Out-of-sample metrics: classification quality + cost-adjusted trading performance."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
    roc_auc_score,
)

from app.engines.ml.labels import CLASS_NAMES, DOWN, UP


def brier_multiclass(y: np.ndarray, p: np.ndarray) -> float:
    onehot = np.eye(3)[y.astype(int)]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def classification_metrics(y: np.ndarray, p: np.ndarray, fwd_ret: np.ndarray | None = None) -> dict:
    y = y.astype(int)
    pred = p.argmax(axis=1)
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=[0, 1, 2], zero_division=0)
    out = {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", labels=[0, 1, 2], zero_division=0)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-7, 1), labels=[0, 1, 2])),
        "brier": brier_multiclass(y, p),
        "roc_auc_ovr_macro": float(roc_auc_score(y, p, multi_class="ovr", average="macro", labels=[0, 1, 2])),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(prec[i]),
                "recall": float(rec[i]),
                "f1": float(f1[i]),
                "support": int(sup[i]),
            }
            for i in range(3)
        },
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1, 2]).tolist(),
        "pred_distribution": np.bincount(pred, minlength=3).tolist(),
    }
    if fwd_ret is not None:
        score = p[:, UP] - p[:, DOWN]
        up = fwd_ret > 0
        if 0 < up.sum() < len(up):
            out["direction_auc"] = float(
                roc_auc_score(up, score)
            )  # does (p_up - p_down) rank future returns?
        out["score_ret_spearman"] = float(pd.Series(score).corr(pd.Series(fwd_ret), method="spearman"))
    return out


def information_coefficient(dates: np.ndarray, score: np.ndarray, fwd_ret: np.ndarray) -> dict:
    """Per-date Spearman correlation between score and forward return (cross-sectional ranking skill)."""
    d = pd.DataFrame({"date": dates, "s": score, "r": fwd_ret}).dropna()
    ics = (
        d.groupby("date")
        .apply(
            lambda g: g["s"].corr(g["r"], method="spearman") if len(g) >= 10 else np.nan, include_groups=False
        )
        .dropna()
    )
    if len(ics) < 2:
        return {}
    return {
        "ic_mean": float(ics.mean()),
        "ic_std": float(ics.std()),
        "ic_t": float(ics.mean() / ics.std() * np.sqrt(len(ics))),
        "ic_positive_share": float((ics > 0).mean()),
        "ic_dates": int(len(ics)),
    }


def prior_baseline(y_train: np.ndarray, y_test: np.ndarray) -> dict:
    """Always predict training-period class frequencies: the bar a model must beat on log loss / Brier."""
    freq = np.bincount(y_train.astype(int), minlength=3) / len(y_train)
    p = np.tile(freq, (len(y_test), 1))
    m = classification_metrics(y_test, p)
    return {k: m[k] for k in ("accuracy", "macro_f1", "log_loss", "brier", "roc_auc_ovr_macro")}


def perf_stats(rets: pd.Series, periods_per_year: float, cost_paid: float = 0.0, trades: int = 0) -> dict:
    rets = rets.fillna(0.0)
    if len(rets) == 0:
        return {"periods": 0}
    eq = (1 + rets).cumprod()
    dd = eq / eq.cummax() - 1
    years = len(rets) / periods_per_year
    sd = rets.std(ddof=1)
    down = rets[rets < 0].std(ddof=1)
    gains, losses = rets[rets > 0].sum(), -rets[rets < 0].sum()
    active = rets[rets != 0]
    return {
        "periods": int(len(rets)),
        "total_return": float(eq.iloc[-1] - 1),
        "annualized_return": float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else None,
        "sharpe": float(rets.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else None,
        "sortino": float(rets.mean() / down * np.sqrt(periods_per_year)) if down and down > 0 else None,
        "max_drawdown": float(dd.min()),
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "win_rate": float((active > 0).mean()) if len(active) else None,
        "trades": int(trades),
        "costs_paid": float(cost_paid),
    }


def swing_backtest(df: pd.DataFrame, p: np.ndarray, horizon: int, cost: float, top_k: int = 5) -> dict:
    """Uses df['fwd_ret_abs'] (actual stock return) when present, so P&L is real even for excess-labelled models."""
    if "fwd_ret_abs" in df:
        df = df.assign(fwd_ret=df["fwd_ret_abs"])
    return _swing_bt(df, p, horizon, cost, top_k)


def _swing_bt(df: pd.DataFrame, p: np.ndarray, horizon: int, cost: float, top_k: int) -> dict:
    """Long-only ranking portfolio. Every `horizon` sessions: hold the top_k stocks by score = p_up - p_down,
    but only those with score > 0 (an unattractive slot stays in cash = NO TRADE). Equal weight 1/top_k per slot.
    Costs are turnover-based: half the round-trip cost on every unit of weight bought or sold.
    Benchmark: equal-weight all stocks over the same periods (bought once, costless)."""
    d = df[["date", "symbol", "fwd_ret"]].copy()
    d["score"] = p[:, UP] - p[:, DOWN]
    dates = sorted(d["date"].unique())[::horizon]  # non-overlapping holding periods
    strat, bench, ls, costs, trades, prev = [], [], [], 0.0, 0, pd.Series(dtype=float)
    turnover_total = 0.0
    for dt in dates:
        x = d[d["date"] == dt].dropna(subset=["fwd_ret"])
        if x.empty:
            continue
        bench.append(x["fwd_ret"].mean())
        ls.append(
            x.nlargest(top_k, "score")["fwd_ret"].mean() - x.nsmallest(top_k, "score")["fwd_ret"].mean()
        )
        pick = x[x["score"] > 0].nlargest(top_k, "score")
        w = pd.Series(1.0 / top_k, index=pick["symbol"].to_numpy())
        turnover = w.subtract(prev, fill_value=0).abs().sum()
        c = turnover * cost / 2
        trades += int((w.index.difference(prev.index)).size)
        gross = float((pick.set_index("symbol")["fwd_ret"] * w).sum())
        strat.append(gross - c)
        costs += c
        turnover_total += turnover
        # weights drift with returns; approximate next-period starting weights by holding weights
        prev = w
    ppy = 252 / horizon
    return {
        "strategy": perf_stats(pd.Series(strat), ppy, costs, trades),
        "benchmark_equal_weight": perf_stats(pd.Series(bench), ppy),
        # Diagnostic only (gross, needs shorting via F&O): top-k minus bottom-k = pure ranking skill.
        "long_short_gross_diagnostic": perf_stats(pd.Series(ls), ppy),
        "rebalances": len(strat),
        "top_k": top_k,
        "cost_per_round_trip": cost,
        "avg_turnover_per_rebalance": turnover_total / max(len(strat), 1),
    }


def intraday_backtest(df: pd.DataFrame, p: np.ndarray, cost: float, threshold: float) -> dict:
    """Trade a decision bar when |p_up - p_down| >= threshold (chosen on the validation slice, never on test):
    long if UP more likely, short if DOWN; exit after the horizon. Daily return = mean of that day's trades."""
    d = df[["date", "fwd_ret"]].copy()
    score = p[:, UP] - p[:, DOWN]
    take = np.abs(score) >= threshold
    d["r"] = np.where(take, np.sign(score) * d["fwd_ret"] - cost, np.nan)
    trades = int(take.sum())
    daily = d.groupby("date")["r"].mean().fillna(0.0)
    per_trade = d["r"].dropna()
    out = {
        "strategy": perf_stats(daily, 252, cost * trades, trades),
        "threshold": float(np.mean(threshold)),  # per-fold thresholds -> report their mean
        "trade_fraction": float(take.mean()),
        "cost_per_round_trip": cost,
    }
    if len(per_trade):
        out["avg_net_return_per_trade_bps"] = float(per_trade.mean() * 1e4)
        out["avg_gross_return_per_trade_bps"] = float((per_trade + cost).mean() * 1e4)
    return out
