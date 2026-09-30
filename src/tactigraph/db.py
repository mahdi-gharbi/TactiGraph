from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from tactigraph.config import Settings


class Base(DeclarativeBase):
    pass


class SourceManifest(Base):
    __tablename__ = "source_manifest"
    path: Mapped[str] = mapped_column(String, primary_key=True)
    commit: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String)
    validation_status: Mapped[str] = mapped_column(String, default="valid")


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(Integer)
    competition: Mapped[str] = mapped_column(String)
    season_id: Mapped[int] = mapped_column(Integer)
    season: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(String)
    home_id: Mapped[int] = mapped_column(Integer)
    home_name: Mapped[str] = mapped_column(String)
    away_id: Mapped[int] = mapped_column(Integer)
    away_name: Mapped[str] = mapped_column(String)
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    source_commit: Mapped[str] = mapped_column(String)
    event_count: Mapped[int] = mapped_column(Integer)
    source_schema: Mapped[str] = mapped_column(String)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    period: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[str] = mapped_column(String)
    period_ms: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer)
    second: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)
    team_id: Mapped[int | None] = mapped_column(Integer)
    team_name: Mapped[str | None] = mapped_column(String)
    player_id: Mapped[int | None] = mapped_column(Integer)
    player_name: Mapped[str | None] = mapped_column(String)
    possession: Mapped[int | None] = mapped_column(Integer)
    possession_team_id: Mapped[int | None] = mapped_column(Integer)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    under_pressure: Mapped[bool | None] = mapped_column(Boolean)


class Pass(Base):
    __tablename__ = "passes"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    recipient_id: Mapped[int | None] = mapped_column(Integer)
    recipient_name: Mapped[str | None] = mapped_column(String)
    end_x: Mapped[float | None] = mapped_column(Float)
    end_y: Mapped[float | None] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String)
    length: Mapped[float | None] = mapped_column(Float)
    height: Mapped[str | None] = mapped_column(String)
    body_part: Mapped[str | None] = mapped_column(String)
    technique: Mapped[str | None] = mapped_column(String)


class Shot(Base):
    __tablename__ = "shots"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    outcome: Mapped[str] = mapped_column(String)
    goal: Mapped[bool] = mapped_column(Boolean)
    body_part: Mapped[str | None] = mapped_column(String)
    shot_type: Mapped[str | None] = mapped_column(String)
    technique: Mapped[str | None] = mapped_column(String)
    key_pass_id: Mapped[str | None] = mapped_column(String)


class LineupSource(Base):
    """Preserve verified lineup input; stint reconstruction belongs to milestone 2."""

    __tablename__ = "lineup_sources"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    payload: Mapped[list] = mapped_column(JSON)


class TeamEntity(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class MatchPlayer(Base):
    __tablename__ = "match_players"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    declared_in_lineup: Mapped[bool] = mapped_column(Boolean)


class EventContext(Base):
    __tablename__ = "event_context"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    play_pattern: Mapped[str | None] = mapped_column(String)
    position_id: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float)
    end_x: Mapped[float | None] = mapped_column(Float)
    end_y: Mapped[float | None] = mapped_column(Float)
    action_outcome: Mapped[str | None] = mapped_column(String)
    pressure_value: Mapped[bool | None] = mapped_column(Boolean)
    pressure_status: Mapped[str] = mapped_column(String)
    ball_out: Mapped[bool | None] = mapped_column(Boolean)
    off_camera: Mapped[bool | None] = mapped_column(Boolean)
    related_event_ids: Mapped[list] = mapped_column(JSON)
    home_score_before: Mapped[int] = mapped_column(Integer)
    away_score_before: Mapped[int] = mapped_column(Integer)
    adapter_version: Mapped[str] = mapped_column(String)
    attributes: Mapped[dict] = mapped_column(JSON)


class LineupStint(Base):
    __tablename__ = "lineup_stints"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    position_id: Mapped[int | None] = mapped_column(Integer)
    position_name: Mapped[str | None] = mapped_column(String)
    start_index: Mapped[int] = mapped_column(Integer)
    end_index: Mapped[int] = mapped_column(Integer)
    start_period: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_period: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    end_event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    end_reason: Mapped[str] = mapped_column(String)


class Possession(Base):
    __tablename__ = "possessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    source_id: Mapped[int] = mapped_column(Integer)
    period: Mapped[int] = mapped_column(Integer)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    start_index: Mapped[int] = mapped_column(Integer)
    end_index: Mapped[int] = mapped_column(Integer)
    event_ids: Mapped[list] = mapped_column(JSON)


class ControlEpisode(Base):
    __tablename__ = "control_episodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    possession_id: Mapped[str] = mapped_column(ForeignKey("possessions.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    period: Mapped[int] = mapped_column(Integer)
    start_index: Mapped[int] = mapped_column(Integer)
    end_index: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    start_reason: Mapped[str] = mapped_column(String)
    end_reason: Mapped[str] = mapped_column(String)
    play_pattern: Mapped[str | None] = mapped_column(String)
    action_count: Mapped[int] = mapped_column(Integer)
    completed_passes: Mapped[int] = mapped_column(Integer)
    has_shot: Mapped[bool] = mapped_column(Boolean)
    goal: Mapped[bool] = mapped_column(Boolean)
    event_ids: Mapped[list] = mapped_column(JSON)
    pipeline_version: Mapped[str] = mapped_column(String)


class EpisodeEvent(Base):
    __tablename__ = "episode_events"
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("control_episodes.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)


class MatchQuality(Base):
    __tablename__ = "match_quality"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    pipeline_version: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)


class IngestionStatus(Base):
    __tablename__ = "ingestion_status"
    match_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pipeline_version: Mapped[str] = mapped_column(String)


class SplitAssignment(Base):
    __tablename__ = "split_assignments"
    match_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer)
    match_date: Mapped[str] = mapped_column(String)
    partition: Mapped[str] = mapped_column(String)
    manifest_hash: Mapped[str] = mapped_column(String)


class DatasetReport(Base):
    __tablename__ = "dataset_reports"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)


class ModelRelease(Base):
    __tablename__ = "model_releases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    family: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    artifact_hash: Mapped[str] = mapped_column(String)
    run_id: Mapped[str] = mapped_column(String)
    feature_version: Mapped[str] = mapped_column(String)
    source_commit: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSON)


class PredictionSample(Base):
    __tablename__ = "prediction_samples"
    id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    task: Mapped[str] = mapped_column(String)
    split: Mapped[str] = mapped_column(String)
    feature_version: Mapped[str] = mapped_column(String)
    label: Mapped[bool] = mapped_column(Boolean)
    penalty: Mapped[bool] = mapped_column(Boolean)
    features: Mapped[dict] = mapped_column(JSON)


class Prediction(Base):
    __tablename__ = "predictions"
    sample_id: Mapped[str] = mapped_column(ForeignKey("prediction_samples.id"), primary_key=True)
    model_version: Mapped[str] = mapped_column(ForeignKey("model_releases.id"), primary_key=True)
    probability: Mapped[float] = mapped_column(Float)


def make_engine(settings: Settings) -> Engine:
    if settings.database_url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    kwargs = (
        {"connect_args": {"check_same_thread": False, "timeout": 30}}
        if (settings.database_url.startswith("sqlite"))
        else {}
    )
    engine = create_engine(settings.database_url, **kwargs)
    if engine.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    return engine


def initialize(engine: Engine):
    from tactigraph.migrate import migrate

    migrate(engine)
    return sessionmaker(engine, expire_on_commit=False)
