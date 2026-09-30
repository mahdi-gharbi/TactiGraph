from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from tactigraph.api.schemas import BaseModel
from tactigraph.api.tactical_schemas import Window

VERSION = "analyst-v1"
Intent = Literal["period_comparison", "chance_creation", "network_concentration"]


class AnalystRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match_id: int = Field(gt=0)
    team_id: int = Field(gt=0)
    intent: Intent
    generation: Literal["deterministic", "local", "groq"] = "deterministic"
    question: str | None = Field(default=None, min_length=1, max_length=500)
    before: Window = Field(default_factory=lambda: Window(period=2, start_ms=0, end_ms=900000))
    after: Window = Field(default_factory=lambda: Window(period=2, start_ms=900000, end_ms=1800000))

    @model_validator(mode="after")
    def validate_windows(self):
        if self.before.period != self.after.period:
            raise ValueError("Comparisons cannot span halftime")
        if self.before.end_ms > self.after.start_ms:
            raise ValueError("Windows must be chronological and non-overlapping")
        return self


class Fact(BaseModel):
    metric: str
    value: float | None
    unit: str
    numerator: float | None
    denominator: float | None
    denominator_unit: str
    evidence_id: str


class ToolResult(BaseModel):
    result_id: str
    tool: Literal["compare_windows", "get_passing_network", "get_model_outputs"]
    arguments: AnalystRequest
    before: list[Fact]
    after: list[Fact]
    source_commit: str
    source_sha256: str
    metric_version: str
    model_versions: dict[str, str]
    quality_warnings: list[str]
    supporting_event_ids: dict[str, list[str]] = Field(default_factory=dict, exclude=True)


class ClaimSelection(BaseModel):
    """A language model can select facts, never supply their numbers or prose."""

    model_config = ConfigDict(extra="forbid")
    predicate: Literal["compare_metric", "limitation"]
    metric: str | None = None
    result_id: str
    limitation: Literal["no_causality", "no_tracking", "small_window"] | None = None


class VerifiedClaim(BaseModel):
    kind: Literal["measured_fact", "limitation"]
    predicate: str
    text: str
    result_id: str
    evidence_ids: list[str]
    before: float | None = None
    after: float | None = None
    unit: str | None = None


class GenerationMetadata(BaseModel):
    provider: Literal["ollama", "groq"] = "ollama"
    request_id: str | None = None
    system_fingerprint: str | None = None
    model: str
    digest: str | None
    attempts: int
    repairs: int
    rejections: int
    input_tokens: int
    output_tokens: int
    latency_ms: float
    fallback_reason: str | None


class AnalystReport(BaseModel):
    report_id: str
    version: str = VERSION
    status: Literal["verified", "abstained"]
    mode: Literal[
        "deterministic", "local_selection", "groq_selection", "deterministic_fallback"
    ] = "deterministic"
    generation: GenerationMetadata | None = None
    generated_at: str
    arguments: AnalystRequest
    claims: list[VerifiedClaim]
    evidence: ToolResult
    trace: list[str]
    tool_calls: int
    verification_rejections: int
    qualifications: list[str]
    attribution: str = "Data provided by StatsBomb Open Data"
    publication_label: str = "Deterministic, machine-verified report; human review pending"
