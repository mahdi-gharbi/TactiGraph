# Third-pass shot prediction — graph-v1

## Target and information boundary

Predict whether an eligible open-play control episode produces a subsequent shot, after
its third completed pass. This is a shot-occurrence probability, not xG or a forecast of
the match winner. At most one sample is taken per episode. Regular Play and From Counter
are eligible; restart and rebound episode starts are excluded. The recipient and endpoint
must be valid and active at completion. The replayed team must have 7–11 players.

The cutoff time is the third pass's timestamp plus recorded duration. Source indices
after this pass are inaccessible to feature extraction, including later Ball Receipt
events, substitutions and goals. Last observed locations are historical on-ball
observations. They never represent a reconstructed formation or off-ball positioning.

Nodes are players active at the cutoff, reconstructed from the prefix alone. Edges are
completed passes in the preceding five minutes of the same period, including the current
prefix. Repeated passes remain separate directed edges. Edges involving players no longer
active are excluded and counted. Last observations may be older than five minutes, with
their age and missingness exposed. No location history crosses halftime.

Player/team identifiers and sample identifiers are metadata, never numeric predictors.
Node roles use a fixed provider-schema vocabulary rather than learning a vocabulary from
future matches. Counts and coordinates use fixed documented scaling. Logistic scaling
is fitted only on the permitted fitting partition. Own goals enter preceding score state
through Own Goal Against events; final scores do not enter features.

## Models and selection

The frozen protocol is `configs/graph-v1.json`. Baselines are prevalence, regularized
logistic regression on prefix/global features, and constrained LightGBM with six additional
NetworkX summaries. There are three logistic and four LightGBM configurations.

The neural model has two GINE layers, width 32, dropout 0.2, mean node pooling, the ball
holder representation and global features. Seeds are 2026, 2027 and 2028. Four ablations
remove message passing, remove earlier-episode edges, remove edge timing/spatial attributes,
or randomize connectivity while preserving node features, edge attributes and edge count.
Randomization does not preserve degrees. Node/edge feature definitions and dimensions are
in `models/graph_features.py`; the schema is versioned as `third-pass-prefix-v1`.

Train/tuning/calibration/test match IDs follow `configs/splits/wsl-v1.json`. Select
hyperparameters and neural epochs by tuning log loss, refit on train+tuning, and fit sigmoid
calibration only on calibration matches. Report both raw and calibrated metrics; use
calibrated predictions for the prespecified final comparison. Never choose calibration
after seeing the test results.

GNN justification requires its mean log loss over three seeds to beat the strongest
tabular baseline with a paired match-bootstrap 95% difference interval below zero, mean
PR-AUC no worse, and credible improvements over both no-message and randomized-connectivity
ablations. Otherwise select the tabular family chosen by tuning log loss. A negative graph
experiment remains a valid result. Seed averages describe metrics, not an ensemble.

Five deterministic team-disjoint stress groups exclude every fitting, tuning and calibration
match involving a held-out team. Test only those teams' later-season actions. Primary
hyperparameters/epochs remain fixed; this is not an independently retuned unseen-team study.

## Reproduction and artifacts

```powershell
uv sync --frozen --extra dev --extra modeling --extra graph
tactigraph graph dataset
tactigraph graph develop
tactigraph graph evaluate
tactigraph graph publish
```

CPU PyTorch and PyTorch Geometric are optional offline dependencies. The web application
reads an exported aggregate report and imports neither training framework. No training runs
in response to an API request. The local MLflow experiment records development metrics.

Private Parquet samples, checkpoints, source audits and locks reside under
`artifacts/graph-v1/`. Development caches verify source and feature hashes. Completed model
checkpoints are resumable under unchanged inputs. Final-test access requires frozen artifact,
protocol, split, data and source hashes and an exclusive access marker. A failed test run
must not silently start again as a new evaluation; inspect the failure explicitly.

Only completed aggregate results are published to `experiments/graph-v1/results.json` and
the Experiments page. Until then the page reports that the graph experiment is not evaluated.
No synthetic score is substituted for an unavailable result.

## Evaluation and limitations

The locked evaluation completed on 24 September 2026: 6,607 eligible episodes across all
132 final-test matches, including 566 later-shot episodes. Development contained 8,252
training, 3,893 tuning and 1,725 calibration samples. Every source episode is accounted
for in the local exclusion audits.

| Model | Log loss | Brier | PR-AUC |
| --- | ---: | ---: | ---: |
| Prevalence | .292480 | .078341 | .085667 |
| Logistic | .261335 | .071667 | .256351 |
| LightGBM + summaries | .249144 | .066991 | .350951 |
| Full GINE, mean of 3 seeds | .260677 | .070898 | .279229 |
| No message passing | .253267 | .069008 | .314834 |
| Current episode edges only | .253973 | .068954 | .317732 |
| No edge timing/space | .262016 | .071680 | .258918 |
| Random connectivity | .264892 | .072411 | .243985 |

The paired GINE-minus-LightGBM log-loss interval is [.008150, .015127]; GINE also loses
to the no-message ablation [.004461, .010638]. It beats random connectivity
[-.007467, -.000830], but this alone does not establish a useful graph contribution.
**Decision: retain LightGBM**, already chosen as the strongest tabular family on tuning.
Its held-out ROC-AUC is .741737. The complete per-seed, calibration, uncertainty and
team-disjoint results accompany the exported report. No hyperparameters changed after
this evaluation.

Report log loss, Brier, ROC-AUC, PR-AUC, reliability bins, calibration intercept/slope,
sample sizes, paired match-bootstrap intervals (1,000 draws), all seeds and ablations.
Warm CPU latency covers a prepared sample: 20 calls after three warmups, excluding feature
extraction and model loading. Hardware and thread count accompany the export.

The 2023/24 season was already inspected for xg-v1 and xt-v1. This graph protocol is locked
before its own test evaluation, but the project-wide holdout is no longer untouched.
Recurring teams across seasons are intentional. Results apply to this sampled WSL release,
not all football. Event-derived control and possession boundaries are imperfect; there is
no tracking or separate 360 coverage. Predictions do not establish tactical causation.

Data provided by StatsBomb Open Data, pinned to
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`. Source files and derived sample tables are private,
excluded from Git and public container images. Code licensing does not cover upstream data.
