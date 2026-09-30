import hashlib
from copy import deepcopy

import httpx
import pytest
from sqlalchemy import func, select

from tactigraph.config import SOURCE_COMMIT, Settings
from tactigraph.data.ingest import acquire, ingest_payload, normalize, period_milliseconds
from tactigraph.db import Event, Match, Pass, Shot


def test_repeat_ingestion_is_idempotent_and_source_ordered(database, payload):
    _, factory = database
    match, events, lineups = payload
    for _ in range(2):
        ingest_payload(factory, match, list(reversed(events)), lineups)
    with factory() as session:
        for model, expected in ((Match, 1), (Event, 6), (Pass, 1), (Shot, 5)):
            assert session.scalar(select(func.count()).select_from(model)) == expected
        ordered = session.scalars(select(Event).order_by(Event.index)).all()
        assert [e.id for e in ordered] == [e["id"] for e in events]
        assert session.get(Match, 1).source_commit == SOURCE_COMMIT


@pytest.mark.parametrize(
    "change", ["duplicate_id", "duplicate_index", "location", "team", "lineup"]
)
def test_invalid_reimport_preserves_existing_match(database, payload, change):
    _, factory = database
    ingest_payload(factory, *payload)
    match, events, lineups = deepcopy(payload)
    if change == "duplicate_id":
        events[1]["id"] = events[0]["id"]
    elif change == "duplicate_index":
        events[1]["index"] = events[0]["index"]
    elif change == "location":
        events[0]["location"] = [float("nan"), 40]
    elif change == "team":
        events[0]["team"]["id"] = 999
    else:
        lineups.pop()
    with pytest.raises(ValueError):
        ingest_payload(factory, match, events, lineups)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 6


def test_time_and_omitted_pressure_semantics(payload):
    _, events, passes, _ = normalize(*payload)
    assert period_milliseconds("00:45:30.123") == 2730123
    assert events[2]["period_ms"] == 2730000
    assert events[3]["period_ms"] == 0
    assert events[3]["minute"] == 45
    assert events[0]["under_pressure"] is None
    assert passes[0]["completed"] is True


def test_cache_checksum_is_checked(tmp_path):
    settings = Settings(data_dir=tmp_path)
    requests = []

    def respond(request):
        requests.append(request.url)
        return httpx.Response(200, content=b'{"synthetic": true}')

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        value, manifest = acquire("data/example.json", settings, client)
        assert value == {"synthetic": True}
        assert manifest["sha256"] == hashlib.sha256(b'{"synthetic": true}').hexdigest()
        acquire("data/example.json", settings, client)
        assert len(requests) == 1
        (tmp_path / "raw" / SOURCE_COMMIT / "data/example.json").write_text("{}")
        with pytest.raises(ValueError, match="checksum mismatch"):
            acquire("data/example.json", settings, client)
