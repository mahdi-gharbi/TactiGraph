"""Outcome analysis is restricted to the training partition; test gets coverage only."""

from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import Integer, case, cast, func, select

from tactigraph.config import PIPELINE_VERSION, SOURCE_COMMIT
from tactigraph.data.pipeline import write_json
from tactigraph.db import (
    ControlEpisode,
    DatasetReport,
    EpisodeEvent,
    Event,
    EventContext,
    IngestionStatus,
    LineupStint,
    Match,
    MatchPlayer,
    MatchQuality,
    Pass,
    Player,
    Possession,
    Shot,
    SourceManifest,
    SplitAssignment,
    TeamEntity,
)


def train_query(*columns):
    return (
        select(*columns)
        .select_from(Event)
        .join(SplitAssignment, SplitAssignment.match_id == Event.match_id)
        .where(SplitAssignment.partition == "train", Event.period < 5)
    )


def training_eda(session):
    distribution = [
        {"name": kind, "count": count}
        for kind, count in session.execute(
            train_query(Event.type, func.count()).group_by(Event.type).order_by(func.count().desc())
        )
    ]
    xbin = cast(func.floor(Event.x / 10), Integer)
    ybin = cast(func.floor(Event.y / 10), Integer)
    xbin, ybin = case((Event.x >= 120, 11), else_=xbin), case((Event.y >= 80, 7), else_=ybin)
    spatial = [
        {"x_bin": x, "y_bin": y, "count": n}
        for x, y, n in session.execute(
            train_query(xbin, ybin, func.count())
            .where(Event.type == "Shot", Event.x.between(0, 120), Event.y.between(0, 80))
            .group_by(xbin, ybin)
            .order_by(xbin, ybin)
        )
    ]
    timebin = cast(func.floor(Event.period_ms / 300000), Integer)
    temporal = [
        {"period": p, "start_minute": b * 5, "count": n}
        for p, b, n in session.execute(
            train_query(Event.period, timebin, func.count())
            .where(Event.type == "Shot")
            .group_by(Event.period, timebin)
            .order_by(Event.period, timebin)
        )
    ]
    teams = [
        {
            "id": tid,
            "name": name,
            "matches": games,
            "events": events,
            "passes": passes,
            "shots": shots,
        }
        for tid, name, games, events, passes, shots in session.execute(
            train_query(
                Event.team_id,
                func.min(Event.team_name),
                func.count(func.distinct(Event.match_id)),
                func.count(),
                func.sum(case((Event.type == "Pass", 1), else_=0)),
                func.sum(case((Event.type == "Shot", 1), else_=0)),
            )
            .where(Event.team_id.is_not(None))
            .group_by(Event.team_id)
            .order_by(Event.team_id)
        )
    ]
    players = [
        {"id": pid, "name": name, "matches": games, "shots": shots, "passes": passes}
        for pid, name, games, shots, passes in session.execute(
            train_query(
                Event.player_id,
                func.min(Event.player_name),
                func.count(func.distinct(Event.match_id)),
                func.sum(case((Event.type == "Shot", 1), else_=0)),
                func.sum(case((Event.type == "Pass", 1), else_=0)),
            )
            .where(Event.player_id.is_not(None))
            .group_by(Event.player_id)
            .order_by(func.sum(case((Event.type == "Shot", 1), else_=0)).desc(), Event.player_id)
            .limit(20)
        )
    ]
    lengths = Counter()
    for length, n in session.execute(
        select(ControlEpisode.action_count, func.count())
        .join(SplitAssignment, SplitAssignment.match_id == ControlEpisode.match_id)
        .where(SplitAssignment.partition == "train")
        .group_by(ControlEpisode.action_count)
    ):
        bucket = (
            "1"
            if length == 1
            else "2–3"
            if length <= 3
            else "4–6"
            if length <= 6
            else "7–10"
            if length <= 10
            else "11+"
        )
        lengths[bucket] += n
    match_ids = list(
        session.scalars(
            select(Match.id)
            .join(SplitAssignment, SplitAssignment.match_id == Match.id)
            .where(SplitAssignment.partition == "train")
            .order_by(Match.id)
        )
    )
    return {
        "partition": "train",
        "match_count": len(match_ids),
        "match_ids": match_ids,
        "event_distribution": distribution,
        "shot_zones": spatial,
        "shot_time_bins": temporal,
        "teams": teams,
        "players": players,
        "episode_lengths": [
            {"name": k, "count": lengths[k]} for k in ("1", "2–3", "4–6", "7–10", "11+")
        ],
        "note": (
            "Training matches only. No tuning, calibration, or final-test outcomes used for EDA."
        ),
    }


def audit_dataset(settings, sessions):
    with sessions() as session:
        assignments = session.scalars(select(SplitAssignment)).all()
        matches = {m.id: m for m in session.scalars(select(Match))}
        qualities = {q.match_id: q.payload for q in session.scalars(select(MatchQuality))}
        statuses = {s.match_id: s.status for s in session.scalars(select(IngestionStatus))}
        counts = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in (
                Match,
                Event,
                Pass,
                Shot,
                Player,
                TeamEntity,
                LineupStint,
                Possession,
                ControlEpisode,
                EpisodeEvent,
                EventContext,
                MatchPlayer,
            )
        }
        seasons, partitions = {}, defaultdict(lambda: {"expected": 0, "ingested": 0})
        issues, missing, schemas = Counter(), Counter(), Counter()
        failed_ids, pending_ids = [], []
        for a in assignments:
            row = seasons.setdefault(
                a.season_id,
                {
                    "season_id": a.season_id,
                    "expected": 0,
                    "ingested": 0,
                    "ready": 0,
                    "events": 0,
                    "shots": 0,
                    "passes": 0,
                },
            )
            row["expected"] += 1
            partitions[a.partition]["expected"] += 1
            if a.match_id in matches:
                row["ingested"] += 1
                partitions[a.partition]["ingested"] += 1
                schemas[matches[a.match_id].source_schema] += 1
            if statuses.get(a.match_id) == "ready":
                row["ready"] += 1
            elif statuses.get(a.match_id) in {"rejected", "export_failed"}:
                failed_ids.append(a.match_id)
            else:
                pending_ids.append(a.match_id)
            q = qualities.get(a.match_id)
            if q:
                issues.update(q["issue_counts"])
                missing.update(q["missing"])
                for key in ("events", "shots", "passes"):
                    row[key] += q["counts"][key]
        ready = sum(row["ready"] for row in seasons.values())
        # Logical referential checks supplement actual database FKs (including legacy columns).
        orphan_actor = session.scalar(
            select(func.count())
            .select_from(Event)
            .outerjoin(
                MatchPlayer,
                (MatchPlayer.match_id == Event.match_id)
                & (MatchPlayer.team_id == Event.team_id)
                & (MatchPlayer.player_id == Event.player_id),
            )
            .where(Event.player_id.is_not(None), MatchPlayer.player_id.is_(None))
        )
        invalid_membership = session.scalar(
            select(func.count())
            .select_from(EpisodeEvent)
            .join(Event)
            .join(ControlEpisode, ControlEpisode.id == EpisodeEvent.episode_id)
            .where(
                (Event.match_id != ControlEpisode.match_id)
                | (Event.team_id != ControlEpisode.team_id)
                | (Event.period != ControlEpisode.period)
            )
        )
        checks = {
            "pass_count_reconciles": counts["passes"]
            == sum(q["counts"]["passes"] for q in qualities.values()),
            "shot_count_reconciles": counts["shots"]
            == sum(q["counts"]["shots"] for q in qualities.values()),
            "event_count_reconciles": counts["events"]
            == sum(m.event_count for m in matches.values()),
            "every_event_has_context": counts["event_context"] == counts["events"],
            "actor_membership_complete": orphan_actor == 0,
            "episode_membership_consistent": invalid_membership == 0,
            "quality_covers_matches": set(qualities) == set(matches),
            "no_unassigned_matches": set(matches) <= {a.match_id for a in assignments},
            "single_split_manifest": len({a.manifest_hash for a in assignments}) == 1,
        }
        report = {
            "source_commit": SOURCE_COMMIT,
            "pipeline_version": PIPELINE_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected_matches": len(assignments),
            "ingested_matches": len(matches),
            "ready_matches": ready,
            "failed_matches": failed_ids,
            "pending_matches": pending_ids,
            "counts": counts,
            "seasons": list(seasons.values()),
            "partitions": [
                {"name": k, **partitions[k]} for k in ("train", "tuning", "calibration", "test")
            ],
            "schema_versions": dict(schemas),
            "missing_fields": dict(missing),
            "quality_issues": [{"name": k, "count": n} for k, n in issues.most_common()],
            "integrity_checks": checks,
            "split_manifest_hash": assignments[0].manifest_hash if assignments else None,
            "coverage_complete": bool(assignments)
            and ready == len(assignments)
            and all(checks.values()),
            "training_eda": training_eda(session),
        }
        source_files = [
            {
                "path": s.path,
                "sha256": s.sha256,
                "commit": s.commit,
                "schema_version": s.schema_version,
            }
            for s in session.scalars(select(SourceManifest).order_by(SourceManifest.path))
        ]
    write_json(settings.data_dir / "reports" / "foundation.json", report)
    write_json(settings.data_dir / "reports" / "source-manifest.json", source_files)
    with sessions.begin() as session:
        session.merge(
            DatasetReport(id="foundation", generated_at=datetime.now(timezone.utc), payload=report)
        )
    return report
