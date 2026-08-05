# S1 clear-vs-stall contrast — what the reference did when it worked

**2026-08-05. Task note for agent execution. Zero model calls, zero compute** — trace
reading plus one mechanical cross-tab. S1 here is the sprint stage (the reproduced
reference agent on the FP8 stack, thinking on — its measurements are VALID; do not
confuse with the voided VP/GI-1/MU screens).

## What and why

S1's stall side was analyzed (the standing `goal_unknown` result: 76% primary, 92%
present, 100% of L1 stalls). Its **success side never was**: nobody has read the traces
of the games it actually cleared. A quick scan (re-derive in step 0) says S1 cleared at
least one level on **4 of 18 games it ran — ar25, sp80, tn36, vc33** — and never scored
on 14, including five of the six slice iteration games.

**The hypothesis under test (H):** the cleared set is exactly the set where the default
goal prior — the "clear the board"/obvious-visual-goal shape that the slice autopsy
showed dominating Qwen's goal channel (2 right / 8 wrong) — happens to match the true
goal. I.e. **the reference never discovers goals; it occasionally gets one for free.**

Either outcome is decision-grade:
- **H holds** → the deployed bottleneck and the slice goal-channel failure are one
  mechanism (same model, same prior, two harnesses); our system only needs to beat the
  reference where the prior fails, which defines the target set.
- **H breaks** → some cleared trace contains real in-context goal discovery. Describe its
  mechanism in detail — what evidence flipped the model off the prior. That is the
  template the M-phase must reproduce, and the first observed instance of the capability.

Feeds: the slice-2 goal-channel decision and the E3/X target-set framing. Recommendation
only — no design decisions in this note.

## Inputs (verified to exist)

- **Runs**: `logs/runs/` — 29 directories, each with `artifacts/*_events.jsonl` (+
  `*_viewer_data.json`), `transcripts/`, `prompts/`, `requests.jsonl`, `run_config.json`,
  `deploy_meta.json`, `stdout.log`. Anything under `logs/quarantine/` is excluded.
- **Working split (w)** — derived by a quick scan of the `score` field in events.jsonl;
  re-derive before use and verify the semantics (score increment = level completed)
  against viewer_data or stdout on one known case:
  cleared: ar25, sp80, tn36, vc33 (max score 1 each) · stalled at 0: bp35, cn04, ft09,
  g50t, ka59, lf52, lp85, ls20, m0r0, r11l, re86, tr87, tu93, wa30 · ~7 public games
  never ran in these dirs (incl. dc22).
- **Stall labels**: `s1d_*` files in `logs/` (draw, pass2, worksheet, result lock) and
  the labeling harness on the archive branch. Inventory what the final labeled corpus is;
  read the archive via `git show archive/screening-line-2026-08-04:<path>` — **do not
  check out the branch** (concurrent agents on main).
- **Slice goal-channel results** for the cross-tab: `cells[].goal` in
  `logs/e2_slice.json`, `logs/e2_slice_seed{1,2}.json`; adjudications in
  `notes/e2-trace-autopsy.md` and `notes/e2-variance-arm.md` §6.
- **True goals**: game source under `data/` — read freely, **never quote into committed
  artifacts** (PUBLISHING.md; git history counts as redistribution; labels/paraphrases
  only). Quoting **S1's own reasoning traces is fine and encouraged** — they are our
  artifacts.

## Step 0 — verify the split, name the arms

Re-derive per-game outcomes from `events.jsonl` across all 29 runs (script it — a small
committed `agent/harness/s1_contrast.py` is welcome; tables from scripts, not by hand).
Group runs by prompt variant from `run_config.json` (kb2, a6c1, d13, dense, supervisor,
…) and report coverage per arm — passes per game are uneven (1–4). Confirm from
`deploy_meta.json` that analyzed runs are the reference-stack lineage; flag any that are
not rather than silently including them.

## Step 1 — the positive set (the new work)

For each cleared pass on ar25, sp80, tn36, vc33: locate the clearing moment in
events.jsonl, then read the transcript window leading to it. Per clear, answer with
quotes:

1. Did the agent **state a goal before clearing**? Quote the statement and its step.
2. Was the stated goal the **default prior shape** or **evidence-derived**? If derived,
   name the evidence in the trace that produced it.
3. **Efficiency split**: actions before vs after the goal articulation. A goal stated
   only after the score moved counts as post-hoc, not discovery.
4. Or was it **accidental** — no articulation, completion stumbled into?

Classify each clear: `prior-match` / `evidence-derived` / `accidental`. This
classification is the heart of the task; support every label with trace text.

## Step 2 — true-goal shapes

From game source, classify the true L1 completion condition of **all 18 run games** (not
just the cleared 4) as prior-compatible ("clear/remove/fill all X"-shaped or visually
self-announcing) or not. Both directions matter: a **prior-compatible game that
stalled** weakens H unless its stall label says the block was mechanics, not goal —
check the label.

## Step 3 — the cross-tab

One table, one row per run game: S1 outcome (per arm) × true-goal prior-compatibility ×
primary stall cause (existing s1d labels; no re-labeling) × slice goal-channel outcome
(where the game is in the slice six). Call out the two anti-examples explicitly:

- **tu93** — S1's largest action budget (294 events), never cleared; yet the only game
  where the slice goal channel ever reasoned to a correct goal (colour-14 inertness).
- **m0r0** — stalled after 36 events; the game whose hidden state the slice channel
  identified 4/4.

## Step 4 — verdict

State per-game support/refutation of H, then one verdict sentence. If refuted, the
refuting trace's discovery mechanism gets its own subsection (what evidence, what
reasoning move, how many actions it took). Close with ≤1 paragraph of implications for
the slice-2 goal channel — a recommendation, not a decision.

## Report

Append a results section to this note: (1) verified split + arm coverage table;
(2) per-clear classifications with quotes; (3) goal-shape table for all 18 games;
(4) the cross-tab; (5) verdict; (6) implications paragraph.

## Cautions

- Judgments (goal-shape classes, clear classifications) are adjudications by one reader —
  label them as such; counts and quotes are mechanical.
- Arms are heterogeneous: never pool cleared/stalled across prompt variants silently.
- No invented numbers; working values labelled (w).
- Concurrent agents share the tree: `git status` before committing, stage only files this
  task created (this note, the script, any small derived JSON in `logs/`).
- Read-only toward everything existing: modify no harness files, no stores, no notes but
  this one.

## Non-goals

No re-running S1, no model calls, no re-labeling of the stall corpus, no slice-2 design,
no game-source quotations anywhere in committed text.

## Estimate

3–5 h agent time (mostly step 1's close reading), zero compute.
