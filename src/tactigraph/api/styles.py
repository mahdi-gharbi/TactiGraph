from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from tactigraph.db import DatasetReport, Match, SourceManifest

router = APIRouter(prefix="/api/v1", tags=["style discovery"])


class StyleCluster(BaseModel):
    cluster: int
    label: str
    training_windows: int
    means: dict[str, float]


class StyleReport(BaseModel):
    version: str
    features: list[str]
    training_windows: int
    training_matches: int
    projected_windows: int
    clusters: list[StyleCluster]
    pca_explained_variance: list[float]
    training_silhouette: float
    seed_ari: list[float]
    match_bootstrap_ari: list[float]
    limitation: str
    model_sha256: str
    source_commit: str


class StyleWindow(BaseModel):
    match_id: int
    team_id: int
    period: int
    start_ms: int
    end_ms: int
    pass_count: int
    spatial_pass_count: int
    features: list[float]
    evidence_id: str
    partition: str
    cluster: int


class StylesResponse(BaseModel):
    status: Literal["available", "not_trained", "stale"]
    report: StyleReport | None = None
    windows: list[StyleWindow] = []


def stored(session, match_id=None):
    stored_report = session.get(DatasetReport, "styles-v1")
    if stored_report is None:
        return StylesResponse(status="not_trained")
    payload = stored_report.payload
    sources = {s.path: s for s in session.scalars(select(SourceManifest))}
    for match, digest in payload["report"]["source_hashes"].items():
        source = sources.get(f"data/events/{match}.json")
        if (
            source is None
            or source.sha256 != digest
            or source.commit != payload["report"]["source_commit"]
        ):
            return StylesResponse(status="stale")
    return StylesResponse(
        status="available",
        report=StyleReport(**payload["report"]),
        windows=[StyleWindow(**w) for w in payload["windows"] if w["match_id"] == match_id],
    )


@router.get("/experiments/styles", response_model=StylesResponse)
def experiment(request: Request):
    with request.app.state.sessions() as session:
        return stored(session)


@router.get("/matches/{match_id}/styles", response_model=StylesResponse)
def match_styles(match_id: int, request: Request):
    with request.app.state.sessions() as session:
        if session.get(Match, match_id) is None:
            raise HTTPException(404, "Match not ingested")
        return stored(session, match_id)
