import { useEffect, useState } from "react";
import { get } from "./api";
import type { components } from "./api.generated";

type Response = components["schemas"]["GraphResponse"];
const number = (v: number | null | undefined) =>
  v == null ? "—" : v.toFixed(4);
const interval = (v: number[]) => v.map(number).join(" to ");
const names: Record<string, string> = {
  prevalence: "Prevalence only",
  logistic: "Logistic regression",
  lightgbm: "LightGBM + graph summaries",
  gine: "Full GINE",
  no_message: "No message passing",
  episode_edges: "Current episode edges only",
  no_edge_time_space: "No edge timing or space",
  random_connectivity: "Randomized connectivity",
};

export function GraphExperiments() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    get<Response>("/experiments/graph", controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  const report = data?.report;
  return (
    <section className="panel experiment-card" aria-labelledby="graph-title">
      <span className="eyebrow">EXPERIMENT 03 / GRAPH LEARNING</span>
      <h2 id="graph-title">Does the passing graph add predictive value?</h2>
      <p>
        At the completion of the third pass in an eligible open-play episode,
        predict whether a shot occurs later in that episode. Historical on-ball
        observations are not tracking positions.
      </p>
      {!report ? (
        <p role="status">
          {error ||
            (data
              ? "Not evaluated. No graph model performance is claimed."
              : "Loading graph experiment…")}
        </p>
      ) : (
        <>
          <p className="experiment-note">
            <strong>
              {report.decision.justified
                ? "Graph contribution supported"
                : "Graph contribution not established"}
              .
            </strong>{" "}
            {report.decision.interpretation}
          </p>
          <p>
            {report.test.n.toLocaleString()} eligible episodes ·{" "}
            {report.test.positive_episodes.toLocaleString()} later shots ·{" "}
            {report.test.matches} final-test matches. Selected serving model:{" "}
            <strong>{names[report.serving] || report.serving}</strong>.
          </p>
          <div className="table-scroll">
            <table>
              <caption>
                Locked comparisons. Lower log loss and Brier are better; higher
                PR-AUC is better.
              </caption>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Log loss</th>
                  <th>95% match interval</th>
                  <th>Brier</th>
                  <th>PR-AUC</th>
                </tr>
              </thead>
              <tbody>
                {["prevalence", "logistic", "lightgbm"].map((name) => (
                  <tr key={name}>
                    <th scope="row">{names[name]}</th>
                    <td>{number(report.results[name].log_loss)}</td>
                    <td>{interval(report.results[name].intervals.log_loss)}</td>
                    <td>{number(report.results[name].brier)}</td>
                    <td>{number(report.results[name].pr_auc)}</td>
                  </tr>
                ))}
                {Object.entries(report.seed_aggregates).map(
                  ([name, result]) => (
                    <tr key={name}>
                      <th scope="row">{names[name]} · 3 seeds</th>
                      <td>{number(result.metrics.log_loss)}</td>
                      <td>{interval(result.intervals.log_loss)}</td>
                      <td>{number(result.metrics.brier)}</td>
                      <td>{number(result.metrics.pr_auc)}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          <p className="experiment-note">{report.seed_definition}</p>
          <details>
            <summary>Graph justification gates and paired differences</summary>
            <ul>
              {Object.entries(report.decision.gates).map(([key, passed]) => (
                <li key={key}>
                  {key.replaceAll("_", " ")}:{" "}
                  <strong>{passed ? "passed" : "not passed"}</strong>
                </li>
              ))}
            </ul>
            <p>
              GINE minus comparator log loss; an interval below zero favors
              GINE.
            </p>
            <ul>
              {Object.entries(report.decision.paired_differences).map(
                ([name, differences]) => (
                  <li key={name}>
                    {names[name]}: {interval(differences.log_loss)}
                  </li>
                ),
              )}
            </ul>
          </details>
          <details>
            <summary>
              Individual seeds, calibration and inference latency
            </summary>
            <p>
              {report.latency_definition} Calibration intercept and slope below
              are held-out diagnostics, not a calibration fitted for serving.
            </p>
            {Object.entries(report.results).map(([name, result]) => (
              <div key={name} className="experiment-note">
                <strong>{name}</strong> · log loss {number(result.log_loss)} ·
                raw log loss {number(result.uncalibrated?.log_loss)} · ROC-AUC{" "}
                {number(result.roc_auc)} · p95{" "}
                {number(result.prepared_inference_p95_ms)} ms · calibration
                intercept {number(result.calibration?.intercept)}, slope{" "}
                {number(result.calibration?.slope)}
                {result.calibration_reason && (
                  <p>{result.calibration_reason}</p>
                )}
                <ul>
                  {result.reliability.map((bin) => (
                    <li key={bin.lower}>
                      {bin.lower.toFixed(1)}–{bin.upper.toFixed(1)}: predicted{" "}
                      {number(bin.predicted)}, observed {number(bin.observed)},
                      n={bin.n}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </details>
          <details>
            <summary>
              Team-disjoint stress test and eligibility exclusions
            </summary>
            <p>
              Every fitting and calibration match involving a held-out team is
              removed. Primary hyperparameters remain fixed; this is a separate
              stress test.
            </p>
            {Object.entries(report.stress).map(([group, result]) => (
              <p key={group}>
                Group {group}: {result.n} episodes, {result.matches} test
                matches; fitting{" "}
                {result.development_counts.train +
                  result.development_counts.tuning}
                , calibration {result.development_counts.calibration}. GINE
                minus baseline log-loss interval:{" "}
                {result.n
                  ? interval(result.paired_difference.log_loss)
                  : "no eligible test samples"}
                .
              </p>
            ))}
            <ul>
              {Object.entries(report.test.exclusions).map(([reason, count]) => (
                <li key={reason}>
                  {reason.replaceAll("_", " ")}: {count.toLocaleString()}
                </li>
              ))}
            </ul>
          </details>
          <p className="experiment-note">{report.test_disclosure}</p>
          <dl className="provenance-list">
            <dt>Model version</dt>
            <dd>{report.version}</dd>
            <dt>Run</dt>
            <dd>{report.lock.run_id}</dd>
            <dt>Artifact SHA-256</dt>
            <dd>{report.lock.artifact_hash}</dd>
            <dt>Evaluated</dt>
            <dd>{report.generated_at}</dd>
          </dl>
          <p>
            {report.attribution}. Reproduce:{" "}
            <code>tactigraph graph develop</code> →{" "}
            <code>tactigraph graph evaluate</code> →{" "}
            <code>tactigraph graph publish</code>.
          </p>
        </>
      )}
    </section>
  );
}
