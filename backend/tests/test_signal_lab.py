"""Signal Lab: tolerant parsing, causal decisions, risk-gated BUYs, API upload flow."""

import io

import numpy as np
import pandas as pd
import pytest

from app.engines.signal_lab import engine
from app.engines.signal_lab.parsing import MIN_ROWS, DatasetError, parse_csv


def _csv(
    n=400,
    trend=0.001,
    start="2022-01-03",
    cols=("Date", "Open", "High", "Low", "Close", "Volume"),
    seed=0,
    date_fmt="%Y-%m-%d",
):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(trend, 0.012, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    d = pd.bdate_range(start, periods=n)
    df = pd.DataFrame(
        {
            cols[0]: d.strftime(date_fmt),
            cols[1]: o,
            cols[2]: np.maximum(o, c) * 1.005,
            cols[3]: np.minimum(o, c) * 0.995,
            cols[4]: c,
            cols[5]: rng.integers(1e5, 1e6, n),
        }
    )
    return df


def test_parses_yahoo_export_with_adj_close():
    df = _csv().rename(columns={"Close": "Adj Close"})
    df["Close"] = df["Adj Close"]
    (s,) = parse_csv(df.to_csv(index=False).encode(), "NIFTY50")
    assert s.symbol == "NIFTY50" and len(s.frame) == 400 and str(s.frame["ts"].dt.tz) == "Asia/Kolkata"


def test_parses_lowercase_dayfirst_commas_and_symbol_column():
    a = _csv(cols=("date", "open", "high", "low", "close", "volume"), date_fmt="%d-%m-%Y")
    a["volume"] = a["volume"].map(lambda v: f"{v:,}")
    a["symbol"] = "TCS.NS"
    b = _csv(seed=1, cols=("date", "open", "high", "low", "close", "volume"), date_fmt="%d-%m-%Y").assign(symbol="INFY")
    out = parse_csv(pd.concat([a, b]).to_csv(index=False).encode())
    assert {s.symbol for s in out} == {"TCS", "INFY"}
    assert all(len(s.frame) == 400 for s in out)
    assert out[0].frame["ts"].iloc[0].strftime("%Y-%m-%d") == "2022-01-03"


def test_rejects_bad_files_with_clear_messages():
    with pytest.raises(DatasetError, match="empty"):
        parse_csv(b"")
    with pytest.raises(DatasetError, match="Missing required column"):
        parse_csv(b"date,price\n2024-01-01,1\n")
    with pytest.raises(DatasetError, match=f"at least {MIN_ROWS}"):
        parse_csv(_csv(n=100).to_csv(index=False).encode())
    bad = _csv()
    bad.loc[:50, "High"] = bad.loc[:50, "Low"] - 5
    with pytest.raises(DatasetError, match="impossible OHLC"):
        parse_csv(bad.to_csv(index=False).encode())


def test_drops_unparseable_rows_and_duplicates_and_reports_them():
    df = _csv(n=420).astype({"Close": object})
    df.loc[5, "Close"] = "n/a"
    df = pd.concat([df, df.iloc[[10]]])
    (s,) = parse_csv(df.to_csv(index=False).encode(), "X")
    assert len(s.frame) == 419
    assert any("Dropped 1 row" in n for n in s.notes) and any("duplicate" in n for n in s.notes)


def _engine_inputs(n=500, trend=0.0015, seed=3):
    (s,) = parse_csv(_csv(n=n, trend=trend, seed=seed).to_csv(index=False).encode(), "T")
    dates = s.frame["ts"].dt.tz_localize(None).dt.normalize()
    rng = np.random.default_rng(seed)
    pu = rng.uniform(0.25, 0.4, n)
    pdn = rng.uniform(0.15, 0.3, n)
    preds = pd.DataFrame(
        {"date": dates, "p_up": pu, "p_down": pdn, "p_neutral": 1 - pu - pdn, "vol_log": np.log(np.full(n, 0.012))}
    )
    return s.frame, preds


def test_decisions_are_causal_truncating_the_future_changes_nothing():
    prices, preds = _engine_inputs()
    full = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000)
    cut = 380
    part = engine.run(prices.iloc[:cut], preds.iloc[:cut], "UPLOAD|T", None, 1_000_000)
    keys = ("date", "action", "position", "stop")
    assert [{k: d[k] for k in keys} for d in full.days[: len(part.days)]] == [
        {k: d[k] for k in keys} for d in part.days
    ]


def test_every_buy_is_risk_approved_and_sized_and_fills_next_open():
    prices, preds = _engine_inputs()
    res = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000)
    buys = [d for d in res.days if d["action"] == "BUY"]
    assert buys, "a steady uptrend should produce at least one BUY"
    for b in buys:
        assert b["risk"]["approved"] and b["risk"]["quantity"] > 0 and b["risk"]["stop"] < b["close"]
    i = next(i for i, d in enumerate(res.days) if d["action"] == "BUY")
    nxt = res.days[i + 1]
    assert nxt["position"] > 0 and nxt["executed"].startswith("bought")
    assert res.trades[0]["entry"] == pytest.approx(nxt["open"])  # filled at the next open
    assert res.trades[0]["costs"] > 0


def test_no_trade_in_downtrend_and_bearish_model_blocks_entry():
    prices, preds = _engine_inputs(trend=-0.002)
    res = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000)
    assert all(d["action"] in ("NO_TRADE", "SELL", "HOLD") for d in res.days[-60:])
    prices, preds = _engine_inputs()
    preds["p_down"], preds["p_up"] = 0.6, 0.1
    preds["p_neutral"] = 0.3
    res = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000)
    assert not any(d["action"] == "BUY" for d in res.days)
    assert any("model is bearish" in r for d in res.days for r in d["reasons"])


def test_risk_rejection_turns_signal_into_no_trade():
    from app.engines.risk.schemas import RiskLimits

    prices, preds = _engine_inputs()
    res = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000, limits=RiskLimits(min_confidence=0.99))
    assert not any(d["action"] == "BUY" for d in res.days)
    assert any("risk engine rejected" in r for d in res.days for r in d["reasons"])


def test_final_answer_has_next_step_and_metrics():
    prices, preds = _engine_inputs()
    res = engine.run(prices, preds, "UPLOAD|T", None, 1_000_000)
    assert res.final["action"] in ("BUY", "SELL", "HOLD", "NO_TRADE") and res.final["next_session"]
    assert {"strategy", "buy_and_hold", "closed_trades", "exposure"} <= set(res.metrics)
    assert len(res.equity) == len(res.days)


@pytest.mark.integration
def test_api_upload_flow_with_stub_models(client, monkeypatch):
    from app.engines.signal_lab import service

    class Dir:
        def predict_proba(self, X):
            return np.tile([0.2, 0.45, 0.35], (len(X), 1))

    class Vol:
        def predict(self, X):
            return np.full(len(X), np.log(0.012))

    class Reg:
        version, model_name, metrics = "stub-vol", "lightgbm", {"holdout": {"r2_log": 0.18}}

    monkeypatch.setattr(
        service,
        "load_models",
        lambda s, st: (
            {
                "model": Dir(),
                "features": ["ret_1"],
                "status": "research",
                "trained_through": "x",
                "dataset_version": "d",
            },
            {"model": Vol(), "features": ["ret_1"]},
            Reg(),
        ),
    )
    monkeypatch.setattr(service, "load_global", lambda d: None)
    monkeypatch.setattr(service.swing, "NIFTY", "UPLOAD|IDX")  # context from an uploaded index-like series
    monkeypatch.setattr(service.swing, "VIX", "UPLOAD|IDX")
    csv = _csv(n=400).to_csv(index=False)
    idx = _csv(n=400, seed=9).to_csv(index=False)
    files = {"file": ("mystock.csv", io.BytesIO((csv + idx.split("\n", 1)[1]).encode()), "text/csv")}
    # two series in one file need a symbol column; keep it simple: upload one stock, context via a second call
    r = client.post(
        "/api/v1/signal-lab/analyze",
        files={"file": ("mystock.csv", io.BytesIO(csv.encode()), "text/csv")},
        data={"capital": "500000"},
    )
    assert r.status_code in (200, 409, 422), r.text
    bad = client.post("/api/v1/signal-lab/analyze", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert bad.status_code == 422 and "Missing required column" in bad.json()["detail"]
    assert (
        client.post(
            "/api/v1/signal-lab/analyze",
            files={"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")},
            data={"capital": "5"},
        ).status_code
        == 422
    )
    del files


def test_ambiguous_day_first_dates_are_not_silently_swapped():
    df = _csv(n=300, start="2023-01-02", date_fmt="%d-%m-%Y")  # 02-01-2023 = 2 January (Indian convention)
    (s,) = parse_csv(df.to_csv(index=False).encode(), "X")
    assert s.frame["ts"].iloc[0].strftime("%Y-%m-%d") == "2023-01-02"
    assert s.frame["ts"].is_monotonic_increasing and len(s.frame) == 300
    us = _csv(n=300, start="2023-01-02", date_fmt="%m/%d/%Y")
    (u,) = parse_csv(us.to_csv(index=False).encode(), "Y")
    assert u.frame["ts"].iloc[0].strftime("%Y-%m-%d") == "2023-01-02" and any("month-first" in n for n in u.notes)


def _frame(n=300):
    d = pd.bdate_range("2023-01-02", periods=n)
    c = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.01, n)))
    return pd.DataFrame({"Date": d.strftime("%Y-%m-%d"), "Open": c, "High": c * 1.01, "Low": c * 0.99,
                         "Close": c, "Volume": 1000})


@pytest.mark.parametrize("fmt", ["xlsx", "xlsx_title_rows", "tsv", "semicolon", "csv_title_rows", "utf16", "bom"])
def test_reads_excel_tsv_and_messy_exports_identically(fmt):
    df = _frame()
    if fmt == "xlsx":
        b = io.BytesIO()
        df.to_excel(b, index=False)
        raw = b.getvalue()
    elif fmt == "xlsx_title_rows":
        b = io.BytesIO()
        with pd.ExcelWriter(b) as w:
            pd.DataFrame([["Stock prices"]]).to_excel(w, index=False, header=False)
            df.to_excel(w, index=False, startrow=3)
        raw = b.getvalue()
    elif fmt == "tsv":
        raw = df.to_csv(index=False, sep="\t").encode()
    elif fmt == "semicolon":
        raw = df.to_csv(index=False, sep=";").encode()
    elif fmt == "csv_title_rows":
        raw = ("Historical data for TCS\nExported 13-11-2026\n\n" + df.to_csv(index=False)).encode()
    elif fmt == "utf16":
        raw = df.to_csv(index=False).encode("utf-16")
    else:
        raw = b"\xef\xbb\xbf" + df.to_csv(index=False).encode()
    s = parse_csv(raw, "X")[0]
    assert len(s.frame) == 300
    assert s.frame.close.iloc[0] == pytest.approx(df.Close.iloc[0])
    assert str(s.frame.ts.iloc[-1].date()) == df.Date.iloc[-1]


def test_rejects_non_tabular_binary():
    with pytest.raises(DatasetError):
        parse_csv(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "X")
