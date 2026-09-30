from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tactigraph.api.app import create_app
from tactigraph.api.styles import stored
from tactigraph.config import Settings
from tactigraph.db import DatasetReport, SourceManifest
from tactigraph.models.styles import fit_styles, windows


def test_half_open_windows_geometry_and_coverage():
    match = SimpleNamespace(id=1, home_id=10, away_id=20)

    def row(ms, period=1, x=20, end=90):
        return (
            SimpleNamespace(period=period, period_ms=ms, team_id=10, x=x, y=40),
            SimpleNamespace(end_x=end, end_y=40, completed=True),
        )

    rows = [row(0), row(899999), row(900000), row(1800000), row(2800000), row(1, 5)]
    result = windows(rows, match, minimum=1)
    assert [w["pass_count"] for w in result] == [2, 1, 1]
    assert result[0]["features"] == [2 / 15, 1, 1, 1, 1, 20]
    assert windows([row(0), row(899999)], match, minimum=1) == []
    assert windows([row(0, x=None), (row(900000)[0], None)], match, minimum=1) == []
    assert all(w["end_ms"] <= 2700000 and w["period"] == 1 for w in result)


def test_later_partitions_cannot_influence_fit_or_stability():
    rng = np.random.default_rng(8)
    train = [
        {
            "features": (rng.normal(size=6) + (i % 2) * 8).tolist(),
            "partition": "train",
            "match_id": i // 4,
        }
        for i in range(40)
    ]
    protocol = {
        "clusters": 2,
        "seed": 42,
        "pca_variance": 0.9,
        "stability_seeds": [7, 19],
        "bootstrap_repeats": 3,
        "version": "test",
    }
    first = deepcopy(train) + [{"features": [0] * 6, "partition": "test", "match_id": 99}]
    second = deepcopy(train) + [{"features": [10000] * 6, "partition": "test", "match_id": 99}]
    a, ra = fit_styles(first, protocol)
    b, rb = fit_styles(second, protocol)
    assert ra == rb
    np.testing.assert_array_equal(a[0].mean_, b[0].mean_)
    assert min(ra["seed_ari"]) == pytest.approx(1)
    assert ra["training_matches"] == 10


def test_unavailable_styles_and_unknown_match(database):
    engine, _ = database
    with TestClient(create_app(Settings(), engine)) as client:
        response = client.get("/api/v1/experiments/styles")
        assert response.status_code == 200
        assert response.json() == {"status": "not_trained", "report": None, "windows": []}
        assert client.get("/api/v1/matches/999/styles").status_code == 404


def test_source_changes_invalidate_all_profiles(database):
    _, sessions = database
    with sessions() as session:
        session.add(
            DatasetReport(
                id="styles-v1",
                generated_at=datetime.now(timezone.utc),
                payload={
                    "report": {"source_hashes": {"1": "expected"}, "source_commit": "pinned"},
                    "windows": [],
                },
            )
        )
        session.commit()
        assert stored(session).status == "stale"
        session.add(
            SourceManifest(
                path="data/events/1.json",
                commit="pinned",
                sha256="changed",
                retrieved_at=datetime.now(timezone.utc),
                schema_version="1",
            )
        )
        session.commit()
        assert stored(session).status == "stale"
