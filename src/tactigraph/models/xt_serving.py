"""Pure-Python lookup of a published aggregate surface; no training runtime."""

from tactigraph.data.geometry import in_pitch
from tactigraph.db import DatasetReport


def report(session):
    stored = session.get(DatasetReport, "xt")
    return stored.payload if stored else None


def provenance(xt):
    if xt is None:
        return None
    return {
        "model_version": xt["version"],
        "family": "spatial-markov",
        "artifact_hash": xt["lock"]["artifact_hash"],
        "run_id": xt["lock"]["run_id"],
        "feature_version": xt["model"]["pipeline_version"],
    }


def movement_value(event, pass_, context, xt):
    """Return (eligible action, value). Shots never receive a movement credit."""
    end = None
    if pass_ is not None:
        if pass_.completed:
            end = (pass_.end_x, pass_.end_y)
    elif event.type == "Carry":
        end = (context.end_x, context.end_y) if context else (None, None)
    elif event.type in {"Dispossessed", "Miscontrol"}:
        pass
    elif event.type == "Dribble" and context and context.action_outcome == "Incomplete":
        pass
    else:
        return False, None
    if xt is None or not in_pitch(event.x, event.y) or (end is not None and not in_pitch(*end)):
        return True, None
    width, height = xt["model"]["grid"]

    def value(x, y):
        index = min(int(y / 80 * height), height - 1) * width + min(int(x / 120 * width), width - 1)
        return xt["model"]["values"][index]

    return True, (value(*end) if end is not None else 0) - value(event.x, event.y)
