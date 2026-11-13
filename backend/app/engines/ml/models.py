"""Tabular model candidates behind one interface.

fit(X, y, Xv, yv) trains on the fit slice, early-stops / calibrates on the purged validation slice.
predict_proba(X) returns calibrated probabilities for classes [DOWN, NEUTRAL, UP].
"""

import warnings
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 42


class Model:
    name = "base"
    defaults: dict[str, Any] = {}

    def __init__(self, **params: Any) -> None:
        self.params = {**self.defaults, **params}
        self.est: Any = None
        self.calibrated: Any = None
        self.best_iteration: int | None = None
        self.feature_names: list[str] = []

    def _fit(self, X, y, Xv, yv) -> None:  # pragma: no cover
        raise NotImplementedError

    def fit(self, X, y, Xv, yv, calibrate: bool = True) -> "Model":
        self.feature_names = list(X.columns)
        self._fit(X, y, Xv, yv)
        if calibrate and len(np.unique(yv)) == 3:
            # Platt scaling on the purged validation slice (few parameters -> little overfitting).
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.calibrated = CalibratedClassifierCV(FrozenEstimator(self.est), method="sigmoid").fit(
                    Xv, yv
                )
        return self

    def predict_proba(self, X) -> np.ndarray:
        return (self.calibrated or self.est).predict_proba(X[self.feature_names])

    def config(self) -> dict:
        return {"name": self.name, "params": self.params, "best_iteration": self.best_iteration}

    def feature_importance(self) -> dict[str, float]:
        return {}


class LogReg(Model):
    name = "logreg"
    defaults = {"C": 0.05, "max_iter": 3000}

    def _fit(self, X, y, Xv, yv):
        self.est = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(random_state=SEED, **self.params),
        ).fit(X, y)

    def feature_importance(self):
        coef = np.abs(self.est[-1].coef_).mean(axis=0)
        return dict(zip(self.feature_names, coef.tolist(), strict=True))


class RandomForest(Model):
    name = "random_forest"
    defaults = {"n_estimators": 300, "min_samples_leaf": 200, "max_features": 0.3, "max_samples": 0.5}

    def _fit(self, X, y, Xv, yv):
        self.est = make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(n_jobs=-1, random_state=SEED, **self.params),
        ).fit(X, y)

    def feature_importance(self):
        return dict(zip(self.feature_names, self.est[-1].feature_importances_.tolist(), strict=True))


class XGBoost(Model):
    name = "xgboost"
    defaults = {
        "n_estimators": 2000,
        "learning_rate": 0.03,
        "max_depth": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.6,
        "min_child_weight": 50,
        "reg_lambda": 5.0,
    }

    def _fit(self, X, y, Xv, yv):
        import xgboost as xgb  # lazy: never loaded in torch-mode processes

        self.est = xgb.XGBClassifier(
            objective="multi:softprob",
            tree_method="hist",
            random_state=SEED,
            n_jobs=-1,
            eval_metric="mlogloss",
            early_stopping_rounds=100,
            **self.params,
        )
        self.est.fit(X, y, eval_set=[(Xv, yv)], verbose=False)
        self.best_iteration = int(self.est.best_iteration)

    def feature_importance(self):
        return dict(zip(self.feature_names, self.est.feature_importances_.tolist(), strict=True))


class LightGBM(Model):
    name = "lightgbm"
    defaults = {
        "n_estimators": 3000,
        "learning_rate": 0.02,
        "num_leaves": 15,
        "min_child_samples": 300,
        "subsample": 0.8,
        "subsample_freq": 1,
        "colsample_bytree": 0.6,
        "reg_lambda": 5.0,
    }

    def _fit(self, X, y, Xv, yv):
        import lightgbm as lgb  # lazy: never loaded in torch-mode processes

        self.est = lgb.LGBMClassifier(
            objective="multiclass", random_state=SEED, n_jobs=-1, verbose=-1, **self.params
        )
        self.est.fit(X, y, eval_set=[(Xv, yv)], callbacks=[lgb.early_stopping(150, verbose=False)])
        self.best_iteration = int(self.est.best_iteration_ or self.params["n_estimators"])

    def feature_importance(self):
        g = self.est.booster_.feature_importance(importance_type="gain")
        return dict(zip(self.feature_names, (g / g.sum()).tolist(), strict=True))


TABULAR: dict[str, type[Model]] = {m.name: m for m in (LogReg, RandomForest, XGBoost, LightGBM)}
