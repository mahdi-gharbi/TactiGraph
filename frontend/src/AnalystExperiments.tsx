import { useEffect, useState } from "react";
import { get } from "./api";
import type { components } from "./api.generated";

type Results = components["schemas"]["ResearchResponse"];
export function AnalystExperiments() {
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    get<Results>("/experiments/analyst", controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="panel methodology">
      <span className="eyebrow">EXPERIMENT 04 / EVIDENCE ANALYST</span>
      <h2>Measured answers. Measured retrieval.</h2>
      {error ? (
        <p role="alert">Evaluation unavailable: {error}</p>
      ) : !data ? (
        <p>Loading evaluation…</p>
      ) : (
        <>
          <h3>Methodology retrieval</h3>
          <p>
            Offline benchmark: {data.retrieval_selected ?? "not evaluated"}.
            Effective guided search: {data.retrieval_serving_v1}.
            Natural-language analyst: {data.query_retrieval_method} ·{" "}
            {data.query_corpus_version}.
          </p>
          <p>
            Query v2 independent evaluation: {data.query_evaluation_status}. No
            final quality claim is made before independent review.
          </p>
          <p>
            30 development and 30 held-out authored queries. Recall@5 measures
            relevant chunks found; MRR@5 rewards an earlier first relevant
            result. Targets: 90% and 80%, respectively.
          </p>
          {data.retrieval.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Partition</th>
                    <th>Method</th>
                    <th>Queries</th>
                    <th>Recall@5</th>
                    <th>MRR@5</th>
                  </tr>
                </thead>
                <tbody>
                  {data.retrieval.map((row) => (
                    <tr key={`${row.partition}-${row.method}`}>
                      <td>{row.partition}</td>
                      <td>{row.method}</td>
                      <td>{row.queries}</td>
                      <td>{(row.recall_at_5 * 100).toFixed(1)}%</td>
                      <td>{(row.mrr_at_5 * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>No published retrieval evaluation.</p>
          )}
          {data.retrieval_selected && (
            <p>
              Selected: {data.retrieval_selected} · {data.retrieval_version}.
              Hybrid search needs the pinned local encoder; lightweight
              deployments explicitly fall back to BM25. Benchmark results do not
              describe that fallback.
            </p>
          )}
          {data.retrieval.some(
            (row) =>
              row.partition === "held_out" &&
              row.method === data.retrieval_selected &&
              (row.mrr_at_5 < 0.8 || row.recall_at_5 < 0.9),
          ) && (
            <p>
              <strong>
                The selected method does not meet every acceptance target.
              </strong>{" "}
              No held-out retuning was performed.
            </p>
          )}
          <h3>Tactical golden cases</h3>
          <p>
            Separate development and held-out matches; statistical comparisons,
            unsupported premises, unavailable information and adversarial
            requests. These are machine checks against author-written
            expectations.
          </p>
          {data.analyst.map((row) => (
            <p key={`${row.mode}-${row.partition}`}>
              <strong>
                {row.mode} / {row.partition}: {row.passed}/{row.cases}
              </strong>{" "}
              passed · {row.local_generations} successful local selections.
              {row.mode === "groq" && (
                <span>
                  {" "}
                  Groq selections: {row.remote_generations}/
                  {row.generation_cases}; deterministic fallbacks:{" "}
                  {row.fallbacks}; repairs: {row.repairs}; rejected selections:{" "}
                  {row.selection_rejections}; tokens: {row.input_tokens} in /{" "}
                  {row.output_tokens} out; generation p95:{" "}
                  {row.generation_p95_ms == null
                    ? "unavailable"
                    : `${(row.generation_p95_ms / 1000).toFixed(2)} s`}
                  .
                </span>
              )}
            </p>
          ))}
          {!data.local_evaluated && (
            <p>
              Local Qwen generation has not yet been evaluated. Deterministic
              success is not evidence of LLM quality.
            </p>
          )}
          {data.groq_evaluated ? (
            <p>{data.groq_limitations}</p>
          ) : (
            <p>Groq has not yet been evaluated on the golden cases.</p>
          )}
          <p>
            <strong>
              Independent human semantic review: {data.human_review}.
            </strong>{" "}
            Finite test results do not guarantee unsupported claims can never
            occur. The public showcase remains pending review.
          </p>
        </>
      )}
    </section>
  );
}
