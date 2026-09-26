from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import Ridge, TweedieRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler


def to_log(values: np.ndarray) -> np.ndarray:
    return np.log1p(np.maximum(values, 0))


def from_log(values: np.ndarray) -> np.ndarray:
    return np.maximum(np.expm1(values), 0)


@dataclass
class Candidate:
    name: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 42
    threads: int = -1

    def fit(self, features: pd.DataFrame, target: np.ndarray) -> Candidate:
        self.columns = list(features.columns)
        x = features.to_numpy(dtype=float)
        self.fitted = self._fit(x, target)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        x = features[self.columns].to_numpy(dtype=float)
        return self._predict(x)

    def _fit(self, x: np.ndarray, y: np.ndarray):
        kind = self.kind
        if kind in ("median", "mean"):
            return float(np.median(y) if kind == "median" else np.mean(y))
        if kind in ("nearest", "idw"):
            return (x[:, :2].copy(), y.copy())
        if kind == "site_mean":
            return (x[:, :2].copy(), y.copy(), float(np.median(y)))
        log_y = to_log(y)
        if kind == "ridge":
            model = make_pipeline(StandardScaler(), Ridge(alpha=self.params.get("alpha", 1.0)))
            return model.fit(x, log_y)
        if kind == "tweedie":
            model = make_pipeline(
                StandardScaler(),
                TweedieRegressor(
                    power=self.params.get("power", 1.5),
                    alpha=self.params.get("alpha", 0.1),
                    link="log",
                    max_iter=2000,
                ),
            )
            return model.fit(x, y)
        if kind == "spline_tweedie":
            model = make_pipeline(
                StandardScaler(),
                SplineTransformer(n_knots=self.params.get("knots", 4), degree=3),
                TweedieRegressor(
                    power=self.params.get("power", 1.5),
                    alpha=self.params.get("alpha", 1.0),
                    link="log",
                    max_iter=3000,
                ),
            )
            return model.fit(x, y)
        if kind == "gp":
            kernel = ConstantKernel(1.0) * Matern(
                length_scale=np.ones(x.shape[1]), nu=self.params.get("nu", 1.5)
            ) + WhiteKernel(0.3)
            model = make_pipeline(
                StandardScaler(),
                GaussianProcessRegressor(
                    kernel=kernel, normalize_y=True, n_restarts_optimizer=2, random_state=self.seed
                ),
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return model.fit(x, log_y)
        if kind in ("random_forest", "extra_trees"):
            estimator = RandomForestRegressor if kind == "random_forest" else ExtraTreesRegressor
            model = estimator(random_state=self.seed, n_jobs=self.threads, **self.params)
            return model.fit(x, log_y)
        if kind == "lightgbm":
            model = lgb.LGBMRegressor(
                random_state=self.seed, n_jobs=self.threads, verbose=-1, **self.params
            )
            return model.fit(x, log_y)
        if kind == "catboost":
            model = CatBoostRegressor(
                random_seed=self.seed,
                thread_count=self.threads,
                allow_writing_files=False,
                verbose=False,
                **self.params,
            )
            return model.fit(x, log_y)
        if kind == "ensemble":
            names = self.params["members"]
            zoo = candidate_zoo(self.seed, self.threads)
            members = [member for member in zoo if member.name in names]
            frame = pd.DataFrame(x, columns=self.columns)
            spatial = {"x_km", "y_km"} <= set(self.columns)
            usable = [m for m in members if spatial or m.kind not in ("nearest", "idw")]
            return [member.fit(frame[self._member_columns(member)], y) for member in usable]
        raise ValueError(f"unknown model {kind}")

    def _member_columns(self, member: Candidate) -> list[str]:
        if member.kind in ("nearest", "idw"):
            return ["x_km", "y_km"]
        return self.columns

    def _predict(self, x: np.ndarray) -> np.ndarray:
        kind = self.kind
        if kind in ("median", "mean"):
            return np.full(len(x), self.fitted)
        if kind in ("nearest", "idw"):
            points, values = self.fitted
            distance = np.sqrt(((x[:, None, :2] - points[None, :, :]) ** 2).sum(axis=2))
            if kind == "nearest":
                return values[np.argmin(distance, axis=1)]
            k = self.params.get("k", 5)
            order = np.argsort(distance, axis=1)[:, :k]
            near = np.take_along_axis(distance, order, axis=1)
            weights = 1 / np.maximum(near, 1.0) ** self.params.get("power", 2)
            logs = to_log(values)[order]
            return from_log((weights * logs).sum(axis=1) / weights.sum(axis=1))
        if kind == "site_mean":
            points, values, fallback = self.fitted
            distance = np.sqrt(((x[:, None, :2] - points[None, :, :]) ** 2).sum(axis=2))
            same = distance <= self.params.get("radius_km", 0.5)
            counts = same.sum(axis=1)
            means = (same * values).sum(axis=1) / np.maximum(counts, 1)
            return np.where(counts > 0, means, fallback)
        if kind in ("tweedie", "spline_tweedie"):
            return np.maximum(self.fitted.predict(x), 0)
        if kind == "ensemble":
            frame = pd.DataFrame(x, columns=self.columns)
            logs = [to_log(member.predict(frame[member.columns])) for member in self.fitted]
            return from_log(np.mean(logs, axis=0))
        return from_log(self.fitted.predict(x))


def candidate_zoo(seed: int = 42, threads: int = -1) -> list[Candidate]:
    zoo = [
        Candidate("median", "median", seed=seed),
        Candidate("mean", "mean", seed=seed),
        Candidate("nearest_neighbour", "nearest", seed=seed),
        Candidate("idw_k5", "idw", {"k": 5, "power": 2}, seed=seed),
        Candidate("ridge_log", "ridge", {"alpha": 3.0}, seed=seed),
        Candidate("tweedie_glm", "tweedie", {"power": 1.5, "alpha": 0.3}, seed=seed),
        Candidate("spline_glm", "spline_tweedie", {"knots": 4, "alpha": 1.0}, seed=seed),
        Candidate("gp_matern", "gp", {"nu": 1.5}, seed=seed),
        Candidate(
            "random_forest",
            "random_forest",
            {"n_estimators": 500, "min_samples_leaf": 3},
            seed=seed,
        ),
        Candidate(
            "extra_trees", "extra_trees", {"n_estimators": 500, "min_samples_leaf": 3}, seed=seed
        ),
        Candidate(
            "lightgbm",
            "lightgbm",
            {
                "n_estimators": 300,
                "learning_rate": 0.03,
                "num_leaves": 7,
                "min_child_samples": 5,
                "subsample": 0.8,
                "subsample_freq": 1,
                "colsample_bytree": 0.8,
                "reg_lambda": 1.0,
            },
            seed=seed,
        ),
        Candidate(
            "catboost",
            "catboost",
            {"iterations": 600, "depth": 4, "learning_rate": 0.03, "l2_leaf_reg": 5.0},
            seed=seed,
        ),
    ]
    for candidate in zoo:
        candidate.threads = threads
    return zoo


BASELINES = ("median", "mean", "nearest_neighbour", "idw_k5")


def ensemble(seed: int = 42, threads: int = -1) -> Candidate:
    members = ["idw_k5", "tweedie_glm", "gp_matern", "random_forest", "catboost"]
    return Candidate("ensemble", "ensemble", {"members": members}, seed=seed, threads=threads)
