# Passing styles — styles-v1

This exploratory M7 model describes team passing in complete 15-minute windows.
It does not estimate team quality, predict outcomes or establish tactical intent.

## Data and boundaries

The frozen WSL split and pinned StatsBomb source are reused. Standardization, PCA
and four-cluster K-means fit on 2,326 eligible windows from the 194 training matches
only. Another 3,153 windows are projected without refitting. Those seasons were
previously inspected by other experiments and are not a fresh test.

Each team has up to six half-open regulation windows: [0,15), [15,30), [30,45)
within each half. Recorded period coverage must reach the end of the window.
Stoppage time, extra time and shootouts are excluded. At least ten attempted passes
and ten passes with valid start/end coordinates are required. Of 5,484 possible
team-windows across 457 matches, 5,479 are eligible. Set-piece passes are included.

## Features

- Attempts per elapsed minute: all attempted passes / 15, not ball-in-play time.
- Completion fraction: completed / all attempted passes.
- Forward fraction: end x > start x / spatially valid passes.
- Long fraction: Euclidean displacement >= 30 StatsBomb coordinate units /
  spatially valid passes. These are pitch coordinates, not a calibrated metre distance.
- Final-third fraction: end x >= 80 / spatially valid passes, including failed attempts.
- Mean start x: mean start coordinate of spatially valid passes.

The standardized six features enter full-SVD PCA retaining at least 90% variance.
Four components retain 95.21%. Four clusters were specified before the run; no
claim is made that four is an optimal or natural number of tactical styles.
K-means uses 20 initializations and seed 42. Identities, goals, xG and future
windows do not enter the features. Cluster names use their two largest absolute
standardized mean differences from the training population; the displayed means
remain in original units.

## Measured results and stability

Training silhouette is 0.2675: separation is modest. Five alternate seeds yield
adjusted Rand index (ARI) 0.9807–0.9988 against the reference labels.
Twenty match-level bootstrap refits of the entire scaler/PCA/K-means pipeline
yield ARI 0.8382–0.9585 on the original training windows. Both teams and all windows
of each sampled match travel together. These are descriptive stability ranges,
not confidence intervals, tactical validity scores or out-of-sample accuracy.

The four groups contain 553, 599, 430 and 744 training windows. Their measured
labels describe advanced starting/ending locations, higher passing volume and
completion, lower completion with more forward passes, and deeper locations.
Scores, opponents, dismissals and missing data may explain part of these patterns.
The method does not identify pressing, defensive shape or off-ball movement.

## Serving and reproduction

Run `tactigraph develop-styles` with the modeling extra and complete corpus.
The command publishes aggregate `experiments/styles-v1/results.json`, saves the
local fitted artifact under ignored `artifacts/styles-v1/`, and stores window
assignments in the application database. Source, protocol, split and model hashes
are recorded. Web requests read stored results; they neither train nor load joblib.
Source-manifest changes invalidate serving until profiles are rebuilt.

Match Lab links each profile to paginated source pass evidence with event UUIDs.
The Experiments page exposes the same cluster means and stability measurements.
Public deployment and publication review remain M8 work.
