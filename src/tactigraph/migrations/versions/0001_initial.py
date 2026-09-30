"""Freeze the existing M1 schema."""

from alembic import op

from tactigraph.migrations.schema import snapshot

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    snapshot("m1").create_all(op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrades are not supported; restore a verified backup.")
