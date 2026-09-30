"""Extract only explicitly requested match partitions; never infer a split from labels."""

from collections import Counter

from sqlalchemy import select

from tactigraph.db import ControlEpisode, Event, EventContext, Pass, Shot
from tactigraph.models.xt import Action, Episode, close_actions


def extract(session, match_ids):
    episodes, exclusions = [], Counter()
    seen = 0
    for mid in sorted(match_ids):
        rows = session.execute(
            select(
                Event.id,
                Event.type,
                Event.x,
                Event.y,
                Pass.completed,
                Pass.end_x.label("pass_x"),
                Pass.end_y.label("pass_y"),
                EventContext.end_x.label("carry_x"),
                EventContext.end_y.label("carry_y"),
                EventContext.action_outcome,
                Shot.goal,
            )
            .outerjoin(Pass, Pass.event_id == Event.id)
            .outerjoin(EventContext, EventContext.event_id == Event.id)
            .outerjoin(Shot, Shot.event_id == Event.id)
            .where(Event.match_id == mid)
        ).all()
        by_id = {r.id: r for r in rows}
        for episode in session.scalars(
            select(ControlEpisode)
            .where(ControlEpisode.match_id == mid, ControlEpisode.period < 5)
            .order_by(ControlEpisode.start_index)
        ):
            seen += 1
            actions = []
            try:
                for event_id in episode.event_ids:
                    r = by_id[event_id]
                    if r.type == "Pass":
                        actions.append(
                            Action("move" if r.completed else "loss", r.x, r.y, r.pass_x, r.pass_y)
                        )
                    elif r.type == "Carry":
                        actions.append(Action("move", r.x, r.y, r.carry_x, r.carry_y))
                    elif r.type == "Shot":
                        actions.append(Action("shot", r.x, r.y, goal=bool(r.goal)))
                    elif r.type in {"Dispossessed", "Miscontrol"} or (
                        r.type == "Dribble" and r.action_outcome == "Incomplete"
                    ):
                        actions.append(Action("loss", r.x, r.y))
                closed = close_actions(actions)
                episodes.append(Episode(episode.id, mid, closed))
            except (ValueError, KeyError) as error:
                exclusions[str(error)] += 1
    return episodes, {
        "source_episodes": seen,
        "eligible_episodes": len(episodes),
        "excluded_episodes": dict(exclusions),
        "matches": len(match_ids),
    }
