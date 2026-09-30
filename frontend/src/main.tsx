import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  ExternalLink,
  FlaskConical,
  GitBranch,
  Layers,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  PanelRightOpen,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import {
  get,
  selectedLeague,
  type MatchCard,
  type MatchList,
  type MatchSummary,
  type ShotEvidence,
  type ShotLayer,
  type ShotPoint,
} from "./api";
import "./styles.css";
import statsbombLogo from "./assets/statsbomb-logo.png";
import { DatasetOverview } from "./DatasetOverview";
import { Experiments } from "./Experiments";
import { TacticalLab } from "./TacticalLab";
import { Styles } from "./Styles";
import { ThirdPassForecasts } from "./ThirdPassForecasts";
import { EvidenceAnalyst } from "./EvidenceAnalyst";
import { CachedShowcase } from "./CachedShowcase";
import "./refinement.css";

const SOURCE = "https://github.com/hudl/open-data";
type Page =
  | "Overview"
  | "Match Lab"
  | "Evidence Analyst"
  | "Experiments"
  | "Methodology";
const navigation: { name: Page; icon: typeof Activity }[] = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Match Lab", icon: Activity },
  { name: "Evidence Analyst", icon: Sparkles },
  { name: "Experiments", icon: FlaskConical },
  { name: "Methodology", icon: BookOpen },
];
const label = (name: string) => name.replace(" WFC", "").replace(" W", "");
const clock = (shot: ShotPoint) =>
  `${shot.minute}:${String(shot.second).padStart(2, "0")}`;

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <GitBranch size={22} />
      </span>
      <span>
        TactiGraph<span className="brand-ai">AI</span>
      </span>
    </div>
  );
}

function Pitch({
  shots,
  match,
  selected,
  onSelect,
}: {
  shots: ShotPoint[];
  match: MatchCard;
  selected: string | null;
  onSelect: (s: ShotPoint) => void;
}) {
  return (
    <svg
      className="pitch"
      viewBox="-5 -5 130 90"
      role="group"
      aria-label="Interactive shot map, both teams attack right"
    >
      <defs>
        <pattern
          id="stripes"
          width="24"
          height="80"
          patternUnits="userSpaceOnUse"
        >
          <rect width="12" height="80" fill="#1c4e48" />
          <rect x="12" width="12" height="80" fill="#24574f" />
        </pattern>
      </defs>
      <rect x="-5" y="-5" width="130" height="90" rx="2" fill="#173b39" />
      <rect width="120" height="80" fill="url(#stripes)" />
      <g fill="none" stroke="#b1cfc4" strokeWidth=".38">
        <rect width="120" height="80" />
        <path d="M60 0V80" />
        <circle cx="60" cy="40" r="10" />
        <path d="M0 18H18V62H0 M120 18H102V62H120 M0 30H6V50H0 M120 30H114V50H120" />
        <path d="M18 32 A10 10 0 0 1 18 48 M102 32 A10 10 0 0 0 102 48" />
        <path d="M0 36H-2V44H0 M120 36H122V44H120" />
      </g>
      <g fill="#b1cfc4">
        <circle cx="60" cy="40" r=".65" />
        <circle cx="12" cy="40" r=".65" />
        <circle cx="108" cy="40" r=".65" />
      </g>
      {shots
        .filter((s) => s.x !== null && s.y !== null)
        .map((s) => (
          <g
            key={s.event_id}
            role="button"
            tabIndex={0}
            className="shot-marker"
            aria-label={`${s.player_name ?? "Unknown player"}, ${s.outcome}, ${clock(s)}, period ${s.period}`}
            onClick={() => onSelect(s)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(s);
              }
            }}
          >
            <title>
              {s.player_name} · {s.outcome} · {clock(s)}
            </title>
            <circle cx={s.x!} cy={s.y!} r="3.5" fill="transparent" />
            {selected === s.event_id && (
              <circle
                cx={s.x!}
                cy={s.y!}
                r="3.4"
                fill="none"
                stroke="#ffffff"
                strokeWidth=".5"
              />
            )}
            <circle
              cx={s.x!}
              cy={s.y!}
              r={s.goal ? 2.25 : 1.75}
              fill={s.team_id === match.home.id ? "#ddf46b" : "#ff9770"}
              stroke={s.goal ? "#fff" : "#183c37"}
              strokeWidth={s.goal ? ".7" : ".4"}
              opacity={s.goal ? 1 : 0.8}
            />
            {s.goal && <circle cx={s.x!} cy={s.y!} r=".6" fill="white" />}
          </g>
        ))}
    </svg>
  );
}

function EvidenceDrawer({
  evidence,
  selected,
  prediction,
  close,
}: {
  evidence: ShotEvidence;
  selected: string | null;
  prediction?: ShotPoint;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  useEffect(() => {
    if (selected)
      ref.current
        ?.querySelector(`[data-event="${selected}"]`)
        ?.scrollIntoView({ block: "nearest" });
  }, [selected, evidence]);
  return (
    <dialog
      ref={ref}
      className="evidence-dialog"
      onCancel={close}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      aria-labelledby="evidence-title"
    >
      <header>
        <div>
          <span className="eyebrow">TRACEABLE BY DESIGN</span>
          <h2 id="evidence-title">The evidence behind it.</h2>
        </div>
        <button
          className="icon-button"
          onClick={close}
          aria-label="Close evidence"
        >
          <X size={20} />
        </button>
      </header>
      <div className="evidence-body">
        {prediction?.model && (
          <section
            className="model-citation"
            aria-label="Prediction provenance"
          >
            <span className="eyebrow">SHOT PROBABILITY / xG</span>
            <h3>{prediction.xg?.toFixed(3) ?? "—"}</h3>
            <p>
              {prediction.xg == null
                ? "No model estimate is available for this shot."
                : `The model estimates a ${(prediction.xg * 100).toFixed(1)}% chance that this shot ends in a goal. This is a probability, not a promise.`}
            </p>
            <p>
              {prediction.model.penalty
                ? "Penalty estimate"
                : "Non-penalty shot"}{" "}
              · {prediction.model.family} · {prediction.model.model_version} ·{" "}
              {prediction.model.split} partition
            </p>
            <p>
              Sample / cutoff event <code>{prediction.model.sample_id}</code>
            </p>
            <p>
              Artifact SHA-256 <code>{prediction.model.artifact_hash}</code>
            </p>
            <p>
              Run <code>{prediction.model.run_id}</code>
            </p>
            <p>Training and tuning predictions are in-sample.</p>
          </section>
        )}
        <span className="status-pill">
          <ShieldCheck size={13} /> Deterministic result
        </span>
        <h3>{evidence.statement}</h3>
        <p>{evidence.definition}</p>
        <dl className="provenance-list">
          <dt>Match</dt>
          <dd>{evidence.match_id}</dd>
          <dt>Metric</dt>
          <dd>{evidence.provenance.metric_version}</dd>
          <dt>Source commit</dt>
          <dd>{evidence.provenance.source_commit}</dd>
          <dt>Result</dt>
          <dd>{evidence.result_id}</dd>
          <dt>File SHA-256</dt>
          <dd>{evidence.source_sha256 ?? "Unavailable for this fixture"}</dd>
        </dl>
        <h4>
          Supporting events{" "}
          <span className="count-badge">{evidence.references.length}</span>
        </h4>
        {!evidence.references.length && (
          <p>
            No matching Shot events were found. This is a verified zero count.
          </p>
        )}
        {evidence.references.map((r) => (
          <article
            key={r.event_id}
            data-event={r.event_id}
            className={`evidence-event ${selected === r.event_id ? "highlight" : ""}`}
          >
            <div>
              <strong>{r.player_name ?? "Unknown player"}</strong>
              <span>{r.outcome}</span>
            </div>
            <p>
              Period {r.period} · {r.timestamp} · event #{r.index}
            </p>
            <code>{r.event_id}</code>
            <a href={r.source_url} target="_blank" rel="noreferrer">
              Open pinned source file <ExternalLink size={12} />
            </a>
          </article>
        ))}
      </div>
    </dialog>
  );
}

function App() {
  const [page, setPage] = useState<Page>("Match Lab");
  const [list, setList] = useState<MatchList | null>(null);
  const [matchId, setMatchId] = useState<number | null>(null);
  const [summary, setSummary] = useState<MatchSummary | null>(null);
  const [layer, setLayer] = useState<ShotLayer | null>(null);
  const [team, setTeam] = useState("");
  const [period, setPeriod] = useState("");
  const [player, setPlayer] = useState("");
  const [allShots, setAllShots] = useState<ShotPoint[]>([]);
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("");
  const [search, setSearch] = useState("");
  const [season, setSeason] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<ShotEvidence | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const evidenceRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    get<MatchList>("/matches")
      .then((data) => {
        setList(data);
        setMatchId(data.matches[0]?.id ?? null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!matchId) return;
    const controller = new AbortController();
    setSummary(null);
    setAllShots([]);
    setError("");
    Promise.all([
      get<MatchSummary>(`/matches/${matchId}/summary`, controller.signal),
      get<ShotLayer>(`/matches/${matchId}/shots`, controller.signal),
    ])
      .then(([s, shots]) => {
        setSummary(s);
        setAllShots(shots.shots);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [matchId]);

  useEffect(() => {
    if (!matchId) return;
    const controller = new AbortController();
    evidenceRequest.current?.abort();
    setEvidenceLoading(false);
    setLayer(null);
    setError("");
    setSelected(null);
    setEvidence(null);
    const params = new URLSearchParams();
    if (team) params.set("team_id", team);
    if (player) params.set("player_id", player);
    if (period) {
      params.set("period", period);
      if (
        Number(start) < 0 ||
        Number(start) > 120 ||
        (end && (Number(end) <= Number(start) || Number(end) > 120))
      ) {
        setError(
          "Choose a period window between 0 and 120 minutes, with end after start.",
        );
        return () => controller.abort();
      }
      params.set("start_ms", String(Math.round(Number(start) * 60000)));
      if (end) params.set("end_ms", String(Math.round(Number(end) * 60000)));
    }
    get<ShotLayer>(`/matches/${matchId}/shots?${params}`, controller.signal)
      .then(setLayer)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [matchId, team, period, player, start, end]);

  async function openEvidence(shot?: ShotPoint) {
    if (!layer) return;
    evidenceRequest.current?.abort();
    const controller = new AbortController();
    evidenceRequest.current = controller;
    setSelected(shot?.event_id ?? null);
    setEvidenceLoading(true);
    setError("");
    try {
      setEvidence(
        await get<ShotEvidence>(
          `/evidence/${layer.result_id}`,
          controller.signal,
        ),
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setEvidenceLoading(false);
    }
  }

  const match = summary?.match;
  const homeStats = summary?.teams.find((s) => s.team_id === match?.home.id);
  const awayStats = summary?.teams.find((s) => s.team_id === match?.away.id);
  const players = Array.from(
    new Map(
      allShots
        .filter((s) => (!team || s.team_id === Number(team)) && s.player_id)
        .map((s) => [s.player_id, s.player_name]),
    ).entries(),
  ).sort((a, b) => (a[1] ?? "").localeCompare(b[1] ?? ""));
  const filteredMatches =
    list?.matches.filter(
      (m) =>
        (!season || m.season === season) &&
        `${m.home.name} ${m.away.name} ${m.season} ${m.date}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) ?? [];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav aria-label="Main navigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button
              key={name}
              aria-label={name}
              className={`nav-item ${page === name ? "active" : ""}`}
              aria-current={page === name ? "page" : undefined}
              onClick={() => setPage(name)}
            >
              <Icon size={18} />
              <span>{name}</span>
              {name === "Evidence Analyst" && <span className="small-dot" />}
            </button>
          ))}
        </nav>
        <a className="nav-guide" href="/guide" target="_blank" rel="noreferrer">
          Guide <ExternalLink size={14} />
        </a>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            {selectedLeague === "premier-league" ? "Premier League" : "WSL"}{" "}
            <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            {list?.mode !== "public" && (
              <label className="league-picker">
                <span className="sr-only">League</span>
                <select
                  aria-label="League"
                  value={selectedLeague}
                  onChange={(event) => {
                    const url = new URL(window.location.href);
                    url.search =
                      event.target.value === "premier-league"
                        ? "?league=premier-league"
                        : "";
                    window.location.assign(url);
                  }}
                >
                  <option value="wsl">Women’s Super League</option>
                  <option value="premier-league">
                    Premier League · 2015/16
                  </option>
                </select>
              </label>
            )}
            <span className="open-data-badge">
              <Database size={13} /> Open data
            </span>
            <a
              href={SOURCE}
              target="_blank"
              rel="noreferrer"
              aria-label="StatsBomb source repository"
            >
              <ExternalLink size={17} />
            </a>
            <span className="workspace-mode">
              {list?.mode === "public" ? "PUBLIC" : "LOCAL"}
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {selectedLeague === "premier-league"
                  ? "MEN’S PREMIER LEAGUE / 2015–16"
                  : "WOMEN’S SUPER LEAGUE / FOUR SEASONS"}
              </span>
              <h1>
                {page === "Match Lab"
                  ? "Match analysis"
                  : page === "Evidence Analyst"
                    ? "Evidence analyst"
                    : page === "Experiments"
                      ? "Model experiments"
                      : page === "Methodology"
                        ? "Methods & data"
                        : "Dataset overview"}
              </h1>
              <p>
                {page === "Match Lab"
                  ? "Explore match events, model estimates and the source behind each number."
                  : page === "Overview"
                    ? "Coverage, data quality and the chronological evaluation split."
                    : page === "Experiments"
                      ? "Compare measured results, baselines and uncertainty."
                      : page === "Methodology"
                        ? "Definitions, source data and limits of interpretation."
                        : "Guided questions with checked numerical evidence."}
              </p>
            </div>
            <span className="research-badge">RESEARCH WORKSPACE</span>
          </div>

          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button onClick={() => window.location.reload()}>Retry</button>
            </div>
          )}
          {loading && (
            <div className="empty-state">
              <LoaderCircle className="spin" /> Loading your workspace…
            </div>
          )}
          {!loading && list?.matches.length === 0 && (
            <div className="empty-state">
              <Database size={36} />
              <h2>Your first match starts here.</h2>
              <p>
                No data has been ingested. Import the pinned Arsenal–Liverpool
                match to explore it.
              </p>
              <code>tactigraph ingest</code>
              <button
                className="primary-button"
                onClick={() => window.location.reload()}
              >
                Refresh matches
              </button>
            </div>
          )}

          {page === "Overview" && (
            <DatasetOverview openLab={() => setPage("Match Lab")} />
          )}

          {page === "Experiments" && <Experiments />}

          {page === "Methodology" && (
            <section className="panel methodology">
              <span className="eyebrow">DATA & DEFINITIONS</span>
              <h2>One source. A reproducible path.</h2>
              <div className="method-grid">
                <article>
                  <Database />
                  <h3>Pinned, not live</h3>
                  <p>
                    {selectedLeague === "premier-league"
                      ? "Official StatsBomb open data for men's Premier League 2015/16. "
                      : "Official StatsBomb open data across four WSL seasons: 2018/19, 2019/20, 2020/21, and 2023/24. "}
                    The Overview reports actual ingestion coverage. JSON
                    checksums and the source commit are recorded during
                    ingestion.
                  </p>
                  <code>
                    {list?.provenance.source_commit ??
                      "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"}
                  </code>
                </article>
                <article>
                  <Target />
                  <h3>What counts as a shot?</h3>
                  <p>
                    Every source Shot event, regardless of outcome or location
                    availability. Penalty shootouts are excluded. Filters use
                    period-local time, inclusive start and exclusive end.
                  </p>
                </article>
                <article>
                  <Layers />
                  <h3>Event data, not tracking</h3>
                  <p>
                    Pitch locations use the 120 × 80 StatsBomb event-team
                    attacking frame. Both teams attack right in this view.
                    Markers show shot origins, not continuous player positions.
                  </p>
                </article>
                <article>
                  <ShieldCheck />
                  <h3>Facts before interpretation</h3>
                  <p>
                    Shot counts come from a deterministic query. Evidence
                    includes event UUIDs, period timestamps, the metric version,
                    and source checksum. Model probabilities have separate
                    versioned provenance. Guided tactical analysis has separate
                    evaluation and review limits.
                  </p>
                </article>
              </div>
              <div className="license-note">
                Data: StatsBomb. Non-commercial research and analysis. Upstream
                data is excluded from the code license.{" "}
                <a
                  href={`${SOURCE}/blob/master/LICENSE.pdf`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Read the data agreement <ExternalLink size={12} />
                </a>
              </div>
            </section>
          )}

          {(page === "Match Lab" || page === "Evidence Analyst") && match && (
            <>
              {page === "Evidence Analyst" && (
                <>
                  <CachedShowcase
                    matches={list?.matches ?? []}
                    onMatch={(id) => {
                      setMatchId(id);
                      setPage("Match Lab");
                    }}
                  />
                  {list?.mode !== "public" && (
                    <EvidenceAnalyst key={match.id} match={match} />
                  )}
                </>
              )}
              <section className="match-selector panel">
                <div className="competition-mark">
                  {selectedLeague === "premier-league" ? "PL" : "WSL"}
                </div>
                <div className="competition-text">
                  <strong>
                    {selectedLeague === "premier-league"
                      ? "Men’s Premier League"
                      : "FA Women’s Super League"}
                  </strong>
                  <span>
                    {match.season} <span className="separator">/</span> Match
                    archive
                  </span>
                </div>
                <div className="match-controls">
                  <label className="season-select">
                    <span className="sr-only">Season</span>
                    <select
                      aria-label="Season"
                      value={season}
                      onChange={(e) => {
                        setSeason(e.target.value);
                        setSearch("");
                        const next = list?.matches.find(
                          (m) => !e.target.value || m.season === e.target.value,
                        );
                        if (next) {
                          setMatchId(next.id);
                          setTeam("");
                          setPeriod("");
                          setPlayer("");
                          setStart("0");
                          setEnd("");
                        }
                      }}
                    >
                      <option value="">All seasons</option>
                      {Array.from(new Set(list?.matches.map((m) => m.season)))
                        .sort()
                        .map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label className="search-field">
                    <Search size={15} />
                    <input
                      aria-label="Search matches"
                      placeholder="Find a match…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </label>
                  <label className="match-select">
                    <span className="sr-only">Select match</span>
                    <select
                      value={matchId ?? ""}
                      onChange={(e) => {
                        setMatchId(Number(e.target.value));
                        setTeam("");
                        setPeriod("");
                        setPlayer("");
                        setStart("0");
                        setEnd("");
                      }}
                    >
                      {!filteredMatches.some((m) => m.id === matchId) && (
                        <option value={matchId ?? ""}>
                          {filteredMatches.length
                            ? "Current selection"
                            : "No matching matches"}
                        </option>
                      )}
                      {filteredMatches.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.date} · {label(m.home.name)} vs{" "}
                          {label(m.away.name)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={14} />
                  </label>
                </div>
              </section>

              <section className="scoreboard panel">
                <div className="match-meta">
                  <span className="status-pill">
                    <Check size={12} /> Full time
                  </span>
                  <span>
                    {new Date(`${match.date}T12:00:00`).toLocaleDateString(
                      "en-GB",
                      { day: "numeric", month: "long", year: "numeric" },
                    )}
                  </span>
                  <span className="source-tag">MATCH #{match.id}</span>
                </div>
                <div className="score-line">
                  <div className="team-block home-team">
                    <span className="team-monogram home">
                      {label(match.home.name).slice(0, 3).toUpperCase()}
                    </span>
                    <div>
                      <h2>{label(match.home.name)}</h2>
                      <span>HOME</span>
                    </div>
                  </div>
                  <div className="score">
                    <span>{match.home.score}</span>
                    <span className="score-divider">:</span>
                    <span>{match.away.score}</span>
                  </div>
                  <div className="team-block away-team">
                    <div>
                      <h2>{label(match.away.name)}</h2>
                      <span>AWAY</span>
                    </div>
                    <span className="team-monogram away">
                      {label(match.away.name).slice(0, 3).toUpperCase()}
                    </span>
                  </div>
                </div>
                <div className="scoreboard-footer">
                  <span>
                    <ShieldCheck size={13} /> Source-linked match data
                  </span>
                  <span>No 360 data · Event analysis only</span>
                </div>
              </section>

              <div className="stats-grid">
                <article className="stat-card">
                  <span>
                    Total shots <Target size={16} />
                  </span>
                  <strong>
                    {homeStats?.shots} <small>—</small> {awayStats?.shots}
                  </strong>
                  <p>
                    {label(match.home.name)} <span>vs</span>{" "}
                    {label(match.away.name)}
                  </p>
                </article>
                <article className="stat-card">
                  <span>
                    Completed passes <GitBranch size={16} />
                  </span>
                  <strong>
                    {homeStats?.completed_passes} <small>—</small>{" "}
                    {awayStats?.completed_passes}
                  </strong>
                  <p>All recorded periods · shootouts excluded</p>
                </article>
                <article className="stat-card">
                  <span>
                    Expected goals <FlaskConical size={16} />
                  </span>
                  <strong data-testid="match-xg">
                    {homeStats?.xg != null && awayStats?.xg != null ? (
                      <>
                        {homeStats.xg.toFixed(2)} <small>—</small>{" "}
                        {awayStats.xg.toFixed(2)}
                      </>
                    ) : homeStats?.xg_status === "unavailable" ? (
                      "Unavailable"
                    ) : (
                      "Not trained"
                    )}
                  </strong>
                  <p>
                    Non-penalty {homeStats?.non_penalty_xg?.toFixed(2) ?? "—"} /{" "}
                    {awayStats?.non_penalty_xg?.toFixed(2) ?? "—"} · Penalties{" "}
                    {homeStats?.penalty_xg?.toFixed(2) ?? "—"} /{" "}
                    {awayStats?.penalty_xg?.toFixed(2) ?? "—"}
                  </p>
                  {summary?.model && (
                    <p className="model-split-note">
                      {summary.prediction_split === "test"
                        ? selectedLeague === "premier-league"
                          ? "Later 2015/16 test match"
                          : "Later-season test match"
                        : summary.prediction_split === "calibration"
                          ? "Calibration partition"
                          : "Fitting match · in-sample xG"}{" "}
                      ·{" "}
                      {(homeStats?.predicted_shots ?? 0) +
                        (awayStats?.predicted_shots ?? 0)}
                      /{(homeStats?.shots ?? 0) + (awayStats?.shots ?? 0)} shots
                      scored
                    </p>
                  )}
                </article>
                <article className="stat-card">
                  <span>
                    Evidence coverage <ShieldCheck size={16} />
                  </span>
                  <strong>
                    {match.event_count.toLocaleString()} <small>events</small>
                  </strong>
                  <p>Pinned source · checksums verified at import</p>
                </article>
              </div>

              <div className="analysis-layout">
                <section className="panel pitch-panel">
                  <header className="panel-header">
                    <div>
                      <h2>
                        <Target size={17} /> Shot map
                      </h2>
                      <p>Every attempt. In its original context.</p>
                    </div>
                    <span className="neutral-pill">Shot origins</span>
                  </header>
                  <div className="filter-bar">
                    <ListFilter size={15} />
                    <label>
                      <span className="sr-only">Team</span>
                      <select
                        aria-label="Team"
                        value={team}
                        onChange={(e) => {
                          setTeam(e.target.value);
                          setPlayer("");
                        }}
                      >
                        <option value="">Both teams</option>
                        <option value={match.home.id}>
                          {label(match.home.name)}
                        </option>
                        <option value={match.away.id}>
                          {label(match.away.name)}
                        </option>
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">Period</span>
                      <select
                        aria-label="Period"
                        value={period}
                        onChange={(e) => {
                          setPeriod(e.target.value);
                          setStart("0");
                          setEnd("");
                        }}
                      >
                        <option value="">Full match</option>
                        {summary?.periods.map((p) => (
                          <option key={p} value={p}>
                            {p === 1
                              ? "First half"
                              : p === 2
                                ? "Second half"
                                : `Period ${p}`}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">Player</span>
                      <select
                        aria-label="Player"
                        value={player}
                        onChange={(e) => setPlayer(e.target.value)}
                      >
                        <option value="">All shooters</option>
                        {players.map(([id, name]) => (
                          <option key={id} value={id!}>
                            {name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {period && (
                    <div className="time-window">
                      <span>Period minutes</span>
                      <label>
                        From{" "}
                        <input
                          aria-label="Start minute"
                          type="number"
                          min="0"
                          max="120"
                          value={start}
                          onChange={(e) => setStart(e.target.value)}
                        />
                      </label>
                      <label>
                        To{" "}
                        <input
                          aria-label="End minute"
                          type="number"
                          min="0"
                          max="120"
                          placeholder="End"
                          value={end}
                          onChange={(e) => setEnd(e.target.value)}
                        />
                      </label>
                      <span>Start included · end excluded</span>
                    </div>
                  )}
                  <div className="pitch-wrap">
                    {layer ? (
                      <Pitch
                        shots={layer.shots}
                        match={match}
                        selected={selected}
                        onSelect={openEvidence}
                      />
                    ) : (
                      <div className="pitch-loading">
                        {error ? (
                          "Adjust filters to continue."
                        ) : (
                          <>
                            <LoaderCircle className="spin" size={22} /> Loading
                            shots…
                          </>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="pitch-legend">
                    <div>
                      <span className="legend-dot home-dot" />{" "}
                      {label(match.home.name)}
                      <span className="legend-dot away-dot" />{" "}
                      {label(match.away.name)}
                      <span className="goal-dot" /> Goal
                    </div>
                    <span>
                      Attacking direction <ArrowRight size={15} />
                    </span>
                  </div>
                  <div className="pitch-footnote">
                    <CircleHelp size={13} /> Select a shot to inspect its
                    source. Both teams attack right; positions are not tracking
                    data.
                  </div>
                </section>

                <aside className="insight-column">
                  <section className="panel insight-card">
                    <span className="eyebrow">CURRENT FILTER / SHOTS</span>
                    <h2>Shots in selection</h2>
                    <p>
                      Observed Shot events matching the filters on the left.
                    </p>
                    <div
                      className="answer-count"
                      data-testid="filtered-shot-count"
                    >
                      {layer?.total_shots ?? "—"}
                      <span>recorded shots</span>
                    </div>
                    <div className="count-context">
                      <span className="online-dot" />{" "}
                      {period ? `Period ${period}` : "Full match"} ·{" "}
                      {team
                        ? label(
                            team === String(match.home.id)
                              ? match.home.name
                              : match.away.name,
                          )
                        : "Both teams"}
                    </div>
                    <button
                      className="primary-button"
                      onClick={() => openEvidence()}
                      disabled={!layer || evidenceLoading}
                    >
                      {evidenceLoading ? (
                        <LoaderCircle className="spin" size={16} />
                      ) : (
                        <PanelRightOpen size={16} />
                      )}{" "}
                      Inspect evidence <ArrowRight size={15} />
                    </button>
                    <span className="verified-note">
                      Event count · calculated from the selected match
                    </span>
                  </section>
                  <section className="context-card">
                    <div>
                      <h3>About this number</h3>
                      <p>
                        This count is observed data. xG in the table is a model
                        estimate for each shot. Inspect a row to see its model
                        version and source event.
                      </p>
                      <button onClick={() => setPage("Experiments")}>
                        View model evaluation <ArrowRight size={13} />
                      </button>
                    </div>
                  </section>
                  <div className="source-caption">
                    <Database size={13} />
                    <span>
                      StatsBomb Open Data
                      <br />
                      <small>
                        Snapshot {list?.provenance.source_commit.slice(0, 8)}
                      </small>
                    </span>
                  </div>
                </aside>
              </div>

              {page === "Match Lab" && (
                <>
                  <TacticalLab key={summary.match.id} match={summary.match} />
                  <Styles
                    key={`styles-${summary.match.id}`}
                    match={summary.match}
                  />
                  <ThirdPassForecasts
                    key={`forecast-${summary.match.id}`}
                    match={summary.match}
                  />
                </>
              )}
              <section className="panel timeline-panel">
                <header className="panel-header">
                  <div>
                    <h2>
                      <Activity size={17} /> Shot timeline{" "}
                      <span className="count-badge">
                        {layer?.total_shots ?? "—"}
                      </span>
                    </h2>
                    <p>
                      The selected events, in source order. Click any row to
                      follow the evidence.
                    </p>
                  </div>
                  <span className="neutral-pill">
                    <Layers size={12} /> {layer?.located_shots ?? "—"} located
                  </span>
                </header>
                <div
                  className="timeline-track"
                  aria-label="Shot timing overview"
                >
                  {[0, 15, 30, 45, 60, 75, 90].map((m) => (
                    <span
                      className="tick"
                      key={m}
                      style={{ left: `${(m / 100) * 100}%` }}
                    >
                      {m}′
                    </span>
                  ))}
                  <div className="track-line" />
                  {layer?.shots.map((s) => (
                    <button
                      key={s.event_id}
                      className={`timeline-dot ${s.team_id === match.home.id ? "home-dot" : "away-dot"} ${s.goal ? "is-goal" : ""}`}
                      style={{
                        left: `${Math.min(s.minute, 100)}%`,
                        top: s.team_id === match.home.id ? 19 : 45,
                      }}
                      onClick={() => openEvidence(s)}
                      title={`${s.player_name}, ${clock(s)}, ${s.outcome}`}
                      aria-label={`Inspect ${s.player_name} at ${clock(s)}`}
                    />
                  ))}
                </div>
                <div className="event-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Player</th>
                        <th>Team</th>
                        <th>Outcome</th>
                        <th>Body part</th>
                        <th>xG</th>
                        <th>
                          <span className="sr-only">Evidence</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {layer?.shots.map((s) => (
                        <tr
                          key={s.event_id}
                          className={
                            selected === s.event_id ? "selected-row" : ""
                          }
                        >
                          <td>
                            <span className="event-time">{clock(s)}</span>
                            <small>P{s.period}</small>
                          </td>
                          <td>
                            <button
                              className="player-button"
                              onClick={() => openEvidence(s)}
                            >
                              {s.player_name ?? "Unknown player"}
                            </button>
                          </td>
                          <td>
                            <span
                              className={`legend-dot ${s.team_id === match.home.id ? "home-dot" : "away-dot"}`}
                            />
                            {label(
                              s.team_id === match.home.id
                                ? match.home.name
                                : match.away.name,
                            )}
                          </td>
                          <td>
                            <span
                              className={s.goal ? "goal-tag" : "outcome-tag"}
                            >
                              {s.outcome}
                            </span>
                          </td>
                          <td>{s.body_part ?? "Unrecorded"}</td>
                          <td>{s.xg?.toFixed(3) ?? "—"}</td>
                          <td>
                            <button
                              className="icon-button"
                              onClick={() => openEvidence(s)}
                              aria-label={`Evidence for event ${s.index}`}
                            >
                              <ArrowRight size={15} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {layer?.shots.length === 0 && (
                    <div className="no-shots">
                      <Target size={24} />
                      <strong>No shots in this selection.</strong>
                      <span>
                        Try another team, period, or time window. The zero count
                        can still be inspected.
                      </span>
                    </div>
                  )}
                </div>
              </section>
            </>
          )}
          {!loading &&
            matchId &&
            !summary &&
            !error &&
            (page === "Match Lab" || page === "Evidence Analyst") && (
              <div className="empty-state">
                <LoaderCircle className="spin" /> Loading the match…
              </div>
            )}
          <footer className="page-footer">
            <span>
              TACTIGRAPH AI <span className="footer-dot">·</span> Historical
              event analysis
            </span>
            <a href="/guide" target="_blank" rel="noreferrer">
              User guide <ExternalLink size={12} />
            </a>
            <a href={SOURCE} target="_blank" rel="noreferrer">
              <span>Data provided by</span>
              <img
                src={statsbombLogo}
                className="statsbomb-logo"
                alt="StatsBomb"
              />
              <ExternalLink size={12} />
            </a>
          </footer>
        </main>
      </div>
      {evidence && (
        <EvidenceDrawer
          evidence={evidence}
          selected={selected}
          prediction={layer?.shots.find((s) => s.event_id === selected)}
          close={() => setEvidence(null)}
        />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
