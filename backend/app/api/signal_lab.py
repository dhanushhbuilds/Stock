"""Signal Lab API: upload any daily OHLCV dataset (or pick a stored stock) and get risk-evaluated signals."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import get_settings
from app.core.db import get_session
from app.engines.data.instruments import MappingError
from app.engines.data.storage import CandleLake
from app.engines.signal_lab import service
from app.engines.signal_lab.parsing import DatasetError, parse_csv

router = APIRouter(prefix="/signal-lab", tags=["signal lab"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_BYTES = 8 * 1024 * 1024


def _run(session, series, capital, source):
    if not 10_000 <= capital <= 1_000_000_000:
        raise HTTPException(422, "capital must be between ₹10,000 and ₹100 crore")
    try:
        result = service.analyze(session, get_settings(), series, capital, source)
    except service.LabUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    record(
        session,
        "decision",
        "signal_lab_run",
        {
            "source": source,
            "symbols": [r["symbol"] for r in result["results"]],
            "final": {r["symbol"]: (r.get("final") or {}).get("action") for r in result["results"]},
        },
    )
    return service.jsonable(result)


@router.post("/analyze")
async def analyze_upload(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    capital: Annotated[float, Form()] = 1_000_000,
    symbol: Annotated[str, Form()] = "",
):
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "file larger than 8 MB")
    try:
        stem = re.split(r"[_\-\s.]", (file.filename or "UPLOAD"))[0] or "UPLOAD"
        series = parse_csv(raw, default_symbol=(symbol or stem).upper()[:20])
    except DatasetError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _run(session, series, capital, f"upload:{file.filename}")


@router.post("/analyze-symbol/{symbol}")
def analyze_symbol(symbol: str, session: SessionDep, capital: float = 1_000_000):
    try:
        series = service.series_from_lake(session, get_settings(), symbol)
    except (MappingError, service.LabUnavailable) as exc:
        raise HTTPException(404, str(exc)) from exc
    return _run(session, series, capital, f"stored:{symbol.upper()}")


@router.get("/sample/{symbol}.csv", response_class=PlainTextResponse)
def sample(symbol: str, session: SessionDep):
    """Export a stored stock as a CSV in the upload format (to try the upload flow end to end)."""
    try:
        s = service.series_from_lake(session, get_settings(), symbol)[0]
    except (MappingError, service.LabUnavailable) as exc:
        raise HTTPException(404, str(exc)) from exc
    f = s.frame.assign(Date=s.frame["ts"].dt.strftime("%Y-%m-%d"))
    csv = f.rename(columns=str.title)[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(index=False)
    return PlainTextResponse(csv, headers={"Content-Disposition": f'attachment; filename="{s.symbol}_daily.csv"'})


@router.get("/status")
def status(session: SessionDep):
    s = get_settings()
    try:
        d, _, vol = service.load_models(session, s)
        return {
            "ready": True,
            "direction": {k: d[k] for k in ("status", "trained_through", "dataset_version")},
            "volatility": {"version": vol.version, "holdout": vol.metrics.get("holdout")},
            "context_through": str(CandleLake(s.data_dir).last_ts("1day", "NSE_INDEX|Nifty 50")),
        }
    except service.LabUnavailable as exc:
        return {"ready": False, "reason": str(exc)}
