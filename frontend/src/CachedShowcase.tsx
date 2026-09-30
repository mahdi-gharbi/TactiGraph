import { useEffect, useState } from "react";
import { get, selectedLeague, type MatchCard } from "./api";
import type { components } from "./api.generated";
import "./showcase.css";

type Showcase = components["schemas"]["ShowcaseResponse"];
type Evidence = components["schemas"]["TacticalEvidence"];
const intents: Record<string, string> = {
  period_comparison: "Progression",
  chance_creation: "Chance creation",
  network_concentration: "Passing concentration",
};

const demoCases = [
  {
    matchId: 19716,
    intent: "period_comparison",
    title: "Progression",
    question: "Did Reading reach the final third less often after minute 60?",
    reading: "Compare entries per elapsed minute across the two equal windows.",
  },
  {
    matchId: 3764233,
    intent: "chance_creation",
    title: "Chance creation",
    question: "Did Arsenal take more shots after minute 60?",
    reading: "Count observed shots in each window; do not infer their cause.",
  },
  {
    matchId: 2275026,
    intent: "network_concentration",
    title: "Passing pattern",
    question: "Did Bristol City's outgoing passes become more concentrated?",
    reading: "Compare the HHI of outgoing passes, not player positions.",
  },
] as const;

export function CachedShowcase({
  matches,
  onMatch,
}: {
  matches: MatchCard[];
  onMatch: (id: number) => void;
}) {
  const [data, setData] = useState<Showcase | null>(null);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [offset, setOffset] = useState(0);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  useEffect(() => {
    const c = new AbortController();
    get<Showcase>("/showcase", c.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  const entry = data?.reports[selected];
  const measuredClaims =
    entry?.report.claims.filter((claim) => claim.evidence_ids.length) ?? [];
  const activeCase = demoCases.findIndex(
    (item) =>
      item.matchId === entry?.report.arguments.match_id &&
      item.intent === entry.report.arguments.intent,
  );
  const guided = activeCase >= 0 ? demoCases[activeCase] : null;
  function selectReport(index: number) {
    setSelected(index);
    setEvidenceId("");
    setEvidence(null);
    setError("");
  }
  function claimEvidence(
    claim: (typeof measuredClaims)[number],
    index: number,
  ) {
    return (
      <div key={`${claim.result_id}-${index}`} className="showcase-claim">
        <p>{claim.text}</p>
        {index === 0 && <span className="eyebrow">03 / CHECK THE SOURCE</span>}
        {claim.evidence_ids.map((id, evidenceIndex) => (
          <button
            type="button"
            key={id}
            onClick={() => {
              setEvidenceId(id);
              setOffset(0);
              setError("");
            }}
          >
            Inspect {evidenceIndex ? "after" : "before"} evidence
          </button>
        ))}
      </div>
    );
  }
  useEffect(() => {
    const c = new AbortController();
    setEvidence(null);
    if (evidenceId)
      get<Evidence>(
        `/tactical-evidence/${evidenceId}?offset=${offset}&limit=20`,
        c.signal,
      )
        .then((e) => {
          if (e.source_sha256 !== entry?.report.evidence.source_sha256)
            throw new Error("Source changed; cached report needs review.");
          setEvidence(e);
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    return () => c.abort();
  }, [evidenceId, offset, entry]);
  function label(matchId: number) {
    const m = matches.find((m) => m.id === matchId);
    return m
      ? `${m.home.name} – ${m.away.name} · ${m.date}`
      : `Match ${matchId}`;
  }
  return (
    <section
      className="panel experiment-card cached-showcase"
      aria-label="Cached showcase"
    >
      <span className="eyebrow">
        {selectedLeague === "premier-league"
          ? "GUIDED SHOWCASE / WSL ONLY"
          : "FIELD GUIDE / THREE MATCH QUESTIONS"}
      </span>
      <h2>
        {selectedLeague === "premier-league"
          ? "A separate showcase is still needed here."
          : "Start with a question. Follow the evidence."}
      </h2>
      <p className="showcase-intro">
        {selectedLeague === "premier-league"
          ? "The three guided examples were prepared from WSL data. Premier League analysis is available below, but has no curated or independently reviewed showcase yet."
          : "A short route through fixed comparisons of minutes 45–60 and 60–75 for the home team. Figures come from saved reports, with no live generation."}
      </p>
      {selectedLeague === "premier-league" && (
        <a href="/">Open the WSL guided cases</a>
      )}
      {error && <p role="alert">{error}</p>}
      {!data ? (
        <p role="status">Loading cached reports…</p>
      ) : (
        <>
          {data.status !== "available" && (
            <p role="status">
              {data.status === "review_pending"
                ? "Independent review pending. Draft reports are visible only in the local workspace."
                : data.status === "stale"
                  ? "Source or model changed. Reports require a fresh review."
                  : selectedLeague === "premier-league"
                    ? "No Premier League showcase has been prepared."
                    : "No showcase has been prepared."}
            </p>
          )}
          {!!data.reports.length && (
            <>
              <div className="showcase-routes" aria-label="Guided cases">
                {demoCases.map((item, caseIndex) => {
                  const reportIndex = data.reports.findIndex(
                    (candidate) =>
                      candidate.report.arguments.match_id === item.matchId &&
                      candidate.report.arguments.intent === item.intent,
                  );
                  return (
                    <button
                      type="button"
                      key={`${item.matchId}-${item.intent}`}
                      disabled={reportIndex < 0}
                      className={`showcase-route ${activeCase === caseIndex ? "is-active" : ""}`}
                      aria-pressed={activeCase === caseIndex}
                      onClick={() => selectReport(reportIndex)}
                    >
                      <span className="showcase-route-number">
                        {String(caseIndex + 1).padStart(2, "0")}
                      </span>
                      <strong>{item.title}</strong>
                      <small>{label(item.matchId)}</small>
                    </button>
                  );
                })}
              </div>
              <p className="showcase-selection-note">
                These three cases illustrate different metrics. They were chosen
                for teaching, not as a representative performance sample.
              </p>
              <label className="showcase-archive-select">
                Explore all prepared reports
                <select
                  value={selected}
                  onChange={(e) => selectReport(Number(e.target.value))}
                >
                  {data.reports.map((e, i) => (
                    <option key={e.sha256} value={i}>
                      {label(e.report.arguments.match_id)} ·{" "}
                      {intents[e.report.arguments.intent]}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {entry && (
            <article className="showcase-report">
              {guided && (
                <div className="showcase-question">
                  <span className="eyebrow">01 / THE QUESTION</span>
                  <h3>{guided.question}</h3>
                  <p>{guided.reading}</p>
                </div>
              )}
              <span className="eyebrow">02 / WHAT THE DATA SAYS</span>
              <h3>
                {label(entry.report.arguments.match_id)} ·{" "}
                {intents[entry.report.arguments.intent]}
              </h3>
              <p className="showcase-review-status">
                {entry.publication_label}
              </p>
              <button
                type="button"
                onClick={() => onMatch(entry.report.arguments.match_id)}
              >
                Open this match
              </button>
              {measuredClaims.slice(0, 1).map(claimEvidence)}
              {measuredClaims.length > 1 && (
                <details className="showcase-more">
                  <summary>
                    {measuredClaims.length - 1} supporting measurements
                  </summary>
                  {measuredClaims
                    .slice(1)
                    .map((claim, index) => claimEvidence(claim, index + 1))}
                </details>
              )}
              <div className="showcase-limit">
                <span className="eyebrow">04 / THE LIMIT</span>
                {entry.report.claims
                  .filter((claim) => claim.kind === "limitation")
                  .map((claim, i) => (
                    <p key={i}>{claim.text}</p>
                  ))}
              </div>
              <details>
                <summary>Report provenance and limitations</summary>
                <p>
                  Prepared {entry.report.generated_at}.{" "}
                  {entry.report.attribution}.
                </p>
                <p className="styles-event-id">
                  Review fingerprint: {entry.sha256}
                </p>
                <ul>
                  {entry.report.qualifications.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </details>
            </article>
          )}
          {evidenceId && (
            <aside aria-label="Cached report evidence" aria-live="polite">
              <h3>Source evidence</h3>
              <button type="button" onClick={() => setEvidenceId("")}>
                Close source evidence
              </button>
              {!evidence ? (
                <p>Loading evidence…</p>
              ) : (
                <>
                  <p>
                    {evidence.definition} · {evidence.total} source events
                  </p>
                  <ol start={offset + 1}>
                    {evidence.references.map((r) => (
                      <li key={r.event_id}>
                        <a href={r.source_url} target="_blank" rel="noreferrer">
                          {r.timestamp} · {r.player_name ?? "Team event"}
                        </a>
                        <small className="styles-event-id">{r.event_id}</small>
                      </li>
                    ))}
                  </ol>
                  <button
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 20))}
                  >
                    Previous evidence
                  </button>
                  <button
                    disabled={offset + 20 >= evidence.total}
                    onClick={() => setOffset(offset + 20)}
                  >
                    Next evidence
                  </button>
                </>
              )}
            </aside>
          )}
        </>
      )}
    </section>
  );
}
