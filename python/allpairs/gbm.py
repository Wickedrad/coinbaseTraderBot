"""LightGBM regressors through the core API (no scikit-learn needed on the runner)."""
from __future__ import annotations

import numpy as np

_ALIASES = {'n_estimators': 'num_iterations', 'subsample': 'bagging_fraction', 'subsample_freq': 'bagging_freq',
            'colsample_bytree': 'feature_fraction', 'min_child_samples': 'min_data_in_leaf', 'reg_lambda': 'lambda_l2'}


class GBM:
    def __init__(self, booster):
        self.booster = booster

    def predict(self, X, pred_contrib: bool = False):
        return self.booster.predict(np.asarray(X, dtype=np.float32), pred_contrib=pred_contrib, num_threads=0)


def fit_gbm(X: np.ndarray, y: np.ndarray, params: dict, seed: int) -> GBM:
    import lightgbm as lgb
    p = {_ALIASES.get(k, k): v for k, v in params.items()}
    rounds = int(p.pop('num_iterations', 100))
    p.update(objective='regression', seed=seed, deterministic=True, force_col_wise=True, verbosity=-1, num_threads=0)
    ds = lgb.Dataset(np.asarray(X, dtype=np.float32), label=np.asarray(y, dtype=np.float64), free_raw_data=True)
    return GBM(lgb.train(p, ds, num_boost_round=rounds))
