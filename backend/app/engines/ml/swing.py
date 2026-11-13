"""Swing pipeline: daily bars -> features at the close of day t -> label over the next 5 sessions."""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.engines.data.storage import CandleLake
from app.engines.ml import indicators as ind
from app.engines.ml.labels import make_labels

NIFTY = "NSE_INDEX|Nifty 50"
VIX = "NSE_INDEX|India VIX"


@dataclass(frozen=True)
class SwingConfig:
    horizon: int = 5
    label_c: float = 0.5
    # Round-trip delivery cost on a Rs 1 lakh position from the charge schedule (strategy/charges.py): ~0.39%.
    cost: float = 0.0039
    start: str = "2016-01-01"
    min_history: int = 200  # EMA200 warm-up
    # absolute: label on the stock's own forward return.
    # excess:   label on forward return minus the cross-sectional mean of the universe on that date
    #           (what a stock-selection model can realistically predict; Krauss et al. 2017, Gu et al. 2020).
    label_mode: str = "excess"
    train_universes: tuple[str, ...] = ("NIFTY50", "NIFTYNEXT50", "NIFTYMIDCAP100")
    # Replace stock-level features by their per-date percentile rank across the universe (market-level
    # context features are left raw). Uses only same-date cross-section, so no look-ahead.
    xs_rank_features: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _daily(lake: CandleLake, key: str) -> pd.DataFrame:
    df = lake.read("1day", key)
    df = df.assign(date=df["ts"].dt.tz_localize(None).dt.normalize()).set_index("date")
    return df[["open", "high", "low", "close", "volume"]]


def price_features(d: pd.DataFrame) -> pd.DataFrame:
    """Features of one instrument's daily bars, all causal."""
    c, h, lo, v = d["close"], d["high"], d["low"], d["volume"].astype("float64")
    f = pd.DataFrame(index=d.index)
    for n in (1, 2, 5, 10, 20, 60):
        f[f"ret_{n}"] = ind.log_ret(c, n)
    for n in (9, 20, 50, 200):
        f[f"dist_ema{n}"] = c / ind.ema(c, n) - 1
    for n in (20, 50):
        f[f"dist_sma{n}"] = c / ind.sma(c, n) - 1
    f["ema20_gt_ema50"] = (ind.ema(c, 20) > ind.ema(c, 50)).astype("float64")
    f["ema9_x_ema20"] = (
        np.sign(ind.ema(c, 9) - ind.ema(c, 20)).diff().fillna(0) / 2
    )  # +1 golden, -1 death cross
    f["rsi14"] = ind.rsi(c, 14)
    f["rsi2"] = ind.rsi(c, 2)
    m, s, hist = ind.macd(c)
    f["macd"], f["macd_sig"], f["macd_hist"] = m / c, s / c, hist / c
    f["roc10"] = ind.roc(c, 10)
    k, dd = ind.stochastic(h, lo, c)
    f["stoch_k"], f["stoch_d"] = k, dd
    f["atr14"] = ind.atr(h, lo, c) / c
    f["bb_pctb"], f["bb_width"] = ind.bollinger(c)
    f["vol20"] = ind.realized_vol(c, 20)
    f["vol60"] = ind.realized_vol(c, 60)
    f["vol_ratio_5_20"] = ind.realized_vol(c, 5) / f["vol20"]
    f["range"] = (h - lo) / c
    f["clv"] = ((c - lo) - (h - c)) / (h - lo).replace(0, np.nan)
    f["gap"] = d["open"] / c.shift(1) - 1
    f["dist_high20"] = c / h.rolling(20).max() - 1
    f["dist_low20"] = c / lo.rolling(20).min() - 1
    if v.sum() > 0:
        f["rel_vol20"] = v / v.rolling(20).mean()
        f["vol_mom_5_20"] = v.rolling(5).mean() / v.rolling(20).mean()
        f["pv_div"] = np.sign(f["ret_5"]) * -np.sign(
            np.log(f["vol_mom_5_20"])
        )  # +1 when price & volume diverge
        f["obv_slope"] = (np.sign(c.diff()) * v).rolling(20).sum() / v.rolling(20).sum()
    return f


def global_features(glob: pd.DataFrame, nse_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Global series returns on their own calendars, then as-of joined STRICTLY before each NSE date."""
    g = pd.DataFrame(index=glob.index)
    for col in ("SPX", "NDX", "N225", "HSI", "BRENT", "USDINR"):
        s = glob[col].dropna()
        g[f"g_{col.lower()}_r1"] = np.log(s / s.shift(1)).reindex(glob.index)
        g[f"g_{col.lower()}_r5"] = np.log(s / s.shift(5)).reindex(glob.index)
    v = glob["USVIX"].dropna()
    g["g_usvix"] = v.reindex(glob.index)
    g["g_usvix_chg5"] = (v / v.shift(5) - 1).reindex(glob.index)
    t = glob["US10Y"].dropna()
    g["g_us10y_chg5"] = (t - t.shift(5)).reindex(glob.index)
    g = g.ffill()  # carry last known value across a market's holidays (still only past information)
    g = g.reset_index(names="gdate").sort_values("gdate")
    g["gdate"] = g["gdate"].astype("datetime64[ns]")
    left = pd.DataFrame({"date": pd.DatetimeIndex(nse_dates).astype("datetime64[ns]")}).sort_values("date")
    out = pd.merge_asof(
        left, g, left_on="date", right_on="gdate", allow_exact_matches=False, direction="backward"
    )
    out["g_age_days"] = (out["date"] - out["gdate"]).dt.days
    return out.drop(columns="gdate").set_index("date")


def build_swing_dataset(
    lake: CandleLake, members: list[tuple], glob: pd.DataFrame | None, cfg: SwingConfig
) -> pd.DataFrame:
    """members: (symbol, instrument_key, sector_index_key[, in_eval_universe]). One row per (date, symbol).
    Stocks with in_eval_universe=False are used for training only (wider cross-section), never for evaluation."""
    nifty = _daily(lake, NIFTY)
    nf = price_features(nifty)[["ret_1", "ret_5", "ret_20", "dist_ema50", "vol20", "rsi14"]].add_prefix(
        "nifty_"
    )
    vix = _daily(lake, VIX)["close"]
    ctx = nf.join(
        pd.DataFrame(
            {
                "vix": vix,
                "vix_chg5": vix / vix.shift(5) - 1,
                "vix_z60": (vix - vix.rolling(60).mean()) / vix.rolling(60).std(),
            }
        )
    )
    if glob is not None:
        ctx = ctx.join(global_features(glob, ctx.index))
    sector_cache: dict[str, pd.DataFrame] = {}

    rows = []
    for mem in members:
        symbol, key, sector_key = mem[:3]
        in_eval = mem[3] if len(mem) > 3 else True
        d = _daily(lake, key)
        if len(d) < cfg.min_history + 30:
            continue
        f = price_features(d)
        f = f.join(ctx, how="left")
        f["rs_nifty_5"] = f["ret_5"] - f["nifty_ret_5"]
        f["rs_nifty_20"] = f["ret_20"] - f["nifty_ret_20"]
        r = ind.log_ret(d["close"])
        nr = ind.log_ret(nifty["close"]).reindex(d.index)
        f["beta60"] = r.rolling(60).cov(nr) / nr.rolling(60).var()
        if sector_key:
            if sector_key not in sector_cache:
                sd = _daily(lake, sector_key)
                sector_cache[sector_key] = pd.DataFrame(
                    {"sec_ret_5": ind.log_ret(sd["close"], 5), "sec_ret_20": ind.log_ret(sd["close"], 20)}
                )
            f = f.join(sector_cache[sector_key])
            f["rs_sector_5"] = f["ret_5"] - f["sec_ret_5"]
            f["rs_sector_20"] = f["ret_20"] - f["sec_ret_20"]
        f["dow"] = f.index.day_of_week.astype("float64")
        sigma = ind.realized_vol(d["close"], 20)
        lab = make_labels(d["close"], sigma, cfg.horizon, cfg.label_c, cfg.cost)
        f = f.join(lab)
        f["close"] = d["close"]
        f["symbol"], f["instrument_key"], f["eval_universe"] = symbol, key, in_eval
        f["bar_index"] = np.arange(len(f))
        f = f[f["bar_index"] >= cfg.min_history]
        rows.append(f[f.index >= pd.Timestamp(cfg.start)])

    ds = pd.concat(rows).reset_index(names="date")
    if cfg.label_mode == "excess":
        ds["fwd_ret_abs"] = ds["fwd_ret"]
        xs_mean = ds.groupby("date")["fwd_ret"].transform("mean")
        ds["fwd_ret"] = ds["fwd_ret"] - xs_mean
        tau = ds["tau"]
        ds["y"] = np.where(ds["fwd_ret"] > tau, 2, np.where(ds["fwd_ret"] < -tau, 0, 1)).astype("float64")
        ds.loc[ds["fwd_ret"].isna(), "y"] = np.nan
    # Cross-sectional ranks within each date (uses only same-date information across stocks).
    for col in ("ret_5", "ret_20", "ret_60", "rel_vol20", "vol20", "rsi14", "dist_ema50"):
        if col in ds:
            ds[f"xs_rank_{col}"] = ds.groupby("date")[col].rank(pct=True)
    if cfg.xs_rank_features:
        context = set(ctx.columns) | {"dow"}
        stock_cols = [c for c in feature_columns(ds) if c not in context and not c.startswith("xs_rank_")]
        ds[stock_cols] = ds.groupby("date")[stock_cols].rank(pct=True)
    return ds.sort_values(["date", "symbol"]).reset_index(drop=True)


META_COLS = [
    "date",
    "symbol",
    "instrument_key",
    "bar_index",
    "close",
    "fwd_ret",
    "fwd_ret_abs",
    "tau",
    "y",
    "eval_universe",
]


def feature_columns(ds: pd.DataFrame) -> list[str]:
    return [c for c in ds.columns if c not in META_COLS]
