import numpy as np
from lightgbm import LGBMClassifier, early_stopping
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from tactigraph.models.graph_features import GLOBAL_NAMES


def matrix(rows, family):
    return np.asarray(
        [r["globals"] if family == "logistic" else r["tabular"] for r in rows], dtype=float
    )


def fit(rows, family, parameters, validation=None):
    x = matrix(rows, family)
    y = np.asarray([r["label"] for r in rows])
    if family == "logistic":
        model = Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=parameters["C"], max_iter=1500)),
            ]
        )
        model.fit(x, y)
    else:
        model = LGBMClassifier(
            **parameters,
            learning_rate=0.04,
            reg_lambda=5,
            max_depth=5,
            random_state=2026,
            n_jobs=2,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
        )
        kwargs = (
            {}
            if validation is None
            else {
                "eval_set": [(matrix(validation, family), [r["label"] for r in validation])],
                "eval_metric": "binary_logloss",
                "callbacks": [early_stopping(35, verbose=False)],
            }
        )
        model.fit(x, y, **kwargs)
    return {
        "family": family,
        "estimator": model,
        "parameters": parameters,
        "feature_count": len(GLOBAL_NAMES) if family == "logistic" else x.shape[1],
    }


def predict(model, rows):
    return model["estimator"].predict_proba(matrix(rows, model["family"]))[:, 1]
