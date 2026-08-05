# E2 retro re-grade — recorded rule proposals under repair semantics, vs a tolerance-mining control

**2026-08-05. Task note for agent execution. Zero model calls, 2–4 h.** Runs **before
the slice-2 night**; its outcome resolves the channel-D conditional in
`notes/e2-slice2.md` and the rule-request conditional in `notes/e2-slice2-build.md`
sub-task 4.

## What and why

External review charged that zero-tolerance verification discards near-miss concepts
("right mechanic, one edge case, whole concept dead"). The measured provenance of the
slice failures says otherwise — most proposals were restatements or support-1 vacuities
— but the charge has one true premise: **a tolerance-graded rule channel was never
actually run** (slice 1.1 deliberately changed only the display). Every proposal is
recorded, so the question is answerable retroactively at zero model cost. The known
candidate case: slice 1's tu93 rule at **312 support / 7 contradictions (2.2%)**,
killed by zero tolerance.

## Inputs

- Recorded proposals with verification: `cells[].verification` in `logs/e2_slice.json`
  (82), `logs/e2_slice_seed1.json` (57), `logs/e2_slice_seed2.json` (51) — each row
  carries the rule string, `support_on_store`, `contradicted_on_store`.
- Store `logs/e1_store_v2/` (frozen) · loader pattern `e2_dose.load_store`.
- Floors: **v1 primary** (`logs/e2_dose.json`) — the proposals were elicited under v1
  digests, same convention as the probe-channel scoring; v2
  (`logs/e2_dose_vocab_v2.json`) reported alongside.

## Arms

- **A — tolerance keep.** Keep proposals with contradiction rate
  `contradicted / (support + contradicted)` under ε, for the whole sweep
  ε ∈ {1%, 2%, 5%, 10%} — report all four, choose nothing. Union kept rules with the
  floor rules; score human L1/L2 per game vs floor (the `e2_slice` union machinery).
- **B — re-guard credit.** Credit the *concept*, not the string: for each proposal,
  take its (action key, guard feature) and let the miner re-fit the best value on the
  store; keep the re-fit if it beats the proposal's own contradiction rate. This scores
  "named the right feature" — the conceptual-prior standard the review demands. Union +
  score as in A.
- **C — the mechanical control: a tolerance tier.** No model anywhere: per unresolved
  key, mine the best single guard with minimal contradictions, same ε sweep. Union +
  score. **This is the credit test.** If C moves floors as much as A/B, the value is
  the tolerance *mechanism* and the miner should simply grow a tolerance tier; the
  model's proposals get no credit for it.

## Pre-committed readout (directions, not thresholds)

Per game × arm × ε: union deltas vs floor (v1 primary, v2 reported), rules kept, their
supports/contradiction rates.

1. **A or B beats the floor where C does not** → the rule channel returns to slice 2 as
   channel D, with the repair bar set from this sweep (measured, not invented).
2. **C ≥ A and B everywhere** → the drop is final; separately, if C itself beats the
   floor, file the tolerance tier as a zero-model miner improvement (its own follow-up
   — that would be a real win, just not the model's).
3. **Nothing moves** → the drop is final and the review's point 1 is closed with data.

Append results here, then update the one-line conditionals in `notes/e2-slice2.md` and
`notes/e2-slice2-build.md` (dated).

## Cautions

- The slice-2 build agent is live in this tree (DSL committed, prior library in
  progress). New files only: `agent/harness/e2_regrade.py`, `logs/e2_regrade.json`. Do
  not touch `e2_dsl.py`, `e2_prior_library.py`, `e2_slice.py`, or other agents' notes.
  `git status` before committing; stage only this task's files.
- Timing: finish before the night is scheduled. If the bundle's sub-task 4 starts
  first, its default (rule request removed) stands and a positive result becomes an
  addendum — coordinate through the conditionals, not through file edits.
- No invented thresholds — the ε sweep is reported whole; the repair bar, if one is
  ever set, comes from these measurements.
- Proposals may parse oddly across slice generations (slice 1 predates the grammar
  statement); a proposal that cannot be re-bound to (key, feature, value) is counted
  `unbindable` and reported, not silently dropped.

## Estimate

2–4 h agent time; compute minutes (re-scoring is the `e2_dose`/`e2_slice` union path).
