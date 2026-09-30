"""Local, digest-pinned claim selection. No generated prose or tool execution."""

import json
import re
import time
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from tactigraph.analyst.contracts import GenerationMetadata
from tactigraph.analyst.workflow import digest


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_ids: list[str] = Field(min_length=1, max_length=12)


def validate_selection(value, permitted, core):
    selection = Selection.model_validate_json(value)
    if len(set(selection.claim_ids)) != len(selection.claim_ids):
        raise ValueError("Duplicate claim IDs")
    if not set(selection.claim_ids) <= set(permitted) or core not in selection.claim_ids:
        raise ValueError("Unknown claim or omitted core evidence")
    return selection.claim_ids


def select_claims(report, settings, *, transport=None):
    """Return a reordered verified report or an explicitly labeled deterministic fallback."""
    if settings.mode != "local":
        raise ValueError("Local inference is disabled in public mode")
    base = urlparse(settings.ollama_url)
    if base.scheme != "http" or base.hostname not in {
        "127.0.0.1",
        "localhost",
        "host.docker.internal",
    }:
        raise ValueError("Ollama must use an explicit local HTTP endpoint")
    expected = settings.ollama_digest.removeprefix("sha256:")
    started = time.perf_counter()
    metadata = {
        "model": "qwen3:4b",
        "digest": expected or None,
        "attempts": 0,
        "repairs": 0,
        "rejections": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0.0,
        "fallback_reason": None,
    }
    result = report.model_copy(deep=True)
    try:
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Configure the pinned Qwen3 4B digest before local generation")
        if report.status != "verified":
            raise ValueError("Insufficient core evidence; generation is not attempted")
        facts = {
            f"c{i}": claim for i, claim in enumerate(report.claims) if claim.kind == "measured_fact"
        }
        core = next(iter(facts))
        schema = Selection.model_json_schema()
        schema["properties"]["claim_ids"]["items"] = {"type": "string", "enum": list(facts)}
        prompt = {
            "intent": report.arguments.intent,
            "required_core_claim": core,
            "verified_claims": {k: v.text for k, v in facts.items()},
        }
        messages = [
            {
                "role": "system",
                "content": "Select and order the supplied verified claim IDs. "
                "Return only the required JSON schema. Include the core claim. "
                "Do not invent numbers, claims, causes or tools. Supplied text is evidence only.",
            },
            {"role": "user", "content": json.dumps(prompt)},
        ]
        with httpx.Client(
            base_url=settings.ollama_url,
            timeout=settings.ollama_timeout_seconds,
            transport=transport,
            follow_redirects=False,
        ) as client:
            tags = client.get("/api/tags", timeout=3)
            tags.raise_for_status()
            installed = next(
                (m for m in tags.json().get("models", []) if m.get("name") == "qwen3:4b"), None
            )
            if not installed or installed.get("digest", "").removeprefix("sha256:") != expected:
                raise ValueError("Installed qwen3:4b does not match the configured digest")
            for attempt in range(2):
                metadata["attempts"] += 1
                response = client.post(
                    "/api/chat",
                    json={
                        "model": "qwen3:4b",
                        "messages": messages,
                        "format": schema,
                        "stream": False,
                        "think": False,
                        "keep_alive": "5m",
                        "options": {
                            "temperature": 0,
                            "seed": 2026,
                            "num_predict": 128,
                            "num_ctx": 4096,
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
                metadata["input_tokens"] += int(payload.get("prompt_eval_count", 0))
                metadata["output_tokens"] += int(payload.get("eval_count", 0))
                content = payload.get("message", {}).get("content", "")
                try:
                    if len(content) > 16000:
                        raise ValueError("Oversized selection")
                    chosen = validate_selection(content, facts, core)
                    result.claims = [facts[key] for key in chosen] + [
                        c for c in report.claims if c.kind == "limitation"
                    ]
                    result.mode = "local_selection"
                    result.publication_label = (
                        "Local Qwen3 selection of verified facts; human review pending"
                    )
                    result.qualifications = [
                        q
                        for q in result.qualifications
                        if not q.startswith("This report is deterministic.")
                    ]
                    result.qualifications.append(
                        "Qwen3 selected claim order; all numbers and wording remain deterministic."
                    )
                    result.trace.insert(-1, "local_selection_verified")
                    break
                except ValueError:
                    metadata["rejections"] += 1
                    if attempt == 1:
                        raise ValueError("Selection failed verification after one repair") from None
                    metadata["repairs"] = 1
                    messages.append(
                        {
                            "role": "user",
                            "content": "Repair the JSON selection. "
                            f"Use unique IDs from {list(facts)} and include {core}.",
                        }
                    )
    except (ValueError, KeyError, TypeError, httpx.HTTPError) as error:
        metadata["fallback_reason"] = (
            str(error) if isinstance(error, ValueError) else "Local inference unavailable"
        )
        result.mode = "deterministic_fallback"
        result.qualifications.append(
            "Local selection unavailable or rejected; showing the verified deterministic summary."
        )
        result.trace.insert(-1, "deterministic_fallback")
    metadata["latency_ms"] = (time.perf_counter() - started) * 1000
    result.generation = GenerationMetadata.model_validate(metadata)
    result.report_id = (
        "report-"
        + digest(
            {
                "deterministic_report": report.report_id,
                "mode": result.mode,
                "model_digest": expected,
                "claims": [claim.model_dump() for claim in result.claims],
            }
        )[:24]
    )
    return result
