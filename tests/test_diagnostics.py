import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import pytest

from tactigraph.api.diagnostics import stored_diagnostics
from tactigraph.api.experiment_schemas import ExperimentReport
from tactigraph.api.graph import GraphReport
from tactigraph.config import Settings
from tactigraph.db import DatasetReport, ModelRelease
from tactigraph.models import diagnostics
from tactigraph.models.features import CATEGORICAL, NUMERIC, digest
from tactigraph.models.fitting import fit_model, predict
from tactigraph.models.metrics import scores


@pytest.mark.parametrize(
    ("labels", "probabilities", "reason"),
    [
        ([0, 1] * 20, [0.25] * 40, "Constant predictions"),
        ([0, 1] * 10, [1e-10, 1e-11] * 10, "Constant predictions"),
        ([0, 1], [0.2, 0.8], "at least 20"),
        ([], [], "at least 20"),
        ([0] * 20, np.linspace(0.1, 0.9, 20), "both outcomes"),
        ([0] * 19 + [1], np.linspace(0.1, 0.9, 20), "at least two"),
    ],
)
def test_degenerate_calibration_is_omitted_with_a_reason(labels, probabilities, reason):
    result = diagnostics.calibration_diagnostic(labels, probabilities)
    assert result["calibration"] is None
    assert reason in result["calibration_reason"]


def test_identifiable_calibration_and_invalid_inputs():
    result = diagnostics.calibration_diagnostic([0, 1, 0, 1] * 10, [0.1, 0.3, 0.6, 0.8] * 10)
    assert result["calibration_reason"] is None
    assert all(math.isfinite(value) for value in result["calibration"].values())
    for y, p in [([0], [0.2, 0.3]), ([2], [0.3]), ([0], [float("nan")]), ([0], [1.1])]:
        with pytest.raises(ValueError):
            diagnostics.calibration_diagnostic(y, p)


def test_grouped_shuffles_preserve_geometry_pass_context_labels_and_input(monkeypatch):
    rows = []
    for index in range(20):
        x, y = 90 + index, 32 + index / 2
        rows.append(
            {
                "sample_id": str(index),
                "match_id": index // 5,
                "label": index % 2,
                "x": x,
                "y": y,
                "distance": math.hypot(120 - x, y - 40),
                "opening_angle": math.atan2(8 * (120 - x), (120 - x) ** 2 + (36 - y) * (44 - y)),
                "assist_cross": index % 2,
                "assist_cutback": (index // 2) % 2,
                "assist_x": index,
                "assist_y": index + 5,
                "assist_height": f"height-{index}",
            }
        )
    original, observed = deepcopy(rows), []

    def checked_predict(_model, values):
        observed.append(deepcopy(values))
        for row in values:
            assert row["distance"] == pytest.approx(math.hypot(120 - row["x"], row["y"] - 40))
            assert row["assist_y"] == row["assist_x"] + 5
            assert row["assist_height"] == f"height-{row['assist_x']}"
            assert row["label"] == original[int(row["sample_id"])]["label"]
        return np.array([0.1 + row["x"] / 200 for row in values])

    monkeypatch.setattr(diagnostics, "predict", checked_predict)
    groups = {key: diagnostics.GROUPS[key] for key in ("shot_geometry", "assisting_pass_context")}
    first = diagnostics.grouped_permutation_importance(
        {"calibrator": None}, rows, repeats=3, groups=groups
    )
    second = diagnostics.grouped_permutation_importance(
        {"calibrator": None}, rows, repeats=3, groups=groups
    )
    assert first == second
    assert rows == original
    assert any(sample[0]["x"] != rows[0]["x"] for sample in observed[1:])
    assert (
        next(item for item in first if item["group"] == "assisting_pass_context")[
            "mean_log_loss_increase"
        ]
        == 0
    )
    with pytest.raises(ValueError, match="allowlisted"):
        diagnostics.grouped_permutation_importance(
            {"calibrator": None}, rows, groups={"bad": ["label"]}
        )


@pytest.fixture
def frozen_bundle(tmp_path, monkeypatch):
    directory = tmp_path / "artifacts" / "xg-v1"
    directory.mkdir(parents=True)
    configs = tmp_path / "configs"
    configs.mkdir()
    rows = [
        {
            **{name: float((index * (column + 1)) % 13) for column, name in enumerate(NUMERIC)},
            **{name: "example" for name in CATEGORICAL},
            "sample_id": str(index),
            "match_id": index // 10 + 1,
            "split": "train",
            "penalty": False,
            "label": int(index % 4 == 0),
        }
        for index in range(40)
    ]
    model = {**fit_model(rows, "logistic", {"C": 1}), "calibrator": None}
    bundle = {"serving": "logistic", "prevalence": 0.25, "models": {"logistic": model}}
    joblib.dump(bundle, directory / "models.joblib")
    pl.DataFrame(rows).write_parquet(directory / "development.parquet")
    test = [{**row, "split": "test"} for row in rows]
    pl.DataFrame(test).write_parquet(directory / "test.parquet")
    manifest = {"assignments": [{"match_id": mid, "partition": "test"} for mid in range(1, 5)]}
    manifest["sha256"] = digest(manifest)
    (configs / "split.json").write_text(json.dumps(manifest))
    protocol = {"version": "xg-v1", "split_manifest": "configs/split.json"}
    (configs / "xg-v1.json").write_text(json.dumps(protocol))
    lock = {
        "version": "xg-v1",
        "protocol_hash": digest(protocol),
        "code_hash": "historical-code",
        "split_hash": manifest["sha256"],
        "artifact_hash": diagnostics.file_hash(directory / "models.joblib"),
        "development_hash": diagnostics.file_hash(directory / "development.parquet"),
    }
    (directory / "lock.json").write_text(json.dumps(lock))
    p = predict(model, test)
    values = scores([row["label"] for row in test], p)
    original = {
        "version": "xg-v1",
        "lock": lock,
        "serving": "logistic",
        "test_non_penalty_shots": 40,
        "test_matches": 4,
        "metrics": {
            "prevalence": scores([row["label"] for row in test], np.full(len(test), 0.25)),
            "logistic": values,
            "logistic_raw": values,
        },
        "test_metadata": {"source_hashes": {}},
    }
    (directory / "evaluation.json").write_text(json.dumps(original))
    monkeypatch.chdir(tmp_path)
    return directory


def test_additive_report_preserves_original_results_and_models(frozen_bundle):
    before = {p.name: p.read_bytes() for p in frozen_bundle.iterdir()}
    report = diagnostics.generate_diagnostics(Settings(_env_file=None), repeats=2, publish=False)
    assert report["version"] == "diagnostics-v2"
    assert report["calibration"]["prevalence"]["calibration"] is None
    assert "Constant" in report["calibration"]["prevalence"]["calibration_reason"]
    assert report["provenance"]["original_code_matches_current"] is False
    assert "first recorded here" in report["provenance"]["test_cache_verification"]
    assert {p.name: p.read_bytes() for p in frozen_bundle.iterdir()} == before
    assert Path("experiments/diagnostics-v2/results.json").is_file()


def test_changed_artifact_is_rejected_before_deserialization(frozen_bundle, monkeypatch):
    (frozen_bundle / "models.joblib").write_bytes(b"changed")
    monkeypatch.setattr(diagnostics.joblib, "load", lambda _: pytest.fail("must not deserialize"))
    with pytest.raises(ValueError, match="artifact checksum"):
        diagnostics.read_frozen_bundle(frozen_bundle, "configs/xg-v1.json")


@pytest.mark.parametrize("field,value", [("split", "train"), ("match_id", 999), ("label", 1)])
def test_test_cache_membership_and_metric_changes_are_rejected(frozen_bundle, field, value):
    cache = frozen_bundle / "test.parquet"
    rows = pl.read_parquet(cache).to_dicts()
    rows[1][field] = value
    pl.DataFrame(rows).write_parquet(cache)
    with pytest.raises(ValueError, match="test membership|test replay"):
        diagnostics.read_frozen_bundle(frozen_bundle, "configs/xg-v1.json")


def test_legacy_report_overlay_corrects_calibration_without_rewriting_history():
    for name, schema in [("xg-v1", ExperimentReport), ("graph-v1", GraphReport)]:
        path = Path("experiments") / name / "results.json"
        before = path.read_bytes()
        source = json.loads(before)
        unchanged = deepcopy(source)
        report = schema.model_validate(source)
        metric = report.metrics["prevalence"] if name == "xg-v1" else report.results["prevalence"]
        assert metric.calibration is None
        assert "Constant" in metric.calibration_reason
        assert source == unchanged
        assert path.read_bytes() == before


def test_diagnostics_endpoint_marks_changed_release_stale(frozen_bundle, database):
    report = diagnostics.generate_diagnostics(Settings(_env_file=None), repeats=2, publish=False)
    _, sessions = database
    with sessions.begin() as session:
        assert stored_diagnostics(session).status == "not_generated"
        release = ModelRelease(
            id="xg-v1",
            family="logistic",
            status="evaluated",
            run_id="example",
            artifact_hash=report["provenance"]["artifact_sha256"],
            feature_version="example",
            source_commit=report["source_commit"],
            created_at=datetime.now(timezone.utc),
            report={},
        )
        session.add(release)
        session.add(
            DatasetReport(
                id="diagnostics-v2",
                generated_at=datetime.now(timezone.utc),
                payload={"report": report, "source_hashes": {}},
            )
        )
        session.flush()
        assert stored_diagnostics(session).status == "available"
        release.status = "stale"
        assert stored_diagnostics(session).status == "stale"
