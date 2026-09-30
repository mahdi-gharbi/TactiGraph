"""Copy the selected showcase into an EMPTY private database, transactionally."""

from sqlalchemy import func, select

from tactigraph.config import Settings
from tactigraph.db import Base, DatasetReport, Event, Match, initialize, make_engine
from tactigraph.release import VERSION


def transfer(source_url, target_settings):
    source = make_engine(Settings(database_url=source_url))
    target = make_engine(target_settings)
    try:
        initialize(target)
        with source.connect() as src, target.begin() as dst:
            if source.dialect.name == "sqlite":
                src.exec_driver_sql("BEGIN")
            payload = src.execute(
                select(DatasetReport.payload).where(DatasetReport.id == VERSION)
            ).scalar_one()
            match_ids = [m["match_id"] for m in payload["matches"]]
            event_ids = select(Event.id).where(Event.match_id.in_(match_ids))
            for table in Base.metadata.sorted_tables:
                if dst.scalar(select(func.count()).select_from(table)):
                    raise ValueError("Target must be empty; existing data is never overwritten")
            counts = {}
            for table in Base.metadata.sorted_tables:
                query = select(table)
                if "match_id" in table.c:
                    query = query.where(table.c.match_id.in_(match_ids))
                elif table.name == Match.__tablename__:
                    query = query.where(table.c.id.in_(match_ids))
                elif "event_id" in table.c:
                    query = query.where(table.c.event_id.in_(event_ids))
                elif "sample_id" in table.c:
                    query = query.where(table.c.sample_id.in_(event_ids))
                count = 0
                for batch in src.execute(query).mappings().partitions(1000):
                    values = [dict(row) for row in batch]
                    if table.name == DatasetReport.__tablename__:
                        values = [
                            row
                            for row in values
                            if not row["id"].startswith("graph-predictions-")
                            or int(row["id"].removeprefix("graph-predictions-")) in match_ids
                        ]
                        for row in values:
                            if row["id"] == "styles-v1":
                                row["payload"] = {
                                    **row["payload"],
                                    "windows": [
                                        w
                                        for w in row["payload"]["windows"]
                                        if w["match_id"] in match_ids
                                    ],
                                }
                    if values:
                        dst.execute(table.insert(), values)
                        count += len(values)
                counts[table.name] = count
            return {"selected_matches": len(match_ids), "rows": counts}
    finally:
        source.dispose()
        target.dispose()
