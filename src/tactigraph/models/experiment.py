"""Development is a separate command from the guarded, one-time test evaluation."""

import hashlib
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np
from sklearn.model_selection import GroupKFold

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.models.features import FEATURES, build_dataset, digest, save_samples
from tactigraph.models.fitting import calibrate, fit_model, fit_sigmoid, labels, predict
from tactigraph.models.metrics import match_bootstrap, paired_difference, scores


def code_hash():
    return digest(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).with_name("features.py"),
                Path(__file__).with_name("fitting.py"),
                Path(__file__).with_name("metrics.py"),
            )
        }
    )


def load_protocol(path):
    config = json.loads(Path(path).read_text())
    manifest = json.loads(
        Path(config.get("split_manifest", "configs/splits/wsl-v1.json")).read_text()
    )
    body = {k: v for k, v in manifest.items() if k != "sha256"}
    if digest(body) != manifest["sha256"]:
        raise ValueError("Split manifest was modified")
    return config, manifest


def develop(settings, protocol_path):
    config, manifest = load_protocol(protocol_path)
    target = Path("artifacts") / config["version"]
    target.mkdir(parents=True, exist_ok=True)
    if (target / "lock.json").exists():
        return json.loads((target / "development.json").read_text())
    if (target / "test-access.json").exists():
        raise ValueError("Test already accessed: use a new disclosed experiment version")
    rows, metadata = build_dataset(settings, manifest, {"train", "tuning", "calibration"})
    save_samples(target / "development.parquet", rows)
    subsets = {
        part: [r for r in rows if r["split"] == part and not r["penalty"]]
        for part in ("train", "tuning", "calibration")
    }
    train, tune, calibration = (subsets[p] for p in ("train", "tuning", "calibration"))
    mlflow.set_tracking_uri((Path("artifacts") / "mlruns").resolve().as_uri())
    mlflow.set_experiment("TactiGraph xG")
    search, selected, dev_predictions, artifacts = [], {}, {}, {}
    configs = [("logistic", {"C": c}) for c in config["logistic_c"]]
    configs += [
        (
            "lightgbm",
            {
                "num_leaves": leaves,
                "min_child_samples": child,
                "reg_lambda": reg,
                "learning_rate": config["learning_rate"],
                "n_estimators": config["max_estimators"],
                "max_depth": 5,
            },
        )
        for leaves, child, reg in itertools.product(
            config["lightgbm_num_leaves"],
            config["lightgbm_min_child_samples"],
            config["lightgbm_reg_lambda"],
        )
    ]
    if sum(f == "lightgbm" for f, _ in configs) > 20:
        raise ValueError("LightGBM search budget exceeds 20")
    with mlflow.start_run(run_name=config["version"]) as run:
        mlflow.log_params(
            {
                "version": config["version"],
                "split_hash": manifest["sha256"],
                "protocol_hash": digest(config),
            }
        )
        for family, parameters in configs:
            model = fit_model(train, family, parameters, seed=config["seed"], validation=tune)
            p = predict(model, tune)
            score = scores(labels(tune), p)
            record = {"family": family, "params": parameters, "metrics": score}
            if family == "lightgbm":
                record["params"] = {
                    **parameters,
                    "n_estimators": int(model["estimator"].best_iteration_),
                }
            search.append(record)
            with mlflow.start_run(run_name=f"{family}-{len(search)}", nested=True):
                mlflow.log_params(record["params"])
                mlflow.log_metrics({f"tuning_{k}": v for k, v in score.items() if v is not None})
            if (
                family not in selected
                or score["log_loss"] < selected[family]["metrics"]["log_loss"]
            ):
                selected[family] = record
                dev_predictions[family] = p
            print(
                f"Tuning {len(search)}/{len(configs)}: {family}, log loss={score['log_loss']:.5f}",
                flush=True,
            )
        decisions = {}
        for family, record in selected.items():
            oof = np.zeros(len(train))
            groups = np.array([r["match_id"] for r in train])
            for fit_idx, val_idx in GroupKFold(config["calibration_folds"]).split(
                groups, groups=groups
            ):
                model = fit_model(
                    [train[i] for i in fit_idx], family, record["params"], seed=config["seed"]
                )
                oof[val_idx] = predict(model, [train[i] for i in val_idx])
            sigmoid = fit_sigmoid(labels(train), oof)
            adjusted = calibrate(sigmoid, dev_predictions[family])
            raw_score, adjusted_score = record["metrics"], scores(labels(tune), adjusted)
            retain = (
                adjusted_score["log_loss"]
                <= raw_score["log_loss"] - config["calibration_min_log_loss_improvement"]
                and adjusted_score["brier"] <= raw_score["brier"]
            )
            decisions[family] = {
                "retain_sigmoid": retain,
                "raw": raw_score,
                "sigmoid": adjusted_score,
            }
            if retain:
                dev_predictions[family] = adjusted
            fitted = fit_model(train + tune, family, record["params"], seed=config["seed"])
            fitted["calibrator"] = (
                fit_sigmoid(labels(calibration), predict(fitted, calibration)) if retain else None
            )
            artifacts[family] = fitted
        _, samples = match_bootstrap(
            labels(tune),
            dev_predictions,
            [r["match_id"] for r in tune],
            replicates=config["bootstrap_replicates"],
            seed=config["seed"],
        )
        difference = paired_difference(samples, "lightgbm", "logistic")
        use_lgbm = (
            difference["log_loss"][1] < 0
            and scores(labels(tune), dev_predictions["lightgbm"])["brier"]
            <= scores(labels(tune), dev_predictions["logistic"])["brier"]
        )
        serving = "lightgbm" if use_lgbm else "logistic"
        penalty_rows = [r for r in rows if r["penalty"] and r["split"] in {"train", "tuning"}]
        penalty_rate = (
            sum(r["label"] for r in penalty_rows) + config["penalty_prior_successes"]
        ) / (
            len(penalty_rows) + config["penalty_prior_successes"] + config["penalty_prior_failures"]
        )
        prevalence = (int(labels(train + tune).sum()) + 1) / (len(train + tune) + 2)
        bundle = {
            "models": artifacts,
            "serving": serving,
            "penalty_rate": penalty_rate,
            "prevalence": prevalence,
            "config": config,
            "split_hash": manifest["sha256"],
        }
        joblib.dump(bundle, target / "models.joblib", compress=3)
        report = {
            "version": config["version"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run.info.run_id,
            "source_commit": SOURCE_COMMIT,
            "split_hash": manifest["sha256"],
            "protocol": config,
            "feature_names": FEATURES,
            "search": search,
            "selected": selected,
            "calibration_decisions": decisions,
            "serving": serving,
            "tuning_paired_difference": difference,
            "counts": {p: len(v) for p, v in subsets.items()},
            "metadata": metadata,
            "penalty": {
                "fitting_n": len(penalty_rows),
                "fitting_goals": sum(r["label"] for r in penalty_rows),
                "probability": penalty_rate,
            },
        }
        write_json(target / "development.json", report)
        mlflow.log_artifact(str(target / "development.json"))
        lock = {
            "version": config["version"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_hash": digest(config),
            "code_hash": code_hash(),
            "artifact_hash": hashlib.sha256((target / "models.joblib").read_bytes()).hexdigest(),
            "development_hash": hashlib.sha256(
                (target / "development.parquet").read_bytes()
            ).hexdigest(),
            "split_hash": manifest["sha256"],
            "run_id": run.info.run_id,
        }
        write_json(target / "lock.json", lock)
        mlflow.log_artifact(str(target / "lock.json"))
    return {
        "version": config["version"],
        "serving": serving,
        "locked": True,
        "counts": report["counts"],
    }
