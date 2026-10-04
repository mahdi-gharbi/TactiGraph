import { useEffect, useRef, useState } from "react";
import { get, apiUrl, type MatchCard } from "./api";
import type { components } from "./api.generated";
import { NaturalLanguageAnalyst } from "./NaturalLanguageAnalyst";

type Report = components["schemas"]["AnalystReport"];
type Evidence = components["schemas"]["TacticalEvidence"];
type Search = components["schemas"]["MethodologyResponse"];
type Intent = Report["arguments"]["intent"];

export function EvidenceAnalyst({ match }: { match: MatchCard }) {
  const [mode, setMode] = useState<"guided" | "query">("guided");
  const [team, setTeam] = useState(match.home.id);
  const [period, setPeriod] = useState(2);
  const [bounds, setBounds] = useState([0, 15, 15, 30]);
  const [intent, setIntent] = useState<Intent>("period_comparison");
  const [report, setReport] = useState<Report | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [generation, setGeneration] = useState<
    "deterministic" | "local" | "groq"
  >("groq");
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [query, setQuery] = useState("final third entries field tilt");
  const [search, setSearch] = useState<Search | null>(null);
  const [searching, setSearching] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const evidenceRef = useRef<HTMLElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    setReport(null);
    setEvidence(null);
  }, [team, period, intent, bounds, question, generation]);
  useEffect(() => {
    evidenceRef.current?.scrollIntoView({ block: "nearest" });
  }, [evidence]);
  async function generate() {
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    setReport(null);
    setEvidence(null);
    try {
      const response = await fetch(apiUrl("/analyst/report"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.current.signal,
        body: JSON.stringify({
          match_id: match.id,
          team_id: team,
          intent,
          generation,
          question: question.trim() || null,
          before: {
            period,
            start_ms: bounds[0] * 60000,
            end_ms: bounds[1] * 60000,
          },
          after: {
            period,
            start_ms: bounds[2] * 60000,
            end_ms: bounds[3] * 60000,
          },
        }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Check the window bounds. Windows cannot overlap or exceed match coverage.",
        );
      setReport(data);
    } catch (e) {
      if (e instanceof Error && e.name !== "AbortError") setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function inspect(id: string) {
    setError("");
    try {
      const result = await get<Evidence>(`/tactical-evidence/${id}`);
      if (result.source_sha256 !== report?.evidence.source_sha256)
        throw new Error("Source changed; generate a new report.");
      setEvidence(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evidence unavailable");
    }
  }
  return (
    <section className="panel experiment-card" aria-labelledby="analyst-title">
      <div className="filter-row" aria-label="Analyst mode">
        <button
          type="button"
          aria-pressed={mode === "guided"}
          onClick={() => setMode("guided")}
        >
          Analyse guidée / Guided analysis
        </button>
        <button
          type="button"
          aria-pressed={mode === "query"}
          onClick={() => setMode("query")}
        >
          Question libre / Free question
        </button>
      </div>
      {mode === "query" ? (
        <NaturalLanguageAnalyst key={match.id} match={match} />
      ) : (
        <>
          <span className="eyebrow">EVIDENCE ANALYST / VERIFIED FACTS</span>
          <h2 id="analyst-title">Test the premise. Inspect the evidence.</h2>
          <p>
            Guided analysis with verified numerical templates. Optional Groq or
            Qwen3 selects supported claims; every number and sentence remains
            verified. Public reports await independent review.
          </p>
          <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
            <label>
              Claim selection provider
              <select
                value={generation}
                onChange={(e) =>
                  setGeneration(e.target.value as typeof generation)
                }
              >
                <option value="groq">
                  Groq · GPT-OSS 20B (backend key required)
                </option>
                <option value="deterministic">
                  Deterministic · no model or external request
                </option>
                <option value="local">Local Ollama · pinned Qwen3 4B</option>
              </select>
            </label>
            <p>
              {generation === "groq"
                ? "Groq receives only verified aggregate statements and returns claim IDs. No raw events or API key reach the browser. If unavailable, the deterministic report remains functional. Provider evaluation and limitations are available in Experiments."
                : generation === "local"
                  ? "Local selection requires the installed, digest-pinned model."
                  : "No language model is called."}
            </p>
            <div className="filter-row">
              <label>
                Optional supported question
                <input
                  maxLength={500}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Did progression decrease?"
                />
              </label>
            </div>
            <p>
              Supported questions mirror the three guided choices. “Why did this
              team lose control after minute 60?” tests the premise through
              progression metrics. Other free-text questions are refused.
            </p>
            <div className="filter-row">
              <label>
                Analyst team
                <select
                  value={team}
                  onChange={(e) => setTeam(Number(e.target.value))}
                >
                  <option value={match.home.id}>{match.home.name}</option>
                  <option value={match.away.id}>{match.away.name}</option>
                </select>
              </label>
              <label>
                Guided question
                <select
                  value={intent}
                  onChange={(e) => setIntent(e.target.value as Intent)}
                >
                  <option value="period_comparison">
                    Did progression decrease?
                  </option>
                  <option value="chance_creation">
                    How did chance creation change?
                  </option>
                  <option value="network_concentration">
                    Did passing become more concentrated?
                  </option>
                </select>
              </label>
              <label>
                Analyst period
                <select
                  value={period}
                  onChange={(e) => setPeriod(Number(e.target.value))}
                >
                  <option value={1}>First half</option>
                  <option value={2}>Second half</option>
                </select>
              </label>
            </div>
            <p>
              Minutes below are relative to the selected period. In the second
              half, 0–15 versus 15–30 means match minutes 45–60 versus 60–75.
              Windows never cross halftime.
            </p>
            <div className="filter-row">
              {["Before start", "Before end", "After start", "After end"].map(
                (label, i) => (
                  <label key={label}>
                    {label}
                    <input
                      type="number"
                      min={0}
                      max={120}
                      step={1}
                      value={bounds[i]}
                      onChange={(e) =>
                        setBounds(
                          bounds.map((v, j) =>
                            j === i ? Number(e.target.value) : v,
                          ),
                        )
                      }
                    />
                  </label>
                ),
              )}
            </div>
            <button className="primary-button" onClick={generate}>
              Generate verified comparison
            </button>
          </fieldset>
          {busy && <p role="status">Checking measurements and citations…</p>}
          {error && <p role="alert">{error}</p>}
          {report && (
            <article aria-label="Verified analyst report">
              {report.generation && (
                <p className="experiment-note">
                  Mode: {report.mode}. Provider: {report.generation.provider};
                  model: {report.generation.model}. Calls:{" "}
                  {report.generation.attempts}; repairs:{" "}
                  {report.generation.repairs}; tokens:{" "}
                  {report.generation.input_tokens} in /{" "}
                  {report.generation.output_tokens} out;{" "}
                  {(report.generation.latency_ms / 1000).toFixed(2)} s.{" "}
                  {report.generation.fallback_reason}
                </p>
              )}
              <h3>
                {report.status === "verified"
                  ? "Verified measurements"
                  : "Insufficient evidence to answer"}
              </h3>
              <p>
                {report.publication_label}. Period{" "}
                {report.arguments.before.period}:{" "}
                {report.arguments.before.start_ms / 60000}–
                {report.arguments.before.end_ms / 60000} versus{" "}
                {report.arguments.after.start_ms / 60000}–
                {report.arguments.after.end_ms / 60000} minutes.
              </p>
              {report.claims.map((claim, i) => (
                <div className="experiment-note" key={i}>
                  <p>{claim.text}</p>
                  {claim.evidence_ids.map((id, j) => (
                    <button
                      key={id}
                      className="player-button"
                      onClick={() => inspect(id)}
                    >
                      Inspect {j === 0 ? "before" : "after"} evidence →
                    </button>
                  ))}
                </div>
              ))}
              <details>
                <summary>Verification, denominators and limitations</summary>
                <ul>
                  {report.qualifications.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
                {[report.evidence.before, report.evidence.after].map(
                  (facts, i) => (
                    <div key={i}>
                      <h4>{i === 0 ? "Before" : "After"}</h4>
                      <ul>
                        {facts.map((f) => (
                          <li key={f.metric}>
                            {f.metric}: {f.value ?? "unavailable"} {f.unit};
                            denominator {f.denominator ?? "not applicable"}{" "}
                            {f.denominator_unit}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ),
                )}
                <p>
                  {report.trace.join(" → ")}. {report.tool_calls}/6 tool calls;{" "}
                  {report.verification_rejections} claims removed.
                </p>
                <p>
                  Report {report.report_id}; metric version{" "}
                  {report.evidence.metric_version}; {report.attribution}.
                </p>
              </details>
            </article>
          )}
          {evidence && (
            <aside
              ref={evidenceRef}
              className="experiment-note"
              aria-label="Analyst evidence"
            >
              <h3>Supporting evidence</h3>
              <p>{evidence.definition}</p>
              <p>
                {evidence.total} supporting events. Showing the first{" "}
                {evidence.references.length}; complete references remain in the
                local analytical result.
              </p>
              <ul>
                {evidence.references.map((event) => (
                  <li key={event.event_id}>
                    <a href={event.source_url} target="_blank" rel="noreferrer">
                      Period {event.period} · {event.timestamp} ·{" "}
                      {event.event_id}
                    </a>
                  </li>
                ))}
              </ul>
            </aside>
          )}
          <h3>Search the methodology</h3>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setError("");
              setSearching(true);
              setSearch(null);
              try {
                setSearch(
                  await get<Search>(
                    `/methodology/search?query=${encodeURIComponent(query)}`,
                  ),
                );
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Search unavailable",
                );
              } finally {
                setSearching(false);
              }
            }}
          >
            <div className="filter-row">
              <label>
                Methodology query
                <input
                  maxLength={500}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  required
                />
              </label>
              <button type="submit" disabled={searching}>
                Search definitions
              </button>
            </div>
          </form>
          {searching && (
            <p role="status">
              Searching approved definitions. The first local search loads the
              pinned encoder.
            </p>
          )}
          {search && (
            <>
              <p>
                {search.method}. Match facts come from structured queries, never
                document retrieval.
              </p>
              {search.chunks.map((chunk) => (
                <div className="experiment-note" key={chunk.chunk_id}>
                  <strong>{chunk.section}</strong>
                  <p>{chunk.text}</p>
                  <small>
                    {chunk.document_id} · {chunk.version} · {chunk.chunk_id}
                  </small>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}
