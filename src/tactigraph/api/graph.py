"""Read-only exported evaluations. This module never imports the ML runtime."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, model_validator

from tactigraph.api.diagnostics import calibration_summary_reason
from tactigraph.api.schemas import BaseModel, ModelProvenance
from tactigraph.api.xt_schemas import XTLock
from tactigraph.db import DatasetReport, Match


class GraphCalibrationBin(BaseModel):
    lower: float
    upper: float
    n: int
    predicted: float
    observed: float


class GraphMetrics(BaseModel):
    log_loss: float
    brier: float
    roc_auc: float | None
    pr_auc: float | None


class GraphScore(GraphMetrics):
    n: int
    positive_episodes: int
    intervals: dict[str, list[float]]
    reliability: list[GraphCalibrationBin]
    calibration: dict[str, float] | None
    calibration_reason: str | None = None
    uncalibrated: GraphMetrics | None = None
    prepared_inference_p95_ms: float | None = None
    artifact_hash: str | None = None


class GraphSeedAggregate(BaseModel):
    seeds: list[str]
    metrics: GraphMetrics
    intervals: dict[str, list[float]]


class GraphDecision(BaseModel):
    justified: bool
    strongest_test_baseline: str
    gates: dict[str, bool]
    paired_differences: dict[str, dict[str, list[float]]]
    interpretation: str


class GraphCoverage(BaseModel):
    n: int
    positive_episodes: int
    matches: int
    source_episodes: int
    exclusions: dict[str, int]


class GraphStress(BaseModel):
    status: Literal["evaluated", "no_eligible_test_samples"]
    held_out_teams: list[int]
    development_counts: dict[str, int]
    n: int
    matches: int
    results: dict[str, GraphScore]
    paired_difference: dict[str, list[float]]


class GraphReport(BaseModel):
    version: str
    generated_at: str
    source_commit: str
    lock: XTLock
    test: GraphCoverage
    development_counts: dict[str, int]
    results: dict[str, GraphScore]
    seed_aggregates: dict[str, GraphSeedAggregate]
    decision: GraphDecision
    serving: str
    stress: dict[str, GraphStress]
    latency_definition: str
    seed_definition: str
    attribution: str
    test_disclosure: str

    @model_validator(mode="after")
    def guard_legacy_calibration(self):
        studies = [self.results, *(study.results for study in self.stress.values())]
        for results in studies:
            for name, result in results.items():
                reason = calibration_summary_reason(name, result.n, result.positive_episodes)
                if reason:
                    result.calibration = None
                    result.calibration_reason = reason
        return self


class GraphResponse(BaseModel):
    status: Literal["evaluated", "not_trained"]
    report: GraphReport | None


class ThirdPassPrediction(BaseModel):
    sample_id: str
    cutoff_event_id: str
    team_id: int
    period: int
    timestamp: str
    cutoff_ms: int
    probability: float = Field(ge=0, le=1)
    split: Literal["train", "tuning", "calibration", "test"]
    observed_later_shot: bool


class ThirdPassResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    match_id: int
    source_commit: str
    model: ModelProvenance | None
    total: int
    samples: list[ThirdPassPrediction]
    warning: str = (
        "Train/tuning predictions are in-sample; calibration data fitted the "
        "probability mapping. Only test predictions support held-out evaluation. These are "
        "historical shot-occurrence predictions, not causal effects or xG."
    )


router = APIRouter(prefix="/api/v1", tags=["graph experiment"])


@router.get("/experiments/graph", response_model=GraphResponse)
def graph_experiment(request: Request):
    with request.app.state.sessions() as session:
        stored = session.get(DatasetReport, "graph")
        return GraphResponse(
            status="evaluated" if stored else "not_trained",
            report=stored.payload if stored else None,
        )


@router.get("/matches/{match_id}/third-pass", response_model=ThirdPassResponse)
def third_pass_predictions(
    match_id: int,
    request: Request,
    team_id: int = Query(gt=0),
    period: int = Query(ge=1, le=4),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
):
    with request.app.state.sessions() as session:
        match = session.get(Match, match_id)
        if match is None:
            raise HTTPException(404, "Match not ingested")
        if team_id not in (match.home_id, match.away_id):
            raise HTTPException(422, "Team does not participate in this match")
        stored = session.get(DatasetReport, f"graph-predictions-{match_id}")
        release = session.get(DatasetReport, "graph")
        available = stored is not None and release is not None
        if available:
            available = (
                stored.payload["source_commit"] == match.source_commit
                and stored.payload["model"]["run_id"] == release.payload["lock"]["run_id"]
            )
        rows = (
            [
                row
                for row in stored.payload["samples"]
                if row["team_id"] == team_id and row["period"] == period
            ]
            if available
            else []
        )
        return ThirdPassResponse(
            status="ready" if available else "unavailable",
            match_id=match_id,
            source_commit=match.source_commit,
            model=stored.payload["model"] if available else None,
            total=len(rows),
            samples=rows[offset : offset + limit],
        )
