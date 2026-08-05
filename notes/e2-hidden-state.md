# E2 hidden-state loop closure — m0r0's parity hypothesis, machine-checked

**2026-08-05. Task note for agent execution. Zero model calls, compute = minutes.** Third
parallel task; two other agents are live in this tree (probe-channel, S1 contrast) — see
the isolation rule below.

## What and why

The one stable model win across both slices: **every m0r0 cell in both seeds (4/4, plus
slice 1) names a hidden action counter whose parity drives a mode switch.** Seed 1/full:
*"step_count (or turn_index / phase), which advances with every action but is not hashed
into the frame."* Seed 2/125: *"a global binary flag or turn parity counter."* Right now
"correct" is a human reading against game source — a judgment. This task converts it to a
measurement, and in doing so dry-runs the **template a re-scoped slice 2 would be built
on: model proposes a latent → machinery encodes it → measured acceptance.**

Success has two halves, and the verdict must name both:

- **(A) Aliasing**: the proposed counter separates the store's genuinely aliased
  outcomes — conflicts collapse under a counter-augmented state.
- **(B) Load-bearing**: mining with the counter as a guard feature beats the floor on
  held-out human replays — the latent matters for predicting competent play, not just for
  bookkeeping.

A holds and B doesn't → the latent is real but not load-bearing (still validates the
template's verify step). Neither holds → the 4/4 was adjudication error or vagueness
credited as correctness. All three outcomes are decision-grade for slice 2.

## Inputs (verified today)

- **Store** `logs/e1_store_v2/m0r0.*`. Transition rows carry `step` = the global count of
  **all** game actions — every `perform()` increments it (test actions, walk moves, and
  prefix-replay actions alike; verified in `e1_explorer.py`). `graph.json`
  `conflict_records` holds only **3** live-detected conflicts — the full census must be
  recomputed from the log (step 1).
- **Miner**: `rs_e0.mine()` reads features from each Transition's `guards` dict directly
  (verified) — an injected key is picked up with **no edits to any shared file**.
- **Human replays**: `rs_transitions.load_game` — full per-session action order, so every
  counter definition is computable exactly on the human side.
- **Loader pattern**: copy `e2_dose.load_store` (it handles the completion rows whose
  post frame the store lacks).
- **Floor of record**: `logs/e2_dose_vocab_v2.json`, m0r0 rows.

## Isolation — hard rule

New files only: `agent/harness/e2_hidden_state.py`, `logs/e2_hidden_state.json`, optional
rerun sidecar `logs/e2_hidden_state_rerun/` (confirm gitignored with `git check-ignore`).
Do not edit `e1_explorer.py`, `rs_*`, `e2_*`, other notes, or the store — **subclass and
import, never patch.** `git status` before committing; stage only files this task created.

## The arms — parity of *what* is the question

- **C1 global**: `step mod 2` — all actions since environment creation. Free from the
  store as recorded.
- **C2 in-episode**: actions since the last RESET. Not directly recorded (routing actions
  sit between recorded rows, resets are not in the transitions log) — needs the
  instrumented rerun (step 2).
- **C3 controls**: mod 3 and mod 4 of the winning base, plus a seeded random binary
  feature (seeds 1–5, **never 20260804**) as the specificity floor.

State the RESET convention per arm (does RESET itself increment?) and apply it
identically on the store and human sides. Human side: compute session-global and
episode/level-relative variants to mirror C1/C2. Report every arm — no cherry-picking; no
invented thresholds, measured deltas decide.

## Step 1 — conflict census (Test A)

Group the full m0r0 transitions log by `(pre, action)`; groups with ≥2 distinct outcomes
(post hash; effect signature as a second view) are the aliased set. Report its size — the
3 recorded `conflict_records` are only what the explorer noticed live. Then, per arm: the
fraction of aliased groups the feature separates perfectly, and the state-level
restatement: conflicts remaining when the state hash is augmented to `(digest, parity)` —
the "do conflicts collapse to zero" number.

## Step 2 — instrumented rerun (for C2 only; skip if C1 already separates everything)

The explorer is deterministic (fixed policy, hash rotation, REPLAY-DET). Rerun m0r0
through a **subclass** of `Explorer` that logs every `perform()` (action, global index,
reset marker) to the sidecar dir, store untouched. **Gate**: the rerun's transition rows
must match the store (compare counts plus first/last 50 rows). Mismatch → drop C2, report
the mismatch, continue with C1/C3.

## Step 3 — mining with the injected feature (Test B)

Loader + inject `parity:<arm>` into `guards` on both sides. Mine the full store → score
on human L1 and L2; compare against the v2 floor. Dose endpoints 125/full too (seconds).
Also the **ceiling arm**: mine human L1 → score L2 with the feature — does the ceiling
itself move? That is the direct measure of whether the latent is load-bearing for
competent play rather than an explorer-side artifact.

## Step 4 — cross-game sanity

Inject the winning definition for all 24 games (same loader; `step` exists in every
store): m0r0 should improve, others should not regress (vocab-v2 acceptance style). Any
*other* game that improves is a finding, not noise — g50t and sc25 have conflict/walk
history in their E1 records.

## Report (append a results section to this note)

1. Census size vs the 3 recorded; per-arm separation fractions; conflicts remaining under
   the augmented hash.
2. Rerun gate: C2 available or dropped, and why.
3. Mining deltas per arm vs the v2 floor (store→L1, store→L2, ceiling arm, controls).
4. Cross-game table.
5. Verdict on m0r0: which counter, if any — with both halves (A, B) stated separately.
6. Verdict on the **template**, ≤1 paragraph: does "model proposes latent → machinery
   encodes → measured acceptance" close as a loop, and what interface would slice 2 need
   from the model for it (executable definitions vs prose)?

## Cautions

- Game source under `data/` is readable but never quoted into committed artifacts
  (PUBLISHING.md; labels/paraphrases only). Quoting Qwen's traces is fine — our artifacts.
- The 4/4 is not independent evidence of discovery from nothing: m0r0 is the only game
  whose digest *showed* alias-conflict lines — the model answered from real evidence.
  State this in the writeup; don't oversell.
- Several arms on one small game = multiple comparisons. The controls plus the
  two-halves requirement are the guard; report all arms including the dead ones.
- Working choices labelled (w); no invented numbers.

## Non-goals

No slice-2 design, no digest or prompt changes, no model calls, no in-place store
regeneration, no hypotheses for other games (m0r0 is the only stable one on file).

## Estimate

3–5 h agent time; compute minutes (one explorer rerun + mining arms).
