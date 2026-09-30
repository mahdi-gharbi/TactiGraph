import { useEffect, useState } from "react";
import { get } from "./api";
import type { components } from "./api.generated";

type Response = components["schemas"]["XTResponse"];
const label: Record<string, string> = {
  xt: "Turnover-aware xT",
  global: "Global episode rate",
  no_transition: "Zone, no transitions",
};
const interval = (v: number[]) => v.map((n) => n.toFixed(6)).join(" to ");

export function XTExperiments() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [zone, setZone] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    get<Response>("/experiments/xt", c.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  const r = data?.report;
  if (!r)
    return (
      <section className="panel experiment-card">
        <h2>Expected threat</h2>
        <p>
          {error ||
            (data
              ? "No evaluated xT release is available."
              : "Loading xT evaluation…")}
        </p>
      </section>
    );
  const [width, height] = r.model.grid;
  const max = Math.max(...r.model.values);
  return (
    <section
      className="panel experiment-card xt-experiment"
      aria-labelledby="xt-title"
    >
      <span className="eyebrow">EXPERIMENT 02 / EXPECTED THREAT</span>
      <h2 id="xt-title">Movement, with the cost of losing the ball.</h2>
      <p>
        Turnover-aware spatial Markov values under the observed historical
        action policy. Predicting a goal before the control episode ends,
        evaluated at its first eligible action.
      </p>
      <div className="experiment-grid">
        <div>
          <svg
            viewBox="-2 -2 124 88"
            role="group"
            aria-label="Expected threat surface, attacking right"
            style={{ width: "100%" }}
          >
            {r.model.values.map((value, i) => (
              <rect
                key={i}
                x={((i % width) * 120) / width}
                y={(Math.floor(i / width) * 80) / height}
                width={120 / width}
                height={80 / height}
                fill={`hsl(142 30% ${94 - (64 * value) / max}%)`}
                stroke={zone === i ? "#ba7838" : "#dbe3d6"}
                strokeWidth={zone === i ? 1 : 0.2}
                tabIndex={0}
                role="button"
                aria-label={`Zone ${i + 1}, value ${value.toFixed(4)}`}
                onClick={() => setZone(i)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setZone(i);
                  }
                }}
              >
                <title>
                  Zone {i + 1}: {value.toFixed(5)} · {r.model.action_counts[i]}{" "}
                  fitting actions
                </title>
              </rect>
            ))}
            <g
              fill="none"
              stroke="#ffffff99"
              strokeWidth=".4"
              pointerEvents="none"
            >
              <path d="M60 0V80 M0 18H18V62H0 M120 18H102V62H120" />
              <circle cx="60" cy="40" r="10" />
            </g>
            <text x="60" y="85" textAnchor="middle" fontSize="3" fill="#51654e">
              DARKER = HIGHER VALUE · ATTACKING RIGHT →
            </text>
          </svg>
          <p>
            Zone {zone + 1}: <strong>{r.model.values[zone].toFixed(5)}</strong>{" "}
            · {r.model.action_counts[zone].toLocaleString()} fitting actions ·{" "}
            {r.model.shot_counts[zone]} shots · {r.model.goal_counts[zone]}{" "}
            goals.
          </p>
        </div>
        <div>
          <h3>
            {width}×{height} grid · {r.model.iterations} iterations
          </h3>
          <p>
            {r.model.episodes.toLocaleString()} fitting episodes. Exactly{" "}
            {r.model.terminal_count.toLocaleString()} terminal actions. Maximum
            final value change: {r.model.maximum_delta.toExponential(3)}.
          </p>
          <p>
            {r.test.matches} test matches ·{" "}
            {r.test.eligible_episodes.toLocaleString()} eligible episodes ·{" "}
            {r.results.xt.goals} goals.
          </p>
          <p>
            1,000 paired match-bootstrap draws. Lower Brier and log loss are
            better. These are episode probabilities, not shot xG.
          </p>
        </div>
      </div>
      <div className="experiment-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Brier</th>
              <th>95% interval</th>
              <th>Log loss</th>
              <th>95% interval</th>
            </tr>
          </thead>
          <tbody>
            {["global", "no_transition", "xt"].map((name) => (
              <tr key={name}>
                <td>{label[name]}</td>
                <td>{r.results[name].brier.toFixed(6)}</td>
                <td>{interval(r.results[name].intervals.brier)}</td>
                <td>{r.results[name].log_loss.toFixed(6)}</td>
                <td>{interval(r.results[name].intervals.log_loss)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>
          Development selection, exclusions & paired differences
        </summary>
        {r.development.candidates.map((c) => (
          <p key={c.grid.join("x")}>
            Grid {c.grid.join("×")}: tuning Brier {c.scores.xt.brier.toFixed(6)}
            ; log loss {c.scores.xt.log_loss.toFixed(6)}.
          </p>
        ))}
        <p>
          Minimum tuning Brier selects the grid; final fitting uses training
          plus tuning. Calibration matches are unused.
        </p>
        {(
          [
            ["Training", r.development.train],
            ["Tuning", r.development.tuning],
            ["Test", r.test],
          ] as const
        ).map(([name, coverage]) => (
          <p key={name}>
            {name}: {coverage.eligible_episodes.toLocaleString()} /{" "}
            {coverage.source_episodes.toLocaleString()} episodes. Exclusions:{" "}
            {Object.entries(coverage.excluded_episodes)
              .map(([reason, count]) => `${count} ${reason.toLowerCase()}`)
              .join("; ") || "none"}
            .
          </p>
        ))}
        {Object.entries(r.paired_differences).map(([baseline, metrics]) => (
          <p key={baseline}>
            xT minus {label[baseline]}: Brier 95% difference{" "}
            {interval(metrics.brier)}; log-loss difference{" "}
            {interval(metrics.log_loss)}.
          </p>
        ))}
      </details>
      <p className="experiment-note">{r.interpretation}</p>
      <p className="experiment-note">{r.test_disclosure}</p>
      <dl className="provenance-list">
        <dt>Run</dt>
        <dd>{r.lock.run_id}</dd>
        <dt>Artifact SHA-256</dt>
        <dd>{r.lock.artifact_hash}</dd>
        <dt>Split manifest</dt>
        <dd>{r.lock.split_hash}</dd>
        <dt>Evaluated</dt>
        <dd>{r.generated_at}</dd>
      </dl>
      <p className="experiment-note">
        Reproduce: <code>tactigraph xt develop</code> →{" "}
        <code>tactigraph xt evaluate</code> → <code>tactigraph xt publish</code>
        .{" "}
        <a href={r.source_url} target="_blank" rel="noreferrer">
          {r.attribution}
        </a>
        .
      </p>
    </section>
  );
}
