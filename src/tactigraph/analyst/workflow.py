"""Explicit state machine. All quantities come from analytical Python tools."""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from tactigraph.analyst.contracts import (
    VERSION,
    AnalystReport,
    AnalystRequest,
    ClaimSelection,
    Fact,
    ToolResult,
    VerifiedClaim,
)
from tactigraph.analytics.windows import VERSION as METRIC_VERSION
from tactigraph.analytics.windows import analyze, load_match
from tactigraph.db import SourceManifest
from tactigraph.models import xt_serving

ALLOWED = {
    "period_comparison": ("final_third_entries", "field_tilt", "passes", "completed_passes"),
    "chance_creation": ("shots", "xg", "movement_xt"),
    "network_concentration": ("network_concentration", "network_passes"),
}
LABELS = {
    "final_third_entries": "Final-third entries per elapsed minute",
    "field_tilt": "Share of completed attacking-third passes",
    "passes": "Attempted passes",
    "completed_passes": "Pass completion fraction",
    "shots": "Shots",
    "xg": "Model xG",
    "movement_xt": "Signed movement xT",
    "network_concentration": "Outgoing pass concentration (HHI)",
    "network_passes": "Included completed network passes",
}
LIMITATIONS = {
    "no_causality": "These indicators do not establish a loss of control or its cause. "
    "Goals, substitutions and dismissals are context, not causal proof.",
    "no_tracking": "Event data cannot establish off-ball runs, defensive shape "
    "or passing alternatives.",
    "small_window": "Small-window passing networks can be unstable; positions are historical "
    "on-ball observations, not a tactical formation.",
}
QUESTIONS = {
    "did progression decrease?": "period_comparison",
    "how did chance creation change?": "chance_creation",
    "did passing become more concentrated?": "network_concentration",
    "why did this team lose control after minute 60?": "period_comparison",
    "explain this team's collapse after minute 60.": "period_comparison",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class State(str, Enum):
    VALIDATE = "validate_request"
    INTENT = "select_intent"
    PLAN = "build_bounded_plan"
    EXECUTE = "execute_tools"
    CONSTRUCT = "construct_claims"
    VERIFY = "verify_claims"
    RENDER = "render_or_abstain"


def execute_tool(session, arguments):
    match, rows, stints, release, predictions = load_match(
        session, arguments.match_id, arguments.team_id, [arguments.before, arguments.after]
    )
    source = session.get(SourceManifest, f"data/events/{match.id}.json")
    if (
        source is None
        or source.commit != match.source_commit
        or source.validation_status != "valid"
    ):
        raise ValueError("A verified source manifest is required")
    xt = xt_serving.report(session)
    complete_results = [
        analyze(match.id, arguments.team_id, window, rows, stints, release, predictions, xt)
        for window in (arguments.before, arguments.after)
    ]
    analyses = [item[0] for item in complete_results]
    event_ids = {}
    for analysis, refs in complete_results:
        for fact in analysis.measurements:
            event_ids[fact.evidence_id] = [e.id for e in refs.get(fact.metric, [])]
        window = analysis.window
        boundary_ids = set()
        for stint, _ in stints:
            if stint.start_period <= window.period <= stint.end_period:
                start = stint.start_ms if stint.start_period == window.period else 0
                end = stint.end_ms if stint.end_period == window.period else window.end_ms
                if max(start, window.start_ms) < min(end, window.end_ms):
                    boundary_ids.update(e for e in (stint.source_event_id, stint.end_event_id) if e)
        event_ids[analysis.network.evidence_id] = sorted(
            {e.id for e in refs["network"]} | boundary_ids
        )

    def facts(analysis):
        values = [
            Fact(**m.model_dump())
            for m in analysis.measurements
            if m.metric in ALLOWED[arguments.intent]
        ]
        if arguments.intent == "network_concentration":
            network = analysis.network
            values += [
                Fact(
                    metric="network_concentration",
                    value=network.concentration,
                    unit="HHI",
                    numerator=None,
                    denominator=network.pass_count,
                    denominator_unit="included completed passes",
                    evidence_id=network.evidence_id,
                ),
                Fact(
                    metric="network_passes",
                    value=network.pass_count,
                    unit="passes",
                    numerator=network.pass_count,
                    denominator=None,
                    denominator_unit="none",
                    evidence_id=network.evidence_id,
                ),
            ]
        return values

    values = {
        "tool": "get_passing_network"
        if arguments.intent == "network_concentration"
        else "compare_windows",
        "arguments": arguments.model_dump(),
        "before": [f.model_dump() for f in facts(analyses[0])],
        "after": [f.model_dump() for f in facts(analyses[1])],
        "source_commit": match.source_commit,
        "source_sha256": source.sha256,
        "metric_version": METRIC_VERSION,
        "model_versions": {
            **({"xg": release.artifact_hash} if release else {}),
            **({"xt": xt["lock"]["artifact_hash"]} if xt else {}),
        },
        "quality_warnings": sorted({w for a in analyses for w in a.warnings}),
    }
    return ToolResult(
        result_id="result-" + digest(values)[:24], supporting_event_ids=event_ids, **values
    )


def verify(selection, evidence):
    """Semantic support and allowlist checks, beyond Pydantic validation."""
    if selection.result_id != evidence.result_id:
        raise ValueError("Claim cites an unrelated result")
    if selection.predicate == "limitation":
        if selection.limitation not in LIMITATIONS or selection.metric is not None:
            raise ValueError("Unsupported limitation")
        return VerifiedClaim(
            kind="limitation",
            predicate=selection.limitation,
            text=LIMITATIONS[selection.limitation],
            result_id=evidence.result_id,
            evidence_ids=[],
        )
    if (
        selection.limitation is not None
        or selection.metric not in ALLOWED[evidence.arguments.intent]
    ):
        raise ValueError("Predicate does not match the requested analysis")
    a = next((f for f in evidence.before if f.metric == selection.metric), None)
    b = next((f for f in evidence.after if f.metric == selection.metric), None)
    if a is None or b is None or a.value is None or b.value is None:
        raise ValueError("Unavailable numerical evidence")
    if a.unit != b.unit or (a.denominator == 0 and a.denominator_unit != "none"):
        raise ValueError("Incomparable or zero-denominator evidence")
    if b.denominator == 0 and b.denominator_unit != "none":
        raise ValueError("Zero-denominator evidence")
    direction = (
        "increased" if b.value > a.value else "decreased" if b.value < a.value else "were unchanged"
    )

    def displayed(value):
        return f"{value:.4f}".rstrip("0").rstrip(".") if value else "0"

    text = (
        f"{LABELS[selection.metric]} {direction}: "
        f"{displayed(a.value)} → {displayed(b.value)} {a.unit}."
    )
    return VerifiedClaim(
        kind="measured_fact",
        predicate="compare_metric",
        text=text,
        result_id=evidence.result_id,
        evidence_ids=[a.evidence_id, b.evidence_id],
        before=a.value,
        after=b.value,
        unit=a.unit,
    )


def run(session, request):
    trace = [State.VALIDATE.value]
    arguments = AnalystRequest.model_validate(request)
    if arguments.question is not None:
        intended = QUESTIONS.get(arguments.question.strip().lower())
        if intended is None or intended != arguments.intent:
            raise ValueError(
                "Unsupported question. Use a guided statistical comparison. "
                "Off-ball explanations, guaranteed outcomes and causal claims "
                "cannot be established from these tools."
            )
    trace.extend([State.INTENT.value, State.PLAN.value, State.EXECUTE.value])
    # One read-only tool, with a hard budget for future extensions.
    plan = [execute_tool]
    if len(plan) > 6:
        raise ValueError("Tool budget exceeded")
    evidence = plan[0](session, arguments)
    trace.append(State.CONSTRUCT.value)
    candidates = [
        ClaimSelection(predicate="compare_metric", metric=metric, result_id=evidence.result_id)
        for metric in ALLOWED[arguments.intent]
    ]
    candidates += [
        ClaimSelection(predicate="limitation", limitation=key, result_id=evidence.result_id)
        for key in ("no_causality", "no_tracking", "small_window")
    ]
    trace.append(State.VERIFY.value)
    claims, rejected = [], 0
    for candidate in candidates:
        try:
            claims.append(verify(candidate, evidence))
        except ValueError:
            rejected += 1
    measured = [c for c in claims if c.kind == "measured_fact"]
    # A period comparison needs progression, not merely a surviving pass count.
    core_metric = ALLOWED[arguments.intent][0]
    core = next(f for f in evidence.before if f.metric == core_metric)
    status = (
        "verified"
        if measured and any(core.evidence_id in c.evidence_ids for c in measured)
        else "abstained"
    )
    trace.append(State.RENDER.value)
    qualifications = evidence.quality_warnings + [
        "Windows are period-local and half-open; all displayed comparisons use the bounds shown.",
        "Unavailable measurements are omitted, never replaced with zero.",
        "This report is deterministic. No language-model generation "
        "or human semantic review is claimed.",
    ]
    if rejected:
        qualifications.append(
            f"{rejected} unsupported or unavailable numerical claims were removed."
        )
    return AnalystReport(
        report_id="report-" + digest({"result": evidence.result_id, "version": VERSION})[:24],
        status=status,
        generated_at=datetime.now(timezone.utc).isoformat(),
        arguments=arguments,
        claims=claims,
        evidence=evidence,
        trace=trace,
        tool_calls=len(plan),
        verification_rejections=rejected,
        qualifications=qualifications,
    )
