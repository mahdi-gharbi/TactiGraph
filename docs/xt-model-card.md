# xT v1 — turnover-aware spatial values

<img src="../frontend/src/assets/statsbomb-logo.png" alt="StatsBomb — data provider" width="130" />

Data provided by StatsBomb Open Data, pinned commit
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`. Code and aggregate analysis are published;
upstream event files and private generated artifacts are excluded from distribution.

## Task and interpretation

Estimate the probability of a goal before a normalized control episode ends, from a
spatial state under the observed historical action policy. This extends the
[original xT location-value formulation](https://karun.in/blog/expected-threat.html)
with explicit losses, episode terminals and fitting-only smoothing. It does not
observe off-ball shape, tracking, replacement behavior or optimal decisions.

Moves are completed passes and carries. Failed passes, incomplete dribbles,
dispossessions and miscontrols terminate with value zero. Shots terminate with goal
one/non-goal zero. Foundation-v1 splits rebounds, restarts and period boundaries.
An episode ending in a retained move receives one synthetic loss at its destination;
an existing shot/loss terminal receives no second terminal.

Successful dribbles, recoveries and interceptions are not retained spatial moves in
this model. Episodes without a modeled action are excluded. An invalid required
origin/destination excludes the entire episode; no gaps are bridged. This owner-only
control-episode sample differs from the complete xG shot sample. Counts and goal
totals must not be compared as though they have the same eligibility.

## Frozen procedure

`configs/xt-v1.json` is the prespecified protocol. The shared split is 194 training,
89 tuning, 42 calibration and 132 test matches. Calibration is unused by this model.
Both grids are fit on training only; tuning Brier selects the grid, then the model
is refitted on training+tuning. No test rows are loaded during development.

The joint categorical distribution over retained destinations, shot and loss has a
total prior mass of 10, centered on fitting-global frequencies. Zone scoring has
prior strength 20 centered on fitting-global shot conversion. The transition
solution must reach maximum value change below 1e-8 within 10,000 iterations.

Protocol, source snapshot, code and artifact hashes are locked before xT test access.
An exclusive test-access marker prevents silent retries after incomplete evaluation;
completed repeated evaluations return the saved report. **The 2023/24 season had
already been inspected for xg-v1.** It is not an untouched project-wide holdout.
New choices require a new version and an explicit prior-inspection disclosure.

## Observed results — 22 September 2026

| Grid | Tuning Brier | Tuning log loss |
| --- | ---: | ---: |
| 12×8, selected | 0.0100983 | 0.0518870 |
| 8×6 | 0.0101174 | 0.0520163 |

Fitting: 56,676 training + 25,538 tuning = 82,214 episodes; exactly one terminal
per episode; 67 iterations. Spatial action/shot/goal counts are published alongside
the value surface so sparse cells remain visible.

Test: 132 matches, 35,899 eligible episodes, 406 goals. Of 35,991 source episodes,
92 had no eligible modeled action. Training exclusions: 69 empty modeled episodes
and 15 invalid destinations. Tuning exclusions: 31 empty episodes and one invalid origin.

| Model | Test Brier | Test log loss |
| --- | ---: | ---: |
| Fitting global episode-goal rate | 0.0111836 | 0.0620308 |
| Smoothed zone immediate reward, no transitions | 0.0108312 | 0.0919268 |
| Turnover-aware xT | **0.0106757** | **0.0542451** |

1,000 paired match-bootstrap draws, seed 2026. xT Brier 95% interval
[0.009679, 0.011636]; log loss [0.049623, 0.058624]. Brier difference versus
global: [-0.000657, -0.000371]; versus no-transition: [-0.000199, -0.000109].
These results support this comparison on the sampled WSL data, not all football.
The no-transition reference is the immediate shot-goal reward, not a separately
fit episode-outcome classifier. The global baseline is the fitting episode-goal rate.

## Application and reproduction

Completed movement receives destination minus origin value; observed failed movement
and loss actions receive minus origin. Shots get xG only. Synthetic terminals are
part of fitting, not invented observed actions in match charts. Invalid coordinates
are excluded from movement totals with explicit coverage warnings. Training/tuning
match values are in-sample; they are descriptive, not additional held-out evaluations.

Run `tactigraph xt develop`, `tactigraph xt evaluate`, `tactigraph xt publish`.
Local MLflow records development. The public aggregate result is
`experiments/xt-v1/results.json`; private artifacts live in ignored `artifacts/xt-v1`.
Publication stores the aggregate report/surface in `dataset_reports`; serving uses
pure Python lookup and imports no model-fitting runtime. Any reingestion invalidates
the report. Republish only after the snapshot and artifact locks validate.
