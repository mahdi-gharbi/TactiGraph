import { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  Database,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { get, selectedLeague } from "./api";
import type { components } from "./api.generated";
import "./dataset.css";

type Dataset = components["schemas"]["DatasetOverview"];
type Counts = components["schemas"]["NamedCount"];
const seasonNames: Record<number, string> = {
  27: "2015/16",
  4: "2018/19",
  42: "2019/20",
  90: "2020/21",
  281: "2023/24",
};
const format = (n: number) => n.toLocaleString("en-GB");

function Bars({ rows }: { rows: Counts[] }) {
  const maximum = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="eda-bars">
      {rows.map((r) => (
        <div className="eda-bar-row" key={r.name}>
          <span>{r.name}</span>
          <div className="eda-bar-track">
            <div style={{ width: `${(100 * r.count) / maximum}%` }} />
          </div>
          <strong>{format(r.count)}</strong>
        </div>
      ))}
    </div>
  );
}

export function DatasetOverview({ openLab }: { openLab: () => void }) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    get<Dataset>("/dataset", controller.signal)
      .then(setDataset)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  if (error)
    return (
      <div className="error-banner" role="alert">
        Dataset audit unavailable: {error}
      </div>
    );
  if (!dataset)
    return (
      <div className="empty-state">
        <LoaderCircle className="spin" /> Loading the dataset audit…
      </div>
    );
  const report = dataset.report;
  if (!report)
    return (
      <section className="panel methodology">
        <Database />
        <h2>The dataset is taking shape.</h2>
        <p>
          {format(dataset.ingested_matches)} matches currently imported. Run{" "}
          <code>
            {selectedLeague === "premier-league"
              ? "tactigraph --league premier-league audit"
              : "tactigraph audit"}
          </code>{" "}
          after ingestion to publish coverage and training-only exploratory
          analysis.
        </p>
      </section>
    );
  const eda = report.training_eda;
  const zoneMax = Math.max(1, ...eda.shot_zones.map((z) => z.count));
  const issues = report.quality_issues.reduce(
    (total, row) => total + row.count,
    0,
  );
  return (
    <div className="dataset-overview">
      <section className="dataset-hero panel">
        <div>
          <span className="eyebrow">
            DATA FOUNDATION /{" "}
            {selectedLeague === "premier-league" ? "PREMIER LEAGUE" : "WSL"}
          </span>
          <h2>
            {format(report.ready_matches)} matches from {report.seasons.length}{" "}
            {report.seasons.length === 1 ? "season" : "seasons"}
          </h2>
          <p>
            Verified source files, normalized events and a dated train/test
            split. Inspect coverage before interpreting model results.
          </p>
          <button className="primary-button" onClick={openLab}>
            Explore the match archive <ArrowRight size={16} />
          </button>
        </div>
        <div className="dataset-hero-number">
          <strong data-testid="dataset-match-count">
            {report.ready_matches}
            <span> / {report.expected_matches}</span>
          </strong>
          <span>ready / listed matches</span>
          <div className="status-pill">
            <ShieldCheck size={13} />{" "}
            {report.coverage_complete
              ? "Coverage & integrity checks passed"
              : "Coverage incomplete — inspect the audit"}
          </div>
        </div>
      </section>
      <div className="stats-grid dataset-stats">
        {[
          ["Source events", report.counts.events],
          ["Recorded shots", report.counts.shots],
          ["Control episodes", report.counts.control_episodes],
          ["Players", report.counts.players],
        ].map(([name, n]) => (
          <article className="stat-card" key={name}>
            <span>
              {name}
              <Database size={15} />
            </span>
            <strong>{format(Number(n))}</strong>
            <p>Observed corpus counts · not model metrics</p>
          </article>
        ))}
      </div>

      <section className="panel">
        <header className="panel-header">
          <div>
            <h2>
              <LockKeyhole size={17} /> Chronological evaluation split
            </h2>
            <p>
              Frozen match assignments. Whole dates stay together. No random
              event split.
            </p>
          </div>
          <span className="neutral-pill">Immutable manifest</span>
        </header>
        <div className="partition-grid">
          {report.partitions.map((p) => (
            <article
              className={`partition-card ${p.name === "test" ? "held-out" : ""}`}
              key={p.name}
            >
              <span>
                {p.name === "test" && <LockKeyhole size={12} />} {p.name}
              </span>
              <strong>
                {p.ingested}
                <small> / {p.expected}</small>
              </strong>
              <p>
                {selectedLeague === "premier-league"
                  ? "2015/16 · chronological dates"
                  : p.name === "train"
                    ? "2018/19 + 2019/20"
                    : p.name === "test"
                      ? "2023/24 · held out"
                      : p.name === "tuning"
                        ? "Earlier 2020/21 dates"
                        : "Later 2020/21 dates"}
              </p>
            </article>
          ))}
        </div>
        <div className="audit-hash">
          SHA-256 <code>{report.split_manifest_hash}</code>
        </div>
      </section>

      <section className="panel dataset-coverage">
        <header className="panel-header">
          <div>
            <h2>
              <ShieldCheck size={17} /> Coverage by season
            </h2>
            <p>
              File availability is not a claim that every historical season is
              complete.
            </p>
          </div>
          <span className="neutral-pill">No separate 360 coverage</span>
        </header>
        <div className="dataset-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Season</th>
                <th>Ready / listed</th>
                <th>Events</th>
                <th>Passes</th>
                <th>Shots</th>
              </tr>
            </thead>
            <tbody>
              {report.seasons.map((s) => (
                <tr key={s.season_id}>
                  <td>{seasonNames[s.season_id] ?? s.season_id}</td>
                  <td>
                    {s.ready} / {s.expected}
                  </td>
                  <td>{format(s.events)}</td>
                  <td>{format(s.passes)}</td>
                  <td>{format(s.shots)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="integrity-grid">
          {Object.entries(report.integrity_checks).map(([key, ok]) => (
            <span key={key} className={ok ? "check-passed" : "check-failed"}>
              {ok ? <Check size={14} /> : <AlertCircle size={14} />}
              {key.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      </section>

      <div className="eda-heading">
        <div>
          <span className="eyebrow">EXPLORATORY ANALYSIS</span>
          <h2>Learn from the training set.</h2>
        </div>
        <span className="status-pill">
          <LockKeyhole size={12} /> {eda.match_count} training matches only
        </span>
      </div>
      <div className="training-notice">
        {eda.note} These charts describe observed data; they are not
        predictive-model evaluations.
      </div>
      <div className="eda-grid">
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Event distribution</h2>
              <p>Ten most frequent recorded event types.</p>
            </div>
          </header>
          <Bars rows={eda.event_distribution.slice(0, 10)} />
        </section>
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>Where shots originate</h2>
              <p>Located training shots · 12 × 8 pitch zones.</p>
            </div>
          </header>
          <div className="eda-pitch-wrap">
            <svg
              viewBox="0 0 120 80"
              aria-label="Training shot density by pitch zone"
              role="img"
            >
              <rect width="120" height="80" fill="#edf2e7" />
              {eda.shot_zones.map((z) => (
                <rect
                  key={`${z.x_bin}-${z.y_bin}`}
                  x={z.x_bin * 10}
                  y={z.y_bin * 10}
                  width="10"
                  height="10"
                  fill="#315e44"
                  opacity={0.12 + 0.88 * Math.sqrt(z.count / zoneMax)}
                >
                  <title>
                    {z.count} shots · x {z.x_bin * 10}–{z.x_bin * 10 + 10}, y{" "}
                    {z.y_bin * 10}–{z.y_bin * 10 + 10}
                  </title>
                </rect>
              ))}
              <g fill="none" stroke="#fff" strokeWidth=".5">
                <rect x=".5" y=".5" width="119" height="79" />
                <path d="M60 0V80 M0 18H18V62H0 M120 18H102V62H120" />
                <circle cx="60" cy="40" r="10" />
              </g>
            </svg>
            <p>
              Attacking direction <ArrowRight size={13} /> · darker means more
              shots
            </p>
          </div>
        </section>
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>
                <GitBranch size={17} /> Control-episode lengths
              </h2>
              <p>Owner actions only; opponent pressure events excluded.</p>
            </div>
          </header>
          <Bars rows={eda.episode_lengths} />
          <p className="eda-caption">
            Episodes end at a shot, loss, restart, stoppage, or period boundary.
            They are a modeling convention, not a causal definition of control.
          </p>
        </section>
        <section className="panel">
          <header className="panel-header">
            <div>
              <h2>When shots occur</h2>
              <p>Five-minute bins, shown separately for each half.</p>
            </div>
          </header>
          <Bars
            rows={eda.shot_time_bins.map((t) => ({
              name: `P${t.period} · ${t.start_minute}–${t.start_minute + 5}′`,
              count: t.count,
            }))}
          />
        </section>
      </div>
      <section className="panel dataset-coverage">
        <header className="panel-header">
          <div>
            <h2>Team profiles</h2>
            <p>
              Training matches only. Raw totals; unequal match coverage matters.
            </p>
          </div>
        </header>
        <div className="dataset-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Team</th>
                <th>Matches</th>
                <th>Passes</th>
                <th>Shots</th>
              </tr>
            </thead>
            <tbody>
              {eda.teams.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td>{t.matches}</td>
                  <td>{format(t.passes)}</td>
                  <td>{format(t.shots)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel dataset-coverage">
        <header className="panel-header">
          <div>
            <h2>Players with the most recorded shots</h2>
            <p>
              Top 20 in the training partition. These are volume counts, not
              player quality rankings.
            </p>
          </div>
        </header>
        <div className="dataset-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Matches with events</th>
                <th>Passes</th>
                <th>Shots</th>
              </tr>
            </thead>
            <tbody>
              {eda.players.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.matches}</td>
                  <td>{format(p.passes)}</td>
                  <td>{format(p.shots)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel methodology">
        <span className="eyebrow">QUALITY IS MEASURED, NOT ASSUMED</span>
        <h2>
          {issues
            ? `${format(issues)} recorded quality flags`
            : "No recorded integrity flags"}
        </h2>
        <p>
          Missing optional fields are reported separately from malformed events.
          An event without coordinates stays in counts and is omitted from
          spatial plots.
        </p>
        <div className="quality-details">
          {report.quality_issues.map((q) => (
            <span key={q.name}>
              {q.name.replaceAll("_", " ")} <strong>{format(q.count)}</strong>
            </span>
          ))}
          {Object.entries(report.missing_fields).map(([name, count]) => (
            <span key={name}>
              {name.replaceAll("_", " ")} missing{" "}
              <strong>{format(count)}</strong>
            </span>
          ))}
        </div>
        <p>
          Audit generated{" "}
          {new Date(report.generated_at).toLocaleString("en-GB")}. Pipeline:{" "}
          {report.pipeline_version}. All checks are reproducible with{" "}
          <code>tactigraph audit</code>.
        </p>
      </section>
    </div>
  );
}
