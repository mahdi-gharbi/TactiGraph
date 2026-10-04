"""Additive, bounded natural-language interface; stored v1 reports remain readable."""

from typing import Literal

from pydantic import ConfigDict, Field

from tactigraph.analyst.contracts import AnalystReport, Intent
from tactigraph.api.schemas import BaseModel
from tactigraph.api.tactical_schemas import Window
from tactigraph.retrieval.bm25 import DocumentChunk

Language = Literal["en", "fr"]
Topic = Literal[
    "movement_xt",
    "passes",
    "completed_passes",
    "shots",
    "xg",
    "final_third_entries",
    "field_tilt",
    "network",
    "limitations",
    "graph",
    "windows",
]


class AnalystQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    language: Language = "en"
    match_id: int = Field(gt=0)
    team_id: int = Field(gt=0)
    before: Window = Field(default_factory=lambda: Window(period=2, start_ms=0, end_ms=900000))
    after: Window = Field(default_factory=lambda: Window(period=2, start_ms=900000, end_ms=1800000))


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "clarification_required", "abstained"]
    intent: Intent | None
    before: Window | None
    after: Window | None
    methodology_topics: list[Topic] = Field(max_length=2)
    reason: Literal["ambiguous", "context_mismatch", "unsupported", "insufficient_data"] | None


class QueryMetadata(BaseModel):
    provider: str = "groq"
    model: str | None = None
    provider_success: bool = False
    attempts: int = 0
    repairs: int = 0
    provider_errors: int = 0
    provider_error_status: int | None = None
    usage_complete: bool = True
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    fallback_reason: str | None = None
    retrieval_method: str | None = None
    corpus_version: str | None = None
    corpus_sha256: str | None = None
    request_id: str | None = None
    system_fingerprint: str | None = None


class QueryStep(BaseModel):
    name: str
    duration_ms: float
    status: str


class AnalystQueryResponse(BaseModel):
    version: str = "analyst-query-v2"
    status: Literal["answered", "clarification_required", "abstained"]
    language: Language
    message: str
    plan: Interpretation | None = None
    report: AnalystReport | None = None
    methodology: list[DocumentChunk] = Field(default_factory=list)
    metadata: QueryMetadata = Field(default_factory=QueryMetadata)
    trace: list[QueryStep] = Field(default_factory=list)
