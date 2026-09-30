"""Precompute once offline; the web application only reads SQL probabilities."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import polars as pl
from sqlalchemy import insert, select

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.db import (
    ModelRelease,
    Prediction,
    PredictionSample,
    SourceManifest,
    initialize,
    make_engine,
)
from tactigraph.models.experiment import load_protocol
from tactigraph.models.features import FEATURES
from tactigraph.models.fitting import calibrate, predict


def publish(settings, protocol_path):
    config, _ = load_protocol(protocol_path)
    folder = Path("artifacts") / config["version"]
    report = json.loads((folder / "evaluation.json").read_text())
    development = json.loads((folder / "development.json").read_text())
    if (
        hashlib.sha256((folder / "models.joblib").read_bytes()).hexdigest()
        != report["lock"]["artifact_hash"]
    ):
        raise ValueError("Artifact hash mismatch")
    bundle = joblib.load(folder / "models.joblib")
    rows = pl.concat(
        [pl.read_parquet(folder / "development.parquet"), pl.read_parquet(folder / "test.parquet")]
    ).to_dicts()
    non_penalty = [r for r in rows if not r["penalty"]]
    model = bundle["models"][bundle["serving"]]
    values = dict(
        zip(
            [r["sample_id"] for r in non_penalty],
            calibrate(model["calibrator"], predict(model, non_penalty)),
            strict=True,
        )
    )
    public_report = {k: v for k, v in report.items() if k != "test_metadata"}
    # Constant probabilities cannot identify an intercept AND slope calibration regression.
    # Keep probability metrics intact; omit that meaningless diagnostic from the public view.
    public_report["metrics"]["prevalence"]["calibration"] = None
    public_report["development"] = {
        k: development[k]
        for k in (
            "search",
            "calibration_decisions",
            "tuning_paired_difference",
            "counts",
            "penalty",
            "protocol",
        )
    }
    public_report["feature_names"] = FEATURES
    public_report["attribution"] = {
        "provider": "StatsBomb",
        "source_commit": SOURCE_COMMIT,
        "source_url": "https://github.com/hudl/open-data",
        "terms": "Upstream data and branding are excluded from the project code license.",
    }
    write_json(Path("experiments") / config["version"] / "results.json", public_report)
    engine = make_engine(settings)
    sessions = initialize(engine)
    try:
        with sessions.begin() as session:
            existing = session.get(ModelRelease, config["version"])
            if existing:
                if (
                    existing.artifact_hash != report["lock"]["artifact_hash"]
                    or existing.status != "evaluated"
                ):
                    raise ValueError(
                        "Release already exists or is stale; publish a reviewed new version"
                    )
                existing.report = public_report
                return {"version": config["version"], "status": "already_published"}
            sources = {
                **development["metadata"]["source_hashes"],
                **report["test_metadata"]["source_hashes"],
            }
            for mid, sha in sources.items():
                stored = session.get(SourceManifest, f"data/events/{mid}.json")
                if stored is None or stored.sha256 != sha or stored.commit != SOURCE_COMMIT:
                    raise ValueError(
                        f"Application source differs from fitted source for match {mid}"
                    )
            session.add(
                ModelRelease(
                    id=config["version"],
                    family=bundle["serving"],
                    status="evaluated",
                    artifact_hash=report["lock"]["artifact_hash"],
                    run_id=report["lock"]["run_id"],
                    feature_version=config["feature_version"],
                    source_commit=SOURCE_COMMIT,
                    created_at=datetime.now(timezone.utc),
                    report=public_report,
                )
            )
            session.flush()
            known = set(session.scalars(select(PredictionSample.id)))
            samples = [
                {
                    "id": r["sample_id"],
                    "match_id": r["match_id"],
                    "task": "xg",
                    "split": r["split"],
                    "feature_version": config["feature_version"],
                    "label": bool(r["label"]),
                    "penalty": r["penalty"],
                    "features": {f: r[f] for f in FEATURES},
                }
                for r in rows
                if r["sample_id"] not in known
            ]
            if samples:
                session.execute(insert(PredictionSample), samples)
            session.execute(
                insert(Prediction),
                [
                    {
                        "sample_id": r["sample_id"],
                        "model_version": config["version"],
                        "probability": bundle["penalty_rate"]
                        if r["penalty"]
                        else float(values[r["sample_id"]]),
                    }
                    for r in rows
                ],
            )
        return {
            "version": config["version"],
            "status": "published",
            "predictions": len(rows),
            "family": bundle["serving"],
        }
    finally:
        engine.dispose()
