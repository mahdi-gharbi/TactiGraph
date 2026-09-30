# M1 methodology

## Shot count v1

Count source events whose type is `Shot`, restricted by the selected match, optional team,
optional player, and optional period-local time window. Include every shot outcome and
missing location. Exclude period 5 (shootouts). Normal penalties remain shots.

Do not equate goals-from-shots with the official score: own goals can make them differ.
The scoreboard reads official match metadata; shots read event records.

## Coordinates and time

Use source coordinates in the StatsBomb 120 Ã— 80 event-team attacking frame. Both teams
attack right on the analytical shot map. Do not flip every second half or suggest that the
positions show live player locations. Plot shot origins only; use equal marker sizes by
outcome class, not invented xG values.

Source index determines event order. Preserve period-local milliseconds and displayed
match minute separately. A first-half event at 45:30 and a second-half event at 45:00 are
distinct; global minute sorting is not a valid substitute for source order.

The timeline overview uses displayed minutes; the authoritative ordered event table retains
period labels and the evidence drawer retains the full period-local timestamp. This first
match has two periods. Extra-time display beyond 100 minutes is a known limitation of the
overview graphic and must be expanded before enabling more competitions.

## Evidence, not an LLM analyst

The evidence sentence is rendered from the validated count and selection. It makes no causal
or tactical claims. The drawer identifies each supporting UUID, source index, timestamp,
source commit, file hash, and metric version. This is the deterministic foundation for later
tool-using analysis, not a claim that an AI analyst already exists.

## Versioned xG

M3 serves xg-v1 logistic probabilities from stored, versioned predictions. Penalties use a
separate smoothed fitting-data conversion rate. Match totals expose non-penalty and penalty
contributions, coverage and the prediction split. Fitting-match predictions are in-sample.
One outside-pitch shot is unscored but remains in the analytical count and evidence.

See [the model card](xg-model-card.md) for features, selection, honest held-out metrics,
calibration, uncertainty and limitations. M4 adds [evaluated xT](xt-model-card.md),
[period comparisons, passing networks and separate trailing curves](tactical-analytics.md).
GNN, retrieval and LLM analysis remain future work.

## Data scope

All 457 listed WSL matches from seasons 4, 42, 90 and 281 at the pinned snapshot are imported.
Separate 360 data is unavailable. Shot freeze frames are distinct and are excluded from models.
