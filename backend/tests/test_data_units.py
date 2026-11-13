"""Pure unit tests for the data engine (no DB, no network)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import pytest

from app.engines.data.candles import TIMEFRAMES, Timeframe, normalize_daily, parse_candles, plan_chunks
from app.engines.data.ratelimit import MultiWindowLimiter
from app.engines.data.storage import CandleLake, aggregate
from app.engines.data.upstox.auth import token_expiry
from app.engines.data.upstox.client import (
    UpstoxAuthError,
    UpstoxClient,
    UpstoxRequestError,
    UpstoxUnavailable,
)
from app.engines.data.validation import validate
from tests.fixtures.upstox_fake import FakeUpstox, minute_candles

IST = ZoneInfo("Asia/Kolkata")
M1, D1 = TIMEFRAMES["1minute"], TIMEFRAMES["1day"]


# ---------- planner ----------


def test_minute_chunks_are_calendar_months():
    ch = plan_chunks(M1, date(2022, 1, 10), date(2022, 3, 15))
    assert ch == [
        (date(2022, 1, 10), date(2022, 1, 31)),
        (date(2022, 2, 1), date(2022, 2, 28)),
        (date(2022, 3, 1), date(2022, 3, 15)),
    ]


def test_minute_start_clamped_to_provider_history():
    assert plan_chunks(M1, date(2019, 5, 1), date(2022, 1, 20)) == [(date(2022, 1, 1), date(2022, 1, 20))]


def test_minute_chunks_cover_range_without_gaps_or_overlap():
    ch = plan_chunks(M1, date(2022, 1, 1), date(2026, 11, 12))
    assert len(ch) == 59
    for (_, b1), (a2, _) in zip(ch, ch[1:], strict=False):
        assert a2 == b1 + timedelta(days=1)
    assert all(a.month == b.month and a.year == b.year for a, b in ch)


def test_thirty_minute_uses_quarters():
    tf = Timeframe("30minute", "minutes", 30)
    assert plan_chunks(tf, date(2023, 2, 1), date(2023, 7, 1)) == [
        (date(2023, 2, 1), date(2023, 3, 31)),
        (date(2023, 4, 1), date(2023, 6, 30)),
        (date(2023, 7, 1), date(2023, 7, 1)),
    ]


def test_daily_chunks_at_most_a_decade():
    # This exact split was accepted by the live Upstox API on 2026-11-13.
    assert plan_chunks(D1, date(2016, 1, 1), date(2026, 11, 12)) == [
        (date(2016, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 11, 12)),
    ]


def test_daily_leap_day_start():
    assert plan_chunks(D1, date(2016, 2, 29), date(2030, 1, 1))[0] == (date(2016, 2, 29), date(2026, 2, 28))


def test_empty_plan_when_start_after_end():
    assert plan_chunks(M1, date(2024, 2, 1), date(2024, 1, 1)) == []


# ---------- rate limiter ----------


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_limiter_blocks_when_window_full():
    c = FakeClock()
    lim = MultiWindowLimiter([(3, 1.0)], clock=c.now, sleep=c.sleep)
    for _ in range(3):
        lim.acquire()
    assert c.sleeps == []
    lim.acquire()
    assert c.sleeps == [pytest.approx(1.0)]


def test_limiter_enforces_every_window():
    c = FakeClock()
    lim = MultiWindowLimiter([(100, 1.0), (5, 60.0)], clock=c.now, sleep=c.sleep)
    for _ in range(6):
        lim.acquire()
    assert sum(c.sleeps) == pytest.approx(60.0)


# ---------- client ----------


def _client(handler, token=None, retries=3):
    slept = []
    cl = UpstoxClient(
        "https://api.upstox.com",
        MultiWindowLimiter([(1000, 1.0)]),
        token_provider=lambda: token,
        transport=httpx.MockTransport(handler),
        max_retries=retries,
        sleep=slept.append,
    )
    return cl, slept


def test_client_encodes_key_and_parses():
    fake = FakeUpstox()
    cl, _ = _client(fake)
    rows = cl.historical_candles("NSE_EQ|INE002A01018", "minutes", 1, date(2024, 6, 25), date(2024, 6, 25))
    assert len(rows) == 375
    assert (
        fake.requests[0]
        .url.raw_path.decode()
        .startswith("/v3/historical-candle/NSE_EQ%7CINE002A01018/minutes/1/")
    )
    assert "authorization" not in fake.requests[0].headers


def test_client_sends_bearer_when_token_available():
    fake = FakeUpstox()
    cl, _ = _client(fake, token="tok")
    cl.historical_candles("NSE_EQ|X", "days", 1, date(2024, 1, 2), date(2024, 1, 1))
    assert fake.requests[0].headers["authorization"] == "Bearer tok"


def test_client_retries_429_with_retry_after():
    calls = []

    def h(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "2"})
        return httpx.Response(200, json={"status": "success", "data": {"candles": []}})

    cl, slept = _client(h)
    assert cl.historical_candles("K|1", "days", 1, date(2024, 1, 2), date(2024, 1, 1)) == []
    assert slept == [2.0] and cl.retries == 1


def test_client_gives_up_after_max_retries():
    cl, slept = _client(lambda r: httpx.Response(503), retries=3)
    with pytest.raises(UpstoxUnavailable):
        cl.historical_candles("K|1", "days", 1, date(2024, 1, 2), date(2024, 1, 1))
    assert cl.requests_made == 4 and len(slept) == 3
    assert all(slept[i] <= slept[i + 1] * 2 for i in range(len(slept) - 1))


def test_client_retries_network_errors():
    calls = []

    def h(req):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"status": "success", "data": {"candles": []}})

    cl, _ = _client(h)
    cl.historical_candles("K|1", "days", 1, date(2024, 1, 2), date(2024, 1, 1))
    assert len(calls) == 3


def test_client_does_not_retry_validation_error():
    fake = FakeUpstox()
    cl, slept = _client(fake)
    with pytest.raises(UpstoxRequestError) as ei:
        cl.historical_candles("K|1", "minutes", 1, date(2022, 3, 15), date(2022, 1, 1))
    assert ei.value.codes == ["UDAPI1148"] and slept == [] and len(fake.requests) == 1


def test_client_auth_error_not_retried():
    cl, slept = _client(lambda r: httpx.Response(401))
    with pytest.raises(UpstoxAuthError):
        cl.historical_candles("K|1", "days", 1, date(2024, 1, 2), date(2024, 1, 1))
    assert slept == []


# ---------- parsing ----------


def test_parse_sorts_ascending_and_types():
    df = parse_candles(minute_candles(date(2024, 6, 25)))
    assert df["ts"].is_monotonic_increasing and len(df) == 375
    assert str(df["ts"].dt.tz) == "Asia/Kolkata"
    assert df["ts"].iloc[0] == pd.Timestamp("2024-06-25 09:15", tz=IST)
    assert df["volume"].dtype == "int64" and df["close"].dtype == "float64"


def test_parse_rejects_malformed_rows():
    with pytest.raises(ValueError, match="7 fields"):
        parse_candles([["2024-01-01T09:15:00+05:30", 1, 2, 3]])


def test_parse_empty():
    assert parse_candles([]).empty


def test_normalize_daily_counts_changes():
    df = parse_candles(
        [
            ["2017-01-02T09:15:00+05:30", 1, 2, 0.5, 1.5, 10, 0],
            ["2017-01-03T00:00:00+05:30", 1, 2, 0.5, 1.5, 10, 0],
        ]
    )
    out, n = normalize_daily(df)
    assert n == 1 and (out["ts"].dt.time == datetime.min.time()).all()


# ---------- validation ----------


def _day(d=date(2024, 6, 25)):
    return parse_candles(minute_candles(d))


def test_clean_day_passes():
    rep = validate(_day(), M1, "K")
    assert rep.passed and rep.warnings == {} and rep.trading_days == 1


def test_identical_duplicates_warn_conflicting_fail():
    df = _day()
    rep = validate(pd.concat([df, df.iloc[[10]]]).sort_values("ts", kind="stable"), M1, "K")
    assert rep.passed and rep.warnings["duplicate_timestamps"] == 1
    bad = df.iloc[[10]].assign(close=df.iloc[10]["close"] + 1)
    rep = validate(pd.concat([df, bad]).sort_values("ts", kind="stable"), M1, "K")
    assert not rep.passed and rep.errors["conflicting_duplicates"] == 1


def test_unsorted_input_is_error():
    df = _day()
    assert validate(df.iloc[::-1], M1, "K").errors["non_monotonic"] is True


def test_ohlc_violation_is_error():
    df = _day()
    df.loc[100, "high"] = df.loc[100, "low"] - 1
    rep = validate(df, M1, "K")
    assert rep.errors["ohlc_violations"]["count"] == 1


def test_open_outside_range_first_bar_warns_elsewhere_errors():
    df = _day()
    df.loc[0, "open"] = df.loc[0, "low"] - 2  # pre-open auction price
    rep = validate(df, M1, "K")
    assert rep.passed and rep.warnings["open_outside_range_at_session_open"]["count"] == 1
    df.loc[200, "open"] = df.loc[200, "high"] + 2
    assert validate(df, M1, "K").errors["ohlc_violations"]["count"] == 1


def test_nonpositive_price_is_error():
    df = _day()
    df.loc[5, ["open", "low"]] = 0.0
    assert not validate(df, M1, "K").passed


def test_bar_outside_session_on_normal_day_is_error():
    df = _day()
    extra = df.iloc[[0]].assign(ts=pd.Timestamp("2024-06-25 16:00", tz=IST))
    rep = validate(pd.concat([df, extra]).sort_values("ts"), M1, "K")
    assert rep.errors["bars_outside_session"]["count"] == 1


def test_evening_only_day_is_special_session_not_error():
    df = _day()
    special = df.iloc[:60].assign(ts=pd.date_range("2024-11-01 18:00", periods=60, freq="1min", tz=IST))
    rep = validate(pd.concat([df, special]), M1, "K")
    assert rep.passed and rep.info["special_session_days"] == ["2024-11-01"]


def test_missing_bars_reported_not_filled():
    df = _day().drop(index=[50, 51, 52]).reset_index(drop=True)
    rep = validate(df, M1, "K")
    assert rep.passed and rep.rows == 372
    assert rep.warnings["incomplete_days"] == {
        "count": 1,
        "missing_bars": 3,
        "pct_missing": 0.8,
        "worst": {"2024-06-25": 372},
    }


def test_short_session_classified_as_info():
    rep = validate(_day().iloc[:70], M1, "K")
    assert rep.info["short_sessions"] == {"2024-06-25": 70} and "incomplete_days" not in rep.warnings


def test_misaligned_timestamp_is_error():
    df = _day()
    df.loc[3, "ts"] = df.loc[3, "ts"] + pd.Timedelta(seconds=30)
    assert "misaligned_timestamps" in validate(df, M1, "K").errors


def test_daily_extreme_move_and_calendar_gaps():
    rows = [[f"2024-01-0{d}T00:00:00+05:30", 100, 101, 99, 100, 1, 0] for d in (1, 2, 3)]
    rows.append(["2024-01-05T00:00:00+05:30", 150, 151, 149, 150, 1, 0])
    cal = {date(2024, 1, d) for d in (1, 2, 3, 4, 5)}
    rep = validate(parse_candles(rows), D1, "K", calendar=cal)
    assert rep.warnings["extreme_daily_moves"] == [{"date": "2024-01-05", "abs_return": 0.5}]
    assert rep.warnings["missing_trading_days"]["examples"] == ["2024-01-04"]


def test_daily_non_midnight_is_error():
    rep = validate(parse_candles([["2017-01-02T09:15:00+05:30", 1, 2, 0.5, 1.5, 10, 0]]), D1, "K")
    assert rep.errors["daily_timestamp_not_midnight"] == 1


def test_empty_frame_fails():
    assert not validate(parse_candles([]), M1, "K").passed


# ---------- storage + aggregation ----------


def test_lake_roundtrip_merge_and_atomicity(tmp_path):
    lake = CandleLake(tmp_path)
    a = _day(date(2024, 12, 31))
    b = _day(date(2025, 1, 1))
    lake.write(a, "1minute", "NSE_EQ|X")
    lake.write(pd.concat([a.tail(10), b]), "1minute", "NSE_EQ|X")  # overlapping write
    out = lake.read("1minute", "NSE_EQ|X")
    assert len(out) == 750 and out["ts"].is_unique and out["ts"].is_monotonic_increasing
    pd.testing.assert_frame_equal(out.iloc[:375].reset_index(drop=True), a.reset_index(drop=True))
    assert [p.name for p in lake.files("1minute", "NSE_EQ|X")] == ["2024.parquet", "2025.parquet"]
    assert not list(tmp_path.rglob("*.tmp"))


def test_lake_later_write_wins(tmp_path):
    lake = CandleLake(tmp_path)
    a = _day()
    lake.write(a, "1minute", "K|1")
    lake.write(a.assign(close=a["close"] + 1), "1minute", "K|1")
    assert (lake.read("1minute", "K|1")["close"] == a["close"] + 1).all()


def test_lake_read_range_accepts_naive_and_aware(tmp_path):
    lake = CandleLake(tmp_path)
    lake.write(_day(), "1minute", "K|1")
    naive = lake.read("1minute", "K|1", start="2024-06-25 10:00", end="2024-06-25 10:04")
    aware = lake.read(
        "1minute",
        "K|1",
        start=pd.Timestamp("2024-06-25 10:00", tz=IST),
        end=pd.Timestamp("2024-06-25 04:34", tz="UTC"),
    )
    assert len(naive) == 5 and len(aware) == 5


def test_aggregate_5m_matches_hand_calculation():
    df = _day()
    agg = aggregate(df, 5)
    assert len(agg) == 75 and (agg["n_bars"] == 5).all()
    first5 = df.iloc[:5]
    r = agg.iloc[0]
    assert r["ts"] == pd.Timestamp("2024-06-25 09:15", tz=IST)
    assert (r["open"], r["high"], r["low"], r["close"], r["volume"]) == (
        first5["open"].iloc[0],
        first5["high"].max(),
        first5["low"].min(),
        first5["close"].iloc[-1],
        first5["volume"].sum(),
    )
    assert agg.iloc[-1]["ts"] == pd.Timestamp("2024-06-25 15:25", tz=IST)


def test_aggregate_marks_partial_buckets():
    agg = aggregate(_day().drop(index=[7]), 5)
    assert agg.loc[agg["ts"] == pd.Timestamp("2024-06-25 09:20", tz=IST), "n_bars"].item() == 4


# ---------- token expiry (per Upstox docs) ----------


@pytest.mark.parametrize(
    "issued,expected",
    [
        ("2026-11-13 20:00", "2026-11-14 03:30"),  # evening -> next day 03:30
        ("2026-11-13 02:30", "2026-11-13 03:30"),  # before cutoff -> same day 03:30
        ("2026-11-13 03:30", "2026-11-14 03:30"),  # exactly at cutoff -> next day
    ],
)
def test_token_expiry(issued, expected):
    got = token_expiry(pd.Timestamp(issued, tz=IST).to_pydatetime())
    assert got == pd.Timestamp(expected, tz=IST).to_pydatetime()


def test_closing_auction_pattern_detected():
    df = _day()
    late = df["ts"].dt.strftime("%H:%M").between("15:15", "15:28")
    px = df.loc[late, "open"].iloc[0]
    df.loc[late, ["open", "high", "low", "close", "volume"]] = [px, px, px, px, 0]
    rep = validate(df, M1, "NSE_EQ|X")
    assert rep.passed and rep.info["closing_auction_pattern"] == {
        "days": 1,
        "first": "2024-06-25",
        "last": "2024-06-25",
    }
    assert "closing_auction_pattern" not in validate(_day(), M1, "NSE_EQ|X").info
    assert "closing_auction_pattern" not in validate(df, M1, "NSE_INDEX|X", is_index=True).info


# ---------- discontinuity registry (unadjusted demergers / index rebases) ----------


def test_adjust_prices_back_adjusts_only_before_event(tmp_path):
    from app.engines.data.storage import adjust_prices

    rows = [[f"2025-10-{d:02d}T00:00:00+05:30", 660.0, 670.0, 650.0, 660.75, 1000, 0] for d in (9, 10, 13)]
    rows.append(["2025-10-14T00:00:00+05:30", 400.0, 421.0, 376.0, 395.45, 5000, 0])
    df = parse_candles(rows)
    adj = adjust_prices(df, [(pd.Timestamp("2025-10-14", tz=IST), 0.605070)])
    assert adj["close"].iloc[2] == pytest.approx(660.75 * 0.605070)
    assert adj["close"].iloc[3] == 395.45 and adj["volume"].iloc[3] == 5000  # event day untouched
    assert adj["volume"].iloc[0] == round(1000 / 0.605070)
    ret = adj["close"].pct_change().iloc[3]
    assert abs(ret) < 0.05  # the fake -40% "return" is gone
    assert df["close"].iloc[2] == 660.75  # input not mutated


def test_lake_read_adjusted_vs_raw(tmp_path):
    lake = CandleLake(tmp_path)
    lake.discontinuities = {"K|1": [(pd.Timestamp("2024-06-25 12:00", tz=IST), 0.5)]}
    lake.write(_day(), "1minute", "K|1")
    raw, adj = lake.read("1minute", "K|1", adjusted=False), lake.read("1minute", "K|1")
    before = raw["ts"] < pd.Timestamp("2024-06-25 12:00", tz=IST)
    assert (adj.loc[before, "close"] == raw.loc[before, "close"] * 0.5).all()
    assert (adj.loc[~before, "close"] == raw.loc[~before, "close"]).all()
    # windowed reads agree with the full adjusted series
    w = lake.read("1minute", "K|1", start="2024-06-25 11:00", end="2024-06-25 11:30")
    assert (w["close"].to_numpy() == adj.set_index("ts").loc[w["ts"], "close"].to_numpy()).all()


def test_registry_file_is_well_formed():
    from app.engines.data.storage import DISCONTINUITIES

    reg = pd.read_csv(DISCONTINUITIES)
    assert list(reg.columns) == ["instrument_key", "date", "factor", "kind", "evidence"]
    assert ((reg["factor"] > 0) & (reg["factor"] < 10)).all() and reg["evidence"].str.len().min() > 40
    assert reg["instrument_key"].str.contains(r"^NSE_(EQ|INDEX)\|").all()


def test_index_preopen_postclose_values_are_info_not_errors():
    df = _day()
    extra = df.iloc[[0, 1]].assign(ts=[pd.Timestamp("2024-06-25 09:07", tz=IST),
                                       pd.Timestamp("2024-06-25 15:31", tz=IST)])
    d = pd.concat([df, extra]).sort_values("ts").reset_index(drop=True)
    rep = validate(d, M1, "NSE_INDEX|Nifty 50", is_index=True)
    assert rep.passed and rep.info["index_preopen_postclose_values"] == 2
    assert not validate(d, M1, "NSE_EQ|X").passed  # for a stock these are still errors
    odd = pd.concat([df, df.iloc[[0]].assign(ts=pd.Timestamp("2024-06-25 17:00", tz=IST))]).sort_values("ts")
    assert not validate(odd, M1, "NSE_INDEX|Nifty 50", is_index=True).passed


def test_quarantine_removes_unrepairable_periods(tmp_path):
    lake = CandleLake(tmp_path)
    lake.quarantine = {"K|1": [(pd.Timestamp("2024-06-25 10:00", tz=IST), pd.Timestamp("2024-06-25 11:00", tz=IST))]}
    lake.write(_day(), "1minute", "K|1")
    adj = lake.read("1minute", "K|1")
    assert len(adj) == 375 - 60 and len(lake.read("1minute", "K|1", adjusted=False)) == 375
    a, b = pd.Timestamp("2024-06-25 10:00", tz=IST), pd.Timestamp("2024-06-25 10:59", tz=IST)
    assert not adj["ts"].between(a, b).any()
