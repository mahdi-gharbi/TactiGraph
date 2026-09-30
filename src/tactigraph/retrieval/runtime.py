"""Optional local hybrid search, with an explicit lightweight public fallback."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from tactigraph.retrieval.bm25 import corpus, retrieve


@lru_cache(maxsize=1)
def index():
    from tactigraph.retrieval.experiment import MiniLM

    release = json.loads(Path("configs/retrieval-serving-v1.json").read_text(encoding="utf-8"))
    snapshot = (
        Path("artifacts/huggingface/models--sentence-transformers--all-MiniLM-L6-v2/snapshots")
        / release["revision"]
    )
    weights = snapshot / "model.safetensors"
    if (
        not weights.exists()
        or hashlib.sha256(weights.read_bytes()).hexdigest() != release["weights_sha256"]
    ):
        raise ValueError("Pinned local encoder is unavailable")
    protocol = json.loads(Path("configs/retrieval-v1.json").read_text(encoding="utf-8"))
    # A local path ensures web requests never download model weights.
    protocol["model"] = str(snapshot.resolve())
    encoder = MiniLM(protocol)
    documents = corpus()
    vectors = encoder.encode([d.section + " " + d.text for d in documents])
    return encoder, documents, vectors


def search(query, *, release=None, topic=None, version=None, language="en"):
    baseline = retrieve(query, topic=topic, version=version, language=language)
    if release is None or release.get("selected") != "hybrid":
        return "BM25", baseline
    try:
        import numpy as np

        from tactigraph.retrieval.experiment import reciprocal_rank_fusion

        documents = corpus()
        fingerprint = hashlib.sha256(
            json.dumps([d.model_dump() for d in documents], sort_keys=True).encode()
        ).hexdigest()
        if release.get("lock", {}).get("corpus") != fingerprint:
            raise ValueError("Released corpus has changed")
        encoder, documents, vectors = index()
        indices = [
            i
            for i, d in enumerate(documents)
            if (topic is None or d.topic == topic)
            and (version is None or d.version == version)
            and d.language == language
        ]
        if not indices:
            return "Hybrid BM25 + pinned local MiniLM", []
        similarities = vectors[indices] @ encoder.encode([query])[0]
        dense = [
            documents[indices[i]].chunk_id for i in np.argsort(-similarities, kind="stable")[:5]
        ]
        rankings = [[d.chunk_id for d in baseline], dense]
        fused = reciprocal_rank_fusion(rankings)
        scores = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(dict.fromkeys(ranking), 1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (60 + rank)
        by_id = {d.chunk_id: d for d in documents}
        return "Hybrid BM25 + pinned local MiniLM", [
            by_id[k].model_copy(update={"score": scores[k]}) for k in fused
        ]
    except (ImportError, OSError, ValueError):
        return "BM25 fallback: optional pinned local encoder unavailable", baseline
