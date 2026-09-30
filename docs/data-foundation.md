# Dataset foundation

`foundation-v1` processes competition 37 at commit
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`: seasons 4, 42, 90 and 281.
The catalog must contain exactly 107, 87, 131 and 132 matches respectively.
These are available-file counts, not assertions of complete competition coverage.

## Reproduce

Run `tactigraph fetch`, `tactigraph ingest --scope wsl`, and `tactigraph audit`.
Acquisition is bounded to four workers by default; normalization uses one writer and
one transaction per match. Downloaded bytes are checked against local SHA-256 manifests.
The audit and complete source manifest live in ignored `data/reports/`.
Every catalog match has a pending, ready, rejected or export_failed status. No failure
is silently excluded. A failed replacement preserves the prior database transaction.

Ten typed Parquet tables are exported per match. JSON columns are encoded as JSON strings
inside Parquet; parse them explicitly when consuming the analytical files. Empty tables
retain their column schema. These private analytical exports are not public artifacts.
Resume requires the same source hashes, pipeline version and all expected export files.
Use `--force` after a deliberate pipeline change; version changed transformations.

## Coordinate, time and missingness contracts

Source coordinates remain in the provider's attacking 120×80 frame. No half-time flip
is applied. Finite coordinates outside that range remain in storage and receive an
event-level quality flag. They are not clipped into an edge zone or plotted on the pitch.
Shot totals and their citations still include such observations.

Events are ordered by unique source index. Period-local milliseconds and displayed
minute/second remain separate. Stoppage time never becomes the start of the next half.
Schema versions 1.0.2, 1.0.3 and 1.1.0 receive explicit pressure adapters: omitted
`under_pressure` is interpreted as false for passes, shots, carries and dribbles only.
Other omitted contexts and unknown schemas remain unavailable. The raw omission, adapted
value and adaptation status are separate fields. Freeze-frame features are not used.

## Compositions, possessions and episodes

Lineup stints replay Starting XI, tactical shifts, substitutions, dismissals and temporary
player exits/returns. Their source-index intervals are half-open. Half-time does not
remove players. Each boundary retains its source UUID. An action by a player absent
from the reconstructed active set generates a quality flag, not an invented stint.
Final stint ends are descriptive fields, never predictive features. Prediction code must
use `replay_active_players`, which reads only events observed through the cutoff.

Provider possessions retain all event membership, including opponent defensive events.
Control episodes include only the owning team's controlled actions. Shots, losses,
restarts, period boundaries and recorded stoppages terminate episodes. A rebound starts
a new episode after the shot. Failed recoveries and unsuccessful interceptions do not
create retained actions. Each eligible action belongs to at most one episode. Terminal
reasons are explicit; xT terminal-transition construction belongs to M4, not this release.
Score state is updated after each observed goal; stored context contains the preceding score.

## Splits and EDA

`configs/splits/wsl-v1.json` freezes exact IDs, dates, teams and a canonical SHA-256 digest.
No score, shot or event outcome participates in splitting. Seasons 4 and 42 train;
season 90 uses the date boundary closest to two-thirds of its matches for tuning, keeping
whole dates together; season 281 is the future-season test. Counts: 194 / 89 / 42 / 132.
Changing an existing manifest is rejected. Sorted team IDs are assigned round-robin to
five fixed stress-test groups; future experiments must remove every fitting match
involving the held-out group, including calibration. This grouping is not yet an evaluation.

Overview distributions and team/player profiles use training matches only. The other
partitions expose coverage and source-quality checks, not model-selection summaries.
Source validation and optional manual Match Lab exploration are not a held-out model
evaluation. Record any future test inspection when conducting experiments.

The dashboard reports missingness separately from validation errors. Event types such as
Starting XI legitimately lack locations. Player profile match counts mean matches with
recorded actions, not appearances or exposure minutes. Shot-frequency rankings do not
measure player quality. No models have been fitted or evaluated in M2.
