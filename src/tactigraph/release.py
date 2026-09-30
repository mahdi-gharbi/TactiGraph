"""Prepare a fixed, reviewable public showcase without external generation."""

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from tactigraph.analyst.contracts import AnalystReport, AnalystRequest
from tactigraph.analyst.workflow import ALLOWED, digest, run
from tactigraph.db import DatasetReport, Match, MatchQuality, SourceManifest
from tactigraph.models.serving import latest_release
from tactigraph.models.xt_serving import report as xt_report

VERSION = "showcase-v1"


def fingerprint(report):
    return digest(report.model_dump(mode="json"))


def current(session, report):
    source = session.get(SourceManifest, f"data/events/{report.arguments.match_id}.json")
    xg = latest_release(session)
    xt = xt_report(session)
    models = {
        **({"xg": xg.artifact_hash} if xg else {}),
        **({"xt": xt["lock"]["artifact_hash"]} if xt else {}),
    }
    return bool(
        source
        and source.validation_status == "valid"
        and source.commit == report.evidence.source_commit
        and source.sha256 == report.evidence.source_sha256
        and models == report.evidence.model_versions
    )


def prepare(session, output=Path("output/release-review")):
    """Three high-coverage matches per season, stable ID tie-break, no outcome selection."""
    if session.get(DatasetReport, VERSION):
        raise ValueError("Showcase already prepared; export the existing review packet instead")
    matches = session.scalars(select(Match).order_by(Match.season_id, Match.id)).all()
    groups = {}
    for match in matches:
        quality = session.get(MatchQuality, match.id)
        if not quality or not quality.payload.get("has_starting_xi"):
            continue
        q = quality.payload
        missing = q.get("missing", {})
        if (
            q.get("issue_counts")
            or missing.get("shot_location", 0)
            or missing.get("completed_pass_recipient", 0)
        ):
            continue
        coverage = 1 - missing.get("pass_endpoint", 0) / max(1, q["counts"]["passes"])
        groups.setdefault(match.season_id, []).append((-coverage, match.id, match))
    if len(groups) != 4:
        raise ValueError("Four ingested WSL seasons with quality reports are required")
    selected, reports, exclusions = [], [], []
    for season, candidates in sorted(groups.items()):
        accepted = 0
        for negative_coverage, _, match in sorted(candidates):
            try:
                batch = [
                    run(
                        session,
                        AnalystRequest(match_id=match.id, team_id=match.home_id, intent=intent),
                    )
                    for intent in ALLOWED
                ]
                if any(
                    r.status != "verified"
                    or r.verification_rejections
                    or set(r.evidence.model_versions) != {"xg", "xt"}
                    for r in batch
                ):
                    raise ValueError("Incomplete measurements or model coverage")
            except (ValueError, HTTPException) as error:
                exclusions.append({"match_id": match.id, "reason": str(error)})
                continue
            selected.append(
                {
                    "match_id": match.id,
                    "season_id": season,
                    "home": match.home_name,
                    "away": match.away_name,
                    "team_id": match.home_id,
                    "pass_endpoint_coverage": -negative_coverage,
                }
            )
            reports.extend(batch)
            accepted += 1
            if accepted == 3:
                break
        if accepted != 3:
            raise ValueError(f"Season {season} has fewer than three complete candidates")
    payload = {
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "Three per season; valid quality, complete models and claims; "
        "pass endpoint coverage descending then match ID ascending. "
        "Home team; H2 0–15 vs 15–30; all three guided intents.",
        "matches": selected,
        "exclusions": exclusions,
        "reports": [
            {"report": r.model_dump(mode="json"), "sha256": fingerprint(r), "review": None}
            for r in reports
        ],
        "publication_review": None,
    }
    session.add(DatasetReport(id=VERSION, generated_at=datetime.now(timezone.utc), payload=payload))
    session.flush()
    export_review(payload, output)
    return {"matches": len(selected), "reports": len(reports), "human_review": "pending"}


def export_review(payload, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "reports.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    approvals = {
        "version": VERSION,
        "reviewer": "",
        "reviewed_at": "",
        "publication_review": {
            "attribution_checked": False,
            "data_terms_checked": False,
            "raw_data_excluded": False,
        },
        "reports": [
            {
                "report_id": e["report"]["report_id"],
                "sha256": e["sha256"],
                "approved": False,
                "notes": "",
            }
            for e in payload["reports"]
        ],
    }
    # Never overwrite a human's filled-in review file.
    path = output / "approvals.json"
    if not path.exists():
        path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")
    sections = []
    for entry in payload["reports"]:
        r = AnalystReport.model_validate(entry["report"])
        match = next(m for m in payload["matches"] if m["match_id"] == r.arguments.match_id)
        title = f"{match['home']} – {match['away']} · {r.arguments.intent}"
        facts = "".join(
            f"<li>{html.escape(c.text)}<br><small>"
            f"{html.escape(', '.join(c.evidence_ids))}</small></li>"
            for c in r.claims
        )
        source = f"https://github.com/hudl/open-data/blob/{r.evidence.source_commit}/data/events/{r.arguments.match_id}.json"
        details = json.dumps(r.evidence.model_dump(mode="json"), indent=2)
        sections.append(
            f"<section><h2>{html.escape(title)}</h2><p>Home team; second half "
            f"0–15 vs 15–30 minutes. Human review pending.</p><ul>{facts}</ul>"
            f'<a href="{source}">Pinned StatsBomb source</a>'
            f"<p>Report: {r.report_id}<br>Review SHA-256: {entry['sha256']}</p>"
            f"<details><summary>Measurements and denominators</summary>"
            f"<pre>{html.escape(details)}</pre></details></section>"
        )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>TactiGraph release review</title>'
        "<style>body{font:16px/1.6 system-ui;max-width:960px;margin:32px auto;padding:20px;"
        "color:#18342c}section{border-top:1px solid #ccd8d2;padding:24px 0}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}small,p{overflow-wrap:anywhere}</style>"
        "<h1>36 cached reports — independent review packet</h1>"
        "<p>Data provided by StatsBomb Open Data. Numerical machine checks passed. "
        "A reviewer must check interpretation, evidence and publication terms, then fill "
        "approvals.json. Nothing in this packet claims human approval.</p>" + "".join(sections)
    )
    (output / "index.html").write_text(document, encoding="utf-8")


def approve(session, path):
    approval = json.loads(path.read_text(encoding="utf-8"))
    reviewer = approval.get("reviewer", "").strip()
    if not reviewer or not approval.get("reviewed_at"):
        raise ValueError("A named reviewer and review date are required")
    datetime.fromisoformat(approval["reviewed_at"])
    publication = approval.get("publication_review", {})
    if any(
        publication.get(k) is not True
        for k in ("attribution_checked", "data_terms_checked", "raw_data_excluded")
    ):
        raise ValueError("Publication review is incomplete")
    row = session.get(DatasetReport, VERSION)
    if row is None or approval.get("version") != VERSION:
        raise ValueError("No matching showcase")
    payload = json.loads(json.dumps(row.payload))
    reviews = {e["report_id"]: e for e in approval["reports"]}
    if len(reviews) != len(payload["reports"]) or len(reviews) != len(approval["reports"]):
        raise ValueError("Every cached report requires a unique review")
    for entry in payload["reports"]:
        report = AnalystReport.model_validate(entry["report"])
        review = reviews.get(report.report_id, {})
        if (
            review.get("approved") is not True
            or review.get("sha256") != entry["sha256"]
            or fingerprint(report) != entry["sha256"]
            or not current(session, report)
        ):
            raise ValueError("Unapproved, modified or stale report")
        entry["review"] = {
            "reviewer": reviewer,
            "reviewed_at": approval["reviewed_at"],
            "notes": review.get("notes", ""),
        }
    payload["publication_review"] = {
        **publication,
        "reviewer": reviewer,
        "reviewed_at": approval["reviewed_at"],
    }
    row.payload = payload
    return {"approved_reports": len(reviews)}
