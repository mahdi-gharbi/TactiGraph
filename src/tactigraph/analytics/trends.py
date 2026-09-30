from tactigraph.analytics.windows import entry_status, evidence_id
from tactigraph.api.tactical_schemas import CandidateShift, MomentumPoint, Window
from tactigraph.models.xt_serving import movement_value


def trends(match_id, team_id, period, rows, release, predictions, xt):
    period_rows = [r for r in rows if r[0].period == period]
    end = max(r[0].period_ms for r in period_rows)
    own = [r for r in period_rows if r[0].team_id == team_id]
    # Each point is [end-5 minutes, end), clipped at the start of THIS period.
    endpoints = sorted(set([*range(60000, end, 60000), end]))
    points = []
    for endpoint in endpoints:
        if endpoint <= 0:
            continue
        w = Window(period=period, start_ms=max(0, endpoint - 300000), end_ms=endpoint)
        selected = [r for r in own if w.start_ms <= r[0].period_ms < w.end_ms]
        shots = [r[0] for r in selected if r[3] is not None]
        probabilities = [predictions[e.id].probability for e in shots if e.id in predictions]
        movements = [movement_value(r[0], r[1], r[2], xt) for r in selected]
        values = [value for eligible, value in movements if eligible and value is not None]
        points.append(
            MomentumPoint(
                start_ms=w.start_ms,
                end_ms=w.end_ms,
                xg=sum(probabilities)
                if release is not None and len(probabilities) == len(shots)
                else None,
                movement_xt=sum(values) if xt else None,
                shots=len(shots),
                predicted_shots=len(probabilities),
                valued_actions=len(values),
                eligible_actions=sum(eligible for eligible, _ in movements),
                xg_evidence_id=evidence_id(match_id, team_id, w, "xg"),
                xt_evidence_id=evidence_id(match_id, team_id, w, "movement_xt"),
            )
        )
    counts = []
    for start in range(0, end - 300000 + 1, 300000):
        counts.append(
            sum(bool(entry_status(r)) for r in own if start <= r[0].period_ms < start + 300000)
        )
    candidates = [
        CandidateShift(
            boundary_ms=i * 300000,
            before_count=counts[i - 1],
            after_count=counts[i],
            rate_difference=(counts[i] - counts[i - 1]) / 5,
            before_evidence_id=evidence_id(
                match_id,
                team_id,
                Window(period=period, start_ms=(i - 1) * 300000, end_ms=i * 300000),
                "final_third_entries",
            ),
            after_evidence_id=evidence_id(
                match_id,
                team_id,
                Window(period=period, start_ms=i * 300000, end_ms=(i + 1) * 300000),
                "final_third_entries",
            ),
        )
        for i in range(1, len(counts))
        if counts[i] != counts[i - 1]
    ]
    return points, sorted(candidates, key=lambda c: (-abs(c.rate_difference), c.boundary_ms))[:3]
