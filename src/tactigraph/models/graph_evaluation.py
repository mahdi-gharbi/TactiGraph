"""Locked graph comparisons; averages across seeds are not prediction ensembles."""

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.db import DatasetReport, initialize, make_engine
from tactigraph.models.graph_experiment import (
    code_hash,
    dataset,
    digest,
    feature_hash,
    file_hash,
    inputs,
    predict_entry,
    source_hash,
)
from tactigraph.models.graph_features import build_dataset, save_samples
from tactigraph.models.metrics import evaluate_predictions, paired_difference, scores


def checked_lock(directory, protocol, manifest, session, settings):
    _, data_lock = dataset(settings, session, manifest, directory)
    lock = json.loads((directory / "lock.json").read_text(encoding="utf-8"))
    expected = {
        "code_hash": code_hash(),
        "feature_hash": feature_hash(),
        "protocol_hash": digest(protocol),
        "dataset_hash": digest(data_lock),
        "source_hash": source_hash(session),
        "split_hash": manifest["sha256"],
        "development_hash": file_hash(directory / "development.json"),
    }
    if any(lock[k] != v for k, v in expected.items()):
        raise ValueError("Graph evaluation inputs differ from the development lock")
    for name, checksum in lock["artifacts"].items():
        if file_hash(directory / name) != checksum:
            raise ValueError(f"Graph artifact checksum changed: {name}")
    return lock


def aggregate_seeds(results, bootstrap, protocol):
    aggregates = {}
    for variant in protocol["variants"]:
        names = [f"{variant}-{seed}" for seed in protocol["seeds"]]
        aggregates[variant] = {
            "seeds": names,
            "metrics": {
                metric: float(np.mean([results[n][metric] for n in names]))
                for metric in ("log_loss", "brier", "roc_auc", "pr_auc")
            },
        }
        bootstrap[variant] = {
            metric: np.mean([bootstrap[n][metric] for n in names], axis=0)
            for metric in ("log_loss", "brier")
        }
        aggregates[variant]["intervals"] = {
            metric: np.quantile(values, [0.025, 0.975]).tolist()
            for metric, values in bootstrap[variant].items()
        }
    return aggregates


def justification(results, aggregates, bootstrap):
    strongest = min(("logistic", "lightgbm"), key=lambda n: results[n]["log_loss"])
    comparisons = {
        name: paired_difference(bootstrap, "gine", name)
        for name in ("logistic", "lightgbm", "no_message", "random_connectivity")
    }
    gates = {
        "strongest_baseline_log_loss": comparisons[strongest]["log_loss"][1] < 0,
        "strongest_baseline_pr_auc": (
            aggregates["gine"]["metrics"]["pr_auc"] >= results[strongest]["pr_auc"]
        ),
        "message_passing_contribution": comparisons["no_message"]["log_loss"][1] < 0,
        "connectivity_contribution": comparisons["random_connectivity"]["log_loss"][1] < 0,
    }
    return {
        "justified": all(gates.values()),
        "strongest_test_baseline": strongest,
        "gates": gates,
        "paired_differences": comparisons,
        "interpretation": (
            "The prespecified graph contribution gates passed on this sample."
            if all(gates.values())
            else "The prespecified gates did not establish a graph contribution; serve the "
            "tabular baseline selected on tuning data."
        ),
    }


def evaluate_locked(directory, protocol, development, rows):
    y = [r["label"] for r in rows]
    probabilities = {"prevalence": np.full(len(rows), development["prevalence"])}
    metadata = {}
    for name, entry in development["entries"].items():
        print(f"Evaluating locked graph model: {name}", flush=True)
        raw, calibrated, latency = predict_entry(directory, entry, rows, protocol)
        probabilities[name] = calibrated
        metadata[name] = {
            "uncalibrated": scores(y, raw),
            "prepared_inference_p95_ms": latency,
            "artifact_hash": entry["artifact_hash"],
        }
    results, bootstrap = evaluate_predictions(
        rows, probabilities, replicates=protocol["bootstrap_replicates"]
    )
    for name, result in results.items():
        result["positive_episodes"] = result.pop("goals")
        result.update(metadata.get(name, {}))
        if "uncalibrated" in result:
            result["uncalibrated"]["positive_episodes"] = result["uncalibrated"].pop("goals")
    aggregates = aggregate_seeds(results, bootstrap, protocol)
    decision = justification(results, aggregates, bootstrap)
    serving = (
        f"gine-{protocol['serving_seed']}" if decision["justified"] else development["baseline"]
    )
    stress = {}
    for group, study in development["stress"].items():
        held_out = set(study["teams"])
        subset = [r for r in rows if r["team_id"] in held_out]
        if not subset:
            stress[group] = {
                "held_out_teams": sorted(held_out),
                "development_counts": study["counts"],
                "status": "no_eligible_test_samples",
                "n": 0,
                "matches": 0,
                "results": {},
                "paired_difference": {},
            }
            continue
        predictions = {}
        for name, entry in study["entries"].items():
            _, predictions[name], _ = predict_entry(directory, entry, subset, protocol)
        group_results, group_bootstrap = evaluate_predictions(
            subset, predictions, replicates=protocol["bootstrap_replicates"]
        )
        for result in group_results.values():
            result["positive_episodes"] = result.pop("goals")
        names = [f"gine-{s}" for s in protocol["seeds"]]
        group_bootstrap["gine"] = {
            metric: np.mean([group_bootstrap[n][metric] for n in names], axis=0)
            for metric in ("log_loss", "brier")
        }
        stress[group] = {
            "status": "evaluated",
            "held_out_teams": sorted(held_out),
            "development_counts": study["counts"],
            "n": len(subset),
            "matches": len({r["match_id"] for r in subset}),
            "results": group_results,
            "paired_difference": paired_difference(
                group_bootstrap, "gine", development["baseline"]
            ),
        }
    pl.DataFrame(
        [
            {
                "sample_id": r["sample_id"],
                "match_id": r["match_id"],
                "label": r["label"],
                **{name: float(p[i]) for name, p in probabilities.items()},
            }
            for i, r in enumerate(rows)
        ]
    ).write_parquet(directory / "test-predictions.parquet")
    return results, aggregates, decision, serving, stress


def stage(settings, protocol_path, command):
    engine = make_engine(settings)
    try:
        sessions = initialize(engine)
        with sessions() as session:
            protocol, manifest, _ = inputs(session, protocol_path)
            directory = Path("artifacts") / protocol["version"]
            lock = checked_lock(directory, protocol, manifest, session, settings)
            development = json.loads((directory / "development.json").read_text(encoding="utf-8"))
            report_path = directory / "evaluation.json"
            if command == "evaluate" and not report_path.exists():
                with (directory / "test-access.json").open("x", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                            "lock_hash": digest(lock),
                            "evaluation_code_hash": file_hash(Path(__file__)),
                        },
                        stream,
                    )
                rows, audit = build_dataset(settings, session, manifest, {"test"})
                if not rows:
                    raise ValueError("No eligible final-test graph samples")
                save_samples(directory / "test.parquet", rows)
                write_json(directory / "test-audit.json", audit)
                results, aggregates, decision, serving, stress = evaluate_locked(
                    directory, protocol, development, rows
                )
                report = {
                    "version": protocol["version"],
                    "status": "evaluated",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source_commit": SOURCE_COMMIT,
                    "protocol": protocol,
                    "lock": lock,
                    "test": {
                        "n": len(rows),
                        "positive_episodes": sum(r["label"] for r in rows),
                        "matches": len({r["match_id"] for r in rows}),
                        "source_episodes": audit["source_episodes"],
                        "exclusions": audit["exclusions"],
                    },
                    "development_counts": development["counts"],
                    "results": results,
                    "seed_aggregates": aggregates,
                    "decision": decision,
                    "serving": serving,
                    "stress": stress,
                    "hardware": {
                        "platform": platform.platform(),
                        "processor": platform.processor(),
                        "torch_threads": protocol["torch_threads"],
                    },
                    "latency_definition": "Warm CPU inference on one prepared sample: p95 of 20 "
                    "calls after 3 warmups; excludes source extraction and model loading.",
                    "seed_definition": "Arithmetic mean of individual seed metrics, not a "
                    "probability ensemble; intervals resample matches and average paired "
                    "seed losses.",
                    "attribution": "Data provided by StatsBomb Open Data",
                    "test_disclosure": protocol["test_disclosure"],
                }
                write_json(report_path, report)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report["lock"] != lock:
                raise ValueError("Graph evaluation and artifact lock differ")
            if command == "publish":
                from tactigraph.models.graph_publish import publish_predictions

                publish_predictions(session, directory, report, development, protocol)
                session.merge(
                    DatasetReport(
                        id="graph", generated_at=datetime.now(timezone.utc), payload=report
                    )
                )
                session.commit()
                write_json(Path("experiments") / protocol["version"] / "results.json", report)
            return {
                "version": report["version"],
                "serving": report["serving"],
                "decision": report["decision"],
                "test": report["test"],
                "status": "published" if command == "publish" else "evaluated",
            }
    finally:
        engine.dispose()
