"""Entity mapping, event classification, scoring and FinBERT sentiment."""

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

# ---------------- entity mapping ----------------

# Only legal-form suffixes are stripped. Meaningful words ("India", "Bank", "Corporation") are kept: stripping
# "india" made "Reserve Bank of India" match "Bank of India" (found on live RBI data, 2026-11-13).
_SUFFIX = re.compile(r"\b(limited|ltd|the)\b")


def norm_name(name: str) -> str:
    n = name.lower().replace(".", " ")
    n = re.sub(r"[^a-z0-9& ]", " ", n)
    n = _SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


@dataclass(frozen=True)
class Entity:
    instrument_key: str
    symbol: str
    name: str
    sector_index_key: str | None = None


class EntityMapper:
    """Maps issuer names / symbols / mentions to instruments that exist in the Upstox master. Never invents keys."""

    def __init__(self, entities: list[Entity], aliases: dict[str, str] | None = None) -> None:
        self.by_symbol = {e.symbol.upper(): e for e in entities}
        self.by_name: dict[str, Entity] = {}
        for e in entities:
            self.by_name.setdefault(norm_name(e.name), e)
        for alias, sym in (aliases or {}).items():
            if sym.upper() in self.by_symbol:
                self.by_name[norm_name(alias)] = self.by_symbol[sym.upper()]
        # longest names first so "hdfc bank" wins over "hdfc"
        self._mentions = sorted(
            ((n, e) for n, e in self.by_name.items() if len(n) >= 4), key=lambda x: -len(x[0])
        )

    def issuer(self, company: str | None, symbol_hint: str | None) -> Entity | None:
        if symbol_hint and symbol_hint.upper() in self.by_symbol:
            return self.by_symbol[symbol_hint.upper()]
        if company:
            return self.by_name.get(norm_name(company))
        return None

    # Names too generic to identify a company when they appear inside free text.
    GENERIC = {"bank", "india", "reserve bank of india", "state bank", "power", "finance", "capital"}

    # Institutions whose names contain a listed company's name ("Reserve Bank of India" ⊃ "Bank of India").
    # They are blanked out before matching. Found on live RBI data, 2026-11-13.
    NON_ISSUERS = (
        "reserve bank of india",
        "securities and exchange board of india",
        "government of india",
        "national stock exchange of india",
        "insurance regulatory and development authority of india",
    )

    def mentions(self, text: str, limit: int = 5) -> list[Entity]:
        t = f" {norm_name(text)} "
        for phrase in self.NON_ISSUERS:
            t = t.replace(f" {phrase} ", " ")
        found: list[Entity] = []
        for n, e in self._mentions:
            if n in self.GENERIC or len(n.split()) < 2:
                continue  # single-word names are too ambiguous in free text
            if f" {n} " in t and e not in found:
                found.append(e)
                t = t.replace(f" {n} ", " ")
                if len(found) >= limit:
                    break
        return found


# ---------------- event classification ----------------

# (event_type, importance 0-1, patterns). First match wins; ordered from most to least specific.
EVENT_RULES: list[tuple[str, float, list[str]]] = [
    ("profit_warning", 0.9, [r"profit warning", r"guidance (cut|lower)", r"loss widen"]),
    (
        "earnings",
        0.9,
        [
            r"financial results?",
            r"\bq[1-4]\s?fy\d{2}",
            r"quarterly results?",
            r"earnings",
            r"outcome of board meeting.*results?",
            r"unaudited",
            r"audited",
        ],
    ),
    ("merger", 0.85, [r"\bmerger\b", r"amalgamation", r"scheme of arrangement", r"demerger"]),
    ("acquisition", 0.85, [r"acquisition", r"\bacquire", r"takeover", r"open offer"]),
    ("buyback", 0.8, [r"buy ?back"]),
    ("dividend", 0.6, [r"dividend"]),
    (
        "fund_raising",
        0.6,
        [
            r"qualified institutions? placement",
            r"\bqip\b",
            r"preferential (issue|allotment)",
            r"rights issue",
            r"fund rais",
            r"non[- ]convertible debentures?",
            r"\bncds?\b",
        ],
    ),
    (
        "management_change",
        0.6,
        [
            r"resignation",
            r"appointment",
            r"cessation",
            r"managing director",
            r"\bceo\b",
            r"change in director",
            r"change in management",
            r"change in auditor",
            r"\bkmp\b",
            r"\bcfo\b",
            r"key managerial",
        ],
    ),
    (
        "legal",
        0.7,
        [
            r"litigation",
            r"\bcourt\b",
            r"tribunal",
            r"\bnclt\b",
            r"penalty",
            r"show cause",
            r"\bfir\b",
            r"insolvency",
            r"\bsebi order",
            r"raid",
            r"search and seizure",
        ],
    ),
    (
        "regulatory",
        0.7,
        [
            r"\brbi\b.*(direction|circular|policy)",
            r"sebi.*(circular|regulation|amend)",
            r"regulatory",
            r"licen[cs]e",
            r"approval from",
        ],
    ),
    ("credit_rating", 0.6, [r"credit rating", r"\brating\b"]),
    (
        "contract",
        0.6,
        [
            r"order (win|received|inflow)",
            r"bags? (an? )?order",
            r"contract",
            r"letter of award",
            r"\bloa\b",
            r"work order",
        ],
    ),
    ("product_launch", 0.5, [r"launch", r"capacity addition", r"commenc\w+ (of )?commercial", r"new plant"]),
    (
        "macro",
        0.7,
        [
            r"monetary policy",
            r"repo rate",
            r"\bcpi\b",
            r"inflation",
            r"\bgdp\b",
            r"forex reserves",
            r"money supply",
            r"liquidity",
            r"auction",
            r"treasury bills?",
            r"government securities",
        ],
    ),
    ("geopolitical", 0.7, [r"\bwar\b", r"sanction", r"conflict", r"tariff"]),
    ("corporate_action", 0.5, [r"record date", r"bonus", r"stock split", r"sub-division", r"redemption"]),
    (
        "board_meeting",
        0.4,
        [
            r"outcome of board meeting",
            r"board meeting",
            r"shareholders meeting",
            r"\bagm\b",
            r"\begm\b",
            r"postal ballot",
        ],
    ),
    ("press_release", 0.4, [r"press release", r"investor presentation", r"disclosure of material"]),
    ("market_activity", 0.4, [r"spurt in volume", r"price movement", r"clarification"]),
    (
        "investor_meet",
        0.2,
        [r"analysts?/institutional investor", r"investor meet", r"con\.? call", r"earnings call"],
    ),
    (
        "routine_disclosure",
        0.1,
        [
            r"declaration of nav",
            r"\bnav\b",
            r"utili[sz]ation of issue proceeds",
            r"deviation",
            r"security cover",
            r"monitoring agency",
            r"regulation \d+",
            r"asset/liability",
            r"payment of interest",
            r"general updates",
            r"^.*: updates$",
            r"trading window",
            r"esop",
            r"esps",
            r"allotment",
            r"certificate",
            r"newspaper",
            r"regulation 74",
            r"loss of share",
            r"duplicate share",
            r"compliance",
        ],
    ),
]


def classify_event(text: str) -> tuple[str, float]:
    t = text.lower()
    for name, imp, pats in EVENT_RULES:
        if any(re.search(p, t) for p in pats):
            return name, imp
    return "other", 0.3


# ---------------- scoring ----------------


def freshness(published_at: datetime, as_of: datetime, half_life_h: float = 24.0) -> float:
    age_h = (as_of - published_at).total_seconds() / 3600
    if age_h < 0:
        return 0.0  # future relative to as_of: unusable
    return math.exp(-math.log(2) * age_h / half_life_h)


def relevance(scope: str, direct_issuer: bool, mentions: int) -> float:
    if direct_issuer:
        return 1.0
    if scope == "company" and mentions:
        return 0.6
    if scope in ("market", "regulatory"):
        return 0.4
    return 0.2 if mentions else 0.0


def content_hash(source: str, title: str, published_raw: str) -> str:
    key = f"{source}|{re.sub(r'\\s+', ' ', title.lower()).strip()}|{published_raw.strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def near_duplicate(a: str, b: str, threshold: float = 0.9) -> bool:
    ta, tb = set(norm_name(a).split()), set(norm_name(b).split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


# ---------------- sentiment ----------------


class SentimentModel(Protocol):
    version: str

    def predict(self, texts: list[str]) -> list[dict[str, float]]: ...


class FinBERT:
    """ProsusAI/finbert (Araci 2019). Loaded from safetensors only (no pickle). Licence CC-BY-NC-SA-4.0."""

    version = "ProsusAI/finbert@safetensors"

    def __init__(self, cache_dir: Path, device: str | None = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained("ProsusAI/finbert", cache_dir=cache_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            "ProsusAI/finbert", cache_dir=cache_dir, use_safetensors=True
        ).eval()
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model.to(self.device)
        self.labels = [self.model.config.id2label[i].lower() for i in range(self.model.config.num_labels)]

    def predict(self, texts: list[str], batch: int = 32) -> list[dict[str, float]]:
        out = []
        for i in range(0, len(texts), batch):
            enc = self.tok(
                texts[i : i + batch], padding=True, truncation=True, max_length=128, return_tensors="pt"
            ).to(self.device)
            with self.torch.no_grad():
                p = self.torch.softmax(self.model(**enc).logits, dim=-1).cpu().numpy()
            out += [dict(zip(self.labels, map(float, row), strict=True)) for row in p]
        return out


def sentiment_score(probs: dict[str, float]) -> float:
    """Scalar in [-1, 1] = P(positive) - P(negative)."""
    return float(probs.get("positive", 0.0) - probs.get("negative", 0.0))
