# Independent semantic review pilot

This pilot checks whether the saved WSL analyst reports are *meaningful and
source-supported* beyond their automatic numerical tests. It does not approve
publication. The separate 36-report and data-rights approval in
`docs/public-release.md` still applies.

Run from the repository root:

```powershell
python -X utf8 scripts/prepare_human_review.py
```

The script verifies report fingerprints, then selects **one report for each of
four seasons × three intents** from the frozen 36-report packet. A fixed hash
chooses among eligible matches without reading the reported values or outcome.
It writes `output/human-evaluation/ratings.csv`. The twelve entries are a
small, stratified pilot within an already coverage-curated showcase. They are
not a random sample of all WSL matches, and no Premier League claim follows.

Ask someone who did not write the report templates to review the twelve rows.
Before scoring, show the report, its question, measurement definitions and
event links in the local Evidence Analyst. Do not show automatic pass counts,
the author's expected answer, or preliminary aggregate results. Check the
underlying event file or cited event rows for each measured claim. Enter the
reviewer's name and ISO date; leave no score blank. Score each dimension:

| Score | Factual accuracy | Source support | Limits clear | Usefulness |
| --- | --- | --- | --- | --- |
| 0 | A material claim is wrong | Evidence is missing or contradicts it | Material uncertainty is hidden | Misleading for the question |
| 1 | Numbers are right, wording is ambiguous | Evidence exists but needs work to verify | Some caveats are incomplete | Partially answers the question |
| 2 | Claims and wording are accurate | Citations directly support measured claims | Main interpretation limits are explicit | Directly answers the guided question |

Set `critical_error_yes_no` to `yes` for a wrong match, period, team, direction,
denominator, source, or causal claim, even if another score is high. Explain
every 0, 1 or critical error in `notes`, with a specific claim and source row.
Unclear cases should be checked by a second reviewer without seeing the first
reviewer's score; preserve both ratings and record an adjudicated decision.

After review, report counts for each score, the number of critical errors and
concrete failure examples. Keep the original worksheet and exact report SHA-256
values. A twelve-report pilot estimates neither population accuracy nor model
generalization. Investigate every critical error, revise the report or metric
code, regenerate fingerprints, then run a fresh review. Do not silently edit
ratings or mark `approvals.json` complete from this pilot alone.
