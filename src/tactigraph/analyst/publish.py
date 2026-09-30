import json
from datetime import datetime, timezone
from pathlib import Path

from tactigraph.db import DatasetReport, initialize, make_engine


def publish(settings):
    engine = make_engine(settings)
    published = []
    try:
        with initialize(engine).begin() as session:
            for name, path in (
                ("retrieval", Path("experiments/retrieval-v1/results.json")),
                (
                    "analyst-deterministic",
                    Path("experiments/analyst-v1/deterministic-results.json"),
                ),
                ("analyst-local", Path("experiments/analyst-v1/local-results.json")),
                ("analyst-groq", Path("experiments/analyst-v1/groq-results.json")),
            ):
                if path.exists():
                    session.merge(
                        DatasetReport(
                            id=name,
                            generated_at=datetime.now(timezone.utc),
                            payload=json.loads(path.read_text(encoding="utf-8")),
                        )
                    )
                    published.append(name)
        return {"published": published, "human_review": "pending"}
    finally:
        engine.dispose()
