"""Legitimate, official news sources (public RSS feeds published by the exchange / regulators).

NSE corporate announcements: https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml
RBI press releases:          https://www.rbi.org.in/pressreleases_rss.xml
SEBI updates:                https://www.sebi.gov.in/sebirss.xml
"""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
UA = "AstraQuant-Research/0.1 (+academic project; respects RSS publication)"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    scope: str  # company | market | regulatory


SOURCES = {
    "nse_announcements": Source(
        "nse_announcements",
        "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
        "company",
    ),
    "rbi_press": Source("rbi_press", "https://www.rbi.org.in/pressreleases_rss.xml", "market"),
    "sebi": Source("sebi", "https://www.sebi.gov.in/sebirss.xml", "regulatory"),
}


class SourceError(Exception):
    pass


@dataclass
class RawItem:
    source: str
    title: str
    body: str
    url: str
    published_at: datetime | None  # tz-aware IST, None if missing/unparseable
    published_raw: str
    company: str | None = None  # NSE: issuer name from <title>
    symbol_hint: str | None = None  # NSE: symbol embedded in the filing URL
    extra: dict = field(default_factory=dict)


def _clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_time(raw: str | None) -> datetime | None:
    """Supports NSE '13-Nov-2026 13:08:37' and RFC-822 'Fri, 13 Nov 2026 10:20:00 [+0530]'. Naive = IST."""
    if not raw:
        return None
    raw = raw.strip().replace(",", "")  # SEBI uses "12 Nov, 2026 +0530"
    m = re.fullmatch(r"(\d{1,2} \w{3} \d{4})( [+-]\d{4})", raw)
    if m:  # date-only with offset: midnight of that day in the given offset
        return datetime.strptime(raw, "%d %b %Y %z").astimezone(IST)
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d %b %Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


NSE_SYMBOL_IN_URL = re.compile(r"/corporate/([A-Z0-9&\-]+)_\d{14}")


def parse_rss(source: str, payload: bytes) -> list[RawItem]:
    try:
        root = ET.fromstring(payload.lstrip(b"\xef\xbb\xbf").strip())
    except ET.ParseError as exc:
        raise SourceError(f"{source}: invalid XML ({exc})") from exc
    items = root.findall(".//item")
    if root.tag != "rss" or not root.findall("channel"):
        raise SourceError(f"{source}: not an RSS 2.0 document")
    out = []
    for it in items:
        title, desc = _clean(it.findtext("title")), _clean(it.findtext("description"))
        url = (it.findtext("link") or "").strip()
        raw_ts = it.findtext("pubDate") or ""
        item = RawItem(
            source=source,
            title=title,
            body=desc,
            url=url,
            published_at=parse_time(raw_ts),
            published_raw=raw_ts,
        )
        if source == "nse_announcements":
            item.company = title
            m = NSE_SYMBOL_IN_URL.search(url)
            item.symbol_hint = m.group(1) if m else None
            subj = desc.split("|SUBJECT:")[-1].strip() if "|SUBJECT:" in desc else ""
            item.extra["subject"] = subj
            item.title = f"{title}: {subj or desc[:120]}"
        if title:
            out.append(item)
    return out


def fetch(source: str, transport: httpx.BaseTransport | None = None, timeout: float = 20.0) -> list[RawItem]:
    if source not in SOURCES:
        raise SourceError(f"unknown source {source!r}")
    with httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml"},
    ) as c:
        r = c.get(SOURCES[source].url)
    if r.status_code != 200:
        raise SourceError(f"{source}: HTTP {r.status_code}")
    return parse_rss(source, r.content)
