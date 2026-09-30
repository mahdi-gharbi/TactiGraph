import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np
import polars as pl

from tactigraph.data.pipeline import write_json
from tactigraph.models.experiment import code_hash, load_protocol
from tactigraph.models.features import FEATURES, build_dataset, digest, save_samples
from tactigraph.models.fitting import calibrate, fit_model, fit_sigmoid, labels, predict
from tactigraph.models.metrics import evaluate_predictions, paired_difference, scores


def stress_test(development, test, bundle, manifest):
    family = bundle["serving"]
    template = bundle["models"][family]
    results = []
    for group in range(5):
        teams = {int(t) for t, g in manifest["team_stress_groups"].items() if g == group}
        permitted = [
            r
            for r in development
            if not r["penalty"]
            and r["home_team_id"] not in teams
            and r["away_team_id"] not in teams
        ]
        fit = [r for r in permitted if r["split"] in {"train", "tuning"}]
        calibration = [r for r in permitted if r["split"] == "calibration"]
        held = [r for r in test if r["team_id"] in teams and not r["penalty"]]
        base = {
            "group": group,
            "teams": sorted(teams),
            "fit_shots": len(fit),
            "fit_matches": len({r["match_id"] for r in fit}),
            "calibration_shots": len(calibration),
            "test_shots": len(held),
            "test_matches": len({r["match_id"] for r in held}),
        }
        if (
            not held
            or len(set(labels(fit))) < 2
            or (template["calibrator"] is not None and len(set(labels(calibration))) < 2)
        ):
            results.append({**base, "status": "insufficient_data", "metrics": None})
            continue
        model = fit_model(fit, family, template["params"])
        sigmoid = (
            fit_sigmoid(labels(calibration), predict(model, calibration))
            if template["calibrator"] is not None
            else None
        )
        p = calibrate(sigmoid, predict(model, held))
        results.append({**base, "status": "evaluated", "metrics": scores(labels(held), p)})
    return results


def permutation_importance(model, rows, *, repeats=5):
    baseline = scores(labels(rows), calibrate(model["calibrator"], predict(model, rows)))[
        "log_loss"
    ]
    rng, output = np.random.default_rng(2026), []
    for feature in FEATURES:
        changes = []
        for _ in range(repeats):
            order = rng.permutation(len(rows))
            modified = [{**r, feature: rows[j][feature]} for r, j in zip(rows, order, strict=True)]
            loss = scores(labels(rows), calibrate(model["calibrator"], predict(model, modified)))[
                "log_loss"
            ]
            changes.append(loss - baseline)
        output.append(
            {
                "feature": feature,
                "mean_log_loss_increase": float(np.mean(changes)),
                "std": float(np.std(changes)),
                "repeats": repeats,
            }
        )
    return sorted(output, key=lambda r: r["mean_log_loss_increase"], reverse=True)


def evaluate(settings, protocol_path):
    config, manifest = load_protocol(protocol_path)
    target = Path("artifacts") / config["version"]
    report_path = target / "evaluation.json"
    if report_path.exists():
        return json.loads(report_path.read_text())
    lock = json.loads((target / "lock.json").read_text())
    if lock["protocol_hash"] != digest(config) or lock["code_hash"] != code_hash():
        raise ValueError("Fitted protocol or feature/fitting code changed after freeze")
    artifact_hash = hashlib.sha256((target / "models.joblib").read_bytes()).hexdigest()
    if artifact_hash != lock["artifact_hash"] or lock["split_hash"] != manifest["sha256"]:
        raise ValueError("Model artifact or split changed after freeze")
    if (
        hashlib.sha256((target / "development.parquet").read_bytes()).hexdigest()
        != lock["development_hash"]
    ):
        raise ValueError("Development samples changed after freeze")
    # Mark access before loading outcomes. Interrupted evaluations resume the same locked artifact.
    access = target / "test-access.json"
    if not access.exists():
        write_json(access, {"first_access_at": datetime.now(timezone.utc).isoformat(), **lock})
    bundle = joblib.load(target / "models.joblib")  # Trusted locally generated artifact only.
    all_test, metadata = build_dataset(settings, manifest, {"test"})
    save_samples(target / "test.parquet", all_test)
    rows = [r for r in all_test if not r["penalty"]]
    development = pl.read_parquet(target / "development.parquet").to_dicts()
    predictions = {"prevalence": np.full(len(rows), bundle["prevalence"])}
    for family, model in bundle["models"].items():
        raw = predict(model, rows)
        predictions[f"{family}_raw"] = raw
        predictions[family] = calibrate(model["calibrator"], raw)
    results, samples = evaluate_predictions(rows, predictions, config["bootstrap_replicates"])
    reference_rows = [r for r in rows if r["reference_xg"] is not None]
    reference = (
        scores(labels(reference_rows), [r["reference_xg"] for r in reference_rows])
        if reference_rows
        else None
    )
    serving = bundle["serving"]
    slices = []
    for field in ("shot_type", "body_part", "season_id"):
        for value in sorted({r[field] for r in rows}, key=str):
            indices = [i for i, r in enumerate(rows) if r[field] == value]
            subset = [rows[i] for i in indices]
            slices.append(
                {
                    "field": field,
                    "value": str(value),
                    "n": len(indices),
                    "metrics": scores(labels(subset), predictions[serving][indices])
                    if len(indices) >= 30
                    else None,
                    "warning": "Small slice; uncertainty is high" if len(indices) < 100 else None,
                }
            )
    penalties = [r for r in all_test if r["penalty"]]
    penalty_results = (
        scores(labels(penalties), np.full(len(penalties), bundle["penalty_rate"]))
        if penalties
        else None
    )
    logistic = bundle["models"]["logistic"]
    coefficients = [
        {"feature": name, "coefficient": float(value)}
        for name, value in zip(
            logistic["preprocessor"].get_feature_names_out(),
            logistic["estimator"].coef_[0],
            strict=True,
        )
    ]
    started = time.perf_counter()
    for _ in range(5):
        predict(bundle["models"][serving], rows)
    batch_ms = (time.perf_counter() - started) / 5 * 1000
    report = {
        "version": config["version"],
        "status": "evaluated",
        "serving": serving,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "lock": lock,
        "test_matches": len({r["match_id"] for r in rows}),
        "test_non_penalty_shots": len(rows),
        "metrics": results,
        "paired_lightgbm_minus_logistic": paired_difference(samples, "lightgbm", "logistic"),
        "reference": {"name": "StatsBomb xG (uncontrolled reference)", "metrics": reference},
        "penalties": {"probability": bundle["penalty_rate"], "test_metrics": penalty_results},
        "slices": slices,
        "logistic_coefficients": coefficients,
        "permutation_importance": permutation_importance(bundle["models"][serving], rows),
        "team_stress": stress_test(development, all_test, bundle, manifest),
        "test_metadata": metadata,
        "prediction_batch_ms": batch_ms,
        "limitations": [
            "Event data only; no tracking or freeze-frame features.",
            "Chronological evaluation; later matches may introduce temporal distribution shift.",
            "Serving selection was locked on tuning data; final-test results do not change it.",
            "Calibration and family selection reuse tuning data; "
            "only final-test results are held-out estimates.",
            "Intervals resample whole matches; PR-AUC is average precision.",
            "Permutation importance is descriptive, not causal; "
            "correlated features can share importance.",
            "Stress folds refit preprocessing and calibration without held-out teams; "
            "primary hyperparameters stay fixed.",
            "Training/tuning match predictions are in-sample; "
            "calibration matches fit the calibrator when retained.",
            "StatsBomb xG has uncontrolled training data and information access.",
        ],
    }
    write_json(report_path, report)
    mlflow.set_tracking_uri((Path("artifacts") / "mlruns").resolve().as_uri())
    with mlflow.start_run(run_id=lock["run_id"]):
        for family, result in results.items():
            mlflow.log_metrics(
                {
                    f"test_{family}_{k}": result[k]
                    for k in ("log_loss", "brier", "roc_auc", "pr_auc")
                    if result[k] is not None
                }
            )
        mlflow.log_artifact(str(report_path))
    # Public summary excludes source hashes and per-event data.
    summary = {k: v for k, v in report.items() if k != "test_metadata"}
    write_json(Path("experiments") / config["version"] / "results.json", summary)
    return summary
