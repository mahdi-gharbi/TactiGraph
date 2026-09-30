from typing import Literal

from pydantic import Field, model_validator

from tactigraph.api.schemas import BaseModel, EventReference, ModelProvenance, Provenance

Metric = Literal[
    "shots",
    "xg",
    "passes",
    "completed_passes",
    "final_third_entries",
    "field_tilt",
    "network",
    "movement_xt",
]


class Window(BaseModel):
    period: int = Field(ge=1, le=4)
    start_ms: int = Field(ge=0, lt=7200000)
    end_ms: int = Field(gt=0, le=7200000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("End must be after start")
        return self


class ComparisonRequest(BaseModel):
    team_id: int = Field(gt=0)
    before: Window
    after: Window

    @model_validator(mode="after")
    def comparable(self):
        if self.before.period != self.after.period:
            raise ValueError("Comparisons cannot span halftime or another period boundary")
        if self.before.end_ms > self.after.start_ms:
            raise ValueError("Comparison windows must be chronological and non-overlapping")
        return self


class Measurement(BaseModel):
    metric: Metric
    value: float | None
    unit: str
    numerator: float | None
    denominator: float | None
    denominator_unit: str
    evidence_id: str


class NetworkNode(BaseModel):
    player_id: int
    name: str
    x: float | None
    y: float | None
    position_samples: int
    exposure_minutes: float | None
    in_strength: int
    out_strength: int
    betweenness: float
    movement_xt: float | None = None
    valued_actions: int = 0


class NetworkEdge(BaseModel):
    sender: int
    recipient: int
    count: int


class PassingNetwork(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    pass_count: int
    excluded_passes: int
    density: float
    concentration: float | None
    evidence_id: str
    position_definition: str = "Mean completed-pass origin and reception locations; not tracking"


class WindowAnalysis(BaseModel):
    window: Window
    measurements: list[Measurement]
    network: PassingNetwork
    warnings: list[str]


class MetricDifference(BaseModel):
    metric: Metric
    value: float | None
    unit: str


class NetworkResponse(BaseModel):
    match_id: int
    team_id: int
    analysis: WindowAnalysis
    model: ModelProvenance | None
    provenance: Provenance
    xt_model: ModelProvenance | None = None


class ComparisonResponse(BaseModel):
    result_id: str
    match_id: int
    team_id: int
    before: WindowAnalysis
    after: WindowAnalysis
    differences: list[MetricDifference]
    statement: str
    model: ModelProvenance | None
    provenance: Provenance
    xt_status: Literal["not_trained", "ready"] = "not_trained"
    xt_model: ModelProvenance | None = None


class TacticalEvidence(BaseModel):
    result_id: str
    match_id: int
    team_id: int
    window: Window
    metric: Metric
    definition: str
    measurement: Measurement | None
    network: PassingNetwork | None = None
    references: list[EventReference]
    total: int
    offset: int
    limit: int
    source_sha256: str | None
    model: ModelProvenance | None
    xt_model: ModelProvenance | None = None
    provenance: Provenance


class MomentumPoint(BaseModel):
    start_ms: int
    end_ms: int
    xg: float | None
    movement_xt: float | None
    shots: int
    predicted_shots: int
    valued_actions: int
    eligible_actions: int
    xg_evidence_id: str
    xt_evidence_id: str


class CandidateShift(BaseModel):
    boundary_ms: int
    before_count: int
    after_count: int
    rate_difference: float
    before_evidence_id: str
    after_evidence_id: str


class TrendsResponse(BaseModel):
    match_id: int
    team_id: int
    period: int
    points: list[MomentumPoint]
    candidate_shifts: list[CandidateShift]
    key_events: list[EventReference]
    warnings: list[str]
    model: ModelProvenance | None
    xt_model: ModelProvenance | None
    provenance: Provenance
