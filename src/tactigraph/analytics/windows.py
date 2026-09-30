"""Period-local, half-open windows. All arithmetic stays on the server."""

import json
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256

import networkx as nx
from fastapi import HTTPException
from sqlalchemy import select

from tactigraph.api.schemas import Provenance
from tactigraph.api.tactical_schemas import Measurement, Window, WindowAnalysis
from tactigraph.data.geometry import in_pitch
from tactigraph.db import Event, EventContext, LineupStint, Match, Pass, Player, Shot
from tactigraph.models.serving import match_predictions
from tactigraph.models.xt_serving import movement_value

VERSION = "windows-network-v1"
DEFINITIONS = {
    "movement_xt": "Signed xT changes for completed passes/carries. "
    "Failed passes, failed dribbles, dispossessions and miscontrols receive minus origin value. "
    "Shots receive no movement credit. Invalid coordinates are excluded and counted in warnings. "
    "This measures observed movement/loss actions, not synthetic episode terminal transitions.",
    "passes": "All attempted passes by the selected team; count, including failed passes.",
    "completed_passes": "Completed passes divided by all attempted passes; fraction, not percent.",
    "shots": "Shots in the selected period-local half-open window; shootouts excluded.",
    "xg": "Sum of stored xG for every shot, including separately modeled penalties. Null if any "
    "shot lacks a prediction or no evaluated model is available. Denominator is shot count.",
    "final_third_entries": "Completed passes or carries from x < 80 to x >= 80, with both "
    "locations inside the 120 by 80 pitch, divided by selected elapsed minutes (not ball-in-play).",
    "field_tilt": "Selected team's completed passes ending at x >= 80 divided by both teams' "
    "such passes, in each event team's attacking frame. Invalid endpoints excluded. "
    "Zero denominator means unavailable, not zero share. Evidence includes both teams.",
    "network": "Directed completed-pass graph. Nodes include players with overlapping lineup "
    "stints plus observed senders/recipients. Self-passes and unknown endpoints excluded. "
    "Strength is pass count; normalized betweenness uses exact inverse-count path distances. "
    "Density is edges / n(n-1); concentration is sum of squared outgoing pass shares (HHI). "
    "Positions average completed-pass origins and receptions; they are not tracking positions. "
    "Evidence includes passes, valued movements/losses and overlapping lineup boundary events.",
}


def evidence_id(match_id, team_id, window, metric):
    return (
        f"tactics-{match_id}-{team_id}-{window.period}-{window.start_ms}-{window.end_ms}-{metric}"
    )


def load_match(session, match_id, team_id, windows):
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Match not ingested")
    if team_id not in (match.home_id, match.away_id):
        raise HTTPException(422, "Team does not participate in this match")
    rows = session.execute(
        select(Event, Pass, EventContext, Shot)
        .outerjoin(Pass, Pass.event_id == Event.id)
        .outerjoin(EventContext, EventContext.event_id == Event.id)
        .outerjoin(Shot, Shot.event_id == Event.id)
        .where(Event.match_id == match_id, Event.period < 5)
        .order_by(Event.index)
    ).all()
    for w in windows:
        period_rows = [r for r in rows if r[0].period == w.period]
        if not period_rows or w.end_ms > max(r[0].period_ms for r in period_rows) + 1:
            raise HTTPException(422, "Window exceeds the recorded period coverage")
    stints = session.execute(
        select(LineupStint, Player.name)
        .join(Player, Player.id == LineupStint.player_id)
        .where(LineupStint.match_id == match_id, LineupStint.team_id == team_id)
    ).all()
    release, predictions = match_predictions(session, match_id)
    return match, rows, stints, release, predictions


def exposure(stints, window):
    intervals = defaultdict(list)
    names = {}
    for stint, name in stints:
        if stint.start_period > window.period or stint.end_period < window.period:
            continue
        start = max(window.start_ms, stint.start_ms if stint.start_period == window.period else 0)
        end = min(
            window.end_ms, stint.end_ms if stint.end_period == window.period else window.end_ms
        )
        if end > start:
            intervals[stint.player_id].append((start, end))
            names[stint.player_id] = name
    minutes = {}
    for player_id, spans in intervals.items():
        # Union intervals: tactical-role changes must not double count exposure.
        total, boundary = 0, -1
        for start, end in sorted(spans):
            total += max(0, end - max(start, boundary))
            boundary = max(boundary, end)
        minutes[player_id] = total / 60000
    return minutes, names


def passing_network(rows, stints, window, result_id, xt=None):
    graph = nx.DiGraph()
    minutes, names = exposure(stints, window)
    graph.add_nodes_from(names)
    positions = defaultdict(list)
    supporting = []
    excluded = 0
    for event, pass_, _, _ in rows:
        if pass_ is None or not pass_.completed:
            continue
        a, b = event.player_id, pass_.recipient_id
        if a is None or b is None or a == b:
            excluded += 1
            continue
        names[a] = event.player_name or names.get(a, f"Player {a}")
        names[b] = pass_.recipient_name or names.get(b, f"Player {b}")
        if graph.has_edge(a, b):
            graph[a][b]["count"] += 1
        else:
            graph.add_edge(a, b, count=1)
        supporting.append(event)
        if in_pitch(event.x, event.y):
            positions[a].append((event.x, event.y))
        if in_pitch(pass_.end_x, pass_.end_y):
            positions[b].append((pass_.end_x, pass_.end_y))
    for _, _, edge in graph.edges(data=True):
        edge["distance"] = Fraction(1, edge["count"])
    between = nx.betweenness_centrality(graph, weight="distance", normalized=True)
    count = len(supporting)
    nodes = []
    player_values = defaultdict(list)
    for event, pass_, context, _ in rows:
        _, value = movement_value(event, pass_, context, xt)
        if value is not None:
            player_values[event.player_id].append(value)
    for player in sorted(graph):
        points = positions[player]
        nodes.append(
            {
                "player_id": player,
                "name": names[player],
                "x": sum(p[0] for p in points) / len(points) if points else None,
                "y": sum(p[1] for p in points) / len(points) if points else None,
                "position_samples": len(points),
                "exposure_minutes": minutes.get(player),
                "in_strength": graph.in_degree(player, weight="count"),
                "out_strength": graph.out_degree(player, weight="count"),
                "betweenness": between[player],
                "movement_xt": sum(player_values[player]) if xt else None,
                "valued_actions": len(player_values[player]),
            }
        )
    return {
        "nodes": nodes,
        "edges": [
            {"sender": a, "recipient": b, "count": d["count"]}
            for a, b, d in sorted(graph.edges(data=True))
        ],
        "pass_count": count,
        "excluded_passes": excluded,
        "density": nx.density(graph),
        "concentration": sum((n["out_strength"] / count) ** 2 for n in nodes) if count else None,
        "evidence_id": result_id,
    }, supporting


def entry_status(row):
    event, pass_, context, _ = row
    if pass_ is not None and pass_.completed:
        end = (pass_.end_x, pass_.end_y)
    elif event.type == "Carry":
        end = (context.end_x, context.end_y) if context else (None, None)
    else:
        return False
    if not in_pitch(event.x, event.y) or not in_pitch(*end):
        return None
    return event.x < 80 <= end[0]


def analyze(match_id, team_id, window: Window, all_rows, stints, release, predictions, xt=None):
    rows = [
        r
        for r in all_rows
        if r[0].period == window.period and window.start_ms <= r[0].period_ms < window.end_ms
    ]
    own = [r for r in rows if r[0].team_id == team_id]
    passes = [r[0] for r in own if r[1] is not None]
    completed = [r[0] for r in own if r[1] is not None and r[1].completed]
    shots = [r[0] for r in own if r[3] is not None]
    thirds = [
        r[0]
        for r in rows
        if r[1] is not None
        and r[1].completed
        and in_pitch(r[1].end_x, r[1].end_y)
        and r[1].end_x >= 80
    ]
    entries, invalid_movements = [], 0
    for row in own:
        status = entry_status(row)
        invalid_movements += status is None
        if status:
            entries.append(row[0])
    refs = {
        "passes": passes,
        "completed_passes": passes,
        "shots": shots,
        "xg": shots,
        "final_third_entries": entries,
        "field_tilt": thirds,
    }
    measured = []

    def add(metric, value, unit, numerator, denominator, denominator_unit):
        measured.append(
            Measurement(
                metric=metric,
                value=value,
                unit=unit,
                numerator=numerator,
                denominator=denominator,
                denominator_unit=denominator_unit,
                evidence_id=evidence_id(match_id, team_id, window, metric),
            )
        )

    duration = (window.end_ms - window.start_ms) / 60000
    predicted = [predictions[e.id].probability for e in shots if e.id in predictions]
    xg = sum(predicted) if release is not None and len(predicted) == len(shots) else None
    add("shots", len(shots), "shots", len(shots), 1, "window")
    add("xg", xg, "expected goals", xg, len(shots), "shots")
    add("passes", len(passes), "passes", len(passes), 1, "window")
    add(
        "completed_passes",
        len(completed) / len(passes) if passes else None,
        "fraction",
        len(completed),
        len(passes),
        "attempted passes",
    )
    add(
        "final_third_entries",
        len(entries) / duration,
        "entries/minute",
        len(entries),
        duration,
        "elapsed minutes",
    )
    own_thirds = sum(e.team_id == team_id for e in thirds)
    add(
        "field_tilt",
        own_thirds / len(thirds) if thirds else None,
        "fraction",
        own_thirds,
        len(thirds),
        "both teams' completed final-third passes",
    )
    network, refs["network"] = passing_network(
        own, stints, window, evidence_id(match_id, team_id, window, "network"), xt
    )
    movement = [(r[0], movement_value(r[0], r[1], r[2], xt)) for r in own]
    eligible = [(event, value) for event, (is_move, value) in movement if is_move]
    valued = [(event, value) for event, value in eligible if value is not None]
    total_xt = sum(value for _, value in valued) if xt else None
    refs["movement_xt"] = [event for event, _ in valued]
    network_ids = {e.id for e in refs["network"]} | {e.id for e in refs["movement_xt"]}
    refs["network"] = [r[0] for r in own if r[0].id in network_ids]
    add("movement_xt", total_xt, "signed xT", total_xt, len(valued), "valued actions")
    warnings = ["Descriptive associations do not establish tactical causes or off-ball shape."]
    if xt and len(valued) != len(eligible):
        warnings.append(
            f"Movement xT: {len(valued)}/{len(eligible)} actions; invalid coordinates excluded."
        )
    if network["pass_count"] < 30:
        warnings.append(
            "Fewer than 30 completed network passes: sparse-window metrics may be unstable."
        )
    if any(r[0].type == "Substitution" for r in own):
        warnings.append(
            "This window includes a substitution. Narrow the bounds to inspect each lineup."
        )
    if invalid_movements:
        warnings.append(
            f"{invalid_movements} movements excluded from entry counts: invalid coordinates."
        )
    if any(n["exposure_minutes"] is None for n in network["nodes"]):
        warnings.append("Some observed players have no verified lineup exposure in this window.")
    if len(predicted) < len(shots):
        warnings.append(
            f"xG coverage: {len(predicted)}/{len(shots)} shots; incomplete totals are unavailable."
        )
    return WindowAnalysis(
        window=window, measurements=measured, network=network, warnings=warnings
    ), refs


def provenance(match):
    return Provenance(source_commit=match.source_commit, metric_version=VERSION)


def comparison_id(match, request, release, before, after, xt=None):
    # Include versions and measurements so changed results do not alias an old comparison ID.
    payload = {
        "match": match.id,
        "commit": match.source_commit,
        "version": VERSION,
        "request": request.model_dump(),
        "model": release.id if release else None,
        "xt_artifact": xt["lock"]["artifact_hash"] if xt else None,
        "before": before.model_dump(),
        "after": after.model_dump(),
    }
    return "comparison-" + sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
