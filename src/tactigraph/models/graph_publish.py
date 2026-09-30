"""Offline prediction materialization; public requests only read stored values."""

from collections import defaultdict
from datetime import datetime, timezone

import polars as pl

from tactigraph.db import DatasetReport, Event
from tactigraph.models.graph_experiment import predict_entry


def publish_predictions(session, directory, report, development, protocol):
    selected = development["entries"][report["serving"]]
    grouped = defaultdict(list)
    for partition in ("train", "tuning", "calibration", "test"):
        rows = pl.read_parquet(directory / f"{partition}.parquet").to_dicts()
        _, probabilities, _ = predict_entry(directory, selected, rows, protocol)
        for row, probability in zip(rows, probabilities, strict=True):
            event = session.get(Event, row["cutoff_event_id"])
            if event is None or event.match_id != row["match_id"]:
                raise ValueError("Graph cutoff evidence is missing from the current database")
            grouped[row["match_id"]].append(
                {
                    "sample_id": row["sample_id"],
                    "cutoff_event_id": row["cutoff_event_id"],
                    "team_id": row["team_id"],
                    "period": row["period"],
                    "timestamp": event.timestamp,
                    "cutoff_ms": row["cutoff_ms"],
                    "probability": float(probability),
                    "split": partition,
                    "observed_later_shot": row["label"],
                }
            )
    for match_id, samples in grouped.items():
        session.merge(
            DatasetReport(
                id=f"graph-predictions-{match_id}",
                generated_at=datetime.now(timezone.utc),
                payload={
                    "match_id": match_id,
                    "source_commit": report["source_commit"],
                    "model": {
                        "model_version": report["version"],
                        "family": report["serving"],
                        "artifact_hash": selected["artifact_hash"],
                        "run_id": report["lock"]["run_id"],
                        "feature_version": protocol["feature_version"],
                    },
                    "samples": sorted(samples, key=lambda s: (s["period"], s["cutoff_ms"])),
                },
            )
        )
    return sum(len(samples) for samples in grouped.values())
