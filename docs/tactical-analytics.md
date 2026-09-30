# Tactical analytics v1

All calculation lives in Python; React formats values and draws the geometry.
Coordinates retain the StatsBomb event-team attacking 120×80 frame. Halves are not
flipped. Each comparison requires two ordered, non-overlapping, half-open windows
inside one recorded period. Default: P2 [0,15) versus [15,30), displayed as 45–60
versus 60–75. Stoppage time remains available; unsupported coverage is rejected.

## Measurements

- Shots and pass attempts are counts, including unlocated events.
- Pass completion is completed / attempted passes. Zero attempts gives null.
- Final-third entries are completed passes/carries from x<80 to x>=80 with valid
  coordinates, divided by selected elapsed minutes, not ball-in-play time.
- Field tilt is a team's completed passes ending at x>=80 / both teams' such passes,
  with valid endpoints in each team's attacking frame. Its evidence includes the
  opponent's denominator events. Zero denominator gives null.
- xG sums stored probabilities only when every shot is scored. Penalties use the
  separate xG penalty model. Incomplete coverage is null, not an understated total.
- Signed movement xT sums valued observed actions; invalid spatial actions are
  counted in warnings. See the xT card for terminal and action-value semantics.

## Passing networks

Directed weighted completed-pass graph, with active lineup players plus observed
senders/recipients. Unknown player endpoints and self-passes are excluded and counted.
Repeated passes increment an edge count. In/out strength sums pass counts; density
is unique directed edges / n(n−1); outgoing HHI sums squared sender pass shares.
Betweenness is normalized, endpoints excluded, using exact rational inverse pass
count distances with [NetworkX](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.betweenness_centrality.html).

Positions average valid completed-pass origins and receptions, with sample counts.
They are not formations or tracking positions. Nodes without coordinates remain
in metrics and the selector. Individual signed movement xT is shown separately
from strength and betweenness, with its valued-action count. Exposure unions overlapping lineup intervals; missing
exposure is null. Lineup boundary and valued-movement citations accompany network pass evidence.
Substitution windows are flagged; users can narrow bounds to a single lineup.
Fewer than 30 passes triggers a descriptive sparsity warning, not a statistical threshold.

## Curves and shifts

Separate trailing-five-minute xG and signed movement xT sums are sampled each minute
and at recorded period end. Initial windows shorten at the half start; missing
model coverage is explicit. Every point resolves to its exact analytical query.
No combined control score is invented. Candidate shifts are the three largest
absolute adjacent complete-five-minute entry-rate changes, excluding zero changes,
with earlier boundaries breaking ties. Incomplete final bins are not ranked.
Goals, substitutions and reconstructed dismissals are source-linked separately.
Shifts are descriptive, not causes or statistical change-point tests.

## API and evidence

### Fixed-network player removal

Select a player in either observed passing network and choose **Remove selected player
from observed network**. The server deletes that node and its incident directed edges,
retaining every other player, isolated node and observed pass weight. Restore resets the
view; no database rows change. Positions and the inspected player's statistics remain
original historical observations. No replacement behaviour or match outcome is predicted.

`GET /api/v1/tactical-evidence/{network-id}/remove-player/{player-id}` returns version
`network-removal-v1`, source provenance, the original evidence ID, and before/after counts:
nodes, directed links, pass weight, density, isolates, weak and strong component sizes,
and reachable ordered pairs excluding self-pairs. Reachability denominators are n(n−1).
Density may increase merely because that denominator shrinks; this is not evidence of
better play. Empty graphs return zero counts and empty component lists. Unknown players
or evidence for a non-network metric are rejected.

This is structural sensitivity of the fixed observed graph, not a football counterfactual.

`POST /api/v1/matches/{id}/compare`, `GET /api/v1/matches/{id}/network`,
`GET /api/v1/matches/{id}/trends`, `GET /api/v1/tactical-evidence/{id}` and
`GET /api/v1/experiments/xt` have typed OpenAPI contracts. Evidence is paginated
at a maximum 250 references per response. These expose citation metadata, not raw
event objects or coordinates. Source commit/checksum, metric/model versions and
complete backing sets are resolved server-side.

Evidence IDs encode validated allowlisted queries, not immutable report records or
authorization tokens. Their payload carries current versions; changed publications
can change model values. Comparison IDs hash query, snapshot, versions and measurements.
Future verified analyst reports must retain their verified payload, rather than
treat query IDs alone as immutable numerical evidence. Public raw-event access stays disabled.
