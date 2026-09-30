"""Small offline retrieval comparison with frozen corpus, queries and encoder."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from tactigraph.data.pipeline import write_json
from tactigraph.retrieval.bm25 import corpus, retrieve


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MiniLM:
    def __init__(self, protocol):
        import torch
        from transformers import AutoModel, AutoTokenizer

        torch.set_num_threads(2)
        self.torch = torch
        self.maximum = protocol["max_tokens"]
        options = {
            "revision": protocol["revision"],
            "cache_dir": "artifacts/huggingface",
            "trust_remote_code": False,
        }
        self.tokenizer = AutoTokenizer.from_pretrained(protocol["model"], **options)
        self.model = AutoModel.from_pretrained(
            protocol["model"], use_safetensors=True, **options
        ).eval()

    def encode(self, texts):
        values = []
        for start in range(0, len(texts), 16):
            encoded = self.tokenizer(
                texts[start : start + 16],
                padding=True,
                truncation=True,
                max_length=self.maximum,
                return_tensors="pt",
            )
            with self.torch.no_grad():
                output = self.model(**encoded)[0]
                mask = encoded["attention_mask"].unsqueeze(-1)
                pooled = (output * mask).sum(1) / mask.sum(1).clamp(min=1)
                values.append(self.torch.nn.functional.normalize(pooled, p=2, dim=1).numpy())
        return np.concatenate(values)


def reciprocal_rank_fusion(rankings, constant=60, limit=5):
    scores = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), 1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (constant + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]


def query_scores(ranking, relevant):
    relevant = set(relevant)
    if not relevant:
        raise ValueError("Each query needs at least one relevance label")
    top = ranking[:5]
    recall = len(set(top) & relevant) / len(relevant)
    reciprocal = next((1 / i for i, value in enumerate(top, 1) if value in relevant), 0)
    return recall, reciprocal


def evaluate():
    protocol_path = Path("configs/retrieval-v1.json")
    questions_path = Path("configs/retrieval-questions-v1.json")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    documents = corpus()
    chunks = [d.chunk_id for d in documents]
    if any(len(questions[p]) != 30 for p in ("development", "held_out")):
        raise ValueError("Exactly 30 development and 30 held-out queries are required")
    if any(not set(labels) <= set(chunks) for rows in questions.values() for _, labels in rows):
        raise ValueError("Unresolved relevance label")
    directory = Path("artifacts") / protocol["version"]
    signature = {
        "protocol": checksum(protocol_path),
        "questions": checksum(questions_path),
        "bm25_code": checksum(Path(__file__).with_name("bm25.py")),
        "evaluation_code": checksum(Path(__file__)),
        "corpus": hashlib.sha256(
            json.dumps([d.model_dump() for d in documents], sort_keys=True).encode()
        ).hexdigest(),
    }
    lock_path = directory / "lock.json"
    if lock_path.exists():
        if json.loads(lock_path.read_text(encoding="utf-8")) != signature:
            raise ValueError("Retrieval evaluation inputs changed; use a new version")
        result_path = directory / "evaluation.json"
        if result_path.exists():
            return json.loads(result_path.read_text(encoding="utf-8"))
    else:
        write_json(lock_path, signature)
    encoder = MiniLM(protocol)
    texts = [d.section + " " + d.text for d in documents]
    token_lengths = [len(encoder.tokenizer(t)["input_ids"]) for t in texts]
    if max(token_lengths) > protocol["max_tokens"]:
        raise ValueError("A methodology chunk exceeds the encoder truncation limit")
    document_vectors = encoder.encode(texts)
    results = {}
    for partition in ("development", "held_out"):
        rows = questions[partition]
        vectors = encoder.encode([q for q, _ in rows])
        records = {name: [] for name in ("bm25", "minilm", "hybrid")}
        for (query, relevant), vector in zip(rows, vectors, strict=True):
            bm25 = [d.chunk_id for d in retrieve(query)]
            dense = [chunks[i] for i in np.argsort(-(document_vectors @ vector), kind="stable")[:5]]
            hybrid = reciprocal_rank_fusion([bm25, dense], protocol["rrf_constant"])
            for name, ranking in (("bm25", bm25), ("minilm", dense), ("hybrid", hybrid)):
                recall, reciprocal = query_scores(ranking, relevant)
                records[name].append(
                    {
                        "query": query,
                        "relevant": relevant,
                        "retrieved": ranking,
                        "recall_at_5": recall,
                        "reciprocal_rank_at_5": reciprocal,
                    }
                )
        results[partition] = {}
        indices = np.random.default_rng(2026).integers(0, 30, size=(1000, 30))
        for name, records_i in records.items():
            metrics = np.array([[r["recall_at_5"], r["reciprocal_rank_at_5"]] for r in records_i])
            intervals = np.quantile(metrics[indices].mean(1), [0.025, 0.975], axis=0).T.tolist()
            results[partition][name] = {
                "queries": 30,
                "recall_at_5": float(metrics[:, 0].mean()),
                "mrr_at_5": float(metrics[:, 1].mean()),
                "recall_interval": intervals[0],
                "mrr_interval": intervals[1],
                "cases": records_i,
            }
        if partition == "development":
            bm25, hybrid = results[partition]["bm25"], results[partition]["hybrid"]
            candidate = (
                "hybrid"
                if hybrid["recall_at_5"] >= bm25["recall_at_5"]
                and hybrid["mrr_at_5"] > bm25["mrr_at_5"]
                else "bm25"
            )
            write_json(
                directory / "development-selection.json",
                {"candidate": candidate, "lock": signature},
            )
    held_out = results["held_out"]
    hybrid_improves = (
        held_out["hybrid"]["recall_at_5"] >= held_out["bm25"]["recall_at_5"]
        and held_out["hybrid"]["mrr_at_5"] > held_out["bm25"]["mrr_at_5"]
    )
    selected = candidate if candidate == "hybrid" and hybrid_improves else "bm25"
    report = {
        "version": protocol["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lock": signature,
        "protocol": protocol,
        "results": results,
        "development_candidate": candidate,
        "selected": selected,
        "maximum_chunk_tokens": max(token_lengths),
        "acceptance_targets_met": held_out[selected]["recall_at_5"] >= 0.90
        and held_out[selected]["mrr_at_5"] >= 0.80,
        "limitations": "Small authored benchmark on 11 shared methodology chunks; "
        "no claim of general-purpose retrieval quality. Relevance labels have not had "
        "independent human review.",
    }
    write_json(directory / "evaluation.json", report)
    write_json(Path("experiments") / protocol["version"] / "results.json", report)
    return report
