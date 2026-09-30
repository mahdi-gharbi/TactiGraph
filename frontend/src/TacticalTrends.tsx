import { useEffect, useState } from "react";
import { get } from "./api";
import type { components } from "./api.generated";

type Trends = components["schemas"]["TrendsResponse"];

export function TacticalTrends({
  matchId,
  teamId,
  period,
  inspect,
}: {
  matchId: number;
  teamId: number;
  period: number;
  inspect: (id: string) => void;
}) {
  const [data, setData] = useState<Trends | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setError("");
    setSelected(0);
    get<Trends>(
      `/matches/${matchId}/trends?team_id=${teamId}&period=${period}`,
      c.signal,
    )
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [matchId, teamId, period]);
  if (!data)
    return (
      <p role={error ? "alert" : "status"}>
        {error || "Loading five-minute trends…"}
      </p>
    );
  const point = data.points[selected];
  const offset = period === 2 ? 45 : 0;
  return (
    <section className="tactical-trends" aria-label="Five-minute trends">
      <h3>Five-minute trends, kept separate.</h3>
      <p className="tactical-note">
        One point per minute; the final point includes recorded stoppage time.
        Each point sums the preceding five minutes within this half.
      </p>
      <div className="network-grid">
        {(["xg", "movement_xt"] as const).map((metric) => {
          const values = data.points
            .map((p) => p[metric])
            .filter((v): v is number => v !== null);
          const low = Math.min(0, ...values);
          const high = Math.max(0.001, ...values);
          const span = high - low;
          const x = (i: number) =>
            42 +
            (388 * data.points[i].end_ms) /
              Math.max(1, data.points.at(-1)!.end_ms);
          const y = (v: number) => 120 - (95 * (v - low)) / span;
          let path = "";
          let previous = false;
          data.points.forEach((p, i) => {
            const v = p[metric];
            if (v === null) {
              previous = false;
              return;
            }
            path += `${previous ? "L" : "M"}${x(i)} ${y(v)} `;
            previous = true;
          });
          return (
            <div key={metric}>
              <h4>{metric === "xg" ? "Model xG" : "Signed movement xT"}</h4>
              <svg
                viewBox="0 0 450 150"
                role="img"
                aria-label={`${metric === "xg" ? "xG" : "Signed xT"} trailing five-minute curve`}
                style={{ width: "100%" }}
              >
                <path
                  d={`M42 ${y(0)}H430`}
                  stroke="#b6c4af"
                  strokeDasharray="3 3"
                />
                <text x="2" y="28" fontSize="10" fill="#596c51">
                  {high.toFixed(3)}
                </text>
                <text x="2" y="123" fontSize="10" fill="#596c51">
                  {low.toFixed(3)}
                </text>
                <path
                  d={path}
                  fill="none"
                  stroke={metric === "xg" ? "#33674d" : "#a46330"}
                  strokeWidth="2"
                />
                {point && point[metric] !== null && (
                  <circle
                    cx={x(selected)}
                    cy={y(point[metric])}
                    r="4"
                    fill="#253d2c"
                  />
                )}
                <text x="42" y="145" fontSize="10">
                  {offset} min
                </text>
                <text x="395" y="145" fontSize="10">
                  {(offset + (data.points.at(-1)?.end_ms ?? 0) / 60000).toFixed(
                    1,
                  )}
                </text>
                {!values.length && (
                  <text x="160" y="70" fontSize="12">
                    Model unavailable
                  </text>
                )}
              </svg>
            </div>
          );
        })}
      </div>
      {point && (
        <div className="trend-inspector">
          <label>
            Trailing window ending
            <select
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {data.points.map((p, i) => (
                <option value={i} key={p.end_ms}>
                  {(offset + p.end_ms / 60000).toFixed(1)} min
                </option>
              ))}
            </select>
          </label>
          <p>
            {(offset + point.start_ms / 60000).toFixed(1)}–
            {(offset + point.end_ms / 60000).toFixed(1)} min · xG{" "}
            {point.xg?.toFixed(3) ?? "unavailable"} ({point.predicted_shots}/
            {point.shots} shots) · signed xT{" "}
            {point.movement_xt?.toFixed(3) ?? "unavailable"} (
            {point.valued_actions}/{point.eligible_actions} actions)
          </p>
          <button onClick={() => inspect(point.xg_evidence_id)}>
            Inspect curve xG
          </button>{" "}
          <button onClick={() => inspect(point.xt_evidence_id)}>
            Inspect curve xT
          </button>
        </div>
      )}
      <details className="tactical-quality">
        <summary>Candidate shifts & key events</summary>
        <p>
          Up to three largest changes between adjacent complete five-minute
          final-third-entry rates. These are descriptive candidates, not causes
          or significance tests.
        </p>
        {data.candidate_shifts.length === 0 && (
          <p>No nonzero adjacent-window change.</p>
        )}
        {data.candidate_shifts.map((s) => (
          <p key={s.boundary_ms}>
            <strong>
              Candidate shift · {offset + s.boundary_ms / 60000} min
            </strong>
            : {s.before_count} → {s.after_count} entries;{" "}
            {s.rate_difference > 0 ? "+" : ""}
            {s.rate_difference.toFixed(2)} entries/min.{" "}
            <button onClick={() => inspect(s.before_evidence_id)}>
              Before shift evidence
            </button>{" "}
            <button onClick={() => inspect(s.after_evidence_id)}>
              After shift evidence
            </button>
          </p>
        ))}
        <ul>
          {data.key_events.map((e) => (
            <li key={e.event_id}>
              <a href={e.source_url} target="_blank" rel="noreferrer">
                P{e.period} {e.timestamp} · {e.outcome} · {e.team_name} ·{" "}
                {e.player_name}
              </a>
              <small className="tactical-code"> · {e.event_id}</small>
            </li>
          ))}
        </ul>
        {data.warnings.map((w) => (
          <p className="tactical-note" key={w}>
            {w}
          </p>
        ))}
      </details>
    </section>
  );
}
