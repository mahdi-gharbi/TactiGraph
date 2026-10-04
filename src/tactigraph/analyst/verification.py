"""Independent all-claim reconciliation for guided and query reports."""

import math

from tactigraph.analyst.contracts import ClaimSelection
from tactigraph.analyst.rendering import FR_LIMITS, french_numeric_text
from tactigraph.analyst.workflow import LIMITATIONS, digest, verify


def verify_report(report, *, session=None):
    evidence = report.evidence
    if evidence.arguments != report.arguments:
        raise ValueError("Report context does not match evidence")
    if not evidence.source_commit or len(evidence.source_sha256) != 64:
        raise ValueError("Missing source provenance")
    expected_id = "result-" + digest(evidence.model_dump(exclude={"result_id"}))[:24]
    if evidence.result_id != expected_id:
        raise ValueError("Tool result fingerprint changed")
    if session is not None:
        from sqlalchemy import select

        from tactigraph.db import Event, Match, SourceManifest

        match = session.get(Match, report.arguments.match_id)
        source = session.get(SourceManifest, f"data/events/{report.arguments.match_id}.json")
        if (
            match is None
            or source is None
            or source.validation_status != "valid"
            or source.commit != evidence.source_commit
            or source.sha256 != evidence.source_sha256
            or match.source_commit != evidence.source_commit
        ):
            raise ValueError("Source provenance changed")
        event_ids = set(session.scalars(select(Event.id).where(Event.match_id == match.id)))
        if any(not set(ids) <= event_ids for ids in evidence.supporting_event_ids.values()):
            raise ValueError("Supporting events do not belong to the selected match")
    verified = 0
    for claim in report.claims:
        if claim.result_id != evidence.result_id:
            raise ValueError("Unrelated claim result")
        if claim.kind == "limitation":
            if claim.predicate not in LIMITATIONS or claim.evidence_ids:
                raise ValueError("Unsupported limitation")
            if claim.text not in {LIMITATIONS[claim.predicate], FR_LIMITS[claim.predicate]}:
                raise ValueError("Limitation wording changed")
            continue
        if len(claim.evidence_ids) != 2:
            raise ValueError("A numerical comparison requires two references")
        # A network evidence ID intentionally backs both HHI and pass-count facts.
        a = next(
            (
                f
                for f in evidence.before
                if f.evidence_id == claim.evidence_ids[0] and f.unit == claim.unit
            ),
            None,
        )
        b = next(
            (
                f
                for f in evidence.after
                if f.evidence_id == claim.evidence_ids[1] and f.unit == claim.unit
            ),
            None,
        )
        if a is None or b is None or a.metric != b.metric or a.value is None or b.value is None:
            raise ValueError("Unrelated numerical evidence")
        for fact in (a, b):
            for value in (fact.value, fact.numerator, fact.denominator):
                if value is not None and not math.isfinite(value):
                    raise ValueError("Nonfinite numerical evidence")
            if fact.evidence_id not in evidence.supporting_event_ids:
                raise ValueError("Missing event support")
            if fact.denominator_unit != "none" and (
                fact.denominator is None or fact.denominator <= 0
            ):
                raise ValueError("Invalid denominator")
            if fact.metric in {"completed_passes", "final_third_entries", "field_tilt"} and (
                fact.numerator is None
                or not math.isclose(
                    fact.value, fact.numerator / fact.denominator, rel_tol=1e-10, abs_tol=1e-12
                )
            ):
                raise ValueError("Numerator and denominator do not reconcile")
        if a.denominator_unit != b.denominator_unit:
            raise ValueError("Incomparable denominators")
        expected = verify(
            ClaimSelection(
                predicate="compare_metric", metric=a.metric, result_id=evidence.result_id
            ),
            evidence,
        )
        if (
            claim.before != expected.before
            or claim.after != expected.after
            or claim.unit != expected.unit
            or claim.evidence_ids != expected.evidence_ids
            or claim.predicate != expected.predicate
            or claim.text not in {expected.text, french_numeric_text(expected, a.metric)}
        ):
            raise ValueError("Claim does not reconcile with tool values")
        verified += 1
    if report.status == "verified" and not verified:
        raise ValueError("Verified report has no numerical claims")
    return {"all_claims_verified": True, "verified_claims": verified}
