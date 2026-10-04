from fastapi import APIRouter, HTTPException, Query, Request

from tactigraph.analyst.contracts import AnalystReport, AnalystRequest
from tactigraph.analyst.query import run_query
from tactigraph.analyst.query_contracts import AnalystQueryRequest, AnalystQueryResponse
from tactigraph.analyst.verification import verify_report
from tactigraph.analyst.workflow import run
from tactigraph.api.schemas import BaseModel
from tactigraph.db import DatasetReport
from tactigraph.retrieval.bm25 import DocumentChunk
from tactigraph.retrieval.runtime import search

router = APIRouter(prefix="/api/v1", tags=["verified analyst"])


class MethodologyResponse(BaseModel):
    method: str
    chunks: list[DocumentChunk]


class RetrievalScore(BaseModel):
    partition: str
    method: str
    queries: int
    recall_at_5: float
    mrr_at_5: float


class AnalystScore(BaseModel):
    mode: str
    partition: str
    cases: int
    passed: int
    local_generations: int
    remote_generations: int = 0
    generation_cases: int = 0
    fallbacks: int = 0
    repairs: int = 0
    selection_rejections: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    generation_p95_ms: float | None = None


class ResearchResponse(BaseModel):
    retrieval_version: str | None = None
    retrieval_selected: str | None = None
    retrieval_generated_at: str | None = None
    retrieval: list[RetrievalScore]
    analyst: list[AnalystScore]
    human_review: str = "pending"
    local_evaluated: bool = False
    groq_evaluated: bool = False
    groq_limitations: str | None = None
    retrieval_serving_v1: str = "BM25"
    query_retrieval_method: str = "BM25 v2"
    query_corpus_version: str = "methodology-v2"
    query_evaluation_status: str = "independent_review_pending"


@router.get("/experiments/analyst", response_model=ResearchResponse)
def research_results(request: Request):
    response = ResearchResponse(retrieval=[], analyst=[])
    with request.app.state.sessions() as session:
        stored = session.get(DatasetReport, "retrieval")
        if stored:
            payload = stored.payload
            response.retrieval_version = payload["version"]
            response.retrieval_selected = payload["selected"]
            response.retrieval_generated_at = payload["generated_at"]
            response.retrieval_serving_v1, _ = search("expected goals", release=payload)
            for partition, methods in payload["results"].items():
                for method, score in methods.items():
                    response.retrieval.append(
                        RetrievalScore(
                            partition=partition,
                            method=method,
                            queries=score["queries"],
                            recall_at_5=score["recall_at_5"],
                            mrr_at_5=score["mrr_at_5"],
                        )
                    )
        for mode in ("deterministic", "local", "groq"):
            stored = session.get(DatasetReport, f"analyst-{mode}")
            if stored:
                response.local_evaluated |= mode == "local"
                response.groq_evaluated |= mode == "groq"
                if mode == "groq":
                    response.groq_limitations = stored.payload.get("limitations")
                for partition, score in stored.payload["summary"].items():
                    response.analyst.append(AnalystScore(mode=mode, partition=partition, **score))
    return response


@router.post("/analyst/report", response_model=AnalystReport)
def analyst_report(arguments: AnalystRequest, request: Request):
    if request.app.state.settings.mode == "public":
        raise HTTPException(
            404, "Live analyst reports are local-only; public showcase pending review"
        )
    try:
        with request.app.state.sessions() as session:
            report = run(session, arguments)
        if arguments.generation == "local":
            from tactigraph.analyst.ollama import select_claims

            report = select_claims(report, request.app.state.settings)
        elif arguments.generation == "groq":
            from tactigraph.analyst.groq import select_claims

            report = select_claims(report, request.app.state.settings)
        with request.app.state.sessions() as session:
            verify_report(report, session=session)
        from tactigraph.observability import record_operation

        metadata = report.generation
        record_operation(
            request,
            outcome=report.status,
            provider=metadata.provider if metadata else "deterministic",
            model_version=metadata.model if metadata else "verified-templates-v1",
            fallback=report.mode == "deterministic_fallback",
            fallback_reason=metadata.fallback_reason if metadata else None,
            input_tokens=metadata.input_tokens if metadata else 0,
            output_tokens=metadata.output_tokens if metadata else 0,
            generation_ms=metadata.latency_ms if metadata else 0,
        )
        return report
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/analyst/query", response_model=AnalystQueryResponse)
async def analyst_query(arguments: AnalystQueryRequest, request: Request):
    if request.app.state.settings.mode == "public":
        raise HTTPException(404, "Interactive queries are local-only")
    result = await run_query(
        request.app.state.sessions,
        arguments,
        request.app.state.settings,
        transport=getattr(request.app.state, "query_transport", None),
    )
    from tactigraph.observability import record_operation

    record_operation(
        request,
        provider=result.metadata.provider,
        outcome=result.status,
        retrieval_method=result.metadata.retrieval_method,
        model_version=result.metadata.model,
        fallback=bool(result.metadata.fallback_reason),
        fallback_reason=result.metadata.fallback_reason,
        generation_ms=result.metadata.latency_ms,
        input_tokens=result.metadata.input_tokens,
        output_tokens=result.metadata.output_tokens,
        usage_complete=result.metadata.usage_complete,
        attempts=result.metadata.attempts,
        repairs=result.metadata.repairs,
        provider_errors=result.metadata.provider_errors,
        stages=[stage.model_dump() for stage in result.trace],
    )
    return result


@router.get("/methodology/search", response_model=MethodologyResponse)
def methodology_search(
    request: Request,
    query: str = Query(min_length=1, max_length=500),
    topic: str | None = Query(None, max_length=80),
    version: str | None = Query(None, max_length=80),
    language: str = Query("en", max_length=8),
):
    try:
        with request.app.state.sessions() as session:
            stored = session.get(DatasetReport, "retrieval")
            release = stored.payload if stored else None
        method, chunks = search(
            query,
            release=release,
            topic=topic,
            version=version,
            language=language,
        )
        return MethodologyResponse(
            method=method,
            chunks=chunks,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
