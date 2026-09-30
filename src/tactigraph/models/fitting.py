import numpy as np
from lightgbm import LGBMClassifier, early_stopping
from scipy.special import expit, logit
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from tactigraph.models.features import FEATURES, NUMERIC


def matrix(rows):
    return np.array(
        [[np.nan if row[f] is None else row[f] for f in FEATURES] for row in rows], dtype=object
    )


def labels(rows):
    return np.array([r["label"] for r in rows], dtype=int)


def fit_model(rows, family, params, *, seed=2026, validation=None):
    if validation and any(r["split"] != "tuning" for r in validation):
        raise ValueError("Early stopping permits only the tuning partition")
    if any(r["split"] not in {"train", "tuning"} or r["penalty"] for r in rows):
        raise ValueError("Base fitting permits only non-penalty train/tuning rows")
    transformer = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="median", add_indicator=True, keep_empty_features=True
                            ),
                        ),
                        ("scale", StandardScaler()),
                    ]
                ),
                list(range(len(NUMERIC))),
            ),
            (
                "category",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(range(len(NUMERIC), len(FEATURES))),
            ),
        ]
    )
    x = transformer.fit_transform(matrix(rows))
    if family == "logistic":
        estimator = LogisticRegression(C=params["C"], max_iter=2000, random_state=seed)
        estimator.fit(x, labels(rows))
    elif family == "lightgbm":
        estimator = LGBMClassifier(
            **params,
            random_state=seed,
            n_jobs=2,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        kwargs = {}
        if validation:
            kwargs = {
                "eval_set": [(transformer.transform(matrix(validation)), labels(validation))],
                "eval_metric": "binary_logloss",
                "callbacks": [early_stopping(70, verbose=False)],
            }
        estimator.fit(x, labels(rows), **kwargs)
    else:
        raise ValueError("Unknown model family")
    return {"preprocessor": transformer, "estimator": estimator, "family": family, "params": params}


def predict(model, rows):
    transformed = model["preprocessor"].transform(matrix(rows))
    if model["family"] == "lightgbm":
        return model["estimator"].booster_.predict(transformed, num_threads=2)
    return model["estimator"].predict_proba(transformed)[:, 1]


def fit_sigmoid(y, probabilities):
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(logit(np.clip(probabilities, 1e-7, 1 - 1e-7)).reshape(-1, 1), y)
    return {"intercept": float(model.intercept_[0]), "slope": float(model.coef_[0, 0])}


def calibrate(parameters, probabilities):
    if parameters is None:
        return np.asarray(probabilities)
    return expit(
        parameters["intercept"]
        + parameters["slope"] * logit(np.clip(probabilities, 1e-7, 1 - 1e-7))
    )
