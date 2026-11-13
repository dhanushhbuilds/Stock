"""End-to-end: candle lake -> swing dataset -> train + register model -> promoted -> inference -> news -> decision
-> risk -> persisted decisions + audit trail. Uses deterministic fixture candles (never the real lake)."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.core.config import get_settings
from app.engines.data import instruments as ins
from app.engines.data.candles import parse_candles
from app.engines.data.global_data import TICKERS, global_dir
from app.engines.data.storage import CandleLake
from app.engines.decision import service as dsvc
from app.engines.ml import swing
from app.engines.ml.evaluate import swing_backtest
from app.engines.ml.splits import holdout_fold, walk_forward
from app.engines.ml.trainer import PipelineSpec, run, save_dataset
from app.engines.news import service as nsvc
from app.engines.news.sources import parse_rss
from app.models import AuditEvent, DecisionRecord, MLModel
from tests.fixtures.upstox_fake import trading_days

pytestmark = pytest.mark.integration
IST = ZoneInfo("Asia/Kolkata")
FIXTURE = Path(__file__).parent / "fixtures" / "NSE_master_subset.json.gz"


def _random_walk_daily(days, seed, base):
    rng = np.random.default_rng(seed)
    c = base * np.exp(np.cumsum(rng.normal(0.0003, 0.015, len(days))))
    o = c * (1 + rng.normal(0, 0.003, len(days)))
    rows = []
    for d, oo, cc in zip(days, o, c, strict=True):
        rows.append([f"{d}T00:00:00+05:30", float(oo), float(max(oo, cc) * 1.006), float(min(oo, cc) * 0.994),
                     float(cc), int(rng.integers(1e5, 1e6)), 0])
    return parse_candles(rows)


@pytest.fixture
def system(db):
    s = get_settings()
    ins.upsert_instruments(db, ins.parse_master(FIXTURE.read_bytes()))
    ins.map_universe(db)
    lake = CandleLake(s.data_dir, db)
    days = trading_days(date(2019, 1, 1), date(2024, 6, 28))
    members = ins.load_reference_universe()[1][:12]
    keys = [db.get(ins.Instrument, ins.resolve(db, m.symbol).instrument_key).instrument_key for m in members]
    for i, k in enumerate([swing.NIFTY, swing.VIX, *keys, *set(ins.INDUSTRY_TO_SECTOR_INDEX.values())]):
        lake.delete("1day", k)
        lake.write(_random_walk_daily(days, i, 100 + 10 * i), "1day", k)
    g = global_dir(s.data_dir)
    g.mkdir(parents=True, exist_ok=True)
    gd = pd.bdate_range("2018-06-01", "2024-06-28")
    for j, name in enumerate(TICKERS):
        pd.DataFrame({"date": gd.date, "open": 100.0 + j, "high": 101.0 + j, "low": 99.0 + j,
                      "close": 100 * np.exp(np.cumsum(np.random.default_rng(j).normal(0, 0.01, len(gd))))}
                     ).to_parquet(g / f"{name}.parquet", index=False)
    return db, s, lake, keys, days


def test_full_pipeline_produces_explained_risk_checked_decisions(system):
    db, s, lake, keys, days = system
    # 1. dataset + training through the real trainer (walk-forward, holdout, registry)
    cfg = swing.SwingConfig(start="2019-06-01", min_history=120, train_universes=("NIFTY50",))
    mem = [(m.symbol, m.instrument_key, m.sector_index_key, True) for m in dsvc.universe_members(db)
           if m.instrument_key in keys]
    from app.engines.data.global_data import load_global

    ds = swing.build_swing_dataset(lake, mem, load_global(s.data_dir), cfg)
    feats = swing.feature_columns(ds)
    ver = save_dataset(db, ds, "swing", {**cfg.to_dict(), "train_universes": list(cfg.train_universes)}, feats,
                       s.data_dir)
    lab = ds[ds["y"].notna()]
    folds = walk_forward(lab["date"], "2023-01-01", "2024-01-01", 6, purge=5)
    hold = holdout_fold(lab["date"], "2024-01-01", purge=5)
    spec = PipelineSpec("swing", 5, cfg.cost, lambda df, p, t: swing_backtest(df, p, 5, cfg.cost, top_k=3))
    out = run(db, ds, feats, spec, folds, hold, ["logreg"], ver, s.artifacts_dir)
    reg = db.get(MLModel, out["registered"]["version"])
    assert reg is not None and Path(reg.artifact_path).exists() and len(reg.artifact_sha256) == 64
    assert len(out["results"]["logreg"]["walk_forward"]["folds"]) == 2
    # Random-walk data has no edge, so the promotion gate must REJECT it -- that is the expected, honest outcome.
    assert reg.promoted is False

    # 2. with no promoted model, the decision service refuses to decide (NO model -> no decisions)
    now = datetime.combine(date(2024, 6, 28), time(16, 0), tzinfo=IST)
    decisions, err = dsvc.run_swing(db, s, now)
    assert decisions == [] and "no promoted swing model" in err

    # 3. force-promote (test only) to exercise inference -> news -> decision -> risk -> persistence
    reg.promoted = True
    db.commit()
    xml = (b'<rss version="2.0"><channel><title>x</title><item><title>' + mem[0][0].encode() + b'</title><link>u</link>'
           b"<description>|SUBJECT: Financial Results</description><pubDate>28-Jun-2024 15:00:00</pubDate></item>"
           b"</channel></rss>")
    items = parse_rss("nse_announcements", xml)
    items[0].company, items[0].symbol_hint = None, mem[0][0]

    class Pos:
        version = "stub"

        def predict(self, texts):
            return [{"positive": 0.9, "negative": 0.05, "neutral": 0.05} for _ in texts]

    nsvc.ingest(db, items, nsvc.build_mapper(db), Pos(), now=now - timedelta(minutes=30))
    decisions, err = dsvc.run_swing(db, s, now)
    assert err is None and len(decisions) == len(mem)
    assert {d.action for d in decisions} <= {"BUY", "NO_TRADE", "HOLD", "SELL"}
    for d in decisions:
        assert d.reasons and d.model_version == reg.version and "ml" in d.contributions
        if d.action == "BUY":
            assert d.risk["approved"] and d.quantity > 0 and d.risk["stop"] < d.risk["take_profit"]
        else:
            assert d.quantity == 0
    news_dec = next(d for d in decisions if d.symbol == mem[0][0])
    assert news_dec.contributions["news"]["items"] == 1
    assert db.query(DecisionRecord).count() == len(mem)
    assert db.query(AuditEvent).filter(AuditEvent.engine == "decision").count() == len(mem)
    # 4. kill switch: every decision becomes NO_TRADE
    from app.engines.risk.service import set_kill_switch

    set_kill_switch(db, True, "e2e test halt", "test")
    halted, _ = dsvc.run_swing(db, s, now)
    assert all(d.action != "BUY" for d in halted)
    set_kill_switch(db, False, "resume", "test")
