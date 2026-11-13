"""LSTM / GRU sequence classifiers (PyTorch), same interface as the tabular models.

Each sample is the last `seq_len` rows of the SAME instrument ending at t (features standardised with
fit-slice statistics only). Rows with insufficient history get zero-padded on the left.
"""

import copy

import numpy as np
import pandas as pd
import torch
from torch import nn

from app.engines.ml.models import SEED


def _device() -> torch.device:
    return torch.device("mps" if torch.backends.mps.is_available() else "cpu")


class _Net(nn.Module):
    def __init__(self, n_feat: int, hidden: int, kind: str, dropout: float) -> None:
        super().__init__()
        rnn = nn.LSTM if kind == "lstm" else nn.GRU
        self.rnn = rnn(n_feat, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 3))

    def forward(self, x):
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


class SequenceModel:
    """Needs `group` (instrument id) and the frame sorted by (group, time) to build windows."""

    def __init__(
        self,
        kind: str = "lstm",
        seq_len: int = 20,
        hidden: int = 32,
        dropout: float = 0.2,
        lr: float = 1e-3,
        batch: int = 512,
        max_epochs: int = 25,
        patience: int = 4,
        max_fit_rows: int | None = None,
    ) -> None:
        self.name = kind
        self.params = dict(
            seq_len=seq_len,
            hidden=hidden,
            dropout=dropout,
            lr=lr,
            batch=batch,
            max_epochs=max_epochs,
            patience=patience,
            max_fit_rows=max_fit_rows,
        )
        self.kind = kind
        self.net: _Net | None = None
        self.mu = self.sd = None
        self.feature_names: list[str] = []
        self.best_iteration: int | None = None
        self.calibrated = None
        self.temperature = 1.0

    # ---- windows ----
    def _windows(self, X: pd.DataFrame, group: pd.Series, rows: np.ndarray) -> np.ndarray:
        L = self.params["seq_len"]
        Z = (X[self.feature_names].to_numpy(np.float32) - self.mu) / self.sd
        Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)
        g = group.to_numpy()
        out = np.zeros((len(rows), L, Z.shape[1]), dtype=np.float32)
        for i, r in enumerate(rows):
            lo = max(r - L + 1, 0)
            while g[lo] != g[r]:  # never cross into another instrument's history
                lo += 1
            seg = Z[lo : r + 1]
            out[i, L - len(seg) :] = seg
        return out

    def fit_frame(
        self, X: pd.DataFrame, y: pd.Series, group: pd.Series, fit_rows: np.ndarray, val_rows: np.ndarray
    ) -> "SequenceModel":
        torch.manual_seed(SEED)
        np.random.seed(SEED)
        self.feature_names = list(X.columns)
        cap = self.params["max_fit_rows"]
        if cap and len(fit_rows) > cap:  # fixed-seed uniform subsample (documented compute limit)
            fit_rows = np.sort(np.random.default_rng(SEED).choice(fit_rows, cap, replace=False))
        if cap and len(val_rows) > cap // 3:
            val_rows = np.sort(np.random.default_rng(SEED + 1).choice(val_rows, cap // 3, replace=False))
        F = X.iloc[fit_rows].to_numpy(np.float32)
        self.mu = np.nanmean(F, axis=0)
        self.sd = np.nanstd(F, axis=0) + 1e-8
        dev = _device()
        Xf = torch.from_numpy(self._windows(X, group, fit_rows))
        yf = torch.from_numpy(y.to_numpy()[fit_rows].astype(np.int64))
        Xv = torch.from_numpy(self._windows(X, group, val_rows)).to(dev)
        yv = torch.from_numpy(y.to_numpy()[val_rows].astype(np.int64)).to(dev)
        net = _Net(Xf.shape[2], self.params["hidden"], self.kind, self.params["dropout"]).to(dev)
        opt = torch.optim.Adam(net.parameters(), lr=self.params["lr"], weight_decay=1e-4)
        lossf = nn.CrossEntropyLoss()
        best, best_state, bad = np.inf, None, 0
        gen = torch.Generator().manual_seed(SEED)
        for epoch in range(self.params["max_epochs"]):
            net.train()
            perm = torch.randperm(len(Xf), generator=gen)  # shuffles mini-batches of the fit slice only
            for i in range(0, len(perm), self.params["batch"]):
                idx = perm[i : i + self.params["batch"]]
                opt.zero_grad()
                loss = lossf(net(Xf[idx].to(dev)), yf[idx].to(dev))
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                vl = float(
                    sum(
                        lossf(net(Xv[i : i + 4096]), yv[i : i + 4096]).item() * len(yv[i : i + 4096])
                        for i in range(0, len(yv), 4096)
                    )
                    / len(yv)
                )
            if vl < best - 1e-5:
                best, best_state, bad, self.best_iteration = vl, copy.deepcopy(net.state_dict()), 0, epoch + 1
            else:
                bad += 1
                if bad >= self.params["patience"]:
                    break
        net.load_state_dict(best_state)
        self.net = net.eval()
        self._fit_temperature(Xv, yv)
        return self

    def _logits(self, W: torch.Tensor) -> torch.Tensor:
        dev = _device()
        with torch.no_grad():
            return torch.cat([self.net(W[i : i + 4096].to(dev)).cpu() for i in range(0, len(W), 4096)])

    def _fit_temperature(self, Xv, yv) -> None:
        """Temperature scaling (Guo et al. 2017) on the validation slice: one parameter."""
        logits, y = self._logits(Xv.cpu()), yv.cpu()
        best_t, best_l = 1.0, np.inf
        for t in np.linspace(0.5, 5.0, 46):
            loss = nn.functional.cross_entropy(logits / t, y).item()
            if loss < best_l:
                best_t, best_l = float(t), loss
        self.temperature = best_t

    def predict_proba_frame(self, X: pd.DataFrame, group: pd.Series, rows: np.ndarray) -> np.ndarray:
        W = torch.from_numpy(self._windows(X, group, rows))
        return torch.softmax(self._logits(W) / self.temperature, dim=1).numpy()

    def config(self) -> dict:
        return {
            "name": self.name,
            "params": self.params,
            "best_iteration": self.best_iteration,
            "temperature": self.temperature,
        }
