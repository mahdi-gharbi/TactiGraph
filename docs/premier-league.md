# Men's Premier League 2015/16

The local application supports the complete 380-match 2015/16 season from the
same pinned StatsBomb Open Data commit as the WSL dataset. Select **Premier League
· 2015/16** in the top bar, or open `http://127.0.0.1:8003/?league=premier-league`.
The selector reloads the workspace: matches, audits, evidence, styles and
experiment results all come from the selected league. This is historical event
data, not a live fixture feed or player tracking.

## Isolation and reproducibility

Premier League source files, exports and database live in `data/premier-league/`.
The WSL database remains `data/tactigraph.db`. Premier League model artifacts and
aggregate results use distinct `*-premier-league-v1` versions. No WSL-trained
model is presented as a Premier League model. Until publication completes, model
panels explicitly show unavailable or not-trained states.

The immutable manifest `configs/splits/premier-league-v1.json` splits entire match
dates chronologically, using only dates and IDs to select boundaries:

| Partition | Matches | Dates |
| --- | ---: | --- |
| Training | 228 | Through 23 January 2016 |
| Tuning | 58 | 24 January through 5 March 2016 |
| Calibration | 37 | 6 March through 10 April 2016 |
| Test | 57 | After 10 April 2016 |

This measures later-match performance within one season. It does not establish
generalization to a new season. All Premier League protocols are frozen before
evaluation; subsequent model evaluations reuse the xG holdout and disclose that
it is no longer an untouched project-wide holdout. Styles are descriptive,
fitted on training windows, with seed and bootstrap stability checks.

## Reproduce locally

Run from the project root using the existing Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_premier_league.py
```

The script downloads verified sources, resumes ingestion, audits integrity, then
develops, evaluates and publishes the separate xG, xT and graph experiments and
fits passing styles. Graph development includes three seeds, ablations and team
stress groups and can take substantial CPU time. Progress and errors are printed;
the script stops on a failed command. Resume with the same command. Locked test
results are reused rather than reopened for selection.

Individual commands accept `--league premier-league` **before** the subcommand:

```powershell
.\.venv\Scripts\tactigraph.exe --league premier-league fetch --workers 6
.\.venv\Scripts\tactigraph.exe --league premier-league ingest
.\.venv\Scripts\tactigraph.exe --league premier-league audit
.\.venv\Scripts\tactigraph.exe --league premier-league xg develop
.\.venv\Scripts\tactigraph.exe --league premier-league xg evaluate
.\.venv\Scripts\tactigraph.exe --league premier-league xg publish
```

Use the same develop/evaluate/publish sequence for `xt` and `graph`, then run
`--league premier-league develop-styles`. The existing local launcher serves both
datasets. Public mode does not expose the additional local database; deployment
and independent publication review remain separate work.

## Interpretation

The completed source audit covers 380 matches, 20 teams, 644 players,
1,313,773 events and 9,908 shots. Every corpus integrity check passes.

Published Premier League measurements (57 chronologically held-out matches):

| Experiment | Evaluated sample | Result |
| --- | --- | --- |
| xG, selected logistic regression | 1,551 non-penalty shots | Log loss 0.2842; Brier 0.08125 |
| xT | 15,807 eligible control episodes | Log loss 0.05256; Brier 0.01006 |
| Third-pass forecast, selected LightGBM | 2,541 episodes | Log loss 0.3019; Brier 0.08462 |

The full graph experiment (three seeds, four ablations and five team stress
groups) did not establish a graph-learning contribution under the prespecified
gates. The application therefore serves the LightGBM baseline selected during
tuning. All graph results remain visible, including the negative result.
Four passing-style clusters were fitted on 2,736 windows from the 228 training
matches (training silhouette 0.240). These are descriptive profiles, not
validated tactical categories or predictions of team quality.

The xG selection was locked using tuning comparisons before test evaluation.
These numbers are specific to this historical split. They are not directly
comparable with WSL scores as evidence that one league's model is better.
Full results and match-bootstrap intervals are in the selected league's
Experiments view and the corresponding `experiments/*-premier-league-v1/` reports.

Use Match Lab to select teams and matches, inspect shots, xG, movement xT,
passing networks, periods, player-removal sensitivity and third-pass forecasts.
Evidence Analyst uses the selected league's stored evidence. Its previous WSL
benchmark and curated showcase are not Premier League validation: no separate
Premier League analyst benchmark or human-reviewed showcase has been claimed.
Experiments displays only the selected dataset's published measurements.

Data provided by StatsBomb. Existing attribution and data-use terms apply.

Two source events have negative durations (one Miscontrol and one Dribble).
Their raw values remain in the checksum-verified cache; normalized duration is
unavailable and the audit records `negative_duration_unavailable` with event ID
and original value. Event counts and match membership are retained. Invalid pass
durations remain ineligible for graph cutoff/edge timing.
