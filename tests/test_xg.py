from copy import deepcopy

import numpy as np
import pytest

from tactigraph.models.features import FEATURES, feature_row, match_samples
from tactigraph.models.fitting import calibrate, fit_model, fit_sigmoid, predict
from tactigraph.models.metrics import match_bootstrap, paired_difference, scores


def test_shot_geometry_and_prefix_invariance(payload):
    _, events, _ = payload
    shot = events[1]
    original = feature_row(shot, events)
    assert original["distance"] == 20
    assert original["opening_angle"] == pytest.approx(2 * np.arctan(4 / 20))
    changed = deepcopy(events)
    for e in changed:
        if e["index"] > shot["index"]:
            e.update(location=[0, 0], team={"id": 999}, player={"id": 888})
            e["shot"] = {"outcome": {"name": "Goal"}, "statsbomb_xg": 1}
    altered_shot = deepcopy(shot)
    altered_shot["shot"].update(
        outcome={"name": "Saved"},
        statsbomb_xg=0.99,
        end_location=[120, 40, 1],
        freeze_frame=[{"junk": True}],
    )
    assert feature_row(altered_shot, changed) == original
    assert set(original) == set(FEATURES)
    assert not {"team_id", "player_id", "label", "reference_xg", "outcome"} & set(original)


def test_assist_requires_prior_same_team_same_possession(payload):
    _, events, _ = payload
    shot, passing = deepcopy(events[1]), deepcopy(events[0])
    passing["possession"] = shot["possession"]
    shot["shot"]["key_pass_id"] = passing["id"]
    passing["pass"]["cross"] = True
    assert feature_row(shot, [passing])["assist_cross"] == 1
    passing["index"] = shot["index"] + 1
    assert feature_row(shot, [passing])["assist_cross"] is None
    passing["index"] = 1
    passing["team"]["id"] = 999
    assert feature_row(shot, [passing])["assist_cross"] is None


def test_targets_penalties_missing_geometry_and_shootout(payload):
    _, events, _ = payload
    events[2]["shot"]["type"]["name"] = "Penalty"
    assignment = {
        "match_id": 1,
        "season_id": 4,
        "partition": "train",
        "home_team_id": 10,
        "away_team_id": 20,
    }
    rows, excluded = match_samples(events, assignment, "1.0.3")
    assert len(rows) == 3
    assert sum(r["penalty"] for r in rows) == 1
    assert sum(r["label"] for r in rows) == 1
    assert excluded == {"missing_or_outside_location": 1, "shootout": 1}


def synthetic_rows(payload, count=100):
    base = feature_row(payload[1][1], payload[1])
    return [
        {
            **base,
            "x": 80 + i % 35,
            "distance": 40 - i % 35,
            "label": int(i % 5 == 0),
            "split": "train",
            "penalty": False,
            "match_id": i // 10,
            "sample_id": str(i),
        }
        for i in range(count)
    ]


def test_preprocessing_and_fit_never_accept_test_rows(payload):
    rows = synthetic_rows(payload)
    model = fit_model(rows, "logistic", {"C": 1})
    test = [
        {**r, "split": "test", "label": 1 - r["label"], "body_part": "Never seen"} for r in rows
    ]
    with pytest.raises(ValueError, match="train/tuning"):
        fit_model(rows + test, "logistic", {"C": 1})
    # Changing test labels/categories cannot affect fitting state or training predictions.
    before = predict(model, rows)
    predict(model, test)
    np.testing.assert_array_equal(before, predict(fit_model(rows, "logistic", {"C": 1}), rows))
    assert "Never seen" not in model["preprocessor"].get_feature_names_out().tolist()


def test_match_bootstrap_is_paired_and_matches_hand_calculation():
    y, p = np.array([0, 1, 0, 1]), np.array([0.1, 0.9, 0.2, 0.8])
    result = scores(y, p)
    assert result["brier"] == pytest.approx(0.025)
    _, draws = match_bootstrap(y, {"a": p, "b": p}, [1, 1, 2, 2], replicates=200)
    assert paired_difference(draws, "a", "b") == {"log_loss": [0.0, 0.0], "brier": [0.0, 0.0]}
    assert set(np.round(draws["a"]["brier"], 3)) <= {0.01, 0.025, 0.04}


def test_sigmoid_stays_finite_and_inside_probability_bounds():
    y = np.array([0, 0, 1, 1])
    p = np.array([0, 0.2, 0.8, 1])
    result = calibrate(fit_sigmoid(y, p), p)
    assert np.isfinite(result).all()
    assert ((result >= 0) & (result <= 1)).all()


def test_full_workflow_locks_before_test_and_cached_evaluation(tmp_path, monkeypatch, payload):
    import hashlib
    import json
    from pathlib import Path

    from tactigraph.config import Settings
    from tactigraph.models import evaluation, experiment
    from tactigraph.models.features import digest

    protocol = json.loads(Path("configs/xg-v1.json").read_text())
    protocol.update(
        logistic_c=[1],
        lightgbm_num_leaves=[3],
        lightgbm_min_child_samples=[5],
        lightgbm_reg_lambda=[1],
        max_estimators=20,
        calibration_folds=2,
        bootstrap_replicates=30,
    )
    datasets = {}
    for part, offset in (("train", 0), ("tuning", 100), ("calibration", 200), ("test", 300)):
        datasets[part] = [
            {
                **r,
                "split": part,
                "match_id": offset + r["match_id"],
                "season_id": 281 if part == "test" else 4,
                "team_id": 10,
                "home_team_id": 10,
                "away_team_id": 20,
                "reference_xg": 0.2,
            }
            for r in synthetic_rows(payload, 60)
        ]
    accessed = []

    def dataset(_settings, _manifest, partitions):
        accessed.append(set(partitions))
        return [r for p in sorted(partitions) for r in datasets[p]], {"exclusions": {}}

    monkeypatch.setattr(experiment, "build_dataset", dataset)
    monkeypatch.setattr(evaluation, "build_dataset", dataset)
    monkeypatch.chdir(tmp_path)
    Path("configs/splits").mkdir(parents=True)
    manifest = {"assignments": [], "team_stress_groups": {"10": 0, "20": 1}}
    manifest["sha256"] = digest(manifest)
    Path("configs/splits/wsl-v1.json").write_text(json.dumps(manifest))
    path = Path("configs/xg-v1.json")
    path.write_text(json.dumps(protocol))
    settings = Settings(data_dir=tmp_path / "data")
    experiment.develop(settings, path)
    assert accessed == [{"train", "tuning", "calibration"}]
    artifact = Path("artifacts/xg-v1/models.joblib")
    before = hashlib.sha256(artifact.read_bytes()).hexdigest()
    for row in datasets["test"]:
        row["label"] = 1 - row["label"]
    report = evaluation.evaluate(settings, path)
    assert report["test_non_penalty_shots"] == 60
    evaluation.evaluate(settings, path)
    assert accessed.count({"test"}) == 1
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == before
