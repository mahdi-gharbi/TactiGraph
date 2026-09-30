from typing import Any, Literal

from tactigraph.api.schemas import BaseModel, ModelProvenance, Provenance


class ProbabilityScores(BaseModel):
    log_loss: float
    brier: float
    roc_auc: float | None
    pr_auc: float | None
    n: int
    goals: int


class ReliabilityBin(BaseModel):
    lower: float
    upper: float
    n: int
    predicted: float
    observed: float


class CalibrationParameters(BaseModel):
    intercept: float
    slope: float


class EvaluatedModel(ProbabilityScores):
    intervals: dict[str, list[float]]
    reliability: list[ReliabilityBin]
    calibration: CalibrationParameters | None


class ReferenceResult(BaseModel):
    name: str
    metrics: ProbabilityScores | None


class PenaltyEvaluation(BaseModel):
    probability: float
    test_metrics: ProbabilityScores | None


class SliceEvaluation(BaseModel):
    field: str
    value: str
    n: int
    metrics: ProbabilityScores | None
    warning: str | None


class Coefficient(BaseModel):
    feature: str
    coefficient: float


class Importance(BaseModel):
    feature: str
    mean_log_loss_increase: float
    std: float
    repeats: int


class StressFold(BaseModel):
    group: int
    teams: list[int]
    fit_shots: int
    fit_matches: int
    calibration_shots: int
    test_shots: int
    test_matches: int
    status: str
    metrics: ProbabilityScores | None


class CalibrationDecision(BaseModel):
    retain_sigmoid: bool
    raw: ProbabilityScores
    sigmoid: ProbabilityScores


class DevelopmentResults(BaseModel):
    search: list[dict[str, Any]]
    calibration_decisions: dict[str, CalibrationDecision]
    tuning_paired_difference: dict[str, list[float]]
    counts: dict[str, int]
    penalty: dict[str, float]
    protocol: dict[str, Any]


class ExperimentReport(BaseModel):
    version: str
    status: str
    serving: str
    evaluated_at: str
    lock: dict[str, str]
    test_matches: int
    test_non_penalty_shots: int
    metrics: dict[str, EvaluatedModel]
    paired_lightgbm_minus_logistic: dict[str, list[float]]
    reference: ReferenceResult
    penalties: PenaltyEvaluation
    slices: list[SliceEvaluation]
    logistic_coefficients: list[Coefficient]
    permutation_importance: list[Importance]
    team_stress: list[StressFold]
    prediction_batch_ms: float
    limitations: list[str]
    development: DevelopmentResults
    feature_names: list[str]


class ExperimentsResponse(BaseModel):
    status: Literal["not_trained", "evaluated", "unavailable"]
    report: ExperimentReport | None = None
    model: ModelProvenance | None = None
    provenance: Provenance = Provenance()
