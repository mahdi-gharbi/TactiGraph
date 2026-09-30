"""Offline development, locked test evaluation, and aggregate-only publication."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
from sqlalchemy import select

from tactigraph.config import PIPELINE_VERSION, SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.data.splits import manifest_digest
from tactigraph.db import DatasetReport, SourceManifest, SplitAssignment, initialize, make_engine
from tactigraph.models.metrics import match_bootstrap, paired_difference, scores
from tactigraph.models.xt import fit, predict
from tactigraph.models.xt_data import extract


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def code_hash():
    return digest(
        {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("xt.py", "xt_data.py", "xt_experiment.py", "metrics.py")
        }
    )


def source_hash(session):
    return digest(
        {
            "pipeline": PIPELINE_VERSION,
            "sources": [
                list(r)
                for r in session.execute(
                    select(
                        SourceManifest.path, SourceManifest.commit, SourceManifest.sha256
                    ).order_by(SourceManifest.path)
                )
            ],
        }
    )


def inputs(session, protocol_path):
    protocol = json.loads(protocol_path.read_text())
    if not protocol["version"].replace("-", "").isalnum():
        raise ValueError("Invalid experiment version")
    manifest = json.loads(
        Path(protocol.get("split_manifest", "configs/splits/wsl-v1.json")).read_text()
    )
    expected = manifest_digest({k: v for k, v in manifest.items() if k != "sha256"})
    if expected != manifest["sha256"] or manifest["source_commit"] != SOURCE_COMMIT:
        raise ValueError("Invalid split manifest")
    assigned = {
        r.match_id: (r.partition, r.manifest_hash) for r in session.scalars(select(SplitAssignment))
    }
    if assigned != {r["match_id"]: (r["partition"], expected) for r in manifest["assignments"]}:
        raise ValueError("Database split assignments differ from the frozen manifest")
    partitions = {
        name: [r["match_id"] for r in manifest["assignments"] if r["partition"] == name]
        for name in ("train", "tuning", "calibration", "test")
    }
    return protocol, manifest, partitions


def checked_lock(directory, protocol, manifest, session):
    lock = json.loads((directory / "lock.json").read_text())
    artifact = json.loads((directory / "model.json").read_text())
    expected = {
        "protocol_hash": digest(protocol),
        "code_hash": code_hash(),
        "split_hash": manifest["sha256"],
        "source_hash": source_hash(session),
        "artifact_hash": digest(artifact),
    }
    if any(lock[k] != v for k, v in expected.items()):
        raise ValueError("xT lock changed; use a new experiment version with prior-test disclosure")
    return lock, artifact


def fit_protocol(episodes, grid, protocol):
    return fit(
        episodes,
        tuple(grid),
        protocol["action_prior_mass"],
        protocol["scoring_prior_strength"],
        protocol["tolerance"],
        protocol["max_iterations"],
    )


def stage(settings, protocol_path, command):
    engine = make_engine(settings)
    try:
        sessions = initialize(engine)
        with sessions() as session:
            protocol, manifest, partitions = inputs(session, protocol_path)
            directory = Path("artifacts") / protocol["version"]
            directory.mkdir(parents=True, exist_ok=True)
            if command == "develop":
                if (directory / "lock.json").exists():
                    checked_lock(directory, protocol, manifest, session)
                    return json.loads((directory / "development.json").read_text())
                if (directory / "test-access.json").exists():
                    raise ValueError("This version has already accessed the test set")
                training, training_audit = extract(session, partitions["train"])
                tuning, tuning_audit = extract(session, partitions["tuning"])
                if not training or not tuning:
                    raise ValueError("Empty development partition")
                candidates = []
                for grid in protocol["grids"]:
                    model = fit_protocol(training, grid, protocol)
                    probabilities = predict(tuning, model)
                    candidates.append(
                        {
                            "grid": grid,
                            "scores": {
                                name: scores([e.goal for e in tuning], values)
                                for name, values in probabilities.items()
                            },
                            "iterations": model["iterations"],
                        }
                    )
                chosen = min(candidates, key=lambda c: c["scores"]["xt"]["brier"])
                artifact = fit_protocol(training + tuning, chosen["grid"], protocol)
                artifact.update(
                    version=protocol["version"],
                    source_commit=SOURCE_COMMIT,
                    pipeline_version=PIPELINE_VERSION,
                )
                tracking = Path("artifacts/mlruns").resolve()
                mlflow.set_tracking_uri(tracking.as_uri())
                mlflow.set_experiment("TactiGraph xT")
                with mlflow.start_run(run_name=protocol["version"]) as run:
                    mlflow.log_params(
                        {
                            "grid": str(chosen["grid"]),
                            "action_prior": protocol["action_prior_mass"],
                            "scoring_prior": protocol["scoring_prior_strength"],
                            "split_hash": manifest["sha256"],
                        }
                    )
                    mlflow.log_metrics(
                        {
                            "tuning_brier": chosen["scores"]["xt"]["brier"],
                            "tuning_log_loss": chosen["scores"]["xt"]["log_loss"],
                        }
                    )
                    run_id = run.info.run_id
                development = {
                    "version": protocol["version"],
                    "status": "locked",
                    "selected_grid": chosen["grid"],
                    "candidates": candidates,
                    "train": training_audit,
                    "tuning": tuning_audit,
                    "fitting_episodes": artifact["episodes"],
                    "iterations": artifact["iterations"],
                }
                write_json(directory / "model.json", artifact)
                write_json(directory / "development.json", development)
                write_json(
                    directory / "lock.json",
                    {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id,
                        "protocol_hash": digest(protocol),
                        "code_hash": code_hash(),
                        "split_hash": manifest["sha256"],
                        "source_hash": source_hash(session),
                        "artifact_hash": digest(artifact),
                    },
                )
                return development
            lock, artifact = checked_lock(directory, protocol, manifest, session)
            report_path = directory / "evaluation.json"
            if command == "evaluate" and not report_path.exists():
                marker = directory / "test-access.json"
                # Exclusive marker: never silently evaluate the final test twice after a crash.
                with marker.open("x", encoding="utf-8") as file:
                    json.dump(
                        {
                            "locked_artifact_hash": lock["artifact_hash"],
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                        },
                        file,
                    )
                episodes, audit = extract(session, partitions["test"])
                if not episodes:
                    raise ValueError("No eligible test episodes")
                probabilities = predict(episodes, artifact)
                y = np.asarray([e.goal for e in episodes])
                intervals, samples = match_bootstrap(
                    y,
                    probabilities,
                    [e.match_id for e in episodes],
                    replicates=protocol["bootstrap_replicates"],
                    seed=protocol["seed"],
                )
                report = {
                    "version": protocol["version"],
                    "status": "evaluated",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source_commit": SOURCE_COMMIT,
                    "protocol": protocol,
                    "lock": lock,
                    "model": artifact,
                    "development": json.loads((directory / "development.json").read_text()),
                    "test": audit,
                    "results": {
                        name: {**scores(y, values), "intervals": intervals[name]}
                        for name, values in probabilities.items()
                    },
                    "paired_differences": {
                        baseline: paired_difference(samples, "xt", baseline)
                        for baseline in ("global", "no_transition")
                    },
                    "attribution": "Data provided by StatsBomb Open Data",
                    "source_url": f"https://github.com/hudl/open-data/tree/{SOURCE_COMMIT}",
                    "interpretation": protocol["interpretation"],
                    "test_disclosure": protocol["test_policy"],
                }
                write_json(report_path, report)
            report = json.loads(report_path.read_text())
            if report["lock"] != lock or digest(report["model"]) != lock["artifact_hash"]:
                raise ValueError("Evaluation and frozen artifact differ")
            if command == "publish":
                session.merge(
                    DatasetReport(id="xt", generated_at=datetime.now(timezone.utc), payload=report)
                )
                session.commit()
                write_json(Path("experiments") / protocol["version"] / "results.json", report)
            return {
                "version": protocol["version"],
                "status": "published" if command == "publish" else "evaluated",
                "grid": artifact["grid"],
                "test": report["test"],
                "results": report["results"],
            }
    finally:
        engine.dispose()
