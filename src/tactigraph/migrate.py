from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tactigraph.migrations.schema import snapshot


def migrate(engine):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        if existing and "alembic_version" not in existing:
            expected = snapshot("m1")
            if existing != set(expected.tables):
                raise RuntimeError(
                    "Unversioned database is not the exact M1 schema; refusing to stamp"
                )
            for name, table in expected.tables.items():
                actual = {c["name"]: c for c in inspector.get_columns(name)}
                if set(actual) != set(table.c.keys()) or any(
                    actual[c.name]["type"]._type_affinity != c.type._type_affinity
                    or actual[c.name]["nullable"] != c.nullable
                    for c in table.columns
                ):
                    raise RuntimeError(f"Unversioned table {name} differs from M1")
            command.stamp(config, "0001")
        command.upgrade(config, "head")
