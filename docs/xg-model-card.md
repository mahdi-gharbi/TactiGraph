# xG v1 — model card

<img src="../frontend/src/assets/statsbomb-logo.png" alt="StatsBomb — data provider" width="130" />

## Intended use

Estimate the probability that an observed non-penalty shot becomes a goal in sampled WSL
event data. This is descriptive chance quality, not a guarantee, match-outcome prediction,
player ranking or causal account of why a team won. Data provided by StatsBomb; attribution
and publication boundaries are in the README. No tracking or freeze-frame features are used.

**Serving model: regularized logistic regression (C=1), without sigmoid calibration.**
Serving selection was locked before final-test access on 22 September 2026.

## Reproducible data and target

Source commit: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`.
The immutable split contains 194 training, 89 tuning, 42 calibration and 132 final-test matches.
Non-penalty eligible shots: 4,993 training, 2,223 tuning, 988 calibration and 3,506 test.
The refitted model uses the 7,216 train+tuning non-penalty shots. Because sigmoid was rejected,
the 988 calibration shots were not used to fit the serving model or its preprocessing.

The target is the provider Shot outcome Goal. Own-goal annotations are not shot-learning
targets; shootouts are excluded. One non-penalty shot at x=120.1 lies outside the nominal
pitch and is excluded from model fitting/prediction, but retained in source counts and
event evidence. The API exposes partial prediction coverage for its match (3775652).
The application stores 11,815 predictions against 11,816 recorded shots across the corpus.

## Features and preprocessing

Allowlisted features: x/y origin, distance to goal centre, angle between posts at (120,36)
and (120,44), body part, shot type, technique, first-time flag, play pattern, pressure,
preceding same-team controlled action in the same possession and elapsed time since its
start, plus an earlier linked assisting pass's cross/cutback flags, height and origin.
Geometry uses StatsBomb coordinate units, not metres. Source attacking orientation is retained.

An assist must precede the shot and share team, possession and period. No future shot-assist
flags, shot endpoints, goalmouth information, outcome, goalkeeper response, provider xG,
team/player identity, final score or future possession statistics enter the feature matrix.
Provider xG is stored separately solely for the uncontrolled reference comparison.

Numerical imputation, missingness indicators, standardization and one-hot vocabulary fit
only on the relevant fitting partition. Unseen categories are ignored. The schema adapters
interpret omitted supported truth-only first-time/pressure flags explicitly; unknown schemas
retain unavailable values. Last controlled action means a preceding event, not a tracking state.

## Prespecified development procedure

Logistic C search: 0.1, 1, 10. Eight constrained LightGBM configurations vary leaves (7/15),
minimum child samples (40/80), and L2 (1/5). Learning rate .04; max depth 5; at most 1,200
trees; early stopping after 70 rounds on tuning log loss. Selected LightGBM: seven leaves,
40 minimum child samples, L2=5 and 144 trees. All random seeds are 2026.

For each selected family, a sigmoid candidate fits three-fold match-grouped training OOF
predictions. Retention requires tuning log loss to improve by at least .001 and Brier not
to worsen. Both sigmoid candidates failed. Neither is retained; no final-test information
was used in that choice. The calibration partition is reserved, not silently merged into fitting.

LightGBM's raw tuning log loss was .311393 versus logistic .313626. Its paired match-bootstrap
95% log-loss difference interval was [-.007923, .003006], crossing zero. The rule therefore
kept logistic. Hyperparameter selection and calibration selection reuse tuning observations;
their scores are development estimates, not final performance estimates.

## Final future-season evaluation

3,506 non-penalty shots, 402 goals, 132 matches in 2023/24. Probability scores use full precision;
numbers below are rounded for presentation. PR-AUC means average precision.

| Model | Log loss | Brier | ROC-AUC | PR-AUC |
| --- | --- | --- | --- | --- |
| Fitting-data prevalence | .356235 | .101530 | .500000 | .114661 |
| Logistic, serving | .314618 | .090669 | .735689 | .326107 |
| LightGBM | .315033 | .091184 | .738840 | .320776 |

Logistic 95% intervals: log loss [.295418, .333565], Brier [.083703, .097391].
Paired LightGBM minus logistic log-loss interval: [-.003829, .004628]. These are percentile
intervals from 1,000 draws of whole matches, retaining every shot in a drawn match. They do
not establish a reliable superiority of LightGBM. Final results did not change the serving choice.

Logistic test calibration intercept .106 and slope 1.048 are diagnostic fits on test predictions,
not additional calibration applied to the model. Reliability bins retain denominators. A constant
prevalence predictor cannot identify a simultaneous intercept and slope; that diagnostic is
omitted from its published result. Slice metrics below 30 shots are withheld; small slices remain
uncertain. Permutation importance uses five shuffles per raw feature on held-out shots and is
descriptive, not causal. Standardized logistic coefficients are also exported.

## Penalties

Penalties use Beta(1,1) smoothing of 52 goals in 69 train+tuning penalties: 53/71 = .746479.
The test has 23 penalties, 18 goals; penalty Brier .171438. Penalty estimates are separate
from non-penalty model metrics and separately identified in match totals and shot citations.

## Team-disjoint stress test

Five frozen ID-based groups remove all fitting and calibration matches involving their teams.
Preprocessing and coefficients are refit from scratch on the remaining train+tuning matches;
calibration would also be refit without those teams if retained. Evaluation uses only the
held-out teams' later-season shots. Primary hyperparameters remain fixed from the main experiment,
which included these teams: this is a fitting-disjoint stress test, not independently nested
unseen-team model selection. Per-fold reduced counts and metrics are exported and displayed.

## Limitations, provenance and replication

Temporal shift across the 2020/21–2023/24 gap, limited sample size, missing defensive information,
and event-provider conventions limit generalization. Recurring teams across seasons are deliberate
in the main split. Training/tuning match predictions shown in Match Lab are explicitly in-sample.
StatsBomb xG is an uncontrolled reference with unknown training overlap and information access.

`artifacts/xg-v1/lock.json` records code, protocol, split and artifact hashes and the MLflow run ID.
`test-access.json` records first access before test events are loaded. Repeated evaluation commands
return cached results. All future versions must disclose that the original final test has been
inspected. Do not tune against this version's published test metrics and call the same test fresh.

Run `tactigraph xg develop`, `tactigraph xg evaluate`, then `tactigraph xg publish` after ingestion.
Only the offline environment needs the modeling dependencies. The web application reads stored
probabilities and their model provenance; it never executes a pickle or fits a model. Reimporting
affected match data marks its model release stale and disables serving until a reviewed release.

Implementation references: [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html),
[LightGBM early stopping](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.early_stopping.html),
[MLflow local tracking](https://mlflow.org/docs/latest/ml/tracking/).
