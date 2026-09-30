import { useEffect, useRef, useState } from "react";
import type { components } from "./api.generated";
import { get, apiUrl, type MatchCard } from "./api";
import "./tactics.css";
import { TacticalTrends } from "./TacticalTrends";

type Comparison = components["schemas"]["ComparisonResponse"];
type Evidence = components["schemas"]["TacticalEvidence"];
type Network = components["schemas"]["PassingNetwork"];
type Sensitivity = components["schemas"]["SensitivityResponse"];
type Measurement = components["schemas"]["Measurement"];
const names: Record<string, string> = {
  shots: "Shots",
  xg: "Model xG",
  passes: "Pass attempts",
  completed_passes: "Pass completion",
  final_third_entries: "Final-third entries / min",
  field_tilt: "Field tilt",
  movement_xt: "Signed movement xT",
};
function value(m: Measurement) {
  if (m.value === null) return "Unavailable";
  return m.unit === "fraction"
    ? `${(m.value * 100).toFixed(1)}%`
    : m.unit === "shots" || m.unit === "passes"
      ? String(m.value)
      : m.value.toFixed(3);
}

const countLabel = (n: number | null) =>
  n === null ? "—" : Number.isInteger(n) ? String(n) : n.toFixed(3);

function NetworkView({
  network,
  label,
  id,
  inspect,
}: {
  network: Network;
  label: string;
  id: string;
  inspect: (id: string) => void;
}) {
  const [player, setPlayer] = useState<number | null>(null);
  const [removal, setRemoval] = useState<Sensitivity | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removalError, setRemovalError] = useState("");
  const removalRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    removalRequest.current?.abort();
    setRemoval(null);
    setRemovalError("");
    setRemoving(false);
    return () => removalRequest.current?.abort();
  }, [player, network.evidence_id]);
  async function remove() {
    if (player === null) return;
    const controller = new AbortController();
    removalRequest.current?.abort();
    removalRequest.current = controller;
    setRemoving(true);
    setRemovalError("");
    try {
      const result = await get<Sensitivity>(
        `/tactical-evidence/${network.evidence_id}/remove-player/${player}`,
        controller.signal,
      );
      if (
        result.before.pass_weight !== network.pass_count ||
        result.before.players !== network.nodes.length
      ) {
        throw new Error("Network changed; compare the windows again.");
      }
      if (!controller.signal.aborted) setRemoval(result);
    } catch (error) {
      if (!controller.signal.aborted)
        setRemovalError(
          error instanceof Error ? error.message : "Removal unavailable",
        );
    } finally {
      if (!controller.signal.aborted) setRemoving(false);
    }
  }
  const displayedEdges = network.edges.filter(
    (e) =>
      e.sender !== removal?.player_id && e.recipient !== removal?.player_id,
  );
  const displayedNodes = network.nodes.filter(
    (n) => n.player_id !== removal?.player_id,
  );
  const selected = network.nodes.find((n) => n.player_id === player);
  return (
    <section className="network-panel" aria-label={`${label} passing network`}>
      <div className="tactical-heading">
        <h3>{label}</h3>
        <button onClick={() => inspect(network.evidence_id)}>
          Pass evidence
        </button>
      </div>
      <svg
        viewBox="-5 -6 130 94"
        className="network-pitch"
        role="group"
        aria-label={`${label}: ${removal ? "player removed from fixed graph" : "observed passing positions"}, attacking right`}
      >
        <defs>
          <marker
            id={id}
            viewBox="0 0 6 6"
            refX="6"
            refY="3"
            markerWidth="3"
            markerHeight="3"
            orient="auto-start-reverse"
          >
            <path d="M0 0L6 3L0 6Z" fill="#467058" />
          </marker>
        </defs>
        <rect
          width="120"
          height="80"
          fill="#e7ede2"
          stroke="#a7b59f"
          strokeWidth=".4"
        />
        <g fill="none" stroke="#a7b59f" strokeWidth=".4">
          <path d="M60 0V80M0 18H18V62H0M120 18H102V62H120" />
          <circle cx="60" cy="40" r="10" />
        </g>
        {displayedEdges.map((e) => {
          const a = network.nodes.find((n) => n.player_id === e.sender);
          const b = network.nodes.find((n) => n.player_id === e.recipient);
          if (a?.x == null || a.y == null || b?.x == null || b.y == null)
            return null;
          const cx = (a.x + b.x) / 2 - (b.y - a.y) * 0.13;
          const cy = (a.y + b.y) / 2 + (b.x - a.x) * 0.13;
          const startLength = Math.hypot(cx - a.x, cy - a.y);
          const endLength = Math.hypot(b.x - cx, b.y - cy);
          if (startLength < 3.5 || endLength < 3.5) return null;
          const sx = a.x + (3.3 * (cx - a.x)) / startLength;
          const sy = a.y + (3.3 * (cy - a.y)) / startLength;
          const ex = b.x - (3.3 * (b.x - cx)) / endLength;
          const ey = b.y - (3.3 * (b.y - cy)) / endLength;
          return (
            <path
              key={`${e.sender}-${e.recipient}`}
              d={`M${sx} ${sy}Q${cx} ${cy} ${ex} ${ey}`}
              stroke="#467058"
              fill="none"
              strokeWidth={0.25 + Math.sqrt(e.count) * 0.3}
              opacity={
                removal ||
                player === null ||
                player === e.sender ||
                player === e.recipient
                  ? 0.65
                  : 0.12
              }
              markerEnd={`url(#${id})`}
            >
              <title>
                {a.name} → {b.name}: {e.count} passes
              </title>
            </path>
          );
        })}
        {displayedNodes
          .filter((n) => n.x !== null && n.y !== null)
          .map((n) => (
            <g
              key={n.player_id}
              role="button"
              tabIndex={0}
              aria-label={`${n.name}: ${n.out_strength} sent, ${n.in_strength} received`}
              onClick={() => setPlayer(n.player_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setPlayer(n.player_id);
                }
              }}
              className="network-node"
            >
              <circle
                cx={n.x!}
                cy={n.y!}
                r="3"
                fill={n.player_id === player ? "#a65d25" : "#285a40"}
                stroke="white"
                strokeWidth=".5"
              />
              <text
                x={n.x!}
                y={n.y! + 1}
                textAnchor="middle"
                fill="white"
                fontSize="3"
              >
                {network.nodes.indexOf(n) + 1}
              </text>
              <title>{n.name}</title>
            </g>
          ))}
        <text x="60" y="86" textAnchor="middle" fontSize="3" fill="#4e6455">
          ATTACKING DIRECTION → · OBSERVED PASS POSITIONS
        </text>
      </svg>
      <p className="network-summary">
        {removal && "Original graph: "}
        {network.pass_count} passes · density {network.density.toFixed(3)} ·
        outgoing HHI {network.concentration?.toFixed(3) ?? "unavailable"}
      </p>
      <label className="network-select">
        Inspect player
        <select
          value={player ?? ""}
          onChange={(e) =>
            setPlayer(e.target.value ? Number(e.target.value) : null)
          }
        >
          <option value="">Choose a player</option>
          {network.nodes.map((n, i) => (
            <option key={n.player_id} value={n.player_id}>
              {i + 1}. {n.name}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <p className="player-statistics">
          <strong>{selected.name}</strong>
          <br />
          {selected.out_strength} sent · {selected.in_strength} received ·
          betweenness {selected.betweenness.toFixed(3)}
          <br />
          Signed movement xT {selected.movement_xt?.toFixed(3) ??
            "unavailable"}{" "}
          · {selected.valued_actions} valued actions
          <br />
          {selected.exposure_minutes?.toFixed(1) ?? "Unknown"} minutes exposure
          · {selected.position_samples} position observations
        </p>
      )}
      <p className="tactical-note">
        {network.position_definition}. Line width represents pass count; arrows
        indicate direction. Unlocated players remain in the player selector.
        Numbers are chart labels, not shirt numbers; overlapping locations may
        hide individual links.
      </p>
      {selected && !removal && (
        <button disabled={removing} onClick={remove}>
          {removing
            ? "Computing structural sensitivity…"
            : "Remove selected player from observed network"}
        </button>
      )}
      {removalError && <p role="alert">{removalError}</p>}
      {removal && (
        <div
          className="experiment-note"
          aria-label="Network removal result"
          role="region"
        >
          <h4>Fixed graph without {removal.player_name}</h4>
          <p>{removal.limitation}</p>
          <dl>
            <dt>Remaining pass weight</dt>
            <dd>
              {removal.after.pass_weight} / {removal.before.pass_weight}{" "}
              observed passes ({removal.removed_pass_weight} removed)
            </dd>
            <dt>Players / directed links</dt>
            <dd>
              {removal.after.players} / {removal.after.directed_edges}
            </dd>
            <dt>Density</dt>
            <dd>
              {removal.before.density.toFixed(3)} →{" "}
              {removal.after.density.toFixed(3)}
            </dd>
            <dt>Reachable ordered pairs</dt>
            <dd>
              {removal.before.reachable_ordered_pairs}/
              {removal.before.possible_ordered_pairs} →{" "}
              {removal.after.reachable_ordered_pairs}/
              {removal.after.possible_ordered_pairs}
            </dd>
            <dt>Weak component sizes</dt>
            <dd>
              {removal.before.weak_component_sizes.join(", ") || "Empty"} →{" "}
              {removal.after.weak_component_sizes.join(", ") || "Empty"}
            </dd>
            <dt>Strong component sizes</dt>
            <dd>
              {removal.before.strong_component_sizes.join(", ") || "Empty"} →{" "}
              {removal.after.strong_component_sizes.join(", ") || "Empty"}
            </dd>
            <dt>Isolated players</dt>
            <dd>
              {removal.before.isolated_players} →{" "}
              {removal.after.isolated_players}
            </dd>
          </dl>
          <p>
            Positions remain their original observations. Player statistics
            above describe the original graph.
          </p>
          <button onClick={() => setRemoval(null)}>
            Restore observed network
          </button>
          <p>
            <small>
              {removal.metric_version} · {removal.result_id}
            </small>
          </p>
        </div>
      )}
      {network.excluded_passes > 0 && (
        <p className="tactical-note">
          {network.excluded_passes} completed passes excluded: unknown player or
          self-pass.
        </p>
      )}
    </section>
  );
}

function EvidenceDialog({ id, close }: { id: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      opener?.focus();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    get<Evidence>(
      `/tactical-evidence/${id}?offset=${offset}&limit=50`,
      controller.signal,
    )
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [id, offset]);
  return (
    <dialog
      ref={dialog}
      className="tactical-dialog"
      aria-labelledby="tactical-evidence-title"
      onCancel={close}
    >
      <div className="tactical-heading">
        <h2 id="tactical-evidence-title">Analytical evidence</h2>
        <button onClick={close} autoFocus>
          Close analytical evidence
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading supporting events…</p>}
      {data && (
        <>
          <p>{data.definition}</p>
          {data.network && (
            <p>
              {data.network.pass_count} network passes ·{" "}
              {data.network.nodes.length} players · density{" "}
              {data.network.density.toFixed(3)} · outgoing HHI{" "}
              {data.network.concentration?.toFixed(3) ?? "unavailable"}.
              Supporting references also include lineup boundaries.
            </p>
          )}
          <p>
            <strong>{data.total} supporting events</strong> · Match{" "}
            {data.match_id} · Period {data.window.period} ·{" "}
            {(data.window.start_ms / 60000).toFixed(1)}–
            {(data.window.end_ms / 60000).toFixed(1)} period minutes
          </p>
          {data.measurement && (
            <p>
              Value: {value(data.measurement)} · Numerator:{" "}
              {data.measurement.numerator ?? "unavailable"} · Denominator:{" "}
              {data.measurement.denominator ?? "unavailable"}{" "}
              {data.measurement.denominator_unit}
            </p>
          )}
          <p className="tactical-code">
            {data.result_id}
            <br />
            Metric: {data.provenance.metric_version}
            <br />
            Source commit: {data.provenance.source_commit}
            <br />
            Source SHA-256: {data.source_sha256 ?? "unavailable"}
          </p>
          {(data.metric === "xg" || data.metric === "movement_xt") &&
            data.model && (
              <p className="tactical-code">
                Model: {data.model.model_version} · Run: {data.model.run_id}
                <br />
                Artifact SHA-256: {data.model.artifact_hash}
              </p>
            )}
          <ol className="tactical-references" start={offset + 1}>
            {data.references.map((r) => (
              <li key={r.event_id}>
                <a href={r.source_url} target="_blank" rel="noreferrer">
                  {r.team_name} · {r.player_name ?? r.outcome} · P{r.period}{" "}
                  {r.timestamp}
                </a>
                <code>{r.event_id}</code>
              </li>
            ))}
          </ol>
          <div className="tactical-heading">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous evidence
            </button>
            <span>
              {data.total ? offset + 1 : 0}–{Math.min(offset + 50, data.total)}{" "}
              / {data.total}
            </span>
            <button
              disabled={offset + 50 >= data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Next evidence
            </button>
          </div>
          <p className="tactical-note">
            Data provided by StatsBomb. References point to the pinned upstream
            source.
          </p>
        </>
      )}
    </dialog>
  );
}

export function TacticalLab({ match }: { match: MatchCard }) {
  const [team, setTeam] = useState(match.home.id);
  const [period, setPeriod] = useState(2);
  const [bounds, setBounds] = useState([0, 15, 15, 30]);
  const [query, setQuery] = useState({
    team_id: match.home.id,
    before: { period: 2, start_ms: 0, end_ms: 900000 },
    after: { period: 2, start_ms: 900000, end_ms: 1800000 },
  });
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const [evidence, setEvidence] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    fetch(apiUrl(`/matches/${match.id}/compare`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(query),
      signal: controller.signal,
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok)
          throw new Error(
            typeof body.detail === "string"
              ? body.detail
              : "Use ordered, non-overlapping windows in one recorded period.",
          );
        return body as Comparison;
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [match.id, query]);
  function windowLabel(w: {
    period: number;
    start_ms: number;
    end_ms: number;
  }) {
    const offset = w.period === 2 ? 45 : 0;
    return `P${w.period} · ${offset + w.start_ms / 60000}–${offset + w.end_ms / 60000} min`;
  }
  return (
    <section className="tactical-lab" aria-labelledby="tactical-title">
      <div className="tactical-heading">
        <div>
          <span className="eyebrow">MEASURE THE CHANGE</span>
          <h2 id="tactical-title">Periods & passing networks</h2>
        </div>
        <span className="tactical-badge">Deterministic analysis</span>
      </div>
      <p>
        Compare progression, chance creation and passing connections. The
        default compares 45–60 with 60–75 minutes. Each window stays inside one
        half.
      </p>
      <form
        className="tactical-controls"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery({
            team_id: team,
            before: {
              period,
              start_ms: Math.round(bounds[0] * 60000),
              end_ms: Math.round(bounds[1] * 60000),
            },
            after: {
              period,
              start_ms: Math.round(bounds[2] * 60000),
              end_ms: Math.round(bounds[3] * 60000),
            },
          });
        }}
      >
        <label>
          Comparison team
          <select
            value={team}
            onChange={(e) => setTeam(Number(e.target.value))}
          >
            <option value={match.home.id}>{match.home.name}</option>
            <option value={match.away.id}>{match.away.name}</option>
          </select>
        </label>
        <label>
          Comparison half
          <select
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
          >
            <option value={1}>First half</option>
            <option value={2}>Second half</option>
          </select>
        </label>
        {["Before start", "Before end", "After start", "After end"].map(
          (name, i) => (
            <label key={name}>
              {name}
              <input
                type="number"
                min="0"
                max="120"
                step="0.1"
                required
                value={bounds[i]}
                onChange={(e) =>
                  setBounds(
                    bounds.map((v, j) =>
                      i === j ? Number(e.target.value) : v,
                    ),
                  )
                }
              />
            </label>
          ),
        )}
        <button type="submit">Compare periods</button>
      </form>
      <p className="tactical-note">
        Inputs are minutes since the start of the selected half; bounds include
        the start and exclude the end. Shot-map filters above are separate from
        this comparison.
      </p>
      {error && (
        <p role="alert" className="tactical-error">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Computing period comparison…</p>}
      {data && (
        <>
          <div className="comparison-verdict">
            <strong>{data.statement}</strong>
            <span>
              {data.team_id === match.home.id
                ? match.home.name
                : match.away.name}{" "}
              · {windowLabel(data.before.window)} →{" "}
              {windowLabel(data.after.window)}
            </span>
          </div>
          <div className="tactical-metrics">
            {data.before.measurements.map((before, i) => {
              const after = data.after.measurements[i];
              const delta = data.differences[i];
              return (
                <article key={before.metric} className="tactical-metric">
                  <h3>{names[before.metric]}</h3>
                  <div className="metric-pair">
                    <button
                      onClick={() => setEvidence(before.evidence_id)}
                      aria-label={`Before ${names[before.metric]} evidence`}
                    >
                      <small>Before</small>
                      <strong>{value(before)}</strong>
                    </button>
                    <span>→</span>
                    <button
                      onClick={() => setEvidence(after.evidence_id)}
                      aria-label={`After ${names[after.metric]} evidence`}
                    >
                      <small>After</small>
                      <strong>{value(after)}</strong>
                    </button>
                  </div>
                  <p>
                    Change:{" "}
                    {delta.value === null
                      ? "unavailable"
                      : `${delta.value > 0 ? "+" : ""}${(delta.value * (delta.unit === "fraction" ? 100 : 1)).toFixed(3)} ${delta.unit === "fraction" ? "percentage points" : delta.unit}`}
                  </p>
                  <small>
                    Before: {countLabel(before.numerator)} /{" "}
                    {countLabel(before.denominator)} · After:{" "}
                    {countLabel(after.numerator)} /{" "}
                    {countLabel(after.denominator)} {before.denominator_unit}
                  </small>
                </article>
              );
            })}
          </div>
          <div className="network-grid">
            <NetworkView
              key={`before-${data.result_id}`}
              network={data.before.network}
              label={`Before · ${windowLabel(data.before.window)}`}
              id="before-arrow"
              inspect={setEvidence}
            />
            <NetworkView
              key={`after-${data.result_id}`}
              network={data.after.network}
              label={`After · ${windowLabel(data.after.window)}`}
              id="after-arrow"
              inspect={setEvidence}
            />
          </div>
          <TacticalTrends
            matchId={match.id}
            teamId={data.team_id}
            period={data.before.window.period}
            inspect={setEvidence}
          />
          <details className="tactical-quality">
            <summary>Definitions, coverage & limitations</summary>
            <p>
              Density uses directed player pairs. Outgoing concentration (HHI)
              sums squared shares of completed passes sent. Betweenness uses
              inverse pass counts as path distances. Exposure is reconstructed
              lineup time, including stoppages.
            </p>
            {[data.before, data.after].map((w, i) => (
              <div key={i}>
                <strong>{i === 0 ? "Before" : "After"}</strong>
                <ul>
                  {w.warnings.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            ))}
            <p>
              Signed movement xT:{" "}
              {data.xt_status === "ready"
                ? data.xt_model?.model_version
                : "not trained"}
              . No control score or causal conclusion is inferred.
            </p>
            <p>
              xT is fitted on training plus tuning episodes; those matches are
              in-sample. Spatial values describe a historical action policy, not
              decision optimality.
            </p>
            <p className="tactical-code">
              {data.result_id}
              <br />
              {data.provenance.metric_version} · {data.provenance.source_commit}
            </p>
          </details>
        </>
      )}
      {evidence && (
        <EvidenceDialog
          key={evidence}
          id={evidence}
          close={() => setEvidence(null)}
        />
      )}
    </section>
  );
}
