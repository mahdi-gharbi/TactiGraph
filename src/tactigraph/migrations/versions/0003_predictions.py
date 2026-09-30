"""Versioned precomputed model results; no runtime training dependency."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_releases",
        sa.Column("id", sa.String(), primary_key=True),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in (
                "family",
                "status",
                "artifact_hash",
                "run_id",
                "feature_version",
                "source_commit",
            )
        ],
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
    )
    op.create_table(
        "prediction_samples",
        sa.Column("id", sa.String(), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        *[
            sa.Column(name, sa.String(), nullable=False)
            for name in ("task", "split", "feature_version")
        ],
        sa.Column("label", sa.Boolean(), nullable=False),
        sa.Column("penalty", sa.Boolean(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
    )
    op.create_index("ix_prediction_samples_match_id", "prediction_samples", ["match_id"])
    op.create_table(
        "predictions",
        sa.Column(
            "sample_id", sa.String(), sa.ForeignKey("prediction_samples.id"), primary_key=True
        ),
        sa.Column(
            "model_version", sa.String(), sa.ForeignKey("model_releases.id"), primary_key=True
        ),
        sa.Column("probability", sa.Float(), nullable=False),
    )


def downgrade():
    raise RuntimeError("Destructive downgrades are not supported; restore a verified backup.")
