import re

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from tactigraph.analytics.trends import trends
from tactigraph.analytics.windows import (
    DEFINITIONS,
    analyze,
    comparison_id,
    load_match,
    provenance,
)
from tactigraph.api.schemas import EventReference
from tactigraph.api.tactical_schemas import (
    ComparisonRequest,
    ComparisonResponse,
    MetricDifference,
    NetworkResponse,
    TacticalEvidence,
    TrendsResponse,
    Window,
)
from tactigraph.api.xt_schemas import XTResponse
from tactigraph.db import LineupStint, SourceManifest
from tactigraph.models import xt_serving
from tactigraph.models.serving import provenance as model_provenance

router = APIRouter(prefix="/api/v1", tags=["tactical analytics"])


@router.get("/matches/{match_id}/trends", response_model=TrendsResponse)
def match_trends(
    match_id: int, request: Request, team_id: int = Query(gt=0), period: int = Query(ge=1, le=4)
):
    with request.app.state.sessions() as session:
        match, rows, _, release, predictions = load_match(session, match_id, team_id, [])
        if not any(r[0].period == period for r in rows):
            raise HTTPException(422, "Period not recorded")
        xt = xt_serving.report(session)
        points, shifts = trends(match_id, team_id, period, rows, release, predictions, xt)
        red_ids = set(
            session.scalars(
                select(LineupStint.end_event_id).where(
                    LineupStint.match_id == match_id, LineupStint.end_reason == "dismissal"
                )
            )
        )
        key_events = []
        for event, _, _, shot in rows:
            if event.period == period and (
                event.type == "Substitution"
                or event.id in red_ids
                or (shot and shot.goal)
                or event.type == "Own Goal Against"
            ):
                key_events.append(
                    EventReference(
                        event_id=event.id,
                        index=event.index,
                        period=period,
                        timestamp=event.timestamp,
                        player_name=event.player_name,
                        team_name=event.team_name,
                        outcome="Dismissal"
                        if event.id in red_ids
                        else "Goal"
                        if shot and shot.goal
                        else event.type,
                        source_url=f"https://github.com/hudl/open-data/blob/{match.source_commit}/data/events/{match_id}.json",
                    )
                )
        return TrendsResponse(
            match_id=match_id,
            team_id=team_id,
            period=period,
            points=points,
            candidate_shifts=shifts,
            key_events=key_events,
            warnings=[
                "Separate five-minute sums, clipped at period start; not a combined control score.",
                "Shifts rank adjacent complete five-minute entry-rate changes; "
                "not causes or significance tests.",
                "xT omits invalid-coordinate actions; inspect valued/eligible counts.",
            ],
            model=model_provenance(release),
            xt_model=xt_serving.provenance(xt),
            provenance=provenance(match),
        )


@router.get("/experiments/xt", response_model=XTResponse)
def xt_experiment(request: Request):
    with request.app.state.sessions() as session:
        result = xt_serving.report(session)
        return XTResponse(status="evaluated" if result else "not_trained", report=result)


@router.post("/matches/{match_id}/compare", response_model=ComparisonResponse)
def compare(match_id: int, arguments: ComparisonRequest, request: Request):
    with request.app.state.sessions() as session:
        match, rows, stints, release, predictions = load_match(
            session, match_id, arguments.team_id, [arguments.before, arguments.after]
        )
        xt = xt_serving.report(session)
        results = [
            analyze(match_id, arguments.team_id, w, rows, stints, release, predictions, xt)[0]
            for w in (arguments.before, arguments.after)
        ]
        before, after = results
        differences = [
            MetricDifference(
                metric=a.metric,
                unit=a.unit,
                value=b.value - a.value if a.value is not None and b.value is not None else None,
            )
            for a, b in zip(before.measurements, after.measurements, strict=True)
        ]
        entry_change = next(d.value for d in differences if d.metric == "final_third_entries")
        direction = (
            "decreased"
            if entry_change < 0
            else "increased"
            if entry_change > 0
            else "were unchanged"
        )
        return ComparisonResponse(
            result_id=comparison_id(match, arguments, release, before, after, xt),
            match_id=match_id,
            team_id=arguments.team_id,
            before=before,
            after=after,
            differences=differences,
            statement=f"Final-third entries per elapsed minute {direction}. "
            "This single indicator does not establish a loss of control or its cause.",
            model=model_provenance(release),
            provenance=provenance(match),
            xt_status="ready" if xt else "not_trained",
            xt_model=xt_serving.provenance(xt),
        )


@router.get("/matches/{match_id}/network", response_model=NetworkResponse)
def network(
    match_id: int,
    request: Request,
    team_id: int = Query(gt=0),
    period: int = Query(ge=1, le=4),
    start_ms: int = Query(ge=0),
    end_ms: int = Query(gt=0),
):
    try:
        window = Window(period=period, start_ms=start_ms, end_ms=end_ms)
    except ValueError as error:
        raise HTTPException(422, "Invalid period-local window") from error
    with request.app.state.sessions() as session:
        match, rows, stints, release, predictions = load_match(session, match_id, team_id, [window])
        xt = xt_serving.report(session)
        return NetworkResponse(
            match_id=match_id,
            team_id=team_id,
            analysis=analyze(match_id, team_id, window, rows, stints, release, predictions, xt)[0],
            model=model_provenance(release),
            provenance=provenance(match),
            xt_model=xt_serving.provenance(xt),
        )


@router.get("/tactical-evidence/{result_id}", response_model=TacticalEvidence)
def evidence(
    result_id: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=250),
):
    parsed = re.fullmatch(r"tactics-(\d+)-(\d+)-(\d+)-(\d+)-(\d+)-([a-z_]+)", result_id)
    if parsed is None or parsed[6] not in DEFINITIONS:
        raise HTTPException(404, "Unknown analytical evidence reference")
    match_id, team_id, period, start, end = map(int, parsed.groups()[:5])
    metric = parsed[6]
    try:
        window = Window(period=period, start_ms=start, end_ms=end)
    except ValueError as error:
        raise HTTPException(422, "Invalid evidence window") from error
    with request.app.state.sessions() as session:
        match, rows, stints, release, predictions = load_match(session, match_id, team_id, [window])
        xt = xt_serving.report(session)
        analysis, refs = analyze(match_id, team_id, window, rows, stints, release, predictions, xt)
        if metric == "network":
            # Exposure and isolated active players also depend on lineup boundary events.
            boundary_ids = set()
            for stint, _ in stints:
                if stint.start_period <= period <= stint.end_period:
                    start = stint.start_ms if stint.start_period == period else 0
                    end = stint.end_ms if stint.end_period == period else window.end_ms
                    if max(start, window.start_ms) < min(end, window.end_ms):
                        boundary_ids.update((stint.source_event_id, stint.end_event_id))
            pass_ids = {e.id for e in refs[metric]}
            refs[metric] = [r[0] for r in rows if r[0].id in boundary_ids | pass_ids]
        events = refs[metric]
        source = session.get(SourceManifest, f"data/events/{match_id}.json")
        url = f"https://github.com/hudl/open-data/blob/{match.source_commit}/data/events/{match_id}.json"
        return TacticalEvidence(
            result_id=result_id,
            match_id=match_id,
            team_id=team_id,
            window=window,
            metric=metric,
            definition=DEFINITIONS[metric],
            measurement=next((m for m in analysis.measurements if m.metric == metric), None),
            network=analysis.network if metric == "network" else None,
            references=[
                EventReference(
                    event_id=e.id,
                    index=e.index,
                    period=e.period,
                    timestamp=e.timestamp,
                    player_name=e.player_name,
                    team_name=e.team_name,
                    outcome=e.type,
                    source_url=url,
                )
                for e in events[offset : offset + limit]
            ],
            total=len(events),
            offset=offset,
            limit=limit,
            source_sha256=source.sha256 if source else None,
            model=xt_serving.provenance(xt)
            if metric == "movement_xt"
            else model_provenance(release),
            xt_model=xt_serving.provenance(xt),
            provenance=provenance(match),
        )
