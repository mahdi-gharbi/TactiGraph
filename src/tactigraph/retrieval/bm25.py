import math
import re
from collections import Counter

from tactigraph.analytics.windows import DEFINITIONS, VERSION
from tactigraph.api.schemas import BaseModel


class DocumentChunk(BaseModel):
    document_id: str
    version: str
    section: str
    chunk_id: str
    topic: str
    language: str = "en"
    text: str
    score: float


def corpus():
    return [
        DocumentChunk(
            document_id="tactical-methodology",
            version=VERSION,
            section=metric.replace("_", " "),
            chunk_id=f"metric-{metric}",
            topic=metric,
            text=definition,
            score=0,
        )
        for metric, definition in DEFINITIONS.items()
    ] + [
        DocumentChunk(
            document_id="limitations",
            version="limitations-v1",
            section="Scope",
            chunk_id="limitations-scope",
            topic="limitations",
            score=0,
            text="The sampled Women's Super League seasons have no separate 360 coverage. "
            "Event observations cannot establish off-ball runs or defensive shape. "
            "Associations do not prove that substitutions caused tactical changes.",
        ),
        DocumentChunk(
            document_id="xg-model-card",
            version="xg-v1",
            section="Probability",
            chunk_id="xg-probability",
            topic="xg",
            score=0,
            text="Expected goals estimates shot scoring probability. Higher total xG "
            "does not guarantee winning. Penalties use a separate historical model. "
            "StatsBomb xG is an uncontrolled external reference.",
        ),
        DocumentChunk(
            document_id="graph-model-card",
            version="graph-v1",
            section="Cutoff",
            chunk_id="graph-cutoff",
            topic="graph",
            score=0,
            text="Third-pass predictions estimate a later shot in the same eligible "
            "control episode. Only the prefix through the third completed pass is used. "
            "Historical on-ball locations are not tracking positions.",
        ),
    ]


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def retrieve(query, *, topic=None, version=None, language="en", limit=5):
    """BM25 k1=1.2, b=.75; approved project-authored chunks only."""
    if not query.strip() or len(query) > 500 or not 1 <= limit <= 5:
        raise ValueError("Invalid bounded retrieval request")
    documents = [
        d
        for d in corpus()
        if (topic is None or d.topic == topic)
        and (version is None or d.version == version)
        and d.language == language
    ]
    if not documents:
        return []
    counts = [Counter(tokens(d.section + " " + d.text)) for d in documents]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths)
    results = []
    for doc, counts_i, length in zip(documents, counts, lengths, strict=True):
        score = 0.0
        for token in set(tokens(query)):
            frequency = sum(token in c for c in counts)
            idf = math.log(1 + (len(documents) - frequency + 0.5) / (frequency + 0.5))
            count = counts_i[token]
            score += idf * (count * 2.2) / (count + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            results.append(doc.model_copy(update={"score": score}))
    return sorted(results, key=lambda d: (-d.score, d.chunk_id))[:limit]
