from typing import Literal

from tactigraph.api.schemas import BaseModel


class XTCoverage(BaseModel):
    source_episodes: int
    eligible_episodes: int
    excluded_episodes: dict[str, int]
    matches: int


class XTScore(BaseModel):
    log_loss: float
    brier: float
    n: int
    goals: int
    intervals: dict[str, list[float]]


class XTSurface(BaseModel):
    grid: list[int]
    values: list[float]
    no_transition: list[float]
    action_counts: list[int]
    shot_counts: list[int]
    goal_counts: list[int]
    global_episode_rate: float
    episodes: int
    total_actions: int
    terminal_count: int
    iterations: int
    maximum_delta: float
    row_probability_error: float


class XTLock(BaseModel):
    created_at: str
    run_id: str
    protocol_hash: str
    code_hash: str
    split_hash: str
    source_hash: str
    artifact_hash: str


class XTTuningScore(BaseModel):
    log_loss: float
    brier: float
    n: int


class XTCandidate(BaseModel):
    grid: list[int]
    scores: dict[str, XTTuningScore]
    iterations: int


class XTDevelopment(BaseModel):
    selected_grid: list[int]
    candidates: list[XTCandidate]
    train: XTCoverage
    tuning: XTCoverage
    fitting_episodes: int
    iterations: int


class XTReport(BaseModel):
    version: str
    generated_at: str
    source_commit: str
    model: XTSurface
    results: dict[str, XTScore]
    development: XTDevelopment
    test: XTCoverage
    lock: XTLock
    paired_differences: dict[str, dict[str, list[float]]]
    attribution: str
    source_url: str
    interpretation: str
    test_disclosure: str


class XTResponse(BaseModel):
    status: Literal["evaluated", "not_trained"]
    report: XTReport | None
