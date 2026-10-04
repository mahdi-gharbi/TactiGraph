"""Read-only diagnostics summaries; importing this router never loads an ML runtime."""

from typing import Literal

from fastapi import APIRouter, Request
from sqlalchemy import select

from tactigraph.api.schemas import BaseModel
from tactigraph.db import DatasetReport, ModelRelease, SourceManifest

MIN_CALIBRATION_OBSERVATIONS = 20


def calibration_summary_reason(name, observations, positives):
    """Conservative display guards that can also be applied to legacy aggregate reports."""
    if name == "prevalence":
        return "Constant predictions cannot identify both a calibration intercept and slope."
    if observations < MIN_CALIBRATION_OBSERVATIONS:
        return "Calibration diagnostic requires at least 20 observations."
    if positives == 0 or positives == observations:
        return "Calibration diagnostic requires observations of both outcomes."
    if min(positives, observations - positives) < 2:
        return "Calibration diagnostic requires at least two observations of each outcome."
    return None


class CalibrationDiagnostic(BaseModel):
    calibration: dict[str, float] | None
    calibration_reason: str | None = None
    n: int
    positives: int


class GroupedImportance(BaseModel):
    group: str
    features: list[str]
    mean_log_loss_increase: float
    std: float
    repeats: int


class DiagnosticProvenance(BaseModel):
    artifact_sha256: str
    original_evaluation_sha256: str
    original_lock_sha256: str
    original_code_hash: str
    current_code_hash: str
    original_code_matches_current: bool
    test_parquet_sha256: str
    diagnostic_code_sha256: str
    protocol_hash: str
    split_hash: str
    test_cache_verification: str


class DiagnosticReport(BaseModel):
    version: str
    source_version: str
    source_commit: str
    generated_at: str
    serving: str
    test_non_penalty_shots: int
    test_matches: int
    seed: int
    repeats: int
    calibration: dict[str, CalibrationDiagnostic]
    grouped_permutation_importance: list[GroupedImportance]
    provenance: DiagnosticProvenance
    limitations: list[str]
    disclosure: str


class DiagnosticsResponse(BaseModel):
    status: Literal["not_generated", "available", "stale"]
    report: DiagnosticReport | None = None


def stored_diagnostics(session):
    stored = session.get(DatasetReport, "diagnostics-v2")
    if stored is None:
        return DiagnosticsResponse(status="not_generated")
    report = stored.payload["report"]
    release = session.get(ModelRelease, report["source_version"])
    if (
        release is None
        or release.status != "evaluated"
        or release.artifact_hash != report["provenance"]["artifact_sha256"]
    ):
        return DiagnosticsResponse(status="stale")
    sources = {s.path: s for s in session.scalars(select(SourceManifest))}
    for match, checksum in stored.payload["source_hashes"].items():
        source = sources.get(f"data/events/{match}.json")
        if (
            source is None
            or source.validation_status != "valid"
            or source.sha256 != checksum
            or source.commit != report["source_commit"]
        ):
            return DiagnosticsResponse(status="stale")
    return DiagnosticsResponse(status="available", report=DiagnosticReport(**report))


router = APIRouter(prefix="/api/v1", tags=["model diagnostics"])


@router.get("/experiments/diagnostics", response_model=DiagnosticsResponse)
def diagnostics(request: Request):
    with request.app.state.sessions() as session:
        return stored_diagnostics(session)
