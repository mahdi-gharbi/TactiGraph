"""Turnover-aware spatial Markov model. NumPy is an offline-only dependency."""

from dataclasses import dataclass

import numpy as np

from tactigraph.data.geometry import in_pitch


@dataclass(frozen=True)
class Action:
    kind: str
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    goal: bool = False


@dataclass(frozen=True)
class Episode:
    id: str
    match_id: int
    actions: tuple[Action, ...]

    @property
    def goal(self):
        return any(a.kind == "shot" and a.goal for a in self.actions)


def zone(x, y, grid):
    if not in_pitch(x, y):
        raise ValueError("Invalid spatial coordinate")
    width, height = grid
    return min(int(y / 80 * height), height - 1) * width + min(int(x / 120 * width), width - 1)


def close_actions(actions):
    """Validate a single control episode and append its otherwise unrecorded terminal."""
    if not actions:
        raise ValueError("No eligible modeled actions")
    result = list(actions)
    for i, action in enumerate(result):
        if not in_pitch(action.x, action.y):
            raise ValueError("Invalid origin")
        if action.kind not in {"move", "loss", "shot"}:
            raise ValueError("Unknown action")
        if action.kind == "move" and not in_pitch(action.end_x, action.end_y):
            raise ValueError("Invalid destination")
        if action.kind != "move" and i != len(result) - 1:
            raise ValueError("Action after terminal")
    last = result[-1]
    if last.kind == "move":
        result.append(Action("loss", last.end_x, last.end_y))
    return tuple(result)


def solve(reward, transition, tolerance=1e-8, max_iterations=10000):
    values = np.zeros_like(reward, dtype=float)
    for iteration in range(1, max_iterations + 1):
        updated = reward + transition @ values
        delta = float(np.max(np.abs(updated - values)))
        if not np.all(np.isfinite(updated)) or np.any(updated < 0) or np.any(updated > 1 + 1e-10):
            raise ValueError("Invalid Markov values")
        values = updated
        if delta < tolerance:
            return values, iteration, delta
    raise ValueError("xT failed to converge")


def fit(
    episodes, grid=(12, 8), action_prior=10, scoring_prior=20, tolerance=1e-8, max_iterations=10000
):
    n = grid[0] * grid[1]
    counts = np.zeros((n, n + 2))  # destinations, shot, loss
    goals = np.zeros(n)
    for episode in episodes:
        for action in close_actions(episode.actions):
            origin = zone(action.x, action.y, grid)
            category = (
                zone(action.end_x, action.end_y, grid)
                if action.kind == "move"
                else n
                if action.kind == "shot"
                else n + 1
            )
            counts[origin, category] += 1
            if action.kind == "shot":
                goals[origin] += action.goal
    total = counts.sum()
    shots = counts[:, n]
    if total == 0 or shots.sum() == 0:
        raise ValueError("Fitting needs eligible actions and shots")
    if action_prior <= 0 or scoring_prior <= 0:
        raise ValueError("Prior strengths must be positive")
    probabilities = (counts + action_prior * counts.sum(axis=0) / total) / (
        counts.sum(axis=1, keepdims=True) + action_prior
    )
    scoring = (goals + scoring_prior * goals.sum() / shots.sum()) / (shots + scoring_prior)
    reward = probabilities[:, n] * scoring
    transition = probabilities[:, :n]
    values, iterations, delta = solve(reward, transition, tolerance, max_iterations)
    return {
        "grid": list(grid),
        "values": values.tolist(),
        "no_transition": reward.tolist(),
        "global_episode_rate": sum(e.goal for e in episodes) / len(episodes),
        "iterations": iterations,
        "maximum_delta": delta,
        "action_counts": counts.sum(axis=1).astype(int).tolist(),
        "shot_counts": shots.astype(int).tolist(),
        "goal_counts": goals.astype(int).tolist(),
        "total_actions": int(total),
        "episodes": len(episodes),
        "terminal_count": int(counts[:, n:].sum()),
        "row_probability_error": float(np.max(np.abs(probabilities.sum(axis=1) - 1))),
    }


def predict(episodes, artifact):
    indices = [zone(e.actions[0].x, e.actions[0].y, artifact["grid"]) for e in episodes]
    return {
        "xt": np.array([artifact["values"][i] for i in indices]),
        "no_transition": np.array([artifact["no_transition"][i] for i in indices]),
        "global": np.full(len(episodes), artifact["global_episode_rate"]),
    }
