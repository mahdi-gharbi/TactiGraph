import re
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from tactigraph.api.analyst import router as analyst_router
from tactigraph.api.experiment_schemas import ExperimentsResponse
from tactigraph.api.graph import router as graph_router
from tactigraph.api.schemas import (
    DatasetOverview,
    EventReference,
    LocalEvent,
    LocalEvents,
    MatchCard,
    MatchList,
    MatchSummary,
    Provenance,
    ShotEvidence,
    ShotLayer,
    ShotPoint,
    Team,
    TeamStats,
)
from tactigraph.api.sensitivity import router as sensitivity_router
from tactigraph.api.showcase import router as showcase_router
from tactigraph.api.styles import router as styles_router
from tactigraph.api.tactics import router as tactics_router
from tactigraph.config import PIPELINE_VERSION, SOURCE_WEB, Settings
from tactigraph.data.geometry import in_pitch, location_status
from tactigraph.db import (
    DatasetReport,
    Event,
    Match,
    ModelRelease,
    Pass,
    Shot,
    SourceManifest,
    initialize,
    make_engine,
)
from tactigraph.models.serving import latest_release, match_predictions
from tactigraph.models.serving import provenance as model_provenance


def card(match: Match) -> MatchCard:
    return MatchCard(
        id=match.id,
        date=match.date,
        competition=match.competition,
        season=match.season,
        home=Team(id=match.home_id, name=match.home_name, score=match.home_score),
        away=Team(id=match.away_id, name=match.away_name, score=match.away_score),
        event_count=match.event_count,
        source_schema=match.source_schema,
        provenance=Provenance(source_commit=match.source_commit),
    )


def require_match(session, match_id):
    match = session.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not ingested. Run: tactigraph ingest")
    return match


def filtered_shots(session, match_id, team_id, period, start_ms, end_ms, player_id):
    match = require_match(session, match_id)
    if team_id is not None and team_id not in (match.home_id, match.away_id):
        raise HTTPException(422, "Team does not participate in this match")
    if period is None and (start_ms != 0 or end_ms is not None):
        raise HTTPException(422, "A time window requires an explicit period")
    if period is not None and period not in (1, 2, 3, 4):
        raise HTTPException(422, "Period must be 1–4; shootouts are excluded")
    if start_ms < 0 or start_ms > 7200000:
        raise HTTPException(422, "Invalid start time")
    if end_ms is not None and (end_ms <= start_ms or end_ms > 7200000):
        raise HTTPException(422, "End must be after start and within 120 period minutes")
    if player_id is not None:
        exists = session.scalar(
            select(Event.id)
            .where(
                Event.match_id == match_id,
                Event.player_id == player_id,
                *([Event.team_id == team_id] if team_id is not None else []),
            )
            .limit(1)
        )
        if exists is None:
            raise HTTPException(422, "Player has no recorded actions for the selected team/match")
    query = (
        select(Event, Shot)
        .join(Shot, Shot.event_id == Event.id)
        .where(
            Event.match_id == match_id,
            Event.period < 5,
        )
    )
    for column, value in (
        (Event.team_id, team_id),
        (Event.period, period),
        (Event.player_id, player_id),
    ):
        if value is not None:
            query = query.where(column == value)
    query = query.where(Event.period_ms >= start_ms)
    if end_ms is not None:
        query = query.where(Event.period_ms < end_ms)
    return match, session.execute(query.order_by(Event.index)).all()


def result_id(match_id, team_id, period, start_ms, end_ms, player_id):
    return (
        f"shots-{match_id}-{team_id or 0}-{period or 0}-{start_ms}-{end_ms or 0}-{player_id or 0}"
    )


def create_app(settings: Settings | None = None, engine=None) -> FastAPI:
    settings = settings or Settings()
    engine = engine or make_engine(settings)
    premier_app = (
        create_app(settings.for_league("premier-league"))
        if settings.mode == "local" and settings.league == "wsl"
        else None
    )

    @asynccontextmanager
    async def lifespan(application):
        application.state.sessions = initialize(engine)
        async with AsyncExitStack() as stack:
            if premier_app is not None:
                await stack.enter_async_context(premier_app.router.lifespan_context(premier_app))
            yield
        engine.dispose()

    app = FastAPI(title="TactiGraph AI", version="0.5.0", lifespan=lifespan)
    app.state.settings = settings
    if premier_app is not None:
        app.mount("/leagues/premier-league", premier_app)
    app.include_router(tactics_router)
    app.include_router(graph_router)
    app.include_router(analyst_router)
    app.include_router(sensitivity_router)
    app.include_router(styles_router)
    app.include_router(showcase_router)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": "0.5.0", "mode": settings.mode}

    @app.get("/api/v1/dataset", response_model=DatasetOverview)
    def dataset():
        with app.state.sessions() as session:
            report = session.get(DatasetReport, "foundation")
            return DatasetOverview(
                status="audited" if report else "not_audited",
                ingested_matches=session.scalar(select(func.count()).select_from(Match)),
                report=report.payload if report else None,
                provenance=Provenance(metric_version=PIPELINE_VERSION),
            )

    @app.get("/api/v1/matches", response_model=MatchList)
    def matches():
        with app.state.sessions() as session:
            records = session.scalars(select(Match).order_by(Match.date, Match.id)).all()
            return MatchList(matches=[card(m) for m in records], mode=settings.mode)

    @app.get("/api/v1/experiments", response_model=ExperimentsResponse)
    def experiments():
        with app.state.sessions() as session:
            release = latest_release(session)
            return ExperimentsResponse(
                status="evaluated"
                if release
                else (
                    "unavailable"
                    if session.scalar(select(func.count()).select_from(ModelRelease))
                    else "not_trained"
                ),
                report=release.report if release else None,
                model=model_provenance(release),
            )

    @app.get("/api/v1/matches/{match_id}/summary", response_model=MatchSummary)
    def summary(match_id: int):
        with app.state.sessions() as session:
            match = require_match(session, match_id)
            release, predictions = match_predictions(session, match_id)
            stats = []
            for team in (match.home_id, match.away_id):
                _, shots = filtered_shots(session, match_id, team, None, 0, None, None)
                passes = session.scalars(
                    select(Pass)
                    .join(Event)
                    .where(
                        Event.match_id == match_id,
                        Event.team_id == team,
                        Event.period < 5,
                    )
                ).all()
                stats.append(
                    TeamStats(
                        team_id=team,
                        shots=len(shots),
                        goals_from_shots=sum(s.goal for _, s in shots),
                        passes=len(passes),
                        completed_passes=sum(p.completed for p in passes),
                        located_shots=sum(in_pitch(e.x, e.y) for e, _ in shots),
                        xg=sum(
                            predictions[e.id].probability for e, _ in shots if e.id in predictions
                        )
                        if release
                        else None,
                        non_penalty_xg=sum(
                            predictions[e.id].probability
                            for e, _ in shots
                            if e.id in predictions and not predictions[e.id].penalty
                        )
                        if release
                        else None,
                        penalty_xg=sum(
                            predictions[e.id].probability
                            for e, _ in shots
                            if e.id in predictions and predictions[e.id].penalty
                        )
                        if release
                        else None,
                        predicted_shots=sum(e.id in predictions for e, _ in shots),
                        xg_status=(
                            "ready" if all(e.id in predictions for e, _ in shots) else "partial"
                        )
                        if release
                        else (
                            "unavailable"
                            if session.scalar(select(func.count()).select_from(ModelRelease))
                            else "not_trained"
                        ),
                    )
                )
            periods = session.scalars(
                select(Event.period)
                .where(
                    Event.match_id == match_id,
                    Event.period < 5,
                )
                .distinct()
                .order_by(Event.period)
            ).all()
            return MatchSummary(
                match=card(match),
                teams=stats,
                periods=list(periods),
                model=model_provenance(release),
                prediction_split=next(iter(predictions.values())).split if predictions else None,
            )

    @app.get("/api/v1/matches/{match_id}/shots", response_model=ShotLayer)
    def shots(
        match_id: int,
        team_id: int | None = None,
        period: int | None = Query(None, ge=1, le=4),
        start_ms: int = Query(0, ge=0, le=7200000),
        end_ms: int | None = Query(None, ge=1, le=7200000),
        player_id: int | None = None,
    ):
        with app.state.sessions() as session:
            _, rows = filtered_shots(
                session, match_id, team_id, period, start_ms, end_ms, player_id
            )
            release, predictions = match_predictions(session, match_id)
            points = [
                ShotPoint(
                    event_id=e.id,
                    index=e.index,
                    period=e.period,
                    timestamp=e.timestamp,
                    period_ms=e.period_ms,
                    minute=e.minute,
                    second=e.second,
                    team_id=e.team_id,
                    player_id=e.player_id,
                    player_name=e.player_name,
                    x=e.x if in_pitch(e.x, e.y) else None,
                    y=e.y if in_pitch(e.x, e.y) else None,
                    outcome=s.outcome,
                    goal=s.goal,
                    body_part=s.body_part,
                    shot_type=s.shot_type,
                    location_status=location_status(e.x, e.y),
                    xg=predictions[e.id].probability if e.id in predictions else None,
                    model=model_provenance(release, predictions[e.id])
                    if e.id in predictions
                    else None,
                )
                for e, s in rows
            ]
            return ShotLayer(
                match_id=match_id,
                shots=points,
                total_shots=len(points),
                located_shots=sum(p.x is not None and p.y is not None for p in points),
                result_id=result_id(match_id, team_id, period, start_ms, end_ms, player_id),
            )

    @app.get("/api/v1/evidence/{evidence_id}", response_model=ShotEvidence)
    def evidence(evidence_id: str):
        if not re.fullmatch(r"shots-\d{1,10}-\d{1,10}-[0-4]-\d{1,8}-\d{1,8}-\d{1,10}", evidence_id):
            raise HTTPException(422, "Invalid evidence identifier")
        mid, team, period, start, end, player = map(int, evidence_id.split("-")[1:])
        with app.state.sessions() as session:
            match, rows = filtered_shots(
                session,
                mid,
                team or None,
                period or None,
                start,
                end or None,
                player or None,
            )
            name = (
                "Both teams"
                if not team
                else (match.home_name if team == match.home_id else match.away_name)
            )
            if player:
                name = (
                    session.scalar(
                        select(Event.player_name)
                        .where(
                            Event.match_id == mid,
                            Event.player_id == player,
                        )
                        .limit(1)
                    )
                    or f"Player {player}"
                )
            scope = "the match (excluding shootouts)" if not period else f"period {period}"
            if start or end:
                scope += (
                    f", from {start / 60000:g} to {end / 60000:g} period minutes"
                    if end
                    else (f", from {start / 60000:g} period minutes to period end")
                )
            source = session.get(SourceManifest, f"data/events/{mid}.json")
            return ShotEvidence(
                result_id=evidence_id,
                match_id=mid,
                value=len(rows),
                team_id=team or None,
                player_id=player or None,
                period=period or None,
                start_ms=start,
                end_ms=end or None,
                definition="Count of Shot events. Start inclusive, end exclusive; "
                "all outcomes and missing locations included. Shootouts excluded.",
                statement=(
                    f"{name} recorded {len(rows)} shot{'s' if len(rows) != 1 else ''} in {scope}."
                ),
                references=[
                    EventReference(
                        event_id=e.id,
                        index=e.index,
                        period=e.period,
                        timestamp=e.timestamp,
                        player_name=e.player_name,
                        team_name=e.team_name,
                        outcome=s.outcome,
                        source_url=f"{SOURCE_WEB}/data/events/{mid}.json",
                    )
                    for e, s in rows
                ],
                source_sha256=source.sha256 if source else None,
            )

    @app.get("/api/v1/matches/{match_id}/events", response_model=LocalEvents)
    def events(match_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=250)):
        if settings.mode != "local":
            raise HTTPException(404, "Full event exploration is available in local mode only")
        with app.state.sessions() as session:
            require_match(session, match_id)
            query = select(Event).where(Event.match_id == match_id)
            records = session.scalars(query.order_by(Event.index).offset(offset).limit(limit)).all()
            total = session.scalar(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.match_id == match_id,
                )
            )
            return LocalEvents(
                events=[LocalEvent.model_validate(e) for e in records],
                offset=offset,
                limit=limit,
                total=total,
            )

    frontend = Path(settings.frontend_dir)
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if (frontend / "index.html").exists():
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})
        return {
            "message": "Build frontend with npm run build, or run its Vite dev server.",
            "docs": "/docs",
        }

    @app.get("/guide", include_in_schema=False)
    def user_guide():
        path = frontend / "guide.html"
        if not path.is_file():
            raise HTTPException(404, "User guide unavailable; rebuild the frontend")
        return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})

    return app
