import { useEffect, useRef, useState } from "react";
import { apiUrl, get, type MatchCard } from "./api";
import type { components } from "./api.generated";

type Result = components["schemas"]["AnalystQueryResponse"];
type Evidence = components["schemas"]["TacticalEvidence"];

export function NaturalLanguageAnalyst({ match }: { match: MatchCard }) {
  const [language, setLanguage] = useState<"fr" | "en">("fr");
  const [team, setTeam] = useState(match.home.id);
  const [question, setQuestion] = useState("");
  const [period, setPeriod] = useState(2);
  const [bounds, setBounds] = useState([0, 15, 15, 30]);
  const [result, setResult] = useState<Result | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const serial = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const fr = language === "fr";
  useEffect(() => {
    serial.current += 1;
    controller.current?.abort();
    setResult(null);
    setEvidence(null);
    setBusy(false);
    setError("");
  }, [match.id, team, language, question, period, bounds]);
  useEffect(() => {
    setTeam(match.home.id);
    setQuestion("");
    return () => {
      serial.current += 1;
      controller.current?.abort();
    };
  }, [match.id, match.home.id]);

  async function submit() {
    controller.current?.abort();
    controller.current = new AbortController();
    const current = ++serial.current;
    setResult(null);
    setEvidence(null);
    setError("");
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/analyst/query"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.current.signal,
        body: JSON.stringify({
          question,
          language,
          match_id: match.id,
          team_id: team,
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
            : fr
              ? "Vérifiez la question et les fenêtres."
              : "Check the question and windows.",
        );
      if (current === serial.current) setResult(data);
    } catch (e) {
      if (
        current === serial.current &&
        e instanceof Error &&
        e.name !== "AbortError"
      )
        setError(e.message);
    } finally {
      if (current === serial.current) setBusy(false);
    }
  }

  async function inspect(id: string) {
    const current = serial.current;
    try {
      const data = await get<Evidence>(`/tactical-evidence/${id}`);
      if (data.source_sha256 !== result?.report?.evidence.source_sha256)
        throw new Error(
          fr
            ? "La source a changé ; relancez la question."
            : "Source changed; ask again.",
        );
      if (current === serial.current) setEvidence(data);
    } catch (e) {
      if (current === serial.current)
        setError(e instanceof Error ? e.message : "Evidence unavailable");
    }
  }

  const examples = fr
    ? [
        "Compare la création d’occasions entre les minutes 45–60 et 60–75, et explique le xG.",
        "La progression a-t-elle diminué ?",
        "Explique la différence entre le xG et le xT.",
        "Comment la création d’occasions a-t-elle changé après la minute 60 ?",
      ]
    : [
        "Compare chance creation between minutes 45–60 and 60–75, and explain xG.",
        "Did progression decrease?",
        "Explain the difference between xG and xT.",
        "How did chance creation change after minute 60?",
      ];
  return (
    <div aria-label="Natural-language analyst">
      <h2 id="analyst-title">
        {fr
          ? "Posez une question. Vérifiez les preuves."
          : "Ask a question. Inspect the evidence."}
      </h2>
      <p>
        {match.home.name} – {match.away.name} · {match.date}.{" "}
        {fr
          ? "Analyse locale ; revue indépendante en attente."
          : "Local analysis; independent review pending."}
      </p>
      <div className="filter-row">
        <label>
          {fr ? "Langue" : "Language"}
          <select
            aria-label="Query language"
            value={language}
            onChange={(e) => setLanguage(e.target.value as "en" | "fr")}
          >
            <option value="fr">Français</option>
            <option value="en">English</option>
          </select>
        </label>
        <label>
          {fr ? "Équipe sélectionnée" : "Selected team"}
          <select
            aria-label="Query team"
            value={team}
            onChange={(e) => setTeam(Number(e.target.value))}
          >
            <option value={match.home.id}>{match.home.name}</option>
            <option value={match.away.id}>{match.away.name}</option>
          </select>
        </label>
        <label>
          {fr ? "Période" : "Period"}
          <select
            aria-label="Query period"
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
          >
            <option value={1}>{fr ? "Première mi-temps" : "First half"}</option>
            <option value={2}>{fr ? "Seconde mi-temps" : "Second half"}</option>
          </select>
        </label>
      </div>
      <p>
        {fr
          ? "Fenêtres du formulaire : minutes relatives à la période. Utilisées si la question ne précise aucune fenêtre."
          : "Form windows use period-relative minutes, used when no explicit windows are requested."}
      </p>
      <div className="filter-row">
        {(fr
          ? ["Début avant", "Fin avant", "Début après", "Fin après"]
          : ["Before start", "Before end", "After start", "After end"]
        ).map((label, i) => (
          <label key={i}>
            {label}
            <input
              type="number"
              min={0}
              max={120}
              value={bounds[i]}
              onChange={(e) =>
                setBounds(
                  bounds.map((v, j) => (j === i ? Number(e.target.value) : v)),
                )
              }
            />
          </label>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label>
          {fr ? "Votre question" : "Your question"}
          <textarea
            aria-label="Analyst question"
            maxLength={500}
            rows={3}
            required
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            style={{ width: "100%", maxWidth: "100%", boxSizing: "border-box" }}
          />
        </label>
        <button
          className="primary-button"
          type="submit"
          disabled={busy || !question.trim()}
        >
          {fr ? "Analyser la question" : "Analyze question"}
        </button>
      </form>
      <details>
        <summary>{fr ? "Exemples" : "Examples"}</summary>
        {examples.map((example) => (
          <p key={example}>
            <button type="button" onClick={() => setQuestion(example)}>
              {example}
            </button>
          </p>
        ))}
      </details>
      {busy && (
        <p role="status">
          {fr
            ? "Interprétation et vérification…"
            : "Interpreting and verifying…"}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {result && (
        <article aria-label="Query result" data-status={result.status}>
          <p role="status">{result.message}</p>
          {result.metadata.fallback_reason && (
            <p>
              {fr
                ? "Passez à l’analyse guidée ci-dessus pour continuer."
                : "Switch to Guided analysis above to continue."}
            </p>
          )}
          {result.report && (
            <>
              <h3>{fr ? "Mesures vérifiées" : "Verified measurements"}</h3>
              <p>
                {fr ? "Fenêtres retenues" : "Resolved windows"}:{" "}
                {result.report.arguments.before.period} ·{" "}
                {result.report.arguments.before.start_ms / 60000}–
                {result.report.arguments.before.end_ms / 60000} /{" "}
                {result.report.arguments.after.start_ms / 60000}–
                {result.report.arguments.after.end_ms / 60000} min.
              </p>
              {result.report.claims.map((claim, i) => (
                <div className="experiment-note" key={i}>
                  <p>{claim.text}</p>
                  {claim.evidence_ids.map((id, j) => (
                    <button
                      type="button"
                      key={id}
                      onClick={() => void inspect(id)}
                    >
                      {fr
                        ? `Preuve ${j === 0 ? "avant" : "après"}`
                        : `Inspect ${j === 0 ? "before" : "after"} evidence`}{" "}
                      →
                    </button>
                  ))}
                </div>
              ))}
              <details>
                <summary>
                  {fr
                    ? "Dénominateurs et limites"
                    : "Denominators and limitations"}
                </summary>
                {[
                  result.report.evidence.before,
                  result.report.evidence.after,
                ].map((facts, i) => (
                  <ul key={i}>
                    {facts.map((f) => (
                      <li key={f.metric}>
                        {f.metric}: {f.value ?? "—"} {f.unit} ·{" "}
                        {f.numerator ?? "—"} / {f.denominator ?? "—"}{" "}
                        {f.denominator_unit}
                      </li>
                    ))}
                  </ul>
                ))}
                <ul>
                  {result.report.qualifications.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </details>
            </>
          )}
          {result.methodology.map((chunk) => (
            <div className="experiment-note" key={chunk.chunk_id}>
              <strong>{chunk.section}</strong>
              <p>{chunk.text}</p>
              <small>
                {chunk.document_id} · {chunk.version} · {chunk.chunk_id}
              </small>
            </div>
          ))}
          <details>
            <summary>
              {fr ? "Exécution et recherche" : "Execution and retrieval"}
            </summary>
            <p>
              {result.metadata.model} ·{" "}
              {result.metadata.retrieval_method ?? "—"} ·{" "}
              {(result.metadata.latency_ms / 1000).toFixed(2)}s ·{" "}
              {result.metadata.attempts} calls · {result.metadata.input_tokens}/
              {result.metadata.output_tokens} tokens.
            </p>
            <p>
              {result.metadata.corpus_version} · {result.metadata.corpus_sha256}
            </p>
            <ul>
              {result.trace.map((step, i) => (
                <li key={i}>
                  {step.name} · {step.status} · {step.duration_ms.toFixed(1)} ms
                </li>
              ))}
            </ul>
          </details>
        </article>
      )}
      {evidence && (
        <aside aria-label="Query evidence">
          <h3>{fr ? "Preuves sources" : "Source evidence"}</h3>
          <p>{evidence.definition}</p>
          <p>
            {evidence.total}{" "}
            {fr ? "événements justificatifs" : "supporting events"}.
          </p>
          <ul>
            {evidence.references.map((event) => (
              <li key={event.event_id}>
                <a href={event.source_url} target="_blank" rel="noreferrer">
                  {event.timestamp} · {event.event_id}
                </a>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
