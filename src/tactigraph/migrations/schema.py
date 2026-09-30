import json
from pathlib import Path

import sqlalchemy as sa


def snapshot(name):
    spec = json.loads(Path(__file__).with_name(f"schema_{name}.json").read_text())
    metadata = sa.MetaData()
    types = {
        t: getattr(sa, t) for t in ("Integer", "String", "Float", "Boolean", "JSON", "DateTime")
    }
    for table_name, table in spec.items():
        columns = []
        for c in table["columns"]:
            args = [sa.ForeignKey(c["foreign_key"])] if c["foreign_key"] else []
            column_type = (
                types[c["type"]](timezone=True) if c["type"] == "DateTime" else types[c["type"]]()
            )
            columns.append(
                sa.Column(
                    c["name"],
                    column_type,
                    *args,
                    nullable=c["nullable"],
                    primary_key=c["primary_key"],
                )
            )
        definition = sa.Table(table_name, metadata, *columns)
        for index in table["indexes"]:
            sa.Index(
                index["name"], *(definition.c[c] for c in index["columns"]), unique=index["unique"]
            )
    return metadata
