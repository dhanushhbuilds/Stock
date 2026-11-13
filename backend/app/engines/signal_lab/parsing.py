"""Parse and validate a user-supplied OHLCV dataset (CSV).

Accepts common layouts: lower/upper-case headers, `Date`/`Datetime`/`Timestamp`, Yahoo exports with `Adj Close`,
optional `Symbol`/`Ticker` column for multiple stocks, day-first or ISO dates. Nothing is filled or invented:
unusable rows are dropped and reported.
"""

import csv
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.engines.data.candles import IST, TIMEFRAMES
from app.engines.data.validation import validate

MIN_ROWS = 260  # 200-day indicators + warm-up
MAX_ROWS = 50_000
MAX_SYMBOLS = 10
ALIASES = {
    "ts": ("date", "datetime", "timestamp", "time", "day"),
    "open": ("open", "open price", "o"),
    "high": ("high", "high price", "h"),
    "low": ("low", "low price", "l"),
    "close": ("close", "close price", "last", "ltp", "c", "closing price"),
    "volume": ("volume", "vol", "total traded quantity", "qty", "shares traded", "v"),
    "symbol": ("symbol", "ticker", "tradingsymbol", "scrip", "stock"),
}


class DatasetError(ValueError):
    pass


@dataclass
class ParsedSeries:
    symbol: str
    frame: pd.DataFrame  # ts (IST midnight), open, high, low, close, volume, oi
    notes: list[str] = field(default_factory=list)
    quality: dict = field(default_factory=dict)


def _norm(c: str) -> str:
    return re.sub(r"[^a-z ]", "", str(c).strip().lower().replace("_", " ").replace(".", " ")).strip()


def _parse_dates(col: pd.Series, notes: list[str]) -> pd.Series:
    """ISO dates parse directly. For dd-mm-yyyy vs mm-dd-yyyy, try both and keep the order that parses every row
    in increasing order; if both fit (all days <= 12), use day-first (Indian convention) and say so."""
    text = col.astype(str).str.strip()
    if text.str.match(r"^\d{4}-\d{1,2}-\d{1,2}").mean() > 0.9:
        return pd.to_datetime(text, errors="coerce", format="mixed")
    day_first = pd.to_datetime(text, errors="coerce", dayfirst=True, format="mixed")
    month_first = pd.to_datetime(text, errors="coerce", dayfirst=False, format="mixed")

    def score(ts):
        ok = ts.notna()
        mono = ts[ok].is_monotonic_increasing or ts[ok].is_monotonic_decreasing
        return (ok.mean(), mono)

    sd, sm = score(day_first), score(month_first)
    if sm > sd:
        notes.append("Dates read as month-first (mm-dd-yyyy).")
        return month_first
    if sd == sm and text.str.match(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}").mean() > 0.9:
        notes.append("Dates were ambiguous; read as day-first (dd-mm-yyyy, Indian convention).")
    return day_first


def _locate_header(grid: pd.DataFrame) -> pd.DataFrame:
    """Broker/NSE exports often have title lines above the table: use the first row (within 15) that names a
    date column and a close column as the header."""
    for i in range(min(15, len(grid))):
        names = {_norm(v) for v in grid.iloc[i].tolist()}
        if names & set(ALIASES["ts"]) and names & set(ALIASES["close"] + ("adj close",)):
            out = grid.iloc[i + 1:].copy()
            out.columns = [str(c).strip() for c in grid.iloc[i].tolist()]
            return out.loc[:, [c for c in out.columns if c and c.lower() != "nan"]].reset_index(drop=True)
    if grid.empty:
        raise DatasetError("The file has no rows.")
    # No recognisable header: treat the first row as the header so validation names the missing column(s).
    out = grid.iloc[1:].copy()
    out.columns = [str(c).strip() for c in grid.iloc[0].tolist()]
    return out.reset_index(drop=True)


def read_table(raw: bytes) -> pd.DataFrame:
    """CSV / TSV / semicolon / Excel (.xlsx, .xls), detected from the file's bytes, not its name."""
    if not raw or not raw.strip():
        raise DatasetError("The file is empty.")
    try:
        if raw[:4] == b"PK\x03\x04":  # .xlsx (zip container)
            grid = pd.read_excel(io.BytesIO(raw), header=None, engine="openpyxl", dtype=str)
        elif raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # legacy .xls
            grid = pd.read_excel(io.BytesIO(raw), header=None, engine="xlrd", dtype=str)
        else:
            utf16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
            if not utf16 and b"\x00" in raw[:4096]:
                raise DatasetError("Unsupported file type: upload a CSV, TSV or Excel (.xlsx / .xls) file.")
            text = None
            for enc in (("utf-16",) if utf16 else ("utf-8-sig", "cp1252", "latin-1")):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise DatasetError("Unrecognised text encoding.")
            # Pick the delimiter that is most frequent on the busiest line (title lines above the table have
            # none), then read rows with the csv module so ragged preamble rows don't truncate the table.
            lines = [ln for ln in text.splitlines() if ln.strip()][:200]
            sep = max((",", "\t", ";", "|"), key=lambda d: max((ln.count(d) for ln in lines), default=0))
            rows = list(csv.reader(io.StringIO(text), delimiter=sep))
            width = max((len(r) for r in rows), default=0)
            grid = pd.DataFrame([r + [None] * (width - len(r)) for r in rows if any(c.strip() for c in r)])
    except DatasetError:
        raise
    except Exception as exc:
        raise DatasetError(f"Could not read the file as CSV or Excel ({type(exc).__name__}).") from exc
    return _locate_header(grid.dropna(how="all"))


def parse_csv(raw: bytes, default_symbol: str = "UPLOAD") -> list[ParsedSeries]:
    df = read_table(raw)
    if len(df) > MAX_ROWS:
        raise DatasetError(f"Too many rows ({len(df):,}); the limit is {MAX_ROWS:,}.")
    cols = {_norm(c): c for c in df.columns}
    if "adj close" in cols and "close" not in cols:
        cols["close"] = cols["adj close"]
    pick = {}
    for target, names in ALIASES.items():
        for n in names:
            if n in cols:
                pick[target] = cols[n]
                break
    missing = [k for k in ("ts", "open", "high", "low", "close") if k not in pick]
    if missing:
        raise DatasetError(
            f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(map(str, df.columns))}."
        )
    out = pd.DataFrame({k: df[v] for k, v in pick.items()})
    notes: list[str] = []
    ts = _parse_dates(out["ts"], notes)
    out["ts"] = ts
    if getattr(out["ts"].dt, "tz", None) is not None:
        out["ts"] = out["ts"].dt.tz_convert(IST).dt.tz_localize(None)
    for c in ("open", "high", "low", "close", "volume"):
        if c in out:
            out[c] = pd.to_numeric(out[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
    if "volume" not in out:
        out["volume"] = 0
        notes.append("No volume column: volume features are unavailable (treated as an index-like series).")
    bad = out[["ts", "open", "high", "low", "close"]].isna().any(axis=1)
    if bad.any():
        notes.append(f"Dropped {int(bad.sum())} row(s) with unparseable dates or prices.")
    out = out[~bad].copy()
    out["volume"] = out["volume"].fillna(0).clip(lower=0).round().astype("int64")
    if "symbol" not in out:
        out["symbol"] = default_symbol
    out["symbol"] = out["symbol"].astype(str).str.strip().str.upper().str.replace(r"\.NS$|\.BO$", "", regex=True)
    syms = out["symbol"].unique()
    if len(syms) > MAX_SYMBOLS:
        raise DatasetError(f"{len(syms)} symbols found; the limit is {MAX_SYMBOLS} per upload.")
    series = []
    for s in syms:
        g = out[out["symbol"] == s].copy()
        g["ts"] = g["ts"].dt.normalize()
        dups = int(g["ts"].duplicated().sum())
        g = g.drop_duplicates("ts", keep="last").sort_values("ts")
        local_notes = list(notes) + ([f"Removed {dups} duplicate date(s) (kept the last)."] if dups else [])
        if len(g) < MIN_ROWS:
            raise DatasetError(f"{s}: {len(g)} usable daily rows; at least {MIN_ROWS} are needed (200-day indicators).")
        frame = pd.DataFrame(
            {
                "ts": g["ts"].dt.tz_localize(IST),
                "open": g["open"].astype(float),
                "high": g["high"].astype(float),
                "low": g["low"].astype(float),
                "close": g["close"].astype(float),
                "volume": g["volume"],
                "oi": np.zeros(len(g), dtype="int64"),
            }
        ).reset_index(drop=True)
        rep = validate(frame, TIMEFRAMES["1day"], f"UPLOAD|{s}")
        if rep.errors.get("ohlc_violations", {}).get("count", 0) > len(frame) * 0.05:
            raise DatasetError(f"{s}: more than 5% of rows have impossible OHLC values (e.g. high < low).")
        series.append(ParsedSeries(s, frame, local_notes, rep.to_dict()))
    return series
