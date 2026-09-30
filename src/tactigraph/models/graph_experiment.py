"""Resumable development; explicit one-time test access; no training in the API."""

import hashlib
import itertools
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np
import polars as pl
import torch

from tactigraph.data.pipeline import write_json
from tactigraph.db import SourceManifest, initialize, make_engine
from tactigraph.models import graph_network as neural
from tactigraph.models import graph_tabular as tabular
from tactigraph.models.fitting import calibrate, fit_sigmoid
from tactigraph.models.graph_features import build_dataset, save_samples
from tactigraph.models.metrics import scores
from tactigraph.models.xt_experiment import digest, inputs, source_hash


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature_hash():
    package = Path(__file__).parent.parent
    return digest(
        {
            name: file_hash(package / name)
            for name in (
                "models/graph_features.py",
                "data/derive.py",
                "data/ingest.py",
                "data/geometry.py",
            )
        }
    )


def code_hash():
    return digest(
        {
            name: file_hash(Path(__file__).with_name(name))
            for name in (
                "graph_experiment.py",
                "graph_features.py",
                "graph_network.py",
                "graph_tabular.py",
                "metrics.py",
                "fitting.py",
            )
        }
    )


def seal_dataset(directory, manifest):
    files = [
        directory / f"{p}{suffix}"
        for p in ("train", "tuning", "calibration")
        for suffix in (".parquet", "-audit.json")
    ]
    result = {
        "feature_hash": feature_hash(),
        "split_hash": manifest["sha256"],
        "files": {p.name: file_hash(p) for p in files},
    }
    write_json(directory / "dataset-lock.json", result)
    return result


def dataset(settings, session, manifest, directory):
    lock_path = directory / "dataset-lock.json"
    if not lock_path.exists():
        for partition in ("train", "tuning", "calibration"):
            rows, audit = build_dataset(settings, session, manifest, {partition})
            save_samples(directory / f"{partition}.parquet", rows)
            write_json(directory / f"{partition}-audit.json", audit)
        seal_dataset(directory, manifest)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["feature_hash"] != feature_hash() or lock["split_hash"] != manifest["sha256"]:
        raise ValueError("Graph dataset definition changed; use a new version")
    for name, checksum in lock["files"].items():
        if file_hash(directory / name) != checksum:
            raise ValueError(f"Graph cache checksum changed: {name}")
    for partition in ("train", "tuning", "calibration"):
        audit = json.loads((directory / f"{partition}-audit.json").read_text(encoding="utf-8"))
        for mid, checksum in audit["source_hashes"].items():
            if session.get(SourceManifest, f"data/events/{mid}.json").sha256 != checksum:
                raise ValueError("Graph cached sources differ from ingested snapshot")
    return {
        p: pl.read_parquet(directory / f"{p}.parquet").to_dicts()
        for p in ("train", "tuning", "calibration")
    }, lock


def calibrator(rows, probabilities):
    if len({r["label"] for r in rows}) < 2:
        raise ValueError(
            "Calibration needs both labels; do not silently publish an uncalibrated model"
        )
    return fit_sigmoid([r["label"] for r in rows], probabilities)


def save_entry(directory, name, model, metadata, is_neural):
    path = directory / (name + (".pt" if is_neural else ".joblib"))
    if is_neural:
        torch.save(model.state_dict(), path)
    else:
        joblib.dump(model, path)
    metadata.update(file=path.name, artifact_hash=file_hash(path))
    write_json(directory / f"{name}.json", metadata)
    return metadata


def entry(directory, name):
    path = directory / f"{name}.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    if file_hash(directory / result["file"]) != result["artifact_hash"]:
        raise ValueError(f"Checkpoint checksum changed: {name}")
    return result


def fit_neural(directory, name, rows, tuning, calibration, variant, seed, protocol, epochs=None):
    existing = entry(directory, name)
    if existing:
        return existing
    history = None
    if epochs is None:
        model, history = neural.train(rows, tuning, variant, seed, protocol)
        tuning_p = neural.predict(model, [neural.graph_data(r, variant, seed) for r in tuning])
        tuning_metrics = scores([r["label"] for r in tuning], tuning_p)
        epochs = history["selected_epoch"]
    else:
        tuning_metrics = None
    model, refit = neural.train(rows + tuning, [], variant, seed, protocol, epochs=epochs)
    p = neural.predict(model, [neural.graph_data(r, variant, seed) for r in calibration])
    return save_entry(
        directory,
        name,
        model,
        {
            "kind": "neural",
            "variant": variant,
            "seed": seed,
            "epochs": epochs,
            "parameters": refit["parameters"],
            "selection": history,
            "tuning": tuning_metrics,
            "calibration": calibrator(calibration, p),
            "fitting_samples": len(rows) + len(tuning),
            "calibration_samples": len(calibration),
        },
        True,
    )


def fit_tabular(directory, name, rows, calibration, family, parameters, tuning_score=None):
    existing = entry(directory, name)
    if existing:
        return existing
    model = tabular.fit(rows, family, parameters)
    return save_entry(
        directory,
        name,
        model,
        {
            "kind": "tabular",
            "family": family,
            "parameters": parameters,
            "calibration": calibrator(calibration, tabular.predict(model, calibration)),
            "fitting_samples": len(rows),
            "calibration_samples": len(calibration),
            "tuning": tuning_score,
        },
        False,
    )


def predict_entry(directory, metadata, rows, protocol):
    if metadata["kind"] == "neural":
        neural.seed_everything(metadata["seed"], protocol["torch_threads"])
        model = neural.ShotAfterThirdPass(
            metadata["variant"], protocol["hidden_width"], protocol["dropout"]
        )
        model.load_state_dict(
            torch.load(directory / metadata["file"], weights_only=True, map_location="cpu")
        )
        prepared = [neural.graph_data(r, metadata["variant"], metadata["seed"]) for r in rows]
        p = neural.predict(model, prepared)

        def predict_one():
            return neural.predict(model, prepared[:1])
    else:
        model = joblib.load(directory / metadata["file"])
        p = tabular.predict(model, rows)

        def predict_one():
            return tabular.predict(model, rows[:1])

    for _ in range(3):
        predict_one()
    timings = []
    for _ in range(20):
        start = time.perf_counter()
        predict_one()
        timings.append((time.perf_counter() - start) * 1000)
    return p, calibrate(metadata["calibration"], p), float(np.quantile(timings, 0.95))


def stress_partitions(rows_by_split, manifest, group):
    held_out = {int(t) for t, g in manifest["team_stress_groups"].items() if g == group}
    excluded = {
        a["match_id"]
        for a in manifest["assignments"]
        if a["home_team_id"] in held_out or a["away_team_id"] in held_out
    }
    return {
        p: [r for r in rows if r["match_id"] not in excluded] for p, rows in rows_by_split.items()
    }, held_out


def develop(directory, data, manifest, protocol):
    train, tuning, calibration = (data[p] for p in ("train", "tuning", "calibration"))
    selection_path = directory / "tabular-selection.json"
    if selection_path.exists():
        selections = json.loads(selection_path.read_text(encoding="utf-8"))
    else:
        selections = {}
        for family in ("logistic", "lightgbm"):
            candidates = (
                [{"C": c} for c in protocol["logistic_c"]]
                if family == "logistic"
                else [
                    {
                        "num_leaves": leaves,
                        "min_child_samples": child,
                        "n_estimators": protocol["lightgbm_max_estimators"],
                    }
                    for leaves, child in itertools.product(
                        protocol["lightgbm_leaves"], protocol["lightgbm_min_child_samples"]
                    )
                ]
            )
            results = []
            for parameters in candidates:
                fitted = tabular.fit(train, family, parameters, tuning)
                values = scores([r["label"] for r in tuning], tabular.predict(fitted, tuning))
                selected = dict(parameters)
                if family == "lightgbm":
                    selected["n_estimators"] = fitted["estimator"].best_iteration_
                results.append({"parameters": selected, "scores": values})
            selections[family] = {
                "candidates": results,
                "chosen": min(results, key=lambda r: r["scores"]["log_loss"]),
            }
        write_json(selection_path, selections)
    baseline = min(selections, key=lambda f: selections[f]["chosen"]["scores"]["log_loss"])
    entries = {}
    for family in selections:
        chosen = selections[family]["chosen"]
        entries[family] = fit_tabular(
            directory,
            family,
            train + tuning,
            calibration,
            family,
            chosen["parameters"],
            chosen["scores"],
        )
    for variant in protocol["variants"]:
        for seed in protocol["seeds"]:
            name = f"{variant}-{seed}"
            print(f"Developing {name}", flush=True)
            entries[name] = fit_neural(
                directory, name, train, tuning, calibration, variant, seed, protocol
            )
    stress = {}
    for group in sorted(set(manifest["team_stress_groups"].values())):
        filtered, teams = stress_partitions(data, manifest, group)
        name = f"stress-{group}-{baseline}"
        current = {
            "teams": sorted(teams),
            "counts": {p: len(r) for p, r in filtered.items()},
            "entries": {},
        }
        current["entries"][baseline] = fit_tabular(
            directory,
            name,
            filtered["train"] + filtered["tuning"],
            filtered["calibration"],
            baseline,
            selections[baseline]["chosen"]["parameters"],
        )
        for seed in protocol["seeds"]:
            name = f"stress-{group}-gine-{seed}"
            print(f"Developing {name}", flush=True)
            current["entries"][f"gine-{seed}"] = fit_neural(
                directory,
                name,
                filtered["train"],
                filtered["tuning"],
                filtered["calibration"],
                "gine",
                seed,
                protocol,
                epochs=entries[f"gine-{seed}"]["epochs"],
            )
        stress[str(group)] = current
    mlflow.set_tracking_uri(Path("artifacts/mlruns").resolve().as_uri())
    mlflow.set_experiment("TactiGraph third-pass graphs")
    with mlflow.start_run(run_name=protocol["version"]) as run:
        mlflow.log_params(
            {
                "baseline": baseline,
                "feature_version": protocol["feature_version"],
                "seeds": str(protocol["seeds"]),
                "split_hash": manifest["sha256"],
            }
        )
        mlflow.log_metrics(
            {
                f"tuning_{name}_log_loss": meta["tuning"]["log_loss"]
                for name, meta in entries.items()
            }
        )
        run_id = run.info.run_id
    return {
        "entries": entries,
        "stress": stress,
        "baseline": baseline,
        "selection": selections,
        "prevalence": float(np.mean([r["label"] for r in train + tuning])),
        "run_id": run_id,
        "counts": {p: len(r) for p, r in data.items()},
    }


def stage(settings, protocol_path, command):
    engine = make_engine(settings)
    try:
        sessions = initialize(engine)
        with sessions() as session:
            protocol, manifest, _ = inputs(session, protocol_path)
            directory = Path("artifacts") / protocol["version"]
            directory.mkdir(parents=True, exist_ok=True)
            data, dataset_lock = dataset(settings, session, manifest, directory)
            signature = {
                "code_hash": code_hash(),
                "feature_hash": feature_hash(),
                "protocol_hash": digest(protocol),
                "dataset_hash": digest(dataset_lock),
                "source_hash": source_hash(session),
                "split_hash": manifest["sha256"],
            }
            working = directory / "working-lock.json"
            if working.exists() and json.loads(working.read_text(encoding="utf-8")) != signature:
                raise ValueError("Development inputs changed; use a new graph version")
            write_json(working, signature)
            if command == "dataset":
                return {
                    "version": protocol["version"],
                    "counts": {p: len(r) for p, r in data.items()},
                }
            development_path = directory / "development.json"
            lock_path = directory / "lock.json"
            if command == "develop":
                if not lock_path.exists():
                    if (directory / "test-access.json").exists():
                        raise ValueError("Test already opened for this version")
                    development = develop(directory, data, manifest, protocol)
                    write_json(development_path, development)
                    artifacts = {
                        p.name: file_hash(p)
                        for pattern in ("*.pt", "*.joblib")
                        for p in directory.glob(pattern)
                    }
                    write_json(
                        lock_path,
                        {
                            **signature,
                            "artifact_hash": digest(artifacts),
                            "artifacts": artifacts,
                            "development_hash": file_hash(development_path),
                            "run_id": development["run_id"],
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                if any(lock[k] != v for k, v in signature.items()):
                    raise ValueError("Locked graph inputs changed")
                if file_hash(development_path) != lock["development_hash"]:
                    raise ValueError("Locked graph development metadata changed")
                for name, checksum in lock["artifacts"].items():
                    if file_hash(directory / name) != checksum:
                        raise ValueError(f"Locked graph artifact changed: {name}")
                return {"version": protocol["version"], "status": "locked"}
            raise ValueError("Evaluation is implemented in the separate graph evaluation module")
    finally:
        engine.dispose()
