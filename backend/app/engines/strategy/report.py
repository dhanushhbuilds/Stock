"""Markdown report from the strategy runner's JSON (numbers copied from computed results)."""

import json
import sys
from pathlib import Path


def _p(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def _n(x):
    return "—" if x is None else f"{x:.2f}"


def render(path: Path) -> Path:
    r = json.loads(path.read_text())
    meta = r.pop("_meta")
    bench = {k: r.pop(k) for k in [k for k in r if k.startswith("_benchmark")]}
    for v in [*r.values(), *bench.values()]:
        v.pop("equity_curve_weekly", None)
    L = [
        f"# Strategy backtests — {meta['run_date']}",
        "",
        f"Universe: {meta['symbols']} current NIFTY 50 stocks, Rs {meta['capital']:,.0f} split equally "
        f"(Rs {meta['capital'] / meta['symbols']:,.0f} per stock). Long-only. Signals at close, executed next open; "
        "2xATR stop on every trade; intraday flat by 15:10.",
        "Costs: full NSE/Upstox charge schedule + 5 bp slippage per side (round trip on Rs 1 lakh: delivery "
        "~0.39%, intraday ~0.18%). Parameters are textbook defaults chosen before testing (no optimisation).",
        "",
    ]
    for period in ("in_sample", "out_of_sample"):
        a, b = meta["periods"][period]
        L += [
            f"## {period.replace('_', '-')} ({a} → {b})",
            "",
            "| strategy | tf | total | ann. | Sharpe | Sortino | max DD | PF | win | trades | avg net/trade | costs / gross profit |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        rows = sorted(
            ((k, v) for k, v in r.items() if period in v),
            key=lambda kv: -(kv[1][period].get("sharpe") or -99),
        )
        for k, v in rows:
            s = v[period]
            L.append(
                f"| {k} | {v['timeframe']} | {_p(s.get('total_return'))} | {_p(s.get('annualized_return'))} | "
                f"{_n(s.get('sharpe'))} | {_n(s.get('sortino'))} | {_p(s.get('max_drawdown'))} | "
                f"{_n(s.get('profit_factor'))} | {_p(s.get('win_rate'))} | {s.get('trades')} | "
                f"{_p(s.get('avg_trade_net_pct'))} | {_n(s.get('costs_pct_of_gross_profit'))} |"
            )
        for name, bv in bench.items():
            s = bv.get(period, {})
            L.append(
                f"| *{name.strip('_').replace('_', ' ')}* | 1day | {_p(s.get('total_return'))} | "
                f"{_p(s.get('annualized_return'))} | {_n(s.get('sharpe'))} | {_n(s.get('sortino'))} | "
                f"{_p(s.get('max_drawdown'))} | {_n(s.get('profit_factor'))} | — | — | — | — |"
            )
        L.append("")
    L += [
        "## Out-of-sample trades by market regime at entry (trend / India VIX percentile)",
        "",
        "| strategy | regime | trades | win rate | avg net return |",
        "|---|---|---|---|---|",
    ]
    for k, v in r.items():
        for reg, g in sorted(v.get("regimes_oos", {}).items()):
            L.append(
                f"| {k} | {reg} | {g['trades']} | {_p(g['win_rate'])} | {g['avg_net_return_pct']:.2f}% |"
            )
    L += [
        "",
        "## Caveats",
        "",
        *[f"- {n}" for n in meta["notes"]],
        "- Intraday results include every order's brokerage and STT; high-turnover rules are dominated by costs.",
    ]
    out = path.with_suffix(".md")
    out.write_text("\n".join(L) + "\n")
    return out


if __name__ == "__main__":
    print(render(Path(sys.argv[1])))
