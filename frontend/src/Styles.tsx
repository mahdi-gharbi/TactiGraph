import { useEffect, useState } from "react";
import { get, type MatchCard } from "./api";
import type { components } from "./api.generated";

type Response = components["schemas"]["StylesResponse"];
type Evidence = components["schemas"]["TacticalEvidence"];
const range = (values: number[]) =>
  `${Math.min(...values).toFixed(3)}–${Math.max(...values).toFixed(3)}`;

export function Styles({ match }: { match?: MatchCard }) {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [selected, setSelected] = useState("");
  const [evidenceError, setEvidenceError] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setError("");
    setSelected("");
    setEvidence(null);
    get<Response>(
      match ? `/matches/${match.id}/styles` : "/experiments/styles",
      c.signal,
    )
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [match?.id]);
  useEffect(() => {
    const c = new AbortController();
    setEvidence(null);
    setEvidenceError("");
    if (selected)
      get<Evidence>(
        `/tactical-evidence/${selected}?offset=${offset}&limit=20`,
        c.signal,
      )
        .then(setEvidence)
        .catch((e) => {
          if (e.name !== "AbortError") setEvidenceError(e.message);
        });
    return () => c.abort();
  }, [selected, offset]);
  const r = data?.report;
  return (
    <section className="panel methodology" aria-label="Passing styles">
      <span className="eyebrow">RESEARCH / 15-MINUTE PASSING STYLES</span>
      <h2>Measured patterns of play</h2>
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p role="status">Loading styles…</p>
      ) : !r ? (
        <p>
          {data.status === "stale"
            ? "Source data changed. Style profiles need rebuilding."
            : "Style discovery has not been published yet."}
        </p>
      ) : (
        <>
          <p>{r.limitation}</p>
          <p>
            Training: {r.training_windows} windows from {r.training_matches}{" "}
            matches. PCA retains{" "}
            {(
              100 * r.pca_explained_variance.reduce((a, b) => a + b, 0)
            ).toFixed(1)}
            % of variance.
          </p>
          <p>
            Training silhouette: {r.training_silhouette.toFixed(3)}. Seed
            stability (ARI): {range(r.seed_ari)}. Match-bootstrap stability
            (ARI): {range(r.match_bootstrap_ari)}. Higher ARI means more
            consistent assignments; it does not establish tactical validity.
          </p>
          <div className="styles-grid">
            {r.clusters.map((c) => (
              <article key={c.cluster}>
                <h3>
                  Profile {c.cluster + 1}: {c.label}
                </h3>
                <p>{c.training_windows} training windows</p>
                <dl>
                  {Object.entries(c.means).map(([name, value]) => (
                    <div key={name}>
                      <dt>{name.replaceAll("_", " ")}</dt>
                      <dd>{value.toFixed(3)}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
          {match && (
            <>
              <h3>
                {match.home.name} – {match.away.name}
              </h3>
              {!data.windows.length && (
                <p>No eligible complete windows for this match.</p>
              )}
              <div className="styles-grid">
                {data.windows.map((w) => (
                  <article key={w.evidence_id}>
                    <h4>
                      {w.team_id === match.home.id
                        ? match.home.name
                        : match.away.name}{" "}
                      · H{w.period} · {w.start_ms / 60000}–{w.end_ms / 60000}{" "}
                      min
                    </h4>
                    <p>
                      Profile {w.cluster + 1} ·{" "}
                      {w.partition === "train"
                        ? "Training sample"
                        : "Later-match projection"}
                    </p>
                    <p>
                      {w.pass_count} attempts · {w.spatial_pass_count} with
                      valid geometry
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(w.evidence_id);
                        setOffset(0);
                      }}
                      aria-pressed={selected === w.evidence_id}
                    >
                      Inspect source passes
                    </button>
                  </article>
                ))}
              </div>
              {selected && (
                <div aria-live="polite">
                  <h3>Source evidence</h3>
                  <button type="button" onClick={() => setSelected("")}>
                    Close evidence
                  </button>
                  {evidenceError ? (
                    <p role="alert">{evidenceError}</p>
                  ) : !evidence ? (
                    <p>Loading evidence…</p>
                  ) : (
                    <>
                      <p>
                        {evidence.definition} · {evidence.total} source events
                      </p>
                      <ol start={offset + 1}>
                        {evidence.references.map((ref) => (
                          <li key={ref.event_id}>
                            <a
                              href={ref.source_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {ref.timestamp} ·{" "}
                              {ref.player_name ?? "Unknown player"} ·{" "}
                              {ref.outcome ?? "Pass"}
                            </a>
                            <small className="styles-event-id">
                              {ref.event_id}
                            </small>
                          </li>
                        ))}
                      </ol>
                      <button
                        type="button"
                        disabled={offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - 20))}
                      >
                        Previous passes
                      </button>
                      <button
                        type="button"
                        disabled={
                          offset + evidence.references.length >= evidence.total
                        }
                        onClick={() => setOffset(offset + 20)}
                      >
                        Next passes
                      </button>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
