import { useEffect, useState } from "react";
import {
  FlaskConical,
  LockKeyhole,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import { get, selectedLeague } from "./api";
import type { components } from "./api.generated";
import "./experiments.css";
import { XTExperiments } from "./XTExperiments";
import { GraphExperiments } from "./GraphExperiments";
import { AnalystExperiments } from "./AnalystExperiments";
import { Styles } from "./Styles";

type Response = components["schemas"]["ExperimentsResponse"];
const names: Record<string, string> = {
  prevalence: "Prevalence baseline",
  logistic: "Logistic regression",
  lightgbm: "LightGBM",
};
const n = (v: number | null | undefined, digits = 4) =>
  v == null ? "—" : v.toFixed(digits);
const interval = (v: number[]) => `${n(v[0])} to ${n(v[1])}`;

export function Experiments() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState("");
  const [family, setFamily] = useState("logistic");
  useEffect(() => {
    const c = new AbortController();
    get<Response>("/experiments", c.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, []);
  if (error)
    return (
      <div className="error-banner" role="alert">
        Experiment report unavailable: {error}
      </div>
    );
  if (!data)
    return <div className="empty-state">Loading the experiment registry…</div>;
  const r = data.report;
  if (!r)
    return (
      <section className="panel methodology">
        <FlaskConical />
        <h2>No published xG result</h2>
        <p>
          {data.status === "unavailable"
            ? "Stored predictions are stale after a data change. A reviewed release is required."
            : "No evaluated xG release has been published. No performance metrics are claimed."}
        </p>
      </section>
    );
  const chosen = r.metrics[r.serving];
  const calibration = r.metrics[family];
  const importanceMax = Math.max(
    ...r.permutation_importance.map((i) => Math.abs(i.mean_log_loss_increase)),
    0.001,
  );
  return (
    <div className="experiments-page">
      <Styles />
      <section className="panel experiment-hero">
        <div>
          <span className="eyebrow">EXPERIMENT 01 / EXPECTED GOALS</span>
          <h2>Shot model evaluation</h2>
          <p>
            Logistic regression and LightGBM evaluated on later matches. The
            serving model was selected before test results were inspected.
          </p>
        </div>
        <div className="experiment-selection">
          <span className="status-pill">
            <LockKeyhole size={13} /> Locked serving model
          </span>
          <strong>{names[r.serving]}</strong>
          <span>{r.version} · non-penalty shot probability</span>
        </div>
      </section>
      <div className="stats-grid">
        {[
          [
            "Held-out matches",
            r.test_matches.toLocaleString(),
            "Chronological test partition",
          ],
          [
            "Non-penalty shots",
            r.test_non_penalty_shots.toLocaleString(),
            `${chosen.goals} observed goals`,
          ],
          ["Log loss", n(chosen.log_loss), "Lower is better"],
          ["Brier score", n(chosen.brier), "Lower is better"],
        ].map(([label, value, note]) => (
          <article className="stat-card" key={label}>
            <span>
              {label}
              <FlaskConical size={15} />
            </span>
            <strong>{value}</strong>
            <p>{note}</p>
          </article>
        ))}
      </div>
      <section className="panel">
        <header className="panel-header">
          <div>
            <h2>What survived the comparison</h2>
            <p>
              Same eligible shots. Paired resampling of whole matches. 95%
              intervals, 1,000 replicates.
            </p>
          </div>
          <span className="neutral-pill">Final test · not tuning</span>
        </header>
        <div className="dataset-table-scroll">
          <table className="experiment-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Log loss / 95% CI</th>
                <th>Brier / 95% CI</th>
                <th>ROC-AUC</th>
                <th>PR-AUC¹</th>
              </tr>
            </thead>
            <tbody>
              {["prevalence", "logistic", "lightgbm"].map((key) => (
                <tr
                  key={key}
                  className={key === r.serving ? "serving-row" : ""}
                >
                  <td>
                    <strong>{names[key]}</strong>
                    {key === r.serving && (
                      <small>Serving · selected on tuning</small>
                    )}
                  </td>
                  <td>
                    {n(r.metrics[key].log_loss)}
                    <small>{interval(r.metrics[key].intervals.log_loss)}</small>
                  </td>
                  <td>
                    {n(r.metrics[key].brier)}
                    <small>{interval(r.metrics[key].intervals.brier)}</small>
                  </td>
                  <td>{n(r.metrics[key].roc_auc)}</td>
                  <td>{n(r.metrics[key].pr_auc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="experiment-note">
          ¹ Average precision. All metrics exclude penalties. The prevalence
          baseline is fitted on train + tuning.
        </p>
        <div className="experiment-decision">
          <ShieldCheck size={20} />
          <div>
            <strong>The simpler model earned its place.</strong>
            <p>
              LightGBM’s tuning log-loss difference versus logistic had a 95%
              interval of{" "}
              {interval(r.development.tuning_paired_difference.log_loss)}. It
              crossed zero, so the prespecified rule retained logistic
              regression.
            </p>
            <p>
              On the final test, the paired difference is{" "}
              {interval(r.paired_lightgbm_minus_logistic.log_loss)}. Negative
              values favour LightGBM. This result does not change the locked
              selection.
            </p>
          </div>
        </div>
      </section>
      <div className="experiment-grid">
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Does 20% mean 20%?</h2>
              <p>
                Reliability on the chronological test
                {selectedLeague === "premier-league"
                  ? " within 2015/16."
                  : " in the later WSL season."}
              </p>
            </div>
          </header>
          <label className="experiment-select">
            Calibration view
            <select
              aria-label="Calibration model"
              value={family}
              onChange={(e) => setFamily(e.target.value)}
            >
              <option value="logistic">Logistic regression</option>
              <option value="lightgbm">LightGBM</option>
            </select>
          </label>
          <svg
            viewBox="0 0 440 315"
            className="reliability-chart"
            role="img"
            aria-label={`Reliability diagram for ${names[family]}`}
          >
            {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => (
              <g key={t}>
                <path
                  d={`M48 ${265 - t * 220}H405 M${48 + t * 350} 45V265`}
                  stroke="#e0e7dc"
                />
                <text x="39" y={269 - t * 220} textAnchor="end">
                  {n(t, 1)}
                </text>
                <text x={48 + t * 350} y="284" textAnchor="middle">
                  {n(t, 1)}
                </text>
              </g>
            ))}
            <path d="M48 265L398 45" stroke="#9aa994" strokeDasharray="5 5" />
            <polyline
              points={calibration.reliability
                .map(
                  (b) => `${48 + b.predicted * 350},${265 - b.observed * 220}`,
                )
                .join(" ")}
              fill="none"
              stroke="#38654b"
              strokeWidth="2"
            />
            {calibration.reliability.map((b) => (
              <circle
                key={b.lower}
                cx={48 + b.predicted * 350}
                cy={265 - b.observed * 220}
                r={3 + Math.sqrt(b.n / r.test_non_penalty_shots) * 10}
                fill="#38654b"
                stroke="white"
              >
                <title>
                  {b.n} shots: predicted {n(b.predicted, 3)}, observed{" "}
                  {n(b.observed, 3)}
                </title>
              </circle>
            ))}
            <text x="225" y="308" textAnchor="middle">
              Mean predicted probability
            </text>
            <text
              x="12"
              y="155"
              transform="rotate(-90 12 155)"
              textAnchor="middle"
            >
              Observed goal rate
            </text>
          </svg>
          <div className="calibration-values">
            <span>
              Intercept{" "}
              <strong>{n(calibration.calibration?.intercept, 3)}</strong>
              <small>Ideal: 0</small>
            </span>
            <span>
              Slope <strong>{n(calibration.calibration?.slope, 3)}</strong>
              <small>Ideal: 1</small>
            </span>
          </div>
          <details className="experiment-details">
            <summary>Inspect bin counts and values</summary>
            <div className="dataset-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Probability bin</th>
                    <th>Shots</th>
                    <th>Predicted</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {calibration.reliability.map((b) => (
                    <tr key={b.lower}>
                      <td>
                        {n(b.lower, 1)}–{n(b.upper, 1)}
                      </td>
                      <td>{b.n}</td>
                      <td>{n(b.predicted, 3)}</td>
                      <td>{n(b.observed, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Calibration was tested, too.</h2>
              <p>A development decision, before the final evaluation.</p>
            </div>
          </header>
          {Object.entries(r.development.calibration_decisions).map(
            ([key, d]) => (
              <div className="calibration-decision" key={key}>
                <h3>{names[key]}</h3>
                <span className="neutral-pill">
                  {d.retain_sigmoid
                    ? "Sigmoid retained"
                    : "Sigmoid not retained"}
                </span>
                <div>
                  <span>
                    Tuning log loss, raw <strong>{n(d.raw.log_loss)}</strong>
                  </span>
                  <ArrowRight size={14} />
                  <span>
                    With sigmoid <strong>{n(d.sigmoid.log_loss)}</strong>
                  </span>
                </div>
              </div>
            ),
          )}
          <p className="experiment-note">
            Sigmoid candidates used match-grouped out-of-fold predictions from
            training. Retention required at least 0.001 better tuning log loss
            and no worse Brier score. A retained sigmoid would be refitted only
            on the separate calibration partition.
          </p>
          <div className="penalty-box">
            <span className="eyebrow">PENALTIES / SEPARATE ESTIMATE</span>
            <strong>{n(r.penalties.probability, 3)} xG</strong>
            <p>
              Beta(1,1) smoothed conversion rate from{" "}
              {r.development.penalty.fitting_n} fitting penalties. Final test:{" "}
              {r.penalties.test_metrics?.n} penalties; Brier{" "}
              {n(r.penalties.test_metrics?.brier)}. Not included in the
              non-penalty comparison.
            </p>
          </div>
        </section>
      </div>
      <section className="panel">
        <header className="panel-header">
          <div>
            <h2>Which inputs matter to this model?</h2>
            <p>
              Held-out permutation importance · {names[r.serving]} · five
              repeats per feature.
            </p>
          </div>
        </header>
        <div className="importance-list">
          {r.permutation_importance.slice(0, 8).map((i) => (
            <div key={i.feature}>
              <span>{i.feature.replaceAll("_", " ")}</span>
              <div className="importance-track">
                <i
                  style={{
                    width: `${(Math.max(0, i.mean_log_loss_increase) / importanceMax) * 100}%`,
                  }}
                />
              </div>
              <strong>
                {n(i.mean_log_loss_increase)}
                <small>± {n(i.std)}</small>
              </strong>
            </div>
          ))}
        </div>
        <p className="experiment-note">
          Increase in log loss when one feature is shuffled. Correlated features
          can share importance. This does not establish causality.
        </p>
        <details className="experiment-details">
          <summary>Inspect standardized logistic coefficients</summary>
          <div className="dataset-table-scroll coefficient-table">
            <table>
              <thead>
                <tr>
                  <th>Transformed feature</th>
                  <th>Coefficient</th>
                </tr>
              </thead>
              <tbody>
                {[...r.logistic_coefficients]
                  .sort(
                    (a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient),
                  )
                  .map((c) => (
                    <tr key={c.feature}>
                      <td>{c.feature}</td>
                      <td>{n(c.coefficient)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <section className="panel">
        <header className="panel-header">
          <div>
            <h2>Beyond the average</h2>
            <p>
              Final-test slices. Metrics withheld below 30 shots; small slices
              remain uncertain.
            </p>
          </div>
        </header>
        <div className="dataset-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Slice</th>
                <th>Shots</th>
                <th>Log loss</th>
                <th>Brier</th>
                <th>ROC-AUC</th>
              </tr>
            </thead>
            <tbody>
              {r.slices.map((s) => (
                <tr key={`${s.field}-${s.value}`}>
                  <td>
                    {s.field.replaceAll("_", " ")} ·{" "}
                    {s.value === "281"
                      ? "2023/24"
                      : s.value === "27"
                        ? "2015/16"
                        : s.value}
                    {s.warning && <small>{s.warning}</small>}
                  </td>
                  <td>{s.n}</td>
                  <td>{n(s.metrics?.log_loss)}</td>
                  <td>{n(s.metrics?.brier)}</td>
                  <td>{n(s.metrics?.roc_auc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <header className="panel-header">
          <div>
            <h2>A harder check: held-out teams</h2>
            <p>
              Five deterministic team groups. Every fitting and calibration
              match involving the held-out group is removed.
            </p>
          </div>
        </header>
        <div className="dataset-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Group</th>
                <th>Fitting shots / matches</th>
                <th>Calibration shots</th>
                <th>Test shots</th>
                <th>Log loss</th>
                <th>Brier</th>
              </tr>
            </thead>
            <tbody>
              {r.team_stress.map((s) => (
                <tr key={s.group}>
                  <td>{s.group + 1}</td>
                  <td>
                    {s.fit_shots} / {s.fit_matches}
                  </td>
                  <td>{s.calibration_shots}</td>
                  <td>{s.test_shots}</td>
                  <td>{n(s.metrics?.log_loss)}</td>
                  <td>{n(s.metrics?.brier)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="experiment-note">
          Preprocessing and model fitting are repeated per fold. Primary
          experiment hyperparameters remain fixed; this is a stress test, not an
          independently retuned unseen-team benchmark.
        </p>
      </section>
      <section className="panel experiment-card">
        <span className="eyebrow">MODEL CARD / {r.version}</span>
        <h2>What these probabilities can tell you.</h2>
        <p>
          The probability that a non-penalty shot becomes a goal, using event
          information available at the shot. Historical player locations,
          defensive shape and goalkeeper response are not observed.
        </p>
        <ul>
          {r.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <p>
          Uncontrolled reference: StatsBomb xG log loss{" "}
          {n(r.reference.metrics?.log_loss)}, Brier{" "}
          {n(r.reference.metrics?.brier)} on {r.reference.metrics?.n} shots. Its
          training sample and information access are not controlled.
        </p>
        <div className="feature-tags">
          {r.feature_names.map((f) => (
            <span key={f}>{f.replaceAll("_", " ")}</span>
          ))}
        </div>
        <dl className="provenance-list">
          <dt>Run</dt>
          <dd>{r.lock.run_id}</dd>
          <dt>Artifact SHA-256</dt>
          <dd>{r.lock.artifact_hash}</dd>
          <dt>Split manifest</dt>
          <dd>{r.lock.split_hash}</dd>
          <dt>Frozen</dt>
          <dd>{r.lock.created_at}</dd>
          <dt>Evaluated</dt>
          <dd>{r.evaluated_at}</dd>
        </dl>
        <p className="experiment-note">
          Reproduce locally: <code>tactigraph xg develop</code> →{" "}
          <code>tactigraph xg evaluate</code> →{" "}
          <code>tactigraph xg publish</code>. Training never runs inside a web
          request.
        </p>
      </section>
      <XTExperiments />
      <GraphExperiments />
      <AnalystExperiments />
    </div>
  );
}
