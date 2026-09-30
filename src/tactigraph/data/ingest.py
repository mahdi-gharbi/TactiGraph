import hashlib
import json
import math
from datetime import datetime, timezone
from uuid import UUID

import httpx
import polars as pl
from sqlalchemy import delete, insert, select, update

from tactigraph.config import MATCH_ID, PIPELINE_VERSION, SOURCE_BASE, SOURCE_COMMIT, Settings
from tactigraph.data.derive import derive
from tactigraph.db import (
    ControlEpisode,
    DatasetReport,
    EpisodeEvent,
    Event,
    EventContext,
    LineupSource,
    LineupStint,
    Match,
    MatchPlayer,
    MatchQuality,
    ModelRelease,
    Pass,
    Player,
    Possession,
    Prediction,
    PredictionSample,
    Shot,
    SourceManifest,
    TeamEntity,
)


def period_milliseconds(timestamp: str) -> int:
    hours, minutes, seconds = timestamp.split(":")
    seconds_ms = round(float(seconds) * 1000)
    if not (0 <= int(minutes) < 60 and 0 <= seconds_ms < 60000 and int(hours) >= 0):
        raise ValueError(f"Invalid period timestamp: {timestamp}")
    return (int(hours) * 3600 + int(minutes) * 60) * 1000 + seconds_ms


def location(value):
    if value is None:
        return None, None
    if len(value) < 2 or not all(
        isinstance(x, (int, float)) and math.isfinite(x) for x in value[:2]
    ):
        raise ValueError("Invalid coordinate pair")
    x, y = float(value[0]), float(value[1])
    # Some source events are just beyond the boundary. Preserve rather than clip;
    # derive.py records quality flags and spatial views exclude those coordinates.
    return x, y


def named(value, key):
    return (value.get(key) or {}).get("name")


def normalize(match: dict, events: list[dict], lineups: list[dict]):
    """Validate the entire match before opening a replacement transaction."""
    if not events:
        raise ValueError("Empty event file")
    ids, indices = set(), set()
    event_rows, pass_rows, shot_rows = [], [], []
    team_ids = {match["home_team"]["home_team_id"], match["away_team"]["away_team_id"]}
    if {row["team_id"] for row in lineups} != team_ids:
        raise ValueError("Lineup teams do not match match metadata")
    for raw in sorted(events, key=lambda e: e["index"]):
        event_id = str(UUID(raw["id"]))
        if event_id in ids or raw["index"] in indices:
            raise ValueError("Duplicate event ID or index")
        ids.add(event_id)
        indices.add(raw["index"])
        if raw["period"] not in range(1, 6) or raw["index"] < 1:
            raise ValueError("Invalid event period or index")
        team = raw.get("team", {})
        if team.get("id") is not None and team["id"] not in team_ids:
            raise ValueError("Event references an unknown team")
        x, y = location(raw.get("location"))
        if raw["type"]["name"] == "Carry":
            location(raw["carry"].get("end_location"))
        if "under_pressure" in raw and not isinstance(raw["under_pressure"], bool):
            raise ValueError("under_pressure must be a boolean when present")
        if "duration" in raw and (
            not isinstance(raw["duration"], (int, float)) or not math.isfinite(raw["duration"])
        ):
            raise ValueError("Invalid event duration")
        player = raw.get("player", {})
        event_rows.append(
            dict(
                id=event_id,
                match_id=match["match_id"],
                index=raw["index"],
                period=raw["period"],
                timestamp=raw["timestamp"],
                period_ms=period_milliseconds(raw["timestamp"]),
                minute=raw["minute"],
                second=raw["second"],
                type=raw["type"]["name"],
                team_id=team.get("id"),
                team_name=team.get("name"),
                player_id=player.get("id"),
                player_name=player.get("name"),
                possession=raw.get("possession"),
                possession_team_id=raw.get("possession_team", {}).get("id"),
                x=x,
                y=y,
                under_pressure=raw.get("under_pressure"),
            )
        )
        if raw["type"]["name"] == "Pass":
            p = raw["pass"]
            end_x, end_y = location(p.get("end_location"))
            pass_rows.append(
                dict(
                    event_id=event_id,
                    recipient_id=p.get("recipient", {}).get("id"),
                    recipient_name=named(p, "recipient"),
                    end_x=end_x,
                    end_y=end_y,
                    completed="outcome" not in p,
                    outcome=named(p, "outcome"),
                    length=p.get("length"),
                    height=named(p, "height"),
                    body_part=named(p, "body_part"),
                    technique=named(p, "technique"),
                )
            )
        if raw["type"]["name"] == "Shot":
            s = raw["shot"]
            if not named(s, "outcome"):
                raise ValueError("Shot outcome is required")
            shot_rows.append(
                dict(
                    event_id=event_id,
                    outcome=named(s, "outcome"),
                    goal=named(s, "outcome") == "Goal",
                    body_part=named(s, "body_part"),
                    shot_type=named(s, "type"),
                    technique=named(s, "technique"),
                    key_pass_id=s.get("key_pass_id"),
                )
            )
    home, away = match["home_team"], match["away_team"]
    match_row = dict(
        id=match["match_id"],
        competition_id=match["competition"]["competition_id"],
        competition=match["competition"]["competition_name"],
        season_id=match["season"]["season_id"],
        season=match["season"]["season_name"],
        date=match["match_date"],
        home_id=home["home_team_id"],
        home_name=home["home_team_name"],
        away_id=away["away_team_id"],
        away_name=away["away_team_name"],
        home_score=match["home_score"],
        away_score=match["away_score"],
        source_commit=SOURCE_COMMIT,
        source_schema=match.get("metadata", {}).get("data_version", "unknown"),
        event_count=len(event_rows),
    )
    return match_row, event_rows, pass_rows, shot_rows


def ingest_payload(session_factory, match, events, lineups, manifests=()):
    rows = normalize(match, events, lineups)
    match_row, event_rows, pass_rows, shot_rows = rows
    mid = match_row["id"]
    derived = derive(match, events, event_rows, pass_rows, shot_rows, lineups)
    with session_factory.begin() as session:
        event_ids = select(Event.id).where(Event.match_id == mid)
        affected = select(Prediction.model_version).where(Prediction.sample_id.in_(event_ids))
        session.execute(
            update(ModelRelease).where(ModelRelease.id.in_(affected)).values(status="stale")
        )
        session.execute(delete(Prediction).where(Prediction.sample_id.in_(event_ids)))
        session.execute(delete(PredictionSample).where(PredictionSample.match_id == mid))
        session.execute(delete(EpisodeEvent).where(EpisodeEvent.event_id.in_(event_ids)))
        session.execute(delete(EventContext).where(EventContext.event_id.in_(event_ids)))
        for model in (LineupStint, ControlEpisode, Possession, MatchPlayer, MatchQuality):
            session.execute(delete(model).where(model.match_id == mid))
        session.execute(delete(DatasetReport))  # Cached audits must never outlive mutations.
        session.execute(delete(Pass).where(Pass.event_id.in_(event_ids)))
        session.execute(delete(Shot).where(Shot.event_id.in_(event_ids)))
        session.execute(delete(Event).where(Event.match_id == mid))
        session.execute(delete(LineupSource).where(LineupSource.match_id == mid))
        session.merge(Match(**match_row))
        for row in derived["teams"]:
            session.merge(TeamEntity(**row))
        for row in derived["players"]:
            session.merge(Player(**row))
        session.flush()
        for model, records in (
            (Event, event_rows),
            (Pass, pass_rows),
            (Shot, shot_rows),
            (MatchPlayer, derived["match_players"]),
            (EventContext, derived["event_context"]),
            (LineupStint, derived["lineup_stints"]),
            (Possession, derived["possessions"]),
            (ControlEpisode, derived["control_episodes"]),
            (EpisodeEvent, derived["episode_events"]),
        ):
            if records:
                session.execute(insert(model), records)
        session.add(
            MatchQuality(
                match_id=mid, pipeline_version=PIPELINE_VERSION, payload=derived["quality"]
            )
        )
        session.add(LineupSource(match_id=mid, payload=lineups))
        for manifest in manifests:
            session.merge(SourceManifest(**manifest))
    return rows


def acquire(path: str, settings: Settings, client: httpx.Client):
    cache = settings.data_dir / "raw" / SOURCE_COMMIT / path
    checksum_file = cache.with_suffix(".sha256")
    if cache.exists():
        content = cache.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if not checksum_file.exists() or checksum_file.read_text().strip() != digest:
            raise ValueError(f"Cached file checksum mismatch: {path}; remove it and retry")
    else:
        response = client.get(f"{SOURCE_BASE}/{path}")
        response.raise_for_status()
        content = response.content
        json.loads(content)  # Never cache an invalid JSON response.
        digest = hashlib.sha256(content).hexdigest()
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(cache)
        checksum_file.write_text(digest)
    return json.loads(content), dict(
        path=path,
        commit=SOURCE_COMMIT,
        sha256=digest,
        retrieved_at=datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc),
        schema_version="pending",
        validation_status="valid",
    )


def ingest_first_match(settings: Settings, session_factory):
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        matches, mm = acquire("data/matches/37/4.json", settings, client)
        match = next(m for m in matches if m["match_id"] == MATCH_ID)
        events, em = acquire(f"data/events/{MATCH_ID}.json", settings, client)
        lineups, lm = acquire(f"data/lineups/{MATCH_ID}.json", settings, client)
    for manifest in (mm, em, lm):
        manifest["schema_version"] = match.get("metadata", {}).get("data_version", "unknown")
    try:
        rows = ingest_payload(session_factory, match, events, lineups, (mm, em, lm))
    except (KeyError, TypeError, ValueError) as error:
        quarantine = settings.data_dir / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        (quarantine / f"{MATCH_ID}.json").write_text(
            json.dumps(
                {
                    "match_id": MATCH_ID,
                    "source_commit": SOURCE_COMMIT,
                    "error": str(error),
                    "status": "rejected; database unchanged",
                },
                indent=2,
            )
        )
        raise
    export = settings.data_dir / "processed" / SOURCE_COMMIT / str(MATCH_ID)
    export.mkdir(parents=True, exist_ok=True)
    for name, values in zip(("matches", "events", "passes", "shots"), rows, strict=True):
        data = [values] if isinstance(values, dict) else values
        pl.DataFrame(data, infer_schema_length=None).write_parquet(export / f"{name}.parquet")
    return {
        "match_id": MATCH_ID,
        "events": len(rows[1]),
        "passes": len(rows[2]),
        "shots": len(rows[3]),
        "source_commit": SOURCE_COMMIT,
    }
