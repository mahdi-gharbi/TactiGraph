# Analyst preview — M6 in progress

Update, 25 September 2026: the user approved Groq as the preferred interactive provider
for this PC. `openai/gpt-oss-20b` is now available alongside optional local Qwen and
deterministic reports. Setup and the external-data boundary are documented in
`groq-setup.md`. Its separate real provider regression passed 60/60 machine checks,
including 40 real selections and 20 mandatory abstentions. Prior deterministic or local
results remain separate; independent human semantic review is still pending.

The local Evidence Analyst now supports three explicit intents: period comparison,
chance-creation comparison and passing-network concentration. The default second-half
windows are period-local 0–15 and 15–30 minutes, corresponding to 45–60 versus 60–75.
Inputs are bounded and validated; windows cannot overlap or span halftime.

The Python state machine validates the request, selects its allowlisted intent, builds
a bounded plan, executes read-only analytical code, constructs candidate claims, verifies
them and renders or abstains. The current implementation uses one tool call, with a
six-call ceiling. Existing analytical functions remain the sole source of metric formulas.

Claim selection contains only a controlled predicate, metric and evidence result ID.
It cannot supply numbers or arbitrary prose. Verification checks the result identity,
intent/metric compatibility, availability, units and denominators. Numerical facts are
rendered from validated server-returned fields; known limitations use fixed templates.
The core metric must survive verification for an answer to be marked verified. Other
available measurements can still be displayed in an abstention summary.

Each result includes arguments, values, units, denominators, source commit/checksum,
metric version, model artifact hashes and quality warnings. Complete supporting event IDs
are retained inside the tool result and excluded from the public response schema. The
evidence viewer resolves paginated analytical references to the pinned upstream source.
Nothing claims that a change caused a decline or that average locations are formations.

BM25 searches only short project-authored definitions and model/coverage limitations.
Results carry document, section, version and chunk IDs; topic/version/language filters
are supported and at most five chunks are returned. Retrieved text is displayed as evidence,
never executed as an instruction. It supplies no match statistics.

The interface explicitly labels reports as deterministic and machine-verified, with
human review pending. `/api/v1/analyst/report` is local-only; it is disabled in public mode.
This preview is not the final 36-report public showcase.

## Evaluated checkpoint (24 September 2026)

The 60 tactical cases use five development matches and five different held-out matches.
Each partition has 15 statistical comparisons, five unsupported-control-premise questions,
five unavailable-information questions and five adversarial requests. The deterministic
workflow passed 30/30 in each partition. Independent raw-JSON calculations check core
metrics; citation support and required qualifications are machine checked. Author-written
expectations do not replace independent human semantic review, which remains pending.

The separate 60-query retrieval evaluation is frozen in `configs/retrieval-v1.json` and
`configs/retrieval-questions-v1.json`. On the 30 held-out queries, BM25 achieved Recall@5
0.8333 and MRR@5 0.7028; hybrid achieved 0.9667 and 0.7744. Hybrid improves both but misses
the proposed MRR target of 0.80. No held-out retuning was performed. Queries share topics;
query-bootstrap uncertainty does not establish generalization to arbitrary questions.

Local hybrid search loads the pinned, checksum-verified MiniLM encoder from disk.
The first search incurs model-loading latency. Production images contain no encoder or
ML dependencies and explicitly fall back to BM25. Every response names the actual method;
the hybrid benchmark must not be attributed to the fallback. Retrieval supplies definitions,
not match facts, and is independently accessible from the analyst interface.

The Qwen3 adapter accepts only claim IDs and their order. It verifies the installed model
digest before calling local Ollama, validates structured output, allows one repair, and
falls back to deterministic facts if selection fails. Numbers and wording never come from
the LLM. The optional question field accepts only the documented guided questions and the
two unsupported-control-premise variants; this is not general free-text question answering.
Real local-generation quality and latency remain unmeasured until the model is installed
and the local evaluation completes. Mock tests are not model evaluations.

Reproduce after ingesting data and publishing the fitted analytical artifacts:

```powershell
uv sync --frozen --extra dev --extra modeling --extra graph --extra retrieval
tactigraph evaluate-retrieval
tactigraph evaluate-analyst
tactigraph publish-analyst
# After installing qwen3:4b and setting TACTIGRAPH_OLLAMA_DIGEST:
tactigraph evaluate-analyst --local
tactigraph publish-analyst
```

The digest comes from the installed model entry in Ollama `/api/tags`; never silently
update it after evaluation. Configure `TACTIGRAPH_OLLAMA_URL` and timeout through the
environment (see `.env.example`). Windows host Ollama is supported; a local Docker app
can use `http://host.docker.internal:11434` if the host service is reachable there.
Do not expose the inference service publicly. The web application never pulls models.

The portable Windows runtime version/checksum and expected official model manifest are
recorded in `configs/ollama-runtime-v1.json`. If `ollama pull qwen3:4b` repeatedly loses
large transfers, stop that pull and run `python infra/fetch_qwen.py`. This optional helper
downloads the pinned official registry layers in resumable 4 MiB ranges, with two workers
and a two-hour attempt budget. It installs no blob until its complete SHA-256 matches,
and writes the model manifest only after all layers verify. Re-running retains completed
chunks. Start Ollama with `OLLAMA_MODELS` pointing to this project's `artifacts/ollama-models`.
Downloading or installing the model is not a successful local-generation evaluation.

Aggregate results are exported to `experiments/` and published to the database for
`/api/v1/experiments/analyst`. Raw golden evidence stays in ignored `artifacts/`.
The 36 human-reviewed public reports belong to the later release milestone.
