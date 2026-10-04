"""Additive, retrospective diagnostics of trusted local frozen xG artifacts.

This module never retrains or rewrites a v1 artifact, protocol, prediction or result.
The original feature/fitting/metrics modules remain untouched because their bytes are
part of the v1 artifact locks. This offline module is not imported by web requests.
"""

import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from sklearn.exceptions import ConvergenceWarning

from tactigraph.api.diagnostics import calibration_summary_reason
from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.db import DatasetReport, ModelRelease, SourceManifest, initialize, make_engine
from tactigraph.models.experiment import code_hash, load_protocol
from tactigraph.models.features import FEATURES, digest
from tactigraph.models.fitting import calibrate, fit_sigmoid, labels, predict
from tactigraph.models.metrics import scores

GROUPS = {
    "shot_geometry": ["x", "y", "distance", "opening_angle"],
    "assisting_pass_context": [
        "assist_cross",
        "assist_cutback",
        "assist_x",
        "assist_y",
        "assist_height",
    ],
}
GROUPS.update(
    {feature: [feature] for feature in FEATURES if feature not in sum(GROUPS.values(), [])}
)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calibration_diagnostic(y, probabilities):
    """Diagnostic regression only, with explicit reasons for degenerate samples."""
    y, p = np.asarray(y), np.asarray(probabilities, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or len(y) != len(p):
        raise ValueError("Calibration inputs must be equally sized one-dimensional arrays")
    if not np.isin(y, (0, 1)).all() or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Calibration requires binary labels and finite probabilities in [0, 1]")
    result = {
        "calibration": None,
        "calibration_reason": None,
        "n": len(y),
        "positives": int(y.sum()),
    }
    # Match the clipping performed by the original sigmoid implementation.
    constant = len(p) > 0 and np.ptp(np.clip(p, 1e-7, 1 - 1e-7)) <= 1e-12
    reason = calibration_summary_reason("prevalence" if constant else "", len(y), int(y.sum()))
    if reason:
        return {**result, "calibration_reason": reason}
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ConvergenceWarning)
        parameters = fit_sigmoid(y, p)
    if any(issubclass(w.category, ConvergenceWarning) for w in captured):
        reason = "Calibration diagnostic did not converge."
    elif not all(np.isfinite(value) for value in parameters.values()):
        reason = "Calibration diagnostic did not produce finite parameters."
    return {
        **result,
        "calibration": parameters if reason is None else None,
        "calibration_reason": reason,
    }


def grouped_permutation_importance(model, rows, *, repeats=20, seed=2026, groups=None):
    """Swap whole feature groups from one donor row; keep labels and row metadata fixed."""
    if not rows or repeats < 2:
        raise ValueError("Grouped importance needs observations and at least two repeats")
    groups = GROUPS if groups is None else groups
    if not groups or any(
        not columns or not set(columns) <= set(FEATURES) for columns in groups.values()
    ):
        raise ValueError("Importance groups must contain only allowlisted model features")
    baseline = scores(labels(rows), calibrate(model["calibrator"], predict(model, rows)))[
        "log_loss"
    ]
    rng, output = np.random.default_rng(seed), []
    for group, columns in groups.items():
        changes = []
        for _ in range(repeats):
            order = rng.permutation(len(rows))
            modified = [
                {**row, **{column: rows[donor][column] for column in columns}}
                for row, donor in zip(rows, order, strict=True)
            ]
            loss = scores(labels(rows), calibrate(model["calibrator"], predict(model, modified)))[
                "log_loss"
            ]
            changes.append(loss - baseline)
        output.append(
            {
                "group": group,
                "features": list(columns),
                "mean_log_loss_increase": float(np.mean(changes)),
                "std": float(np.std(changes)),
                "repeats": repeats,
            }
        )
    return sorted(output, key=lambda item: item["mean_log_loss_increase"], reverse=True)


def read_frozen_bundle(directory, protocol_path):
    """Verify locked inputs before deserializing a locally generated joblib bundle."""
    directory = Path(directory)
    protocol, manifest = load_protocol(protocol_path)
    lock = json.loads((directory / "lock.json").read_text(encoding="utf-8"))
    original = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    if (
        original["lock"] != lock
        or original["version"] != protocol["version"]
        or lock["version"] != protocol["version"]
        or lock["protocol_hash"] != digest(protocol)
        or lock["split_hash"] != manifest["sha256"]
    ):
        raise ValueError("Frozen evaluation, protocol or split differs from its original lock")
    if file_hash(directory / "models.joblib") != lock["artifact_hash"]:
        raise ValueError("Frozen model artifact checksum changed")
    if file_hash(directory / "development.parquet") != lock["development_hash"]:
        raise ValueError("Frozen development sample checksum changed")
    # Original v1 did not persist a checksum for this cache. Membership and replay
    # checks below are explicit weaker checks; do not claim an original byte hash.
    all_rows = pl.read_parquet(directory / "test.parquet").to_dicts()
    allowed = {a["match_id"] for a in manifest["assignments"] if a["partition"] == "test"}
    if (
        not all_rows
        or any(r["split"] != "test" or r["match_id"] not in allowed for r in all_rows)
        or len({r["sample_id"] for r in all_rows}) != len(all_rows)
    ):
        raise ValueError("Cached test samples violate the frozen test membership")
    rows = [r for r in all_rows if not r["penalty"]]
    if (
        len(rows) != original["test_non_penalty_shots"]
        or len({r["match_id"] for r in rows}) != original["test_matches"]
    ):
        raise ValueError("Cached test sample counts differ from the original evaluation")
    bundle = joblib.load(directory / "models.joblib")  # Trusted local artifact; hash checked above.
    if bundle["serving"] != original["serving"]:
        raise ValueError("Frozen serving family differs from the original evaluation")
    predictions = {"prevalence": np.full(len(rows), bundle["prevalence"])}
    for family, model in bundle["models"].items():
        raw = predict(model, rows)
        predictions[f"{family}_raw"] = raw
        predictions[family] = calibrate(model["calibrator"], raw)
    for name, values in predictions.items():
        current = scores(labels(rows), values)
        historical = original["metrics"][name]
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc", "n", "goals"):
            if current[metric] is None or historical[metric] is None:
                matches = current[metric] is historical[metric]
            else:
                matches = bool(
                    np.isclose(current[metric], historical[metric], atol=1e-9, rtol=1e-8)
                )
            if not matches:
                raise ValueError(f"Cached test replay differs from original {name} {metric}")
    return bundle, rows, predictions, original, lock


def generate_diagnostics(
    settings, *, repeats=20, seed=2026, artifact_dir=None, output_dir=None, publish=True
):
    """Generate an additive report from already-inspected test predictions; never fit a model."""
    premier = settings.league == "premier-league"
    source_version = "xg-premier-league-v1" if premier else "xg-v1"
    version = "diagnostics-premier-league-v2" if premier else "diagnostics-v2"
    directory = (
        Path(artifact_dir) if artifact_dir is not None else Path("artifacts") / source_version
    )
    output = Path(output_dir) if output_dir is not None else Path("experiments") / version
    protected = (
        "lock.json",
        "evaluation.json",
        "models.joblib",
        "development.parquet",
        "test.parquet",
    )
    before = {name: file_hash(directory / name) for name in protected}
    bundle, rows, predictions, original, lock = read_frozen_bundle(
        directory, Path("configs") / f"{source_version}.json"
    )
    current_hash = code_hash()
    report = {
        "version": version,
        "source_version": source_version,
        "source_commit": SOURCE_COMMIT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "serving": bundle["serving"],
        "test_non_penalty_shots": len(rows),
        "test_matches": len({r["match_id"] for r in rows}),
        "seed": seed,
        "repeats": repeats,
        "calibration": {
            name: calibration_diagnostic(labels(rows), p) for name, p in predictions.items()
        },
        "grouped_permutation_importance": grouped_permutation_importance(
            bundle["models"][bundle["serving"]], rows, repeats=repeats, seed=seed
        ),
        "provenance": {
            "artifact_sha256": before["models.joblib"],
            "original_evaluation_sha256": before["evaluation.json"],
            "original_lock_sha256": before["lock.json"],
            "original_code_hash": lock["code_hash"],
            "current_code_hash": current_hash,
            "original_code_matches_current": current_hash == lock["code_hash"],
            "test_parquet_sha256": before["test.parquet"],
            "diagnostic_code_sha256": file_hash(Path(__file__)),
            "protocol_hash": lock["protocol_hash"],
            "split_hash": lock["split_hash"],
            "test_cache_verification": (
                "Original v1 did not hash test.parquet. Its checksum is first recorded here. "
                "Frozen split membership, unique samples, counts and all original probability "
                "metrics were checked by replay; this is not an original byte-for-byte attestation."
            ),
        },
        "limitations": [
            "Retrospective explanation of an already-inspected test set; "
            "no new held-out performance claim.",
            "Geometry and assisting-pass features each move together from one donor row. "
            "Dependencies between groups may still be broken.",
            "Importance is descriptive, not causal; shuffle standard deviation "
            "is not a confidence interval.",
            "Calibration fits are diagnostics only and are never applied to serving predictions.",
            "Calibration diagnostics require 20 observations, both outcomes and at least "
            "two of each; passing these guards does not establish precise calibration.",
        ],
        "disclosure": "Additive diagnostics-v2. Original v1 scores, predictions, artifacts "
        "and serving selection are preserved.",
    }
    if before != {name: file_hash(directory / name) for name in protected}:
        raise ValueError("Frozen inputs changed while diagnostics were running")
    if publish:
        sources = original["test_metadata"]["source_hashes"]
        engine = make_engine(settings)
        sessions = initialize(engine)
        try:
            with sessions.begin() as session:
                release = session.get(ModelRelease, source_version)
                if (
                    release is None
                    or release.status != "evaluated"
                    or release.artifact_hash != lock["artifact_hash"]
                ):
                    raise ValueError("An evaluated matching xG release must be published first")
                for match, checksum in sources.items():
                    source = session.get(SourceManifest, f"data/events/{match}.json")
                    if (
                        source is None
                        or source.validation_status != "valid"
                        or source.sha256 != checksum
                        or source.commit != SOURCE_COMMIT
                    ):
                        raise ValueError(
                            f"Application source differs from diagnostic source for match {match}"
                        )
                session.merge(
                    DatasetReport(
                        id="diagnostics-v2",
                        generated_at=datetime.now(timezone.utc),
                        payload={"report": report, "source_hashes": sources},
                    )
                )
        finally:
            engine.dispose()
    write_json(output / "results.json", report)
    return report
