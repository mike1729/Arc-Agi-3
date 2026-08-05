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

---

# Result — 2026-08-05. **Readout direction 2: the drop is final; the tolerance tier is a
real zero-model miner win.**

Harness `agent/harness/e2_regrade.py` · results `logs/e2_regrade.json` · readout regenerable
with `e2_regrade.py --report logs/e2_regrade.json` (the console dump and run log are
gitignored). Zero model calls. 190 recorded
proposals over 36 cells (3 slices × 6 games × 2 doses), both vocabularies, ε ∈ {0, 1, 2, 5,
10 %}. Keep rule: `support > 0 and contradicted / (support + contradicted) <= ε`, so ε = 0 is
the committed zero-tolerance rule verbatim, carried as the anchor.

## Two reproduction gates, both passed

The recorded `verification` rows carry no effect, so proposals were re-bound from the
extraction traces. Under **v1 — the vocabulary the proposals were elicited under** — all
**36/36** cells reproduce their recorded rule ids, supports and contradiction counts, and
**36/36** reproduce the committed *union* accuracy at ε = 0 (the whole scoring path, not
just the re-binding). Recomputed floors match the committed `logs/e2_dose.json` for all six
games. Under v2, 36/36 re-bind and 30/36 match the committed union — the six exceptions are
all **ft09**, whose floor moved 0.2522 → 0.3017 when `clicked_adjacent_to` was adopted after
the slices ran. That is the known v2 effect, not a discrepancy.
**Unbindable: 2 of 190** (both ft09 slice-1 dose-125, the recorded `parse_rejected` pair).

## The headline (v1 primary; v2 differs by ≤ 0.02 and changes no direction)

Summed union-accuracy delta vs the miner floor over the **12 distinct (game, dose) cells**,
A and B averaged across the three slices. Arm C is model-free and identical in all three
slices, so summing raw cells would count it 3× — this table is the like-for-like one.

| ε | A: L1 | B: L1 | **C: L1** | A: L2 | B: L2 | **C: L2** |
|---|---|---|---|---|---|---|
| 0 % | +0.0391 (+4/−0) | +0.0380 (+5/−1) | **+0.5303 (+7/−1)** | +0.0075 (+2/−0) | −0.0755 (+1/−1) | **+0.1390 (+5/−0)** |
| 1 % | +0.0452 | +0.0442 | **+0.5303** | +0.0112 | −0.0718 | **+0.1390** |
| 2 % | +0.0502 (+4/−0) | +0.0492 (+5/−1) | **+0.5451 (+8/−1)** | +0.0125 | −0.0705 | **+0.1427 (+6/−0)** |
| 5 % | +0.0502 | +0.0492 | **+0.7169** | +0.0125 | −0.0705 | **+0.1752** |
| 10 % | +0.0502 (+4/−0) | +0.0492 (+5/−1) | **+0.7732 (+8/−1)** | +0.0125 (+2/−0) | −0.0705 (+2/−1) | **+0.1890 (+7/−0)** |

**C ≥ A and B at every ε, on both targets, by 10–15×.** Per game (v1, L1, ε = 2 %): dc22
A/B +0.003 vs C +0.061 · ft09 all three 0.000 · ls20 A 0.000, B +0.104, C +0.225 · m0r0
A/B 0.000, C +0.087 · tu93 A +0.104, B −0.004, C +1.000 · vc33 A/B +0.044, C +0.263 (these
per-game rows are summed over 6 cells, so they are 3× on C — the corrected comparison is the
table above).

**Tolerance buys the model almost nothing.** Widening ε from 0 to 10 % moves arm A by
+0.011 (L1) and +0.005 (L2) in total, across all twelve cells. Of the 190 proposals only
**13** sit in the near-miss band 0 < rate ≤ 10 %; 20 are kept at ε = 0 and 33 at ε = 10 %,
and **41 have zero support on the store at all**. The review's premise that a graded channel
was never run was true; the conclusion that it was hiding near-misses is not — the band is
nearly empty, and the largest near-misses (tu93's `A:*|adj:4:*` family, 89–119 support at
1–2 %) are restatements of the same movement mechanic the control finds by itself.

**Arm B — conceptual credit — is the weakest arm, not the strongest.** 60 of 190 proposals
re-fit to something that beats their own contradiction rate (75 name no guard feature at
all), but firing those re-fits *hurts* L2 (−0.07 summed, driven by tu93 at −0.25). Naming
the feature is not worth credit here: the miner can find the same feature mechanically, and
where the model's (key, feature) pair differs from the miner's choice, it is worse.

## Two honest exceptions, both sub-threshold

There are 11 (cell, ε, target) points in v1 where A or B beats the floor and C does not:
five are **dc22 dose-125**, where C mildly *hurts* (−0.0047) while A gives +0.0031; six are
**tu93 dose-full at ε ≤ 1 %**, where tu93's best-feature cells sit at ~2 % and C therefore
keeps nothing, while A/B give +0.007…+0.02. At ε ≥ 2 % — the tolerance regime the review is
actually arguing for — C dominates tu93 by +0.24…+0.32 per cell. The exceptions are real and
are reported; they are one to two orders of magnitude below C's wins and none of them is a
rule channel worth a night of decode.

## The finding that is worth a follow-up, and it is not the model's

**Arm C at ε = 0 already delivers +0.53 (L1) / +0.14 (L2).** Almost the whole control win is
available with *no tolerance whatsoever*. The mechanism is not tolerance: it is that tier 1
is **all-or-nothing** — a feature that resolves most of a key's cells purely and one cell
impurely is discarded entirely and leaves no trace (`rs_e0.key_purity` says exactly this and
declines to act on it). Arm C keeps the *pure cells* of the best-by-contradiction feature and
lets the majority rule cover the rest. Widening ε from 0 to 10 % adds +0.24 on top of that,
so tolerance is the smaller half of the effect.

Best single cell: **tu93 dose-125, floor 0.4778 → 0.7963 (+0.3185) from two kept rules.**
tu93 full store: four unresolved keys, each with one `adj:9:*` feature at a 1.9–2.8 %
contradiction rate — the note's cited case (`A:4|adj:9:right=4`, 312 support / 7
contradictions) is one of its cells, and it is found *mechanically*, without the model.

**Follow-up filed (per readout 2), zero-model, own task —
[`notes/miner-partial-tier1.md`](miner-partial-tier1.md):** partial tier 1 — emit the pure
cells of the best single feature per unresolved key, with an optional contradiction
tolerance on top. It must be measured on the E0 within-L1/L1→L2 protocol before adoption,
not on this re-grade: these numbers come from mining the explorer store and scoring on human
replays, which is E2's protocol and a different question from E0's survival claim.

## Conditionals resolved

* `notes/e2-slice2.md` — the rule-channel drop is **final**. No channel D. Updated below the
  drop paragraph, dated.
* `notes/e2-slice2-build.md` sub-task 4 — the default (rule request removed) **stands**.
* Review point 1 ("zero tolerance discards near-misses") is **closed with data**: the
  near-miss band holds 13 of 190 proposals, and everything tolerance recovers, the mechanical
  control recovers better without a model.
