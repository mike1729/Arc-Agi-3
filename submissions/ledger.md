# Submission Ledger

Every submission is one row. Preserve failed and negative-result submissions as carefully as successful
ones.

| Date (UTC) | Submission ID | Commit | Config diff vs previous | Ablation | Hypothesis | Result | Wall-clock to result | Warnings |
|---|---|---|---|---|---|---|---|---|
| 2026-07-25 | Kaggle notebook Version 2, `scriptVersionId=337941384` | Official pinned starter V13, `scriptVersionId=306264908` (`+0/-0`; local repo HEAD `01fc46a7e86d12a43f32680b1f855aa3d59e321d` was not the submitted payload) | First submission; untouched copy of the official pinned Random Agent | — (path proof) | The official starter passes both Kaggle's visible validation and hidden competition rerun without payload changes | Visible validation: **PASS** — Version 1 run `337941208`, 20.3 s; submitted Version 2 visible run: **PASS**; hidden rerun: **RUNNING**; public score: pending | `>33 min`, still running when last checked at 2026-07-25 21:12 UTC | None reported while running |

## Column rules

Fixed before the first row so that row 1 and row 20 are comparable. Fields are the union of §5 (every
submission) and §3.1 item 3 (the S0 row specifically).

- **Config diff vs previous** — diffed against the *previous submission*, not against `main`. The
  comparison is what makes this column an ablation rather than a description.
- **Ablation** — the one component contrast this submission represents. **S0 is the standing exception:**
  it is the starter untouched, proving the external path, and represents no contrast — write
  `— (path proof)`. Any *other* empty cell here is a lapse, not an exception (§9).
- **Result** — record **both passes separately**: validation *and* the hidden rerun, plus the score if
  one is returned. A green validation with a failed rerun is the exact failure mode S0 exists to catch
  (§3.1 item 2); a single collapsed verdict hides it.
- **Wall-clock to result** — submission to final report. Under the 1/day quota (V13) this is the number
  that says whether a retry fits inside the same day or costs the next one.
- **Warnings** — any warning text, verbatim, *including on a submission that passed*. A warning on a
  green run is the cheapest early signal available.
