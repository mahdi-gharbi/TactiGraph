"""Third-pass graphs with an explicit source-index information boundary."""

import hashlib
import json
import math
from collections import Counter
from fractions import Fraction

import networkx as nx
import polars as pl
from sqlalchemy import select

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.derive import reconstruct_stints
from tactigraph.data.geometry import in_pitch
from tactigraph.data.ingest import period_milliseconds
from tactigraph.db import ControlEpisode, SourceManifest

FEATURE_VERSION = "third-pass-prefix-v1"
ROLE_COUNT = 26  # Unknown, then the fixed StatsBomb role IDs 1..25.
NODE_DIM = ROLE_COUNT + 8
EDGE_DIM = 15
GLOBAL_NAMES = [
    "ball_x",
    "ball_y",
    "prefix_seconds",
    "period",
    "period_time",
    "score_difference",
    "prefix_actions",
    "prefix_progression",
    "pass_length",
    "prefix_carries",
    "counterattack",
    "pressure_share",
]
GRAPH_NAMES = ["nodes", "edges", "density", "concentration", "reciprocity", "mean_betweenness"]
TOUCHES = {
    "Pass",
    "Carry",
    "Dribble",
    "Shot",
    "Ball Receipt*",
    "Ball Recovery",
    "Interception",
    "Miscontrol",
    "Dispossessed",
}


def valid_location(value):
    return isinstance(value, list) and len(value) >= 2 and in_pitch(*value[:2])


def completion_ms(event):
    duration = event.get("duration")
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        raise ValueError("missing_or_invalid_pass_duration")
    return period_milliseconds(event["timestamp"]) + round(duration * 1000)


def graph_at_cutoff(raw, cutoff_index, episode_event_ids, team_id, match_id):
    # Filter BEFORE normalization, lineup replay or any feature computation.
    prefix = sorted((e for e in raw if e["index"] <= cutoff_index), key=lambda e: e["index"])
    cutoff = prefix[-1]
    if cutoff["index"] != cutoff_index or cutoff["type"]["name"] != "Pass":
        raise ValueError("cutoff_is_not_a_pass")
    current = [e for e in prefix if e["id"] in set(episode_event_ids)]
    completed = [e for e in current if e["type"]["name"] == "Pass" and "outcome" not in e["pass"]]
    if len(completed) != 3 or completed[-1]["id"] != cutoff["id"]:
        raise ValueError("cutoff_is_not_third_completed_pass")
    if any(e["type"]["name"] == "Shot" for e in current) or cutoff.get("out"):
        raise ValueError("not_controlled_at_cutoff")
    if cutoff.get("team", {}).get("id") != team_id:
        raise ValueError("cutoff_team_mismatch")
    end = cutoff["pass"].get("end_location")
    if not valid_location(end):
        raise ValueError("invalid_ball_location")
    period, cutoff_ms = cutoff["period"], completion_ms(cutoff)
    if period not in (1, 2, 3, 4):
        raise ValueError("unsupported_period")
    normalized = [
        {
            "id": e["id"],
            "index": e["index"],
            "period": e["period"],
            "period_ms": period_milliseconds(e["timestamp"]),
            "type": e["type"]["name"],
            "team_id": e.get("team", {}).get("id"),
            "player_id": e.get("player", {}).get("id"),
        }
        for e in prefix
    ]
    stints, _ = reconstruct_stints(match_id, prefix, normalized)
    active = {
        s["player_id"]: s["position_id"]
        for s in stints
        if s["team_id"] == team_id and s["start_index"] <= cutoff_index < s["end_index"]
    }
    holder = cutoff["pass"].get("recipient", {}).get("id")
    if not 7 <= len(active) <= 11:
        raise ValueError("invalid_replayed_lineup_size")
    if holder not in active or cutoff.get("player", {}).get("id") not in active:
        raise ValueError("cutoff_player_not_active")
    player_ids = sorted(active)
    node_id = {pid: i for i, pid in enumerate(player_ids)}
    touches, sent, received = Counter(), Counter(), Counter()
    last, edges, attributes, edge_ids = {}, [], [], []
    excluded_edges = Counter()
    episode_ids = {e["id"] for e in current}

    def observe(pid, loc, time):
        if pid in active and valid_location(loc) and time <= cutoff_ms:
            if pid not in last or time >= last[pid][2]:
                last[pid] = (loc[0], loc[1], time)

    score = 0
    for event in prefix:
        kind, tid = event["type"]["name"], event.get("team", {}).get("id")
        if kind == "Shot" and event.get("shot", {}).get("outcome", {}).get("name") == "Goal":
            score += 1 if tid == team_id else -1
        elif kind == "Own Goal Against":
            score += -1 if tid == team_id else 1
        if event["period"] != period or tid != team_id:
            continue
        time = period_milliseconds(event["timestamp"])
        if time > cutoff_ms:
            continue
        pid = event.get("player", {}).get("id")
        if kind in TOUCHES:
            observe(pid, event.get("location"), time)
            if time >= cutoff_ms - 300000:
                touches[pid] += 1
        if kind == "Carry" and event.get("duration", 0) >= 0:
            observe(
                pid,
                event.get("carry", {}).get("end_location"),
                time + round(event.get("duration", 0) * 1000),
            )
        if kind != "Pass" or "outcome" in event["pass"]:
            continue
        try:
            end_time = completion_ms(event)
        except ValueError:
            excluded_edges["missing_duration"] += 1
            continue
        recipient = event["pass"].get("recipient", {}).get("id")
        observe(recipient, event["pass"].get("end_location"), end_time)
        if not cutoff_ms - 300000 <= end_time <= cutoff_ms:
            continue
        sent[pid] += 1
        received[recipient] += 1
        if pid not in active or recipient not in active:
            excluded_edges["inactive_endpoint"] += 1
            continue
        a, b = event.get("location"), event["pass"].get("end_location")
        spatial = valid_location(a) and valid_location(b)
        length = event["pass"].get("length")
        height = event["pass"].get("height", {}).get("name")
        height_index = {"Ground Pass": 1, "Low Pass": 2, "High Pass": 3}.get(height, 0)
        attributes.append(
            [
                a[0] / 120 if spatial else 0,
                a[1] / 80 if spatial else 0,
                b[0] / 120 if spatial else 0,
                b[1] / 80 if spatial else 0,
                length / 120 if length is not None else 0,
                (cutoff_ms - end_time) / 300000,
                float(event.get("under_pressure", False)),
                0.0,
                float(event["id"] in episode_ids),
                float(not spatial),
                float(length is None),
                *[float(i == height_index) for i in range(4)],
            ]
        )
        edges.append([node_id[pid], node_id[recipient]])
        edge_ids.append(event["id"])
    # The third pass endpoint/recipient is known at completion, without reading Ball Receipt.
    observe(holder, end, cutoff_ms)
    nodes = []
    for pid in player_ids:
        role = active[pid] if active[pid] in range(1, ROLE_COUNT) else 0
        observation = last.get(pid)
        nodes.append(
            [
                *[float(i == role) for i in range(ROLE_COUNT)],
                touches[pid] / 20,
                sent[pid] / 20,
                received[pid] / 20,
                observation[0] / 120 if observation else 0,
                observation[1] / 80 if observation else 0,
                (cutoff_ms - observation[2]) / 300000 if observation else 0,
                float(observation is None),
                float(pid == holder),
            ]
        )
    lengths = [e["pass"].get("length", 0) for e in completed]
    progression = sum(
        e["pass"]["end_location"][0] - e["location"][0]
        for e in completed
        if valid_location(e.get("location")) and valid_location(e["pass"].get("end_location"))
    )
    globals_ = [
        end[0] / 120,
        end[1] / 80,
        (cutoff_ms - period_milliseconds(current[0]["timestamp"])) / 300000,
        period / 4,
        cutoff_ms / 2700000,
        score / 5,
        len(current) / 20,
        progression / 120,
        sum(lengths) / 3 / 120,
        sum(e["type"]["name"] == "Carry" for e in current) / 10,
        float(current[0].get("play_pattern", {}).get("name") == "From Counter"),
        sum(e.get("under_pressure", False) for e in current) / len(current),
    ]
    graph = nx.DiGraph()
    graph.add_nodes_from(range(len(nodes)))
    for a, b in edges:
        graph.add_edge(a, b, count=graph.get_edge_data(a, b, {}).get("count", 0) + 1)
    for _, _, edge in graph.edges(data=True):
        edge["distance"] = Fraction(1, edge["count"])
    centrality = nx.betweenness_centrality(graph, weight="distance")
    summary = [
        len(nodes) / 11,
        len(edges) / 100,
        nx.density(graph),
        sum((graph.out_degree(n, weight="count") / len(edges)) ** 2 for n in graph) if edges else 0,
        nx.reciprocity(graph) if graph.number_of_edges() else 0,
        sum(centrality.values()) / len(nodes),
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "edge_attributes": attributes,
        "globals": globals_,
        "tabular": globals_ + summary,
        "holder": node_id[holder],
        "player_ids": player_ids,
        "edge_event_ids": edge_ids,
        "cutoff_ms": cutoff_ms,
        "excluded_history_edges": {
            reason: excluded_edges[reason] for reason in ("missing_duration", "inactive_endpoint")
        },
    }


def build_dataset(settings, session, manifest, partitions):
    samples, exclusions, hashes = [], Counter(), {}
    source_episodes = 0
    assignments = [a for a in manifest["assignments"] if a["partition"] in partitions]
    for number, assignment in enumerate(assignments, 1):
        mid = assignment["match_id"]
        path = settings.data_dir / "raw" / SOURCE_COMMIT / "data" / "events" / f"{mid}.json"
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        source = session.get(SourceManifest, f"data/events/{mid}.json")
        if source is None or checksum != source.sha256 or source.commit != SOURCE_COMMIT:
            raise ValueError(f"Source snapshot mismatch: {mid}")
        hashes[str(mid)] = checksum
        raw = json.loads(content)
        by_id = {e["id"]: e for e in raw}
        episodes = session.scalars(
            select(ControlEpisode)
            .where(ControlEpisode.match_id == mid)
            .order_by(ControlEpisode.start_index)
        ).all()
        for episode in episodes:
            source_episodes += 1
            if (
                episode.period > 4
                or episode.play_pattern not in {"Regular Play", "From Counter"}
                or episode.start_reason in {"restart", "after_shot"}
            ):
                exclusions["not_open_play_episode"] += 1
                continue
            actions = [by_id[eid] for eid in episode.event_ids]
            completed = [
                e for e in actions if e["type"]["name"] == "Pass" and "outcome" not in e["pass"]
            ]
            if len(completed) < 3:
                exclusions["fewer_than_three_completed_passes"] += 1
                continue
            cutoff = completed[2]
            prefix_ids = [e["id"] for e in actions if e["index"] <= cutoff["index"]]
            try:
                features = graph_at_cutoff(raw, cutoff["index"], prefix_ids, episode.team_id, mid)
            except ValueError as error:
                exclusions[str(error)] += 1
                continue
            samples.append(
                {
                    "sample_id": f"{mid}:{cutoff['id']}",
                    "match_id": mid,
                    "episode_id": episode.id,
                    "team_id": episode.team_id,
                    "split": assignment["partition"],
                    "cutoff_event_id": cutoff["id"],
                    "cutoff_index": cutoff["index"],
                    "period": episode.period,
                    "label": any(
                        e["type"]["name"] == "Shot" and e["index"] > cutoff["index"]
                        for e in actions
                    ),
                    **features,
                }
            )
        if number % 25 == 0:
            print(
                f"Graph extraction: {number}/{len(assignments)} matches, {len(samples)} samples",
                flush=True,
            )
    return samples, {
        "source_episodes": source_episodes,
        "eligible_samples": len(samples),
        "exclusions": dict(exclusions),
        "source_hashes": hashes,
        "feature_version": FEATURE_VERSION,
    }


def save_samples(path, samples):
    # Polars infers nested child types before applying schema overrides. Convert
    # only the declared numeric vectors, retaining strict validation elsewhere.
    samples = [
        {
            **row,
            **{
                name: [[float(value) for value in vector] for vector in row[name]]
                for name in ("nodes", "edge_attributes")
            },
            **{name: [float(value) for value in row[name]] for name in ("globals", "tabular")},
        }
        for row in samples
    ]
    pl.DataFrame(
        samples,
        infer_schema_length=None,
        schema_overrides={
            "nodes": pl.List(pl.List(pl.Float64)),
            "edge_attributes": pl.List(pl.List(pl.Float64)),
            "globals": pl.List(pl.Float64),
            "tabular": pl.List(pl.Float64),
        },
    ).write_parquet(path)
