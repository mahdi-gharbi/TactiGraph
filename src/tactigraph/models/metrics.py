import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from tactigraph.models.fitting import fit_sigmoid


def scores(y, p):
    y, p = np.asarray(y), np.clip(p, 1e-7, 1 - 1e-7)
    both = len(np.unique(y)) == 2
    return {
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "pr_auc": float(average_precision_score(y, p)) if both else None,
        "n": len(y),
        "goals": int(y.sum()),
    }


def reliability(y, p):
    y, p = np.asarray(y), np.asarray(p)
    bins = []
    for i in range(10):
        mask = (p >= i / 10) & ((p < (i + 1) / 10) if i < 9 else (p <= 1))
        if mask.any():
            bins.append(
                {
                    "lower": i / 10,
                    "upper": (i + 1) / 10,
                    "n": int(mask.sum()),
                    "predicted": float(p[mask].mean()),
                    "observed": float(y[mask].mean()),
                }
            )
    return bins


def match_bootstrap(y, probabilities, match_ids, *, replicates=1000, seed=2026):
    """Resample matches with replacement and retain all their shots, paired across models."""
    y = np.asarray(y)
    ids, group = np.unique(match_ids, return_inverse=True)
    counts = np.bincount(group)
    weights = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1 / len(ids)), size=replicates
    )
    denominator = weights @ counts
    samples, intervals = {}, {}
    for name, prediction in probabilities.items():
        p = np.clip(prediction, 1e-7, 1 - 1e-7)
        losses = {"log_loss": -(y * np.log(p) + (1 - y) * np.log1p(-p)), "brier": (y - p) ** 2}
        samples[name], intervals[name] = {}, {}
        for metric, loss in losses.items():
            means = (weights @ np.bincount(group, weights=loss)) / denominator
            samples[name][metric] = means
            intervals[name][metric] = [float(v) for v in np.quantile(means, [0.025, 0.975])]
    return intervals, samples


def paired_difference(samples, left, right):
    return {
        metric: [
            float(v)
            for v in np.quantile(samples[left][metric] - samples[right][metric], [0.025, 0.975])
        ]
        for metric in ("log_loss", "brier")
    }


def evaluate_predictions(rows, predictions, replicates=1000):
    y = np.array([r["label"] for r in rows])
    intervals, samples = match_bootstrap(
        y, predictions, [r["match_id"] for r in rows], replicates=replicates
    )
    results = {}
    for name, p in predictions.items():
        results[name] = {
            **scores(y, p),
            "intervals": intervals[name],
            "reliability": reliability(y, p),
            "calibration": fit_sigmoid(y, p) if len(np.unique(y)) == 2 else None,
        }
    return results, samples
