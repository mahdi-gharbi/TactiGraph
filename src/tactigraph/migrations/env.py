from alembic import context

from tactigraph.db import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations through 'tactigraph migrate'")
context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
