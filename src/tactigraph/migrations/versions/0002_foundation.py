"""Add M2 catalog, dimensions, event context, stints, possessions and split manifests."""

from alembic import op

from tactigraph.migrations.schema import snapshot

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    schema = snapshot("m2")
    legacy_names = set(snapshot("m1").tables)
    schema.create_all(
        op.get_bind(), tables=[t for t in schema.sorted_tables if t.name not in legacy_names]
    )
    op.create_index("ix_events_match_period_team", "events", ["match_id", "period", "team_id"])
    op.create_index("uq_events_match_index", "events", ["match_id", "index"], unique=True)


def downgrade():
    raise RuntimeError("Destructive downgrades are not supported; restore a verified backup.")
