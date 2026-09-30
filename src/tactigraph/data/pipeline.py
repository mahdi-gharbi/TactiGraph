"""Single-writer corpus ingestion with per-match transactions and explicit failures."""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import polars as pl
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from tactigraph.config import PIPELINE_VERSION, SOURCE_COMMIT, Settings
from tactigraph.data.catalog import catalog
from tactigraph.data.ingest import acquire, ingest_payload
from tactigraph.data.splits import freeze_manifest
from tactigraph.db import (
    ControlEpisode,
    EpisodeEvent,
    Event,
    EventContext,
    IngestionStatus,
    LineupStint,
    Match,
    MatchPlayer,
    MatchQuality,
    Pass,
    Possession,
    Shot,
    SourceManifest,
)

EXPORT_MODELS = (
    Match,
    Event,
    Pass,
    Shot,
    MatchPlayer,
    EventContext,
    LineupStint,
    Possession,
    ControlEpisode,
    EpisodeEvent,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def export_match(settings, sessions, mid):
    target = settings.data_dir / "processed" / SOURCE_COMMIT / str(mid)
    target.mkdir(parents=True, exist_ok=True)
    with sessions() as session:
        for model in EXPORT_MODELS:
            table = model.__table__
            if "match_id" in table.c:
                query = select(table).where(table.c.match_id == mid)
            elif model is Match:
                query = select(table).where(table.c.id == mid)
            else:
                query = select(table).where(
                    table.c.event_id.in_(select(Event.id).where(Event.match_id == mid))
                )
            records = [dict(r) for r in session.execute(query).mappings()]
            # Explicit types preserve empty partitions and all-null optional columns.
            types = {
                "Integer": pl.Int64,
                "String": pl.String,
                "Boolean": pl.Boolean,
                "Float": pl.Float64,
            }
            schema = {c.name: types.get(type(c.type).__name__, pl.String) for c in table.c}
            for row in records:
                for c in table.c:
                    if type(c.type).__name__ == "JSON":
                        row[c.name] = json.dumps(row[c.name], sort_keys=True)
            frame = pl.DataFrame(records, schema=schema)
            temporary = target / f"{table.name}.tmp"
            frame.write_parquet(temporary)
            temporary.replace(target / f"{table.name}.parquet")


def status(sessions, match, value, error=None):
    with sessions.begin() as session:
        session.merge(
            IngestionStatus(
                match_id=match["match_id"],
                season_id=match["season"]["season_id"],
                status=value,
                error=error,
                updated_at=datetime.now(timezone.utc),
                pipeline_version=PIPELINE_VERSION,
            )
        )


def ingest_scope(
    settings: Settings, sessions, *, force=False, split_path=Path("configs/splits/wsl-v1.json")
):
    matches, catalog_manifests = catalog(settings)
    manifest = freeze_manifest(matches, split_path, sessions)
    with sessions.begin() as session:
        for record in catalog_manifests:
            session.merge(SourceManifest(**record))
        for match in matches:
            if session.get(IngestionStatus, match["match_id"]) is None:
                session.add(
                    IngestionStatus(
                        match_id=match["match_id"],
                        season_id=match["season"]["season_id"],
                        status="pending",
                        error=None,
                        updated_at=datetime.now(timezone.utc),
                        pipeline_version=PIPELINE_VERSION,
                    )
                )
    failures, ready, skipped = [], 0, 0
    with httpx.Client(
        timeout=90, follow_redirects=True, transport=httpx.HTTPTransport(retries=3)
    ) as client:
        for count, match in enumerate(matches, 1):
            mid = match["match_id"]
            phase = "acquire"
            try:
                events, em = acquire(f"data/events/{mid}.json", settings, client)
                lineups, lm = acquire(f"data/lineups/{mid}.json", settings, client)
                em["schema_version"] = match.get("metadata", {}).get("data_version", "unknown")
                lm["schema_version"] = "lineups-v2"
                with sessions() as session:
                    previous, quality = (
                        session.get(IngestionStatus, mid),
                        session.get(MatchQuality, mid),
                    )
                    unchanged = (
                        not force
                        and previous is not None
                        and previous.status == "ready"
                        and (quality is not None and quality.pipeline_version == PIPELINE_VERSION)
                        and all(
                            (stored := session.get(SourceManifest, m["path"])) is not None
                            and stored.sha256 == m["sha256"]
                            and stored.commit == SOURCE_COMMIT
                            for m in (em, lm)
                        )
                    )
                exported = all(
                    (
                        settings.data_dir
                        / "processed"
                        / SOURCE_COMMIT
                        / str(mid)
                        / f"{model.__tablename__}.parquet"
                    ).exists()
                    for model in EXPORT_MODELS
                )
                if unchanged and exported:
                    skipped += 1
                else:
                    phase = "normalize"
                    ingest_payload(sessions, match, events, lineups, (em, lm))
                    phase = "export"
                    export_match(settings, sessions, mid)
                    status(sessions, match, "ready")
                    quarantine = settings.data_dir / "quarantine" / f"{mid}.json"
                    if quarantine.exists():
                        write_json(
                            quarantine,
                            {
                                "match_id": mid,
                                "status": "resolved",
                                "pipeline_version": PIPELINE_VERSION,
                            },
                        )
                ready += 1
            except (
                httpx.HTTPError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                SQLAlchemyError,
            ) as exc:
                failure = {"match_id": mid, "phase": phase, "error": str(exc)[:2000]}
                failures.append(failure)
                status(
                    sessions,
                    match,
                    "export_failed" if phase == "export" else "rejected",
                    failure["error"],
                )
                write_json(settings.data_dir / "quarantine" / f"{mid}.json", failure)
            if count % 10 == 0 or count == len(matches):
                print(
                    f"Processed {count}/{len(matches)}; ready={ready}, resumed={skipped}, "
                    f"failures={len(failures)}",
                    flush=True,
                )
    report = {
        "source_commit": SOURCE_COMMIT,
        "pipeline_version": PIPELINE_VERSION,
        "expected": len(matches),
        "ready": ready,
        "resumed": skipped,
        "failures": failures,
        "split_manifest_hash": manifest["sha256"],
    }
    write_json(settings.data_dir / "reports" / "ingestion.json", report)
    return report
