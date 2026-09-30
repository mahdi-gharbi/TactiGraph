"""Serving reads stored probabilities; it never imports an ML runtime or artifact."""

from sqlalchemy import select

from tactigraph.db import ModelRelease, Prediction, PredictionSample


def latest_release(session):
    return session.scalar(
        select(ModelRelease)
        .where(ModelRelease.status == "evaluated")
        .order_by(ModelRelease.created_at.desc())
        .limit(1)
    )


def match_predictions(session, match_id):
    release = latest_release(session)
    if release is None:
        return None, {}
    rows = session.execute(
        select(
            Prediction.sample_id,
            Prediction.probability,
            PredictionSample.penalty,
            PredictionSample.split,
        )
        .join(PredictionSample, PredictionSample.id == Prediction.sample_id)
        .where(Prediction.model_version == release.id, PredictionSample.match_id == match_id)
    ).all()
    return release, {r.sample_id: r for r in rows}


def provenance(release, sample=None):
    if release is None:
        return None
    return {
        "model_version": release.id,
        "family": release.family,
        "artifact_hash": release.artifact_hash,
        "run_id": release.run_id,
        "feature_version": release.feature_version,
        "sample_id": sample.sample_id if sample else None,
        "split": sample.split if sample else None,
        "penalty": sample.penalty if sample else None,
    }
