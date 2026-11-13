"""Chronological walk-forward splits with purging (Lopez de Prado, Advances in Financial ML, ch. 7).

Never shuffled. A row at date d has label window (d, d+h]. Any training row whose label window reaches into
a later evaluation slice is purged: we drop the `purge` (= h) sessions immediately before every boundary.
Folds are expanding and forward-only, so training data never follows test data (no embargo case arises).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Fold:
    k: int
    fit_end: pd.Timestamp  # last date for model fitting
    val_start: pd.Timestamp  # early-stopping + calibration slice [val_start, val_end]
    val_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    def as_dict(self) -> dict:
        return {k: (str(v.date()) if isinstance(v, pd.Timestamp) else v) for k, v in self.__dict__.items()}


def _unique_dates(dates) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(sorted(pd.unique(pd.DatetimeIndex(dates))))


def _fold(
    u: pd.DatetimeIndex, k: int, test_start: pd.Timestamp, test_end: pd.Timestamp, purge: int, val_frac: float
) -> Fold:
    ti = u.get_loc(test_start)
    val_end = u[ti - purge - 1]  # purge before test
    train_dates = u[u <= val_end]
    vi = int(len(train_dates) * (1 - val_frac))
    val_start = train_dates[vi]
    fit_end = train_dates[vi - purge - 1]  # purge before validation
    return Fold(k, fit_end, val_start, val_end, test_start, test_end)


def walk_forward(
    dates, first_test: str, holdout_start: str, test_months: int, purge: int, val_frac: float = 0.15
) -> list[Fold]:
    u = _unique_dates(dates)
    folds, start, hold = [], pd.Timestamp(first_test), pd.Timestamp(holdout_start)
    while start < hold:
        end = min(
            start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1), hold - pd.Timedelta(days=1)
        )
        td = u[(u >= start) & (u <= end)]
        if len(td) == 0:
            break
        # The last `purge` sessions of a test window have labels that look past it; they are still legitimate
        # test rows (the model never trained on them), so they stay.
        folds.append(_fold(u, len(folds), td[0], td[-1], purge, val_frac))
        start = end + pd.Timedelta(days=1)
    return folds


def holdout_fold(dates, holdout_start: str, purge: int, val_frac: float = 0.15) -> Fold:
    u = _unique_dates(dates)
    td = u[u >= pd.Timestamp(holdout_start)]
    return _fold(u, -1, td[0], td[-1], purge, val_frac)


def masks(date_col: pd.Series, f: Fold) -> tuple[pd.Series, pd.Series, pd.Series]:
    fit = date_col <= f.fit_end
    val = (date_col >= f.val_start) & (date_col <= f.val_end)
    test = (date_col >= f.test_start) & (date_col <= f.test_end)
    return fit, val, test
