import { useEffect, useRef, useState } from "react";
import { get, type MatchCard } from "./api";
import type { components } from "./api.generated";

type Response = components["schemas"]["ThirdPassResponse"];
type Sample = components["schemas"]["ThirdPassPrediction"];

export function ThirdPassForecasts({ match }: { match: MatchCard }) {
  const [team, setTeam] = useState(match.home.id);
  const [period, setPeriod] = useState(1);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Response | null>(null);
  const [selected, setSelected] = useState<Sample | null>(null);
  const [error, setError] = useState("");
  const evidenceRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selected) evidenceRef.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setSelected(null);
    setError("");
    get<Response>(
      `/matches/${match.id}/third-pass?team_id=${team}&period=${period}&offset=${offset}`,
      controller.signal,
    )
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [match.id, team, period, offset]);
  return (
    <section
      className="panel experiment-card"
      aria-labelledby="third-pass-title"
    >
      <span className="eyebrow">PREFIX PREDICTION / AFTER THREE PASSES</span>
      <h2 id="third-pass-title">Will this episode produce a shot?</h2>
      <p>
        Stored predictions use only information available at the third completed
        pass. The observed outcome is shown separately.
      </p>
      <div className="filter-row">
        <label>
          Prediction team{" "}
          <select
            value={team}
            onChange={(e) => {
              setTeam(Number(e.target.value));
              setOffset(0);
            }}
          >
            <option value={match.home.id}>{match.home.name}</option>
            <option value={match.away.id}>{match.away.name}</option>
          </select>
        </label>
        <label>
          Prediction period{" "}
          <select
            value={period}
            onChange={(e) => {
              setPeriod(Number(e.target.value));
              setOffset(0);
            }}
          >
            <option value={1}>First half</option>
            <option value={2}>Second half</option>
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading stored predictions…</p>}
      {data?.status === "unavailable" && (
        <p>No evaluated third-pass predictions are available for this match.</p>
      )}
      {data?.status === "ready" && (
        <>
          <p className="experiment-note">{data.warning}</p>
          <p>
            {data.total} eligible episodes · {data.model?.family} ·{" "}
            {data.model?.model_version}
          </p>
          <div className="forecast-list">
            {data.samples.map((sample) => (
              <button
                className="forecast-item"
                key={sample.sample_id}
                onClick={() => setSelected(sample)}
                aria-pressed={selected?.sample_id === sample.sample_id}
              >
                <span>
                  Period {sample.period} ·{" "}
                  {(sample.cutoff_ms / 60000).toFixed(2)} min
                </span>
                <strong>
                  {(sample.probability * 100).toFixed(1)}% shot probability
                </strong>
                <span>
                  Observed:{" "}
                  {sample.observed_later_shot ? "later shot" : "no later shot"}
                </span>
              </button>
            ))}
          </div>
          <div className="filter-row">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous predictions
            </button>
            <button
              disabled={offset + 25 >= data.total}
              onClick={() => setOffset(offset + 25)}
            >
              Next predictions
            </button>
          </div>
          {selected && (
            <aside
              ref={evidenceRef}
              className="experiment-note"
              aria-label="Third-pass prediction evidence"
            >
              <h3>Prediction evidence</h3>
              <dl className="provenance-list">
                <dt>Sample</dt>
                <dd>{selected.sample_id}</dd>
                <dt>Cutoff event</dt>
                <dd>{selected.cutoff_event_id}</dd>
                <dt>Source start time</dt>
                <dd>
                  Period {selected.period} · {selected.timestamp}
                </dd>
                <dt>Completion cutoff</dt>
                <dd>{selected.cutoff_ms} period-local ms</dd>
                <dt>Split</dt>
                <dd>{selected.split}</dd>
                <dt>Artifact SHA-256</dt>
                <dd>{data.model?.artifact_hash}</dd>
                <dt>Run</dt>
                <dd>{data.model?.run_id}</dd>
                <dt>Source commit</dt>
                <dd>{data.source_commit}</dd>
              </dl>
              <p>
                Only the source prefix ending at this pass enters the
                prediction. Its endpoint and recipient are known; subsequent
                events supply the retrospective outcome only.
              </p>
              <a
                href={`https://github.com/hudl/open-data/blob/${data.source_commit}/data/events/${match.id}.json`}
                target="_blank"
                rel="noreferrer"
              >
                Inspect the pinned StatsBomb source
              </a>
            </aside>
          )}
        </>
      )}
    </section>
  );
}
