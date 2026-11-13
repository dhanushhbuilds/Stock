"""Markdown + JSON evaluation reports. Numbers are copied from computed results, never typed by hand."""

import json
from pathlib import Path


def _f(x, pct=False, nd=4):
    if x is None:
        return "—"
    return f"{x * 100:.2f}%" if pct else f"{x:.{nd}f}"


def write_report(out: dict, report_dir: Path, pipeline: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    base = report_dir / f"{pipeline}_{out['run_id']}"
    base.with_suffix(".json").write_text(json.dumps(out, indent=2, default=str))
    d = out["dataset"]
    L = [
        f"# {pipeline.title()} model evaluation — run {out['run_id']}",
        "",
        f"Dataset `{d['version']}`: {d['rows']:,} rows ({d['labelled_rows']:,} labelled), {d['symbols']} symbols, "
        f"{d['first_date']} → {d['last_date']}, {len(d['features'])} features.",
        f"Label distribution [DOWN, NEUTRAL, UP]: {d['label_distribution']}. Config: `{json.dumps(d['config'])}`.",
        f"Protocol: walk-forward from {d['protocol']['first_test']} in {d['protocol']['test_months']}-month test "
        f"windows, purged; locked holdout from {d['protocol']['holdout_start']}.",
        "",
        f"**Selected on walk-forward results only:** `{out['selected']}` (ranking: {', '.join(out['ranking'])}).",
        f"**Registry:** `{out['registered']['version']}` — promoted: **{out['registered']['promoted']}**",
        "",
    ]
    L += [f"- {r}" for r in out["registered"]["reasons"]]
    for part, key in (
        ("Walk-forward (out-of-sample, all folds pooled)", "walk_forward"),
        ("Locked holdout", "holdout"),
    ):
        L += [
            "",
            f"## {part}",
            "",
            "| model | acc | macro-F1 | log loss | prior log loss | Brier | ROC-AUC (OvR) | direction AUC | IC mean | IC t |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, r in out["results"].items():
            m = r[key]
            L.append(
                f"| {name} | {_f(m['accuracy'])} | {_f(m['macro_f1'])} | {_f(m['log_loss'])} | "
                f"{_f(m['baseline_prior']['log_loss'])} | {_f(m['brier'])} | {_f(m['roc_auc_ovr_macro'])} | "
                f"{_f(m.get('direction_auc'))} | {_f(m.get('ic_mean'))} | {_f(m.get('ic_t'), nd=2)} |"
            )
        L += [
            "",
            "Trading after costs:",
            "",
            "| model | total return | ann. return | Sharpe | Sortino | max DD | profit factor | win rate | trades |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        bench = None
        for name, r in out["results"].items():
            t = r[key]["trading"]
            s = t["strategy"]
            bench = t.get("benchmark_equal_weight", bench)
            L.append(
                f"| {name} | {_f(s.get('total_return'), True)} | {_f(s.get('annualized_return'), True)} | "
                f"{_f(s.get('sharpe'), nd=2)} | {_f(s.get('sortino'), nd=2)} | {_f(s.get('max_drawdown'), True)} | "
                f"{_f(s.get('profit_factor'), nd=2)} | {_f(s.get('win_rate'), True)} | {s.get('trades')} |"
            )
        lsd = {n: r[key]["trading"].get("long_short_gross_diagnostic") for n, r in out["results"].items()}
        if any(lsd.values()):
            L += [
                "",
                "Ranking diagnostic — top-10 minus bottom-10, gross, needs shorting (not a tradable cash strategy):",
                "",
                "| model | total | ann. | Sharpe | max DD |",
                "|---|---|---|---|---|",
            ]
            L += [
                f"| {n} | {_f(v.get('total_return'), True)} | {_f(v.get('annualized_return'), True)} | "
                f"{_f(v.get('sharpe'), nd=2)} | {_f(v.get('max_drawdown'), True)} |"
                for n, v in lsd.items()
                if v
            ]
            L.append("")
        if bench:
            L.append(
                f"| *benchmark: equal-weight universe* | {_f(bench.get('total_return'), True)} | "
                f"{_f(bench.get('annualized_return'), True)} | {_f(bench.get('sharpe'), nd=2)} | "
                f"{_f(bench.get('sortino'), nd=2)} | {_f(bench.get('max_drawdown'), True)} | "
                f"{_f(bench.get('profit_factor'), nd=2)} | {_f(bench.get('win_rate'), True)} | — |"
            )
    sel = out["results"][out["selected"]]
    L += [
        "",
        f"## Selected model per fold ({out['selected']})",
        "",
        "| test window | n | log loss | prior | direction AUC | best iter |",
        "|---|---|---|---|---|---|",
    ]
    for fr in sel["walk_forward"]["folds"]:
        m = fr["metrics"]
        L.append(
            f"| {fr['fold']['test_start']} → {fr['fold']['test_end']} | {m['n']} | {_f(m['log_loss'])} | "
            f"{_f(fr['baseline']['log_loss'])} | {_f(m.get('direction_auc'))} | {fr['best_iteration']} |"
        )
    ho = sel["holdout"]
    L += [
        "",
        "Holdout confusion matrix (rows = true DOWN/NEUTRAL/UP, cols = predicted):",
        "",
        "```",
        *[str(r) for r in ho["confusion_matrix"]],
        "```",
    ]
    base.with_suffix(".md").write_text("\n".join(L) + "\n")
    return base.with_suffix(".md")
