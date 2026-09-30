import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from tactigraph.config import SOURCE_COMMIT, Settings
from tactigraph.data import pipeline
from tactigraph.db import Event


def test_corpus_retry_preserves_ready_matches_and_resumes(tmp_path, database, payload, monkeypatch):
    _, sessions = database
    records, sources = [], {}
    for mid, season, date in (
        (1, 4, "2018-09-09"),
        (2, 42, "2019-09-09"),
        (3, 90, "2020-09-09"),
        (4, 90, "2021-04-09"),
        (5, 281, "2023-09-09"),
    ):
        match, events, lineups = deepcopy(payload)
        match.update(match_id=mid, match_date=date)
        match["season"]["season_id"] = season
        for event in events:
            event["id"] = str(UUID(int=mid * 100 + event["index"]))
        records.append(match)
        sources[f"data/events/{mid}.json"] = events
        sources[f"data/lineups/{mid}.json"] = lineups
    monkeypatch.setattr(pipeline, "catalog", lambda _: (records, []))

    def acquire(path, _settings, _client):
        value = sources[path]
        digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        return deepcopy(value), {
            "path": path,
            "commit": SOURCE_COMMIT,
            "sha256": digest,
            "retrieved_at": datetime.now(timezone.utc),
            "schema_version": "pending",
            "validation_status": "valid",
        }

    monkeypatch.setattr(pipeline, "acquire", acquire)
    sources["data/events/2.json"].append(deepcopy(sources["data/events/2.json"][0]))
    settings = Settings(data_dir=tmp_path)
    split_path = tmp_path / "split.json"
    first = pipeline.ingest_scope(settings, sessions, split_path=split_path)
    assert first["ready"] == 4
    assert [f["match_id"] for f in first["failures"]] == [2]
    assert (tmp_path / "quarantine/2.json").exists()
    sources["data/events/2.json"].pop()
    second = pipeline.ingest_scope(settings, sessions, split_path=split_path)
    assert second["ready"] == 5 and second["resumed"] == 4
    third = pipeline.ingest_scope(settings, sessions, split_path=split_path)
    assert third["ready"] == third["resumed"] == 5
    assert not third["failures"]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 30
    assert len(list((tmp_path / "processed").rglob("*.parquet"))) == 50
