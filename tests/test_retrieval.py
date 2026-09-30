import json
from pathlib import Path

import pytest

from tactigraph.retrieval.bm25 import corpus
from tactigraph.retrieval.experiment import query_scores, reciprocal_rank_fusion


def test_recall_and_rank_use_relevance_labels_and_top_five():
    assert query_scores(["a", "b", "c"], ["b", "c"]) == (1, 0.5)
    assert query_scores(["a", "b", "c", "d", "e", "f"], ["f"]) == (0, 0)
    with pytest.raises(ValueError):
        query_scores(["a"], [])


def test_fusion_deduplicates_each_ranker_and_is_deterministic():
    assert reciprocal_rank_fusion([["a", "b"], ["b", "a"]]) == ["a", "b"]
    assert reciprocal_rank_fusion([["a", "a", "b"], ["b", "a"]]) == ["a", "b"]


def test_authored_queries_are_disjoint_and_resolve_to_approved_chunks():
    data = json.loads(Path("configs/retrieval-questions-v1.json").read_text(encoding="utf-8"))
    assert len(data["development"]) == len(data["held_out"]) == 30
    assert not {q for q, _ in data["development"]} & {q for q, _ in data["held_out"]}
    ids = {d.chunk_id for d in corpus()}
    assert all(set(labels) <= ids for partition in data.values() for _, labels in partition)


def test_runtime_refuses_stale_corpus_without_loading_encoder(monkeypatch):
    from tactigraph.retrieval import runtime

    def forbidden():
        pytest.fail("Stale corpus must not load the encoder")

    monkeypatch.setattr(runtime, "index", forbidden)
    method, chunks = runtime.search("field tilt", release={"selected": "hybrid", "lock": {}})
    assert method.startswith("BM25 fallback")
    assert chunks


def test_runtime_reports_actual_fusion_scores(monkeypatch):
    import hashlib

    import numpy as np

    from tactigraph.retrieval import runtime

    documents = corpus()
    fingerprint = hashlib.sha256(
        json.dumps([d.model_dump() for d in documents], sort_keys=True).encode()
    ).hexdigest()

    class Encoder:
        def encode(self, queries):
            return np.array([[1.0]])

    monkeypatch.setattr(
        runtime,
        "index",
        lambda: (
            Encoder(),
            documents,
            np.arange(len(documents), 0, -1).reshape(-1, 1),
        ),
    )
    monkeypatch.setattr(runtime, "retrieve", lambda *args, **kwargs: documents[:2])
    method, chunks = runtime.search(
        "query",
        release={
            "selected": "hybrid",
            "lock": {"corpus": fingerprint},
        },
    )
    assert method.startswith("Hybrid")
    assert chunks[0].score == pytest.approx(2 / 61)
    assert chunks[1].score == pytest.approx(2 / 62)
