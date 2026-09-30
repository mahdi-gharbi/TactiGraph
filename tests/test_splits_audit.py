from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from tactigraph.config import PIPELINE_VERSION, Settings
from tactigraph.data.audit import audit_dataset
from tactigraph.data.ingest import ingest_payload
from tactigraph.data.splits import build_manifest, freeze_manifest
from tactigraph.db import IngestionStatus, SplitAssignment


def catalog_fixture():
    return [
        {
            "match_id": i + 1,
            "match_date": date,
            "season": {"season_id": season},
            "home_team": {"home_team_id": 10},
            "away_team": {"away_team_id": 20},
            "home_score": i % 3,
            "away_score": 0,
        }
        for i, (season, date) in enumerate(
            [
                (4, "2018-10-01"),
                (42, "2019-10-01"),
                (90, "2020-10-01"),
                (90, "2020-10-01"),
                (90, "2021-01-01"),
                (90, "2021-01-01"),
                (90, "2021-04-01"),
                (90, "2021-04-01"),
                (281, "2023-10-01"),
            ]
        )
    ]


def test_splits_are_date_grouped_disjoint_and_outcome_blind():
    matches = catalog_fixture()
    manifest = build_manifest(matches)
    assert manifest["counts"] == {"train": 2, "tuning": 4, "calibration": 2, "test": 1}
    assert manifest["tuning_last_date"] == "2021-01-01"
    assert len({a["match_id"] for a in manifest["assignments"]}) == 9
    assert all(a["partition"] == "test" for a in manifest["assignments"] if a["season_id"] == 281)
    for m in matches:
        m["home_score"] = 999
        m["away_score"] = 888
    assert build_manifest(list(reversed(matches))) == manifest


def test_frozen_manifest_is_repeatable_and_rejects_mutation(tmp_path, database):
    _, sessions = database
    path = tmp_path / "splits.json"
    first = freeze_manifest(catalog_fixture(), path, sessions)
    assert freeze_manifest(catalog_fixture(), path, sessions) == first
    original = path.read_bytes()
    changed = catalog_fixture()
    changed[2]["match_date"] = "2021-03-01"
    with pytest.raises(ValueError, match="Immutable"):
        freeze_manifest(changed, path, sessions)
    assert path.read_bytes() == original


def test_audit_eda_never_reads_test_outcomes(tmp_path, database, payload):
    _, sessions = database
    train = deepcopy(payload)
    ingest_payload(sessions, *train)
    test = deepcopy(payload)
    test[0]["match_id"] = 2
    test[0]["season"]["season_id"] = 281
    for e in test[1]:
        e["id"] = str(UUID(int=e["index"] + 1000))
    ingest_payload(sessions, *test)
    with sessions.begin() as session:
        for mid, partition in ((1, "train"), (2, "test")):
            session.add(
                SplitAssignment(
                    match_id=mid,
                    season_id=4 if mid == 1 else 281,
                    match_date="2018-09-09" if mid == 1 else "2023-09-09",
                    partition=partition,
                    manifest_hash="synthetic",
                )
            )
            session.add(
                IngestionStatus(
                    match_id=mid,
                    season_id=4 if mid == 1 else 281,
                    status="ready",
                    error=None,
                    updated_at=datetime.now(timezone.utc),
                    pipeline_version=PIPELINE_VERSION,
                )
            )
    settings = Settings(data_dir=tmp_path)
    before = audit_dataset(settings, sessions)
    test[0]["home_score"] = 50
    for event in test[1]:
        if event["type"]["name"] == "Shot":
            event["shot"]["outcome"]["name"] = "Goal"
            event["location"] = [1, 1]
    ingest_payload(sessions, *test)
    after = audit_dataset(settings, sessions)
    assert after["training_eda"] == before["training_eda"]
    assert before["training_eda"]["match_ids"] == [1]
    assert sum(c["count"] for c in before["training_eda"]["shot_zones"]) == 3
    assert all(before["integrity_checks"].values())
    assert Path(tmp_path / "reports/foundation.json").exists()
