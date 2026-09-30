from typing import Literal

from pydantic import BaseModel as PydanticModel
from pydantic import ConfigDict, Field

from tactigraph.config import METRIC_VERSION, SOURCE_COMMIT


class BaseModel(PydanticModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Provenance(BaseModel):
    source_commit: str = SOURCE_COMMIT
    metric_version: str = METRIC_VERSION
    coordinate_frame: str = "StatsBomb event-team attacking frame, 120 × 80"


class Team(BaseModel):
    id: int
    name: str
    score: int


class MatchCard(BaseModel):
    id: int
    date: str
    competition: str
    season: str
    home: Team
    away: Team
    event_count: int
    source_schema: str
    provenance: Provenance = Field(default_factory=Provenance)


class MatchList(BaseModel):
    matches: list[MatchCard]
    mode: Literal["local", "public"]
    provenance: Provenance = Field(default_factory=Provenance)


class TeamStats(BaseModel):
    team_id: int
    shots: int
    goals_from_shots: int
    passes: int
    completed_passes: int
    located_shots: int
    xg: float | None = None
    non_penalty_xg: float | None = None
    penalty_xg: float | None = None
    predicted_shots: int = 0
    xg_status: Literal["not_trained", "ready", "partial", "unavailable"] = "not_trained"


class ModelProvenance(BaseModel):
    model_version: str
    family: str
    artifact_hash: str
    run_id: str
    feature_version: str
    sample_id: str | None = None
    split: str | None = None
    penalty: bool | None = None


class MatchSummary(BaseModel):
    match: MatchCard
    teams: list[TeamStats]
    periods: list[int]
    model: ModelProvenance | None = None
    prediction_split: str | None = None
    provenance: Provenance = Field(default_factory=Provenance)


class ShotPoint(BaseModel):
    event_id: str
    index: int
    period: int
    timestamp: str
    period_ms: int
    minute: int
    second: int
    team_id: int
    player_id: int | None
    player_name: str | None
    x: float | None
    y: float | None
    outcome: str
    goal: bool
    body_part: str | None
    shot_type: str | None
    location_status: Literal["valid", "missing", "outside_pitch"]
    xg: float | None = None
    model: ModelProvenance | None = None


class ShotLayer(BaseModel):
    match_id: int
    shots: list[ShotPoint]
    total_shots: int
    located_shots: int
    result_id: str
    provenance: Provenance = Field(default_factory=Provenance)


class EventReference(BaseModel):
    event_id: str
    index: int
    period: int
    timestamp: str
    player_name: str | None
    team_name: str | None
    outcome: str
    source_url: str


class ShotEvidence(BaseModel):
    result_id: str
    match_id: int
    predicate: Literal["shot_count"] = "shot_count"
    value: int
    unit: Literal["shots"] = "shots"
    team_id: int | None
    player_id: int | None
    period: int | None
    start_ms: int
    end_ms: int | None
    definition: str
    statement: str
    references: list[EventReference]
    source_sha256: str | None
    provenance: Provenance = Field(default_factory=Provenance)


class LocalEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    index: int
    period: int
    timestamp: str
    type: str
    team_name: str | None
    player_name: str | None
    x: float | None
    y: float | None


class LocalEvents(BaseModel):
    events: list[LocalEvent]
    offset: int
    limit: int
    total: int
    provenance: Provenance = Field(default_factory=Provenance)


class NamedCount(BaseModel):
    name: str
    count: int


class ShotZone(BaseModel):
    x_bin: int
    y_bin: int
    count: int


class ShotTimeBin(BaseModel):
    period: int
    start_minute: int
    count: int


class EntityStatistics(BaseModel):
    id: int
    name: str
    matches: int
    shots: int
    passes: int
    events: int | None = None


class TrainingEDA(BaseModel):
    partition: Literal["train"]
    match_count: int
    match_ids: list[int]
    event_distribution: list[NamedCount]
    shot_zones: list[ShotZone]
    shot_time_bins: list[ShotTimeBin]
    teams: list[EntityStatistics]
    players: list[EntityStatistics]
    episode_lengths: list[NamedCount]
    note: str


class SeasonCoverage(BaseModel):
    season_id: int
    expected: int
    ingested: int
    ready: int
    events: int
    shots: int
    passes: int


class PartitionCoverage(BaseModel):
    name: str
    expected: int
    ingested: int


class FoundationReport(BaseModel):
    source_commit: str
    pipeline_version: str
    generated_at: str
    expected_matches: int
    ingested_matches: int
    ready_matches: int
    failed_matches: list[int]
    pending_matches: list[int]
    counts: dict[str, int]
    seasons: list[SeasonCoverage]
    partitions: list[PartitionCoverage]
    schema_versions: dict[str, int]
    missing_fields: dict[str, int]
    quality_issues: list[NamedCount]
    integrity_checks: dict[str, bool]
    split_manifest_hash: str | None
    coverage_complete: bool
    training_eda: TrainingEDA


class DatasetOverview(BaseModel):
    status: Literal["not_audited", "audited"]
    ingested_matches: int
    report: FoundationReport | None
    provenance: Provenance = Field(default_factory=Provenance)
