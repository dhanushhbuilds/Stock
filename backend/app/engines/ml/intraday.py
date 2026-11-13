"""Intraday pipeline: 5-minute bars -> features at a bar close -> label over the next 30 minutes (6 bars).

Session handling (see ARCHITECTURE.md §4a): only bars starting 09:15-15:10 are used. Since 2026-08-03 the
15:15-15:28 bars are closing-auction placeholders, so every feature and label lives inside continuous
trading in both regimes. Decisions are taken at bar closes 09:45, 10:00, ..., 14:45 (every 15 minutes);
the 30-minute label therefore ends at or before 15:15.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.engines.data.storage import CandleLake
from app.engines.ml import indicators as ind
from app.engines.ml.swing import NIFTY, VIX, global_features

SEQ_FEATURES = [
    "r1",
    "r3",
    "r6",
    "vwap_dist",
    "rsi14",
    "macd_hist",
    "atr14",
    "rel_vol_tod",
    "ret_day",
    "n_r1",
    "n_r6",
    "tod",
    "dist_or_high",
    "dist_or_low",
]


@dataclass(frozen=True)
class IntradayConfig:
    horizon_bars: int = 6  # 30 minutes
    label_c: float = 0.5
    # Round-trip intraday cost on a Rs 1 lakh position from the charge schedule (strategy/charges.py): ~0.18%
    # (brokerage 2 x Rs 20, STT 0.025% sell, exchange/GST/stamp, slippage 5 bp per side).
    cost: float = 0.0018
    first_bar: str = "09:15"
    last_bar: str = "15:10"
    decision_from: str = "09:40"  # bar START times (close = +5 min)
    decision_to: str = "14:40"
    decision_every_min: int = 15
    start: str = "2022-01-01"

    def to_dict(self) -> dict:
        return asdict(self)


def _five_min(lake: CandleLake, key: str, cfg: IntradayConfig) -> pd.DataFrame:
    df = lake.read("5minute", key)
    if df.empty:
        return df
    df = df.assign(ts=df["ts"].dt.tz_localize(None))
    hm = df["ts"].dt.strftime("%H:%M")
    df = df[(hm >= cfg.first_bar) & (hm <= cfg.last_bar)].copy()
    df["date"] = df["ts"].dt.normalize()
    # Regular sessions only, decided with information available at the open (no full-day bar count):
    # weekday AND the session's first bar is 09:15. Excludes Muhurat (evening / 13:45 starts) and weekend
    # special sessions. Using the whole day's bar count here would be look-ahead (caught by
    # test_intraday_features_do_not_use_future).
    first = df.groupby("date")["ts"].transform("min").dt.strftime("%H:%M")
    regular = (first == cfg.first_bar) & (df["ts"].dt.day_of_week < 5)
    return df[regular].reset_index(drop=True)


def _asof_before(left_dates: pd.Series, daily: pd.DataFrame) -> pd.DataFrame:
    """For each session date D, the latest daily row dated strictly before D. Works identically in history and
    live (where today's daily bar does not exist yet) -- a plain shift(1) would not."""
    right = daily.reset_index(names="ddate").assign(ddate=lambda x: x["ddate"].astype("datetime64[ns]"))
    left = pd.DataFrame({"date": pd.to_datetime(left_dates).astype("datetime64[ns]").unique()})
    out = pd.merge_asof(
        left.sort_values("date"),
        right.sort_values("ddate"),
        left_on="date",
        right_on="ddate",
        allow_exact_matches=False,
        direction="backward",
    )
    return out.drop(columns="ddate").set_index("date")


def _daily_context(lake: CandleLake, key: str) -> pd.DataFrame:
    """Daily features of each session (to be joined as-of strictly BEFORE the intraday session date)."""
    d = lake.read("1day", key)
    d = d.assign(date=d["ts"].dt.tz_localize(None).dt.normalize()).set_index("date")
    c = d["close"]
    f = pd.DataFrame(
        {
            "pd_close": c,
            "pd_high": d["high"],
            "pd_low": d["low"],
            "d_rsi14": ind.rsi(c, 14),
            "d_ret5": ind.log_ret(c, 5),
            "d_dist_ema20": c / ind.ema(c, 20) - 1,
            "d_vol20": ind.realized_vol(c, 20),
        }
    )
    return f


def bar_features(b: pd.DataFrame) -> pd.DataFrame:
    """b: one instrument's filtered 5-minute bars (continuous across days, sorted)."""
    c, h, lo, v = b["close"], b["high"], b["low"], b["volume"].astype("float64")
    f = pd.DataFrame(index=b.index)
    for n in (1, 3, 6, 12):
        f[f"r{n}"] = ind.log_ret(c, n)
    f["dist_ema9"] = c / ind.ema(c, 9) - 1
    f["dist_ema20"] = c / ind.ema(c, 20) - 1
    f["rsi14"] = ind.rsi(c, 14)
    _, _, hist = ind.macd(c)
    f["macd_hist"] = hist / c
    f["atr14"] = ind.atr(h, lo, c) / c
    f["bb_pctb"], f["bb_width"] = ind.bollinger(c)
    f["range"] = (h - lo) / c
    day = b["date"]
    g = b.groupby(day)
    tp = (h + lo + c) / 3
    cum_v = (v).groupby(day).cumsum()
    f["vwap_dist"] = c / ((tp * v).groupby(day).cumsum() / cum_v.replace(0, np.nan)) - 1
    slot = b["ts"].dt.strftime("%H:%M")
    hist_v = v.groupby(slot).transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    f["rel_vol_tod"] = v / hist_v
    f["vol_mom"] = v.rolling(3).mean() / v.rolling(12).mean()
    day_open = g["open"].transform("first")
    f["ret_day"] = c / day_open - 1
    first6 = b["ts"].dt.strftime("%H:%M") <= "09:40"
    orh = h.where(first6).groupby(day).transform("max")
    orl = lo.where(first6).groupby(day).transform("min")
    after_or = b["ts"].dt.strftime("%H:%M") >= "09:40"  # OR complete at the 09:40 bar's close
    f["dist_or_high"] = (c / orh - 1).where(after_or)
    f["dist_or_low"] = (c / orl - 1).where(after_or)
    f["day_vol_sofar"] = f["r1"].groupby(day).transform(lambda s: s.expanding(min_periods=3).std())
    f["tod"] = (b["ts"].dt.hour * 60 + b["ts"].dt.minute - (9 * 60 + 15)).astype("float64")
    f["_day_open"] = day_open
    return f


def build_intraday_dataset(
    lake: CandleLake, members: list[tuple], glob: pd.DataFrame | None, cfg: IntradayConfig
) -> pd.DataFrame:
    nb = _five_min(lake, NIFTY, cfg)
    nf = bar_features(nb)
    nifty = pd.DataFrame(
        {"ts": nb["ts"], "n_r1": nf["r1"], "n_r6": nf["r6"], "n_ret_day": nf["ret_day"]}
    )  # index has no volume -> no VWAP
    vix = lake.read("1day", VIX)
    vix = vix.assign(date=vix["ts"].dt.tz_localize(None).dt.normalize()).set_index("date")["close"]
    nd = lake.read("1day", NIFTY)
    nd = nd.assign(date=nd["ts"].dt.tz_localize(None).dt.normalize()).set_index("date")["close"]
    dctx = pd.DataFrame(
        {
            "vix_prev": vix,
            "vix_chg5_prev": vix / vix.shift(5) - 1,
            "nifty_d_ret1_prev": np.log(nd / nd.shift(1)),
            "nifty_d_ret5_prev": np.log(nd / nd.shift(5)),
        }
    )
    session_dates = pd.DatetimeIndex(sorted(nb["date"].unique()))
    dctx = _asof_before(pd.Series(session_dates), dctx)
    if glob is not None:
        gf = global_features(glob, session_dates)[
            ["g_spx_r1", "g_ndx_r1", "g_usvix", "g_usdinr_r1", "g_brent_r1", "g_n225_r1", "g_hsi_r1"]
        ]
        dctx = dctx.join(gf)

    frames = []
    for mem in members:
        symbol, key = mem[0], mem[1]
        b = _five_min(lake, key, cfg)
        if len(b) < 1000:
            continue
        f = bar_features(b)
        f["ts"], f["date"], f["close"] = b["ts"], b["date"], b["close"]
        f = f.merge(
            _asof_before(f["date"], _daily_context(lake, key)), left_on="date", right_index=True, how="left"
        )
        f["gap"] = f["_day_open"] / f["pd_close"] - 1
        f["dist_pdh"] = f["close"] / f["pd_high"] - 1
        f["dist_pdl"] = f["close"] / f["pd_low"] - 1
        # Label: close exactly 30 minutes after the decision bar's close (bar start + 30 min), same session.
        by_ts = f.set_index("ts")["close"]
        fwd_close = by_ts.reindex(f["ts"] + pd.Timedelta(minutes=5 * cfg.horizon_bars)).to_numpy()
        sigma = ind.log_ret(f["close"]).rolling(75, min_periods=40).std()
        fwd = fwd_close / f["close"].to_numpy() - 1
        tau = np.maximum(cfg.label_c * sigma.to_numpy() * np.sqrt(cfg.horizon_bars), cfg.cost)
        y = np.where(fwd > tau, 2.0, np.where(fwd < -tau, 0.0, 1.0))
        y[np.isnan(fwd) | np.isnan(tau)] = np.nan
        f["fwd_ret"], f["tau"], f["y"] = fwd, tau, y
        hm = f["ts"].dt.strftime("%H:%M")
        mins = f["ts"].dt.hour * 60 + f["ts"].dt.minute
        start_min = int(cfg.decision_from[:2]) * 60 + int(cfg.decision_from[3:])
        keep = (
            (hm >= cfg.decision_from)
            & (hm <= cfg.decision_to)
            & ((mins - start_min) % cfg.decision_every_min == 0)
        )
        f = f[keep & (f["date"] >= pd.Timestamp(cfg.start))]
        f["symbol"], f["instrument_key"] = symbol, key
        frames.append(f)

    ds = pd.concat(frames, ignore_index=True)
    ds = ds.merge(nifty, on="ts", how="left").merge(dctx, left_on="date", right_index=True, how="left")
    ds["rs_r6"] = ds["r6"] - ds["n_r6"]
    ds["rs_day"] = ds["ret_day"] - ds["n_ret_day"]
    for col in ("r6", "ret_day", "vwap_dist", "rel_vol_tod", "rsi14"):
        ds[f"xs_rank_{col}"] = ds.groupby("ts")[col].rank(pct=True)
    ds = ds.drop(columns=["_day_open", "pd_close", "pd_high", "pd_low"])
    float_cols = ds.select_dtypes("float64").columns.difference(["fwd_ret", "tau", "y", "close"])
    ds[float_cols] = ds[float_cols].astype("float32")
    return ds.sort_values(["ts", "symbol"]).reset_index(drop=True)


META_COLS = ["ts", "date", "symbol", "instrument_key", "close", "fwd_ret", "tau", "y"]


def feature_columns(ds: pd.DataFrame) -> list[str]:
    return [c for c in ds.columns if c not in META_COLS]
