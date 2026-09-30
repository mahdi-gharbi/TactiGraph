"""Event-sourced dimensions and sequence reconstruction; no predictive fitting."""

from collections import Counter

from tactigraph.config import PIPELINE_VERSION
from tactigraph.data.geometry import in_pitch

SUPPORTED_SCHEMAS = {"1.0.2", "1.0.3", "1.1.0"}
CONTROL_ACTIONS = {
    "Pass",
    "Carry",
    "Shot",
    "Dribble",
    "Dispossessed",
    "Miscontrol",
    "Ball Recovery",
    "Interception",
}
RESTARTS = {"Kick Off", "Throw-in", "Goal Kick", "Free Kick", "Corner"}


def name(event, field):
    return (event.get(field) or {}).get("name")


def dimensions(match, raw, lineups):
    mid = match["match_id"]
    teams = [
        {
            "id": match[f"{side}_team"][f"{side}_team_id"],
            "name": match[f"{side}_team"][f"{side}_team_name"],
        }
        for side in ("home", "away")
    ]
    players, members = {}, {}

    def register(team, player, declared=False):
        pid = player.get("id") or player.get("player_id")
        pname = player.get("name") or player.get("player_name")
        if pid is None or pname is None:
            return
        players[pid] = {"id": pid, "name": pname}
        key = (team, pid)
        members[key] = {
            "match_id": mid,
            "team_id": team,
            "player_id": pid,
            "declared_in_lineup": declared or members.get(key, {}).get("declared_in_lineup", False),
        }

    for team in lineups:
        for player in team.get("lineup", []):
            register(team["team_id"], player, True)
    for event in raw:
        tid = event.get("team", {}).get("id")
        if tid is None:
            continue
        register(tid, event.get("player", {}))
        register(tid, event.get("pass", {}).get("recipient", {}))
        register(tid, event.get("substitution", {}).get("replacement", {}))
        for player in event.get("tactics", {}).get("lineup", []):
            register(tid, player["player"])
    return teams, sorted(players.values(), key=lambda p: p["id"]), list(members.values())


def contexts(match, raw, normalized):
    schema = match.get("metadata", {}).get("data_version", "unknown")
    home_id, away_id = match["home_team"]["home_team_id"], match["away_team"]["away_team_id"]
    score = {home_id: 0, away_id: 0}
    rows = []
    for event, e in zip(raw, normalized, strict=True):
        kind = event["type"]["name"]
        body = event.get(kind.lower().replace(" ", "_"), {})
        end = body.get("end_location") if kind in {"Pass", "Carry"} else None
        pressure = event.get("under_pressure")
        # Preserve raw omission. Schema-specific truth-only normalization is explicit.
        pressure_status = "explicit" if pressure is not None else "omitted_not_inferred"
        if (
            pressure is None
            and schema in SUPPORTED_SCHEMAS
            and kind in {"Pass", "Shot", "Carry", "Dribble"}
        ):
            pressure, pressure_status = False, "omitted_false_supported_action"
        if schema not in SUPPORTED_SCHEMAS:
            pressure_status = "unknown_schema" if pressure is None else "explicit_unknown_schema"
        rows.append(
            {
                "event_id": e["id"],
                "play_pattern": name(event, "play_pattern"),
                "position_id": event.get("position", {}).get("id"),
                "duration": (event.get("duration") if event.get("duration", 0) >= 0 else None),
                "end_x": float(end[0]) if end else None,
                "end_y": float(end[1]) if end else None,
                "action_outcome": name(body, "outcome"),
                "pressure_value": pressure,
                "pressure_status": pressure_status,
                "ball_out": event.get("out"),
                "off_camera": event.get("off_camera"),
                "related_event_ids": event.get("related_events", []),
                "home_score_before": score[home_id],
                "away_score_before": score[away_id],
                "adapter_version": f"statsbomb-{schema}/{PIPELINE_VERSION}",
                "attributes": {
                    k: body[k]
                    for k in (
                        "first_time",
                        "follows_dribble",
                        "cross",
                        "cutback",
                        "through_ball",
                        "switch",
                        "aerial_won",
                        "recovery_failure",
                    )
                    if k in body
                },
            }
        )
        if e["period"] == 5:
            continue
        if kind == "Shot" and name(body, "outcome") == "Goal":
            score[e["team_id"]] += 1
        elif kind == "Own Goal Against":
            score[away_id if e["team_id"] == home_id else home_id] += 1
    return rows, score


def reconstruct_stints(mid, raw, normalized):
    active, suspended, expelled, stints, issues = {}, {}, set(), [], []

    def start(tid, pid, position, event, e):
        key = (tid, pid)
        active[key] = {
            "id": f"{mid}:{tid}:{pid}:{e['index']}",
            "match_id": mid,
            "team_id": tid,
            "player_id": pid,
            "position_id": position.get("id"),
            "position_name": position.get("name"),
            "start_index": e["index"],
            "start_period": e["period"],
            "start_ms": e["period_ms"],
            "source_event_id": e["id"],
        }

    def end(key, e, reason, final=False):
        row = active.pop(key, None)
        if row:
            stints.append(
                {
                    **row,
                    "end_index": e["index"] + int(final),
                    "end_period": e["period"],
                    "end_ms": e["period_ms"],
                    "end_event_id": e["id"],
                    "end_reason": reason,
                }
            )
        return row

    for event, e in zip(raw, normalized, strict=True):
        tid, pid, kind = e["team_id"], e["player_id"], e["type"]
        if kind in {"Starting XI", "Tactical Shift"}:
            entries = event.get("tactics", {}).get("lineup", [])
            next_ids = {p["player"]["id"] for p in entries}
            for key in list(active):
                if key[0] == tid and key[1] not in next_ids:
                    end(key, e, "lineup_change")
            for entry in entries:
                pid2 = entry["player"]["id"]
                key, pos = (tid, pid2), entry.get("position", {})
                if key in expelled or key in suspended:
                    continue
                if key in active and active[key]["position_id"] != pos.get("id"):
                    end(key, e, "role_change")
                if key not in active:
                    start(tid, pid2, pos, event, e)
        elif kind == "Substitution":
            old = end((tid, pid), e, "substitution") or suspended.pop((tid, pid), None)
            replacement = event.get("substitution", {}).get("replacement", {}).get("id")
            expelled.add((tid, pid))
            if replacement is not None:
                if old is None:
                    issues.append(
                        {"code": "substitution_without_active_player", "event_id": e["id"]}
                    )
                position = (
                    {"id": old["position_id"], "name": old["position_name"]}
                    if old
                    else event.get("position", {})
                )
                start(tid, replacement, position, event, e)
        elif name(event.get("bad_behaviour", {}), "card") in {"Red Card", "Second Yellow"} or name(
            event.get("foul_committed", {}), "card"
        ) in {"Red Card", "Second Yellow"}:
            end((tid, pid), e, "dismissal")
            suspended.pop((tid, pid), None)
            expelled.add((tid, pid))
        elif kind == "Player Off":
            old = end((tid, pid), e, "player_off")
            if event.get("player_off", {}).get("permanent"):
                expelled.add((tid, pid))
            elif old:
                suspended[(tid, pid)] = old
        elif kind == "Player On" and (tid, pid) not in expelled:
            old = suspended.pop((tid, pid), None)
            if old:
                start(tid, pid, {"id": old["position_id"], "name": old["position_name"]}, event, e)
        if pid is not None and kind in CONTROL_ACTIONS and (tid, pid) not in active:
            issues.append({"code": "actor_not_in_active_lineup", "event_id": e["id"]})
    for key in list(active):
        end(key, normalized[-1], "match_end", final=True)
    return stints, issues


def possessions_and_episodes(mid, raw, normalized):
    groups = {}
    for e in normalized:
        if e["possession"] is None or e["possession_team_id"] is None:
            continue
        key = f"{mid}:{e['period']}:{e['possession']}"
        group = groups.setdefault(
            key,
            {
                "id": key,
                "match_id": mid,
                "source_id": e["possession"],
                "period": e["period"],
                "team_id": e["possession_team_id"],
                "start_index": e["index"],
                "end_index": e["index"],
                "event_ids": [],
            },
        )
        if group["team_id"] != e["possession_team_id"]:
            raise ValueError(f"Conflicting possession owner: {key}")
        group["end_index"] = e["index"]
        group["event_ids"].append(e["id"])

    episodes, membership, current = [], [], None
    next_reason, previous_group = "possession_start", None

    def close(reason):
        nonlocal current, next_reason
        if current:
            current["end_reason"] = reason
            episodes.append(current)
            for ordinal, eid in enumerate(current["event_ids"]):
                membership.append(
                    {"event_id": eid, "episode_id": current["id"], "ordinal": ordinal}
                )
        current = None
        next_reason = "after_shot" if reason == "shot" else "after_loss"

    for event, e in zip(raw, normalized, strict=True):
        key = f"{mid}:{e['period']}:{e['possession']}"
        if e["period"] == 5:
            close("period_end")
            continue
        if key != previous_group:
            if current:
                close("period_end" if e["period"] != current["period"] else "possession_change")
            next_reason = "possession_start"
            previous_group = key
        if e["type"] in {"Half End", "Half Start"}:
            close("period_end")
            next_reason = "period_start"
            continue
        if key not in groups:
            close("unknown_possession")
            continue
        # Opponent pressure/duels belong to the source possession but are not owner's actions.
        if e["team_id"] != e["possession_team_id"]:
            continue
        kind = e["type"]
        if kind not in CONTROL_ACTIONS:
            if kind in {"Foul Won", "Foul Committed", "Injury Stoppage"} and not event.get(
                kind.lower().replace(" ", "_"), {}
            ).get("advantage", False):
                close("stoppage")
                next_reason = "restart"
            continue
        body = event.get(kind.lower().replace(" ", "_"), {})
        if kind == "Ball Recovery" and body.get("recovery_failure"):
            continue
        if kind == "Interception" and name(body, "outcome") not in {
            "Won",
            "Success",
            "Success In Play",
            "Success Out",
        }:
            continue
        if kind == "Pass" and name(body, "type") in RESTARTS:
            close("restart")
            next_reason = "restart"
        if current is None:
            current = {
                "id": f"{mid}:episode:{e['index']}",
                "match_id": mid,
                "possession_id": key,
                "team_id": e["team_id"],
                "period": e["period"],
                "start_index": e["index"],
                "end_index": e["index"],
                "start_ms": e["period_ms"],
                "end_ms": e["period_ms"],
                "start_reason": next_reason,
                "end_reason": "unknown",
                "play_pattern": name(event, "play_pattern"),
                "action_count": 0,
                "completed_passes": 0,
                "has_shot": False,
                "goal": False,
                "event_ids": [],
                "pipeline_version": PIPELINE_VERSION,
            }
        current["end_index"], current["end_ms"] = e["index"], e["period_ms"]
        current["action_count"] += 1
        current["event_ids"].append(e["id"])
        if kind == "Pass" and "outcome" not in body:
            current["completed_passes"] += 1
        if kind == "Shot":
            current["has_shot"] = True
            current["goal"] = name(body, "outcome") == "Goal"
            close("shot")
        elif (
            kind in {"Dispossessed", "Miscontrol"}
            or (kind == "Pass" and "outcome" in body)
            or (kind == "Dribble" and name(body, "outcome") == "Incomplete")
        ):
            close("loss")
        elif event.get("out"):
            close("ball_out")
    close("file_end")
    return list(groups.values()), episodes, membership


def derive(match, raw, normalized, passes, shots, lineups):
    raw = sorted(raw, key=lambda e: e["index"])
    mid = match["match_id"]
    teams, players, members = dimensions(match, raw, lineups)
    context_rows, score = contexts(match, raw, normalized)
    stints, issues = reconstruct_stints(mid, raw, normalized)
    for event in raw:
        if event.get("duration", 0) < 0:
            issues.append(
                {
                    "code": "negative_duration_unavailable",
                    "event_id": event["id"],
                    "source_duration": event["duration"],
                }
            )
    possessions, episodes, membership = possessions_and_episodes(mid, raw, normalized)
    ids = {e["id"]: e for e in normalized}
    for e in normalized:
        if e["x"] is not None and not in_pitch(e["x"], e["y"]):
            issues.append({"code": "event_location_outside_pitch", "event_id": e["id"]})
    for context in context_rows:
        if context["end_x"] is not None and not in_pitch(context["end_x"], context["end_y"]):
            issues.append(
                {"code": "movement_endpoint_outside_pitch", "event_id": context["event_id"]}
            )
    for s in shots:
        key = s["key_pass_id"]
        if key and (
            key not in ids
            or ids[key]["type"] != "Pass"
            or ids[key]["index"] >= ids[s["event_id"]]["index"]
        ):
            issues.append({"code": "invalid_prior_key_pass", "event_id": s["event_id"]})
    for side in ("home", "away"):
        if score[match[f"{side}_team"][f"{side}_team_id"]] != match[f"{side}_score"]:
            issues.append({"code": "score_reconciliation", "side": side})
    for member in members:
        if not member["declared_in_lineup"]:
            issues.append({"code": "player_not_declared", "player_id": member["player_id"]})
    schema = match.get("metadata", {}).get("data_version", "unknown")
    if schema not in SUPPORTED_SCHEMAS:
        issues.append({"code": "unknown_source_schema", "schema": schema})
    row_by_id = {e["id"]: e for e in normalized}
    missing = {
        "event_location": sum(e["x"] is None for e in normalized),
        "shot_location": sum(row_by_id[s["event_id"]]["x"] is None for s in shots),
        "pass_endpoint": sum(p["end_x"] is None for p in passes),
        "completed_pass_recipient": sum(
            p["completed"] and p["recipient_id"] is None for p in passes
        ),
    }
    quality = {
        "match_id": mid,
        "schema": schema,
        "pipeline_version": PIPELINE_VERSION,
        "counts": {
            "events": len(normalized),
            "passes": len(passes),
            "shots": len(shots),
            "possessions": len(possessions),
            "control_episodes": len(episodes),
            "lineup_stints": len(stints),
        },
        "missing": missing,
        "issue_counts": dict(Counter(i["code"] for i in issues)),
        "issues": issues,
        "has_starting_xi": sum(e["type"] == "Starting XI" for e in normalized) == 2,
    }
    return {
        "teams": teams,
        "players": players,
        "match_players": members,
        "event_context": context_rows,
        "lineup_stints": stints,
        "possessions": possessions,
        "control_episodes": episodes,
        "episode_events": membership,
        "quality": quality,
    }


def active_players_at(stints, team_id, cutoff_index):
    """Intervals are descriptive; use replay_active_players for prediction feature generation."""
    return {
        s["player_id"]
        for s in stints
        if s["team_id"] == team_id and s["start_index"] <= cutoff_index < s["end_index"]
    }


def replay_active_players(mid, raw, normalized, team_id, cutoff_index):
    """Replay only observed events. Suffix mutations cannot alter this snapshot."""
    pairs = [(r, e) for r, e in zip(raw, normalized, strict=True) if e["index"] <= cutoff_index]
    if not pairs:
        return set()
    r, e = zip(*pairs, strict=True)
    stints, _ = reconstruct_stints(mid, list(r), list(e))
    return active_players_at(stints, team_id, cutoff_index)
