from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tactigraph.analyst.contracts import AnalystReport
from tactigraph.db import DatasetReport
from tactigraph.release import VERSION, current, fingerprint

router = APIRouter(prefix="/api/v1", tags=["cached showcase"])


class CachedReport(BaseModel):
    report: AnalystReport
    sha256: str
    review_status: Literal["pending", "approved"]
    publication_label: str
    cached: bool = True


class ShowcaseResponse(BaseModel):
    status: Literal["not_prepared", "review_pending", "available", "stale"]
    reports: list[CachedReport] = []


def showcase(session, public, match_id=None):
    stored = session.get(DatasetReport, VERSION)
    if stored is None:
        return ShowcaseResponse(status="not_prepared")
    payload = stored.payload
    reports = []
    pending = not payload.get("publication_review")
    for entry in payload["reports"]:
        report = AnalystReport.model_validate(entry["report"])
        if fingerprint(report) != entry["sha256"] or not current(session, report):
            return ShowcaseResponse(status="stale")
        reviewed = bool(entry.get("review"))
        pending |= not reviewed
        if match_id is None or report.arguments.match_id == match_id:
            label = (
                "Cached deterministic report; independent review recorded"
                if reviewed
                else "Cached deterministic preview; human review pending"
            )
            reports.append(
                CachedReport(
                    report=report,
                    sha256=entry["sha256"],
                    review_status="approved" if reviewed else "pending",
                    publication_label=label,
                )
            )
    return ShowcaseResponse(
        status="review_pending" if pending else "available",
        reports=[] if pending and public else reports,
    )


@router.get("/showcase", response_model=ShowcaseResponse)
def cached_reports(request: Request, match_id: int | None = None):
    with request.app.state.sessions() as session:
        return showcase(session, request.app.state.settings.mode == "public", match_id)


@router.get("/ready")
def ready(request: Request):
    with request.app.state.sessions() as session:
        result = showcase(session, True)
        if result.status != "available" or len(result.reports) != 36:
            raise HTTPException(503, "Reviewed showcase is not ready")
        return {"status": "ready", "cached_reports": len(result.reports)}
