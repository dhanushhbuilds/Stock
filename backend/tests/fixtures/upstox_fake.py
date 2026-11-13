"""Deterministic Upstox historical-candle fixtures for tests.

These are synthetic candles in the exact wire format of the V3 historical endpoint. They exist only to test
plumbing (parsing, batching, retries, storage) and are never written to the real data lake.
"""

import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from urllib.parse import unquote

import httpx

IST_OFFSET = "+05:30"
PATH_RE = re.compile(
    r"^/v3/historical-candle/(?P<key>[^/]+)/(?P<unit>\w+)/(?P<interval>\d+)/"
    r"(?P<to>[\d-]+)/(?P<frm>[\d-]+)$"
)


def trading_days(start: date, end: date) -> list[date]:
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def minute_candles(day: date, base: float = 1000.0, scale: float = 1.0) -> list[list]:
    """375 one-minute bars 09:15..15:29, deterministic, OHLC-consistent, newest first (as Upstox)."""
    rows = []
    t0 = datetime(day.year, day.month, day.day, 9, 15)
    seed = day.toordinal()
    for i in range(375):
        mid = base + 10 * math.sin((seed + i) / 37.0) + (seed % 11)
        o = round(mid * scale, 2)
        c = round((mid + math.sin(i / 3.0)) * scale, 2)
        h = round(max(o, c) + 0.5 * scale, 2)
        lo = round(min(o, c) - 0.5 * scale, 2)
        ts = (t0 + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S") + IST_OFFSET
        rows.append([ts, o, h, lo, c, 1000 + (seed + i) % 500, 0])
    return rows[::-1]


def daily_candle(day: date, base: float = 1000.0, scale: float = 1.0) -> list:
    m = minute_candles(day, base, scale)[::-1]
    return [
        f"{day.isoformat()}T00:00:00{IST_OFFSET}",
        m[0][1],
        max(r[2] for r in m),
        min(r[3] for r in m),
        m[-1][4],
        sum(r[5] for r in m),
        0,
    ]


class FakeUpstox:
    """httpx handler serving fixture candles; records requests; supports injected failures."""

    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale
        self.requests: list[httpx.Request] = []
        self.fail: Callable[[httpx.Request], httpx.Response | None] = lambda req: None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if (injected := self.fail(request)) is not None:
            return injected
        m = PATH_RE.match(request.url.raw_path.decode().split("?")[0])
        if not m:
            return httpx.Response(404, json={"status": "error"})
        unit, interval = m["unit"], int(m["interval"])
        frm, to = date.fromisoformat(m["frm"]), date.fromisoformat(m["to"])
        if unit == "minutes" and interval <= 15 and (to - frm).days > 31:
            return httpx.Response(
                400,
                json={
                    "status": "error",
                    "errors": [{"errorCode": "UDAPI1148", "message": "Invalid date range"}],
                },
            )
        days = trading_days(frm, to)
        if unit == "days":
            candles = [daily_candle(d, scale=self.scale) for d in days][::-1]
        else:
            candles = [c for d in reversed(days) for c in minute_candles(d, scale=self.scale)]
        return httpx.Response(200, content=json.dumps({"status": "success", "data": {"candles": candles}}))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def keys_requested(self) -> list[str]:
        return [
            unquote(PATH_RE.match(r.url.raw_path.decode())["key"])
            for r in self.requests
            if PATH_RE.match(r.url.raw_path.decode())
        ]
