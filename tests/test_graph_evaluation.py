"""Synthetic release-gate and team-disjoint partition checks."""

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from tactigraph.models.graph_evaluation import aggregate_seeds, justification  # noqa: E402
from tactigraph.models.graph_experiment import stress_partitions  # noqa: E402


def test_stress_excludes_matches_on_either_side_and_calibration():
    manifest = {
        "team_stress_groups": {"10": 0, "20": 1, "30": 2},
        "assignments": [
            {"match_id": 1, "home_team_id": 10, "away_team_id": 20},
            {"match_id": 2, "home_team_id": 30, "away_team_id": 10},
            {"match_id": 3, "home_team_id": 20, "away_team_id": 30},
        ],
    }
    rows = {p: [{"match_id": mid} for mid in (1, 2, 3)] for p in ("train", "tuning", "calibration")}
    filtered, held_out = stress_partitions(rows, manifest, 0)
    assert held_out == {10}
    assert all(partition == [{"match_id": 3}] for partition in filtered.values())


def gate_fixture():
    protocol = {"seeds": [1, 2, 3], "variants": ["gine", "no_message", "random_connectivity"]}
    results, samples = {}, {}
    for variant, loss in (("gine", 0.3), ("no_message", 0.4), ("random_connectivity", 0.4)):
        for seed in protocol["seeds"]:
            name = f"{variant}-{seed}"
            results[name] = {"log_loss": loss, "brier": loss, "pr_auc": 0.7, "roc_auc": 0.8}
            samples[name] = {metric: np.full(100, loss) for metric in ("log_loss", "brier")}
    for name in ("logistic", "lightgbm"):
        results[name] = {"log_loss": 0.5, "pr_auc": 0.6}
        samples[name] = {metric: np.full(100, 0.5) for metric in ("log_loss", "brier")}
    return results, samples, aggregate_seeds(results, samples, protocol)


def test_graph_requires_both_topology_ablations_and_baseline_gain():
    results, bootstrap, aggregates = gate_fixture()
    assert justification(results, aggregates, bootstrap)["justified"]
    bootstrap["random_connectivity"]["log_loss"][:] = 0.2
    result = justification(results, aggregates, bootstrap)
    assert not result["justified"]
    assert not result["gates"]["connectivity_contribution"]


def test_graph_rejects_uncertain_improvement_and_worse_precision_recall():
    results, bootstrap, aggregates = gate_fixture()
    bootstrap["gine"]["log_loss"][:10] = 0.6
    assert not justification(results, aggregates, bootstrap)["justified"]
    bootstrap["gine"]["log_loss"][:] = 0.3
    aggregates["gine"]["metrics"]["pr_auc"] = 0.5
    assert not justification(results, aggregates, bootstrap)["justified"]


def test_complete_locked_comparison_exports_predictions_and_stress(tmp_path, monkeypatch):
    import polars as pl

    from tactigraph.models import graph_evaluation as evaluation

    protocol = {
        "seeds": [1, 2, 3],
        "serving_seed": 1,
        "bootstrap_replicates": 20,
        "variants": [
            "gine",
            "no_message",
            "episode_edges",
            "no_edge_time_space",
            "random_connectivity",
        ],
    }
    entries = {name: {"artifact_hash": "synthetic"} for name in ("logistic", "lightgbm")}
    entries.update(
        {
            f"{v}-{s}": {"artifact_hash": "synthetic"}
            for v in protocol["variants"]
            for s in protocol["seeds"]
        }
    )
    rows = [
        {"sample_id": str(i), "match_id": i // 4, "team_id": 10, "label": bool(i % 2)}
        for i in range(12)
    ]
    development = {
        "entries": entries,
        "prevalence": 0.5,
        "baseline": "logistic",
        "stress": {
            "0": {
                "teams": [10],
                "counts": {"train": 8, "tuning": 4, "calibration": 4},
                "entries": {n: entries[n] for n in ("logistic", "gine-1", "gine-2", "gine-3")},
            }
        },
    }

    def prediction(directory, metadata, subset, protocol):
        p = np.asarray([0.7 if row["label"] else 0.3 for row in subset])
        return p, p, 1.0

    monkeypatch.setattr(evaluation, "predict_entry", prediction)
    result, _, decision, serving, stress = evaluation.evaluate_locked(
        tmp_path, protocol, development, rows
    )
    assert result["logistic"]["positive_episodes"] == 6
    assert not decision["justified"]  # Tied losses cannot establish a contribution.
    assert serving == "logistic"
    assert stress["0"]["n"] == 12
    assert stress["0"]["paired_difference"]["log_loss"] == [0.0, 0.0]
    assert pl.read_parquet(tmp_path / "test-predictions.parquet").height == 12
