"""Offline descriptive styles. No identities or future partitions enter fitting."""

import json
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select

from tactigraph.config import SOURCE_COMMIT
from tactigraph.data.geometry import in_pitch
from tactigraph.db import DatasetReport, Event, Match, Pass, SourceManifest, initialize, make_engine

FEATURES = [
    "passes_per_minute",
    "completion_fraction",
    "forward_fraction",
    "long_fraction",
    "final_third_fraction",
    "mean_start_x",
]
LIMITATION = (
    "Exploratory clusters of observed passing, not team identities, quality rankings or causal "
    "tactics. Score, opponent and player availability can influence membership. Only complete "
    "15-minute regulation windows with at least 10 passes and valid geometry are included; "
    "stoppage time and extra time are excluded. Later matches are projections, not a fresh test."
)


def windows(rows, match, minimum=10):
    groups = defaultdict(list)
    ends = defaultdict(int)
    for event, passing in rows:
        ends[event.period] = max(ends[event.period], event.period_ms)
        if (
            passing is not None
            and event.period in (1, 2)
            and 0 <= event.period_ms < 2700000
            and event.team_id in (match.home_id, match.away_id)
        ):
            groups[(event.team_id, event.period, event.period_ms // 900000)].append(
                (event, passing)
            )
    result = []
    for (team, period, slot), passes in sorted(groups.items()):
        if ends[period] < (slot + 1) * 900000 or len(passes) < minimum:
            continue
        spatial = [(e, p) for e, p in passes if in_pitch(e.x, e.y) and in_pitch(p.end_x, p.end_y)]
        if len(spatial) < minimum:
            continue
        count, valid = len(passes), len(spatial)
        result.append(
            {
                "match_id": match.id,
                "team_id": team,
                "period": period,
                "start_ms": slot * 900000,
                "end_ms": (slot + 1) * 900000,
                "pass_count": count,
                "spatial_pass_count": valid,
                "features": [
                    count / 15,
                    sum(p.completed for _, p in passes) / count,
                    sum(p.end_x > e.x for e, p in spatial) / valid,
                    sum(
                        ((p.end_x - e.x) ** 2 + (p.end_y - e.y) ** 2) ** 0.5 >= 30
                        for e, p in spatial
                    )
                    / valid,
                    sum(p.end_x >= 80 for _, p in spatial) / valid,
                    sum(e.x for e, _ in spatial) / valid,
                ],
                "evidence_id": f"tactics-{match.id}-{team}-{period}-"
                f"{slot * 900000}-{(slot + 1) * 900000}-passes",
            }
        )
    return result


def fit_styles(samples, protocol):
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    train = [s for s in samples if s["partition"] == "train"]
    x = np.asarray([s["features"] for s in train])
    k = protocol["clusters"]
    if len(train) <= k or len(np.unique(x, axis=0)) < k:
        raise ValueError("Insufficient distinct training windows for style discovery")

    def fit(values, seed):
        model = make_pipeline(
            StandardScaler(),
            PCA(n_components=protocol["pca_variance"], svd_solver="full"),
            KMeans(n_clusters=k, n_init=20, random_state=seed),
        )
        return model.fit(values)

    model = fit(x, protocol["seed"])
    labels = model.predict(x)
    seed_ari = [
        float(adjusted_rand_score(labels, fit(x, seed).predict(x)))
        for seed in protocol["stability_seeds"]
    ]
    rng = np.random.default_rng(protocol["seed"])
    match_ids = sorted({s["match_id"] for s in train})
    by_match = {m: [i for i, s in enumerate(train) if s["match_id"] == m] for m in match_ids}
    bootstrap = []
    for _ in range(protocol["bootstrap_repeats"]):
        indices = [
            i for m in rng.choice(match_ids, len(match_ids), replace=True) for i in by_match[m]
        ]
        bootstrap.append(
            float(adjusted_rand_score(labels, fit(x[indices], protocol["seed"]).predict(x)))
        )
    centers = []
    for cluster in range(k):
        mean = x[labels == cluster].mean(axis=0)
        deviations = (mean - x.mean(axis=0)) / np.maximum(x.std(axis=0), 1e-12)
        strongest = np.argsort(-np.abs(deviations))[:2]
        label = "; ".join(
            f"{'Higher' if deviations[i] >= 0 else 'Lower'} {FEATURES[i].replace('_', ' ')}"
            for i in strongest
        )
        centers.append(
            {
                "cluster": cluster,
                "label": label,
                "training_windows": int(sum(labels == cluster)),
                "means": dict(zip(FEATURES, mean.tolist())),
            }
        )
    projected = model.predict(np.asarray([s["features"] for s in samples]))
    for sample, cluster in zip(samples, projected):
        sample["cluster"] = int(cluster)
    report = {
        "version": protocol["version"],
        "features": FEATURES,
        "protocol": protocol,
        "training_windows": len(train),
        "training_matches": len(match_ids),
        "projected_windows": len(samples) - len(train),
        "clusters": centers,
        "pca_explained_variance": model[1].explained_variance_ratio_.tolist(),
        "training_silhouette": float(silhouette_score(model[:2].transform(x), labels)),
        "seed_ari": seed_ari,
        "match_bootstrap_ari": bootstrap,
        "limitation": LIMITATION,
    }
    return model, report


def develop(settings, protocol_path=Path("configs/styles-v1.json")):
    import joblib

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    split_path = Path(protocol.get("split_manifest", "configs/splits/wsl-v1.json"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    partitions = {s["match_id"]: s["partition"] for s in split["assignments"]}
    engine = make_engine(settings)
    try:
        sessions = initialize(engine)
        with sessions() as session:
            samples, sources = [], {}
            matches = session.scalars(select(Match).order_by(Match.id)).all()
            if set(partitions) - {m.id for m in matches}:
                raise ValueError("Full frozen corpus must be ingested before styles development")
            for match in matches:
                if match.id not in partitions:
                    continue
                source = session.get(SourceManifest, f"data/events/{match.id}.json")
                if source is None or source.commit != SOURCE_COMMIT:
                    raise ValueError(f"Unverified source for match {match.id}")
                sources[str(match.id)] = source.sha256
                rows = session.execute(
                    select(Event, Pass)
                    .outerjoin(Pass, Pass.event_id == Event.id)
                    .where(Event.match_id == match.id)
                    .order_by(Event.index)
                ).all()
                for sample in windows(rows, match, protocol["minimum_passes"]):
                    sample["partition"] = partitions[match.id]
                    samples.append(sample)
            model, report = fit_styles(samples, protocol)
            report.update(
                source_commit=SOURCE_COMMIT,
                source_hashes=sources,
                split_sha256=sha256(split_path.read_bytes()).hexdigest(),
                protocol_sha256=sha256(protocol_path.read_bytes()).hexdigest(),
            )
            artifact = Path("artifacts") / protocol["version"]
            artifact.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, artifact / "model.joblib")
            report["model_sha256"] = sha256((artifact / "model.joblib").read_bytes()).hexdigest()
            export = Path("experiments") / protocol["version"] / "results.json"
            export.parent.mkdir(parents=True, exist_ok=True)
            export.write_text(
                json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
            )
            session.merge(
                DatasetReport(
                    id="styles-v1",
                    generated_at=datetime.now(timezone.utc),
                    payload={"report": report, "windows": samples},
                )
            )
            session.commit()
            return report
    finally:
        engine.dispose()
