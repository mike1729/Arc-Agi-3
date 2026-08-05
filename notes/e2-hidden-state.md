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

---

# Results — 2026-08-05

Machinery: [`agent/harness/e2_hidden_state.py`](../agent/harness/e2_hidden_state.py) (new).
Numbers: [`logs/e2_hidden_state.json`](../logs/e2_hidden_state.json). Rerun sidecars in
`logs/e2_hidden_state_rerun/` (gitignored). Zero model calls; ~12 min compute. Isolation held
— no shared file edited, `Explorer` subclassed and imported.

**Headline: the latent is real, and the model's description of it is wrong.** m0r0 does carry
a hidden action counter that gates the outcome of a visibly identical board; it is
**in-episode** (RESET zeroes it), not global. But **parity is refuted** — the counter's effect
is not `mod 2` — and the counter is **not load-bearing**: every mining arm, at both dose
endpoints, on both effect modes, is at or below the v2 floor, and indistinguishable from a
seeded random bit.

## 1. Census (step 1) — empty by construction, and that is the finding

| quantity | m0r0 |
|---|---:|
| store transition rows | 2943 |
| distinct `(pre, action)` groups | 2943 |
| groups with ≥2 rows | **0** |
| aliased groups (post hash / effect signature) | **0 / 0** |
| `graph.json` `conflict_records` | 3 |

The note's step 1 assumed the log could disagree with itself. It cannot: the explorer appends
a row only from `test()`, and `test()` pops each candidate from a state's frontier exactly
once, so a repeated `(pre, action)` row is unreachable. The three recorded conflicts came from
*routing* actions, which are never recorded as transitions. **The store as designed cannot
measure aliasing**; that is a property of the instrument, not evidence that m0r0 is
alias-free, and it is the first thing a slice-2 design has to fix.

The instrumented rerun recovers the routing actions and lifts the census to **6 repeated
groups, 3 aliased** — still far too small to decide half A, which is why the probe below was
added as a declared deviation.

Per-arm separation over those 3 groups, reported for completeness and trusted for nothing:

| arm | cells | separates | conflicts remaining under `(digest, feature)` |
|---|---:|---:|---:|
| baseline (digest only) | — | — | 3 |
| `c1_global` | 1 | 0/3 | 3 |
| `c2_episode` | 2 | 2/3 | 1 |
| `c2_episode_incl` | 2 | 2/3 | 1 |
| `c1_global_m4` | 2 | 1/3 | 2 |
| `c1_global_m3` | 2 | 3/3 | 0 |
| `c2_episode_m3` | 3 | 3/3 | 0 |
| `c2_episode_m4` | 3 | 3/3 | 0 |
| **`rand4`, `rand5`** (control) | 2 | **2/3** | **1** |
| `rand1`–`rand3` (control) | 2 | 1/3 | 2 |

The controls settle it: two of the five seeded random bits **tie `c2_episode` exactly**, and
`c1_global_m3` "wins" on n=3 only because more cells separate more by arithmetic alone. This
census is not evidence for anything, which is why the probe exists.

## 2. Rerun gate — passed, on all 24 games

m0r0: 2943/2943 rows byte-identical to the store, counts and first/last 50 matched, and in
fact **every row matched**. C2 is therefore available and the step-index join between store
rows and rerun counters is licensed.

Then, beyond the note's ask, the same rerun was run for all 24 games (`--stage rerun_all`):
**24/24 gates pass, all rows identical**. That is an independent REPLAY-DET confirmation over
the whole public set at ~66k actions, not just m0r0. Rerun census across games — aliased
groups: g50t 43, cn04 4, m0r0 3, sc25 3, cd82 1, all others 0. g50t and sc25 having live
aliasing matches their E1 records; g50t is the only game where the store holds enough repeated
observations for a passive census to mean anything — §7 runs it there.

## 3. The probe (declared deviation) — what the latent actually is

Two abandoned instruments first, because their failure is itself evidence:

- **Self-loops are not self-loops.** The padding design in the note's spirit — repeat an
  action the store recorded with `post == pre` — fails at the *second* application: the same
  click at the same board is a no-op once and moves the board next time. The instrument broke
  on the very effect it was built to measure.
- **`graph["prefix"]` does not replay.** RESET + the explorer's stored prefix lands on a
  different digest for 12 of 15 sampled states, and identically so for one, two or three
  RESETs. Stored prefixes are stale; every route here is built by execution instead.

**P1 — does a counter survive RESET?** `RESET; k filler; RESET; path; target`, k = 0…5, so the
in-episode count is fixed and the count since environment creation varies. 15 targets (the 3
conflicted edges plus 12 clean controls), 90 executions, all usable, parity falsifiable on
every one. **0/15 vary.** The counter is zeroed by RESET; the global reading `c1_global` is
refuted.

**P2 — does the in-episode count gate the outcome?** Executed paths of different length to the
same digest, three distinct routes per length as the content control. 24 states × 3 target
actions = 72 targets, 582 executions.

| result | value |
|---|---:|
| targets whose outcome varies with path length | **72/72** |
| lengths where distinct same-length routes disagree | **0** |
| targets where parity was falsifiable | 72/72 |
| targets where **parity** explains the variation | **0/72** |
| observed length→outcome pattern | `(6, 7) agree, 8 differs` — 72/72 |

The control is what makes this a claim: three different routes of the same length always
produce the same outcome, so the outcome is a function of `(board, in-episode action count)`
and not of which actions were taken. And with three counts available, parity is testable and
**fails** — 6 and 8 share a parity class and do *not* share an outcome.

Limit, stated plainly: the path search can only offer the length band `[6, 7, 8]` at a shared
digest (72 digests, one band, at every search depth tried up to 13). Three consecutive counts
distinguish "not parity" from "parity", which is the question asked, but they cannot
distinguish a threshold from a longer period. **The counter exists and is in-episode; its
functional form is unresolved beyond "not mod 2".**

## 4. Mining with the injected feature (step 3) — half B fails, cleanly

Baseline reproduces the v2 floor exactly (m0r0, full mode: L1 0.2624, L2 0.3988, ceiling
0.3514; moveset: 0.4869 / 0.5283 / 0.5283). Injection was verified to reach the miner: an
oracle feature equal to the effect is selected 38 times, so `selected = 0` below means the
feature carries no signal, not that the wiring is broken.

**Full store (the dose that matters):** every arm — `c1_global`, `c2_episode`,
`c2_episode_incl`, the mod-3/mod-4 controls, and all five random bits — leaves L1 and L2
**unchanged to four decimals**, with the feature selected **0 times**. Weighted purity of every
arm on the store is **0.000**: the feature does not put a single unresolved key's transitions
into a pure cell.

**Dose 125**, where thin evidence lets tier 1 pick it up (2 rules each), every arm that gets
selected **loses**:

| arm | full L1 | full L2 | moveset L1 | moveset L2 |
|---|---:|---:|---:|---:|
| baseline | 0.2362 | 0.3422 | 0.4781 | 0.5272 |
| `c1_global` | 0.2362 | 0.3335 | 0.4781 | 0.5185 |
| `c2_episode` | 0.2332 | 0.3347 | 0.4752 | 0.5197 |
| `c2_episode_incl` | 0.2332 | 0.3347 | 0.4752 | 0.5197 |
| `c1_global_m3` | 0.2274 | 0.3249 | 0.4694 | 0.5098 |
| `c1_global_m4` | 0.2274 | 0.3156 | 0.4694 | 0.5006 |
| `c2_episode_m3` | 0.2332 | 0.3243 | 0.4752 | 0.5092 |
| `c2_episode_m4` | 0.2274 | 0.3150 | 0.4694 | 0.5000 |
| **`rand3` (control)** | 0.2362 | 0.3387 | 0.4781 | 0.5237 |
| `rand1/2/4/5` | 0.2362 | 0.3422 | 0.4781 | 0.5272 |

The seeded random bit `rand3` is selected exactly as the real arms are and loses **less** than
any of them. On human L1 the real arms' purity (0.0059) is *below* `rand3`'s (0.0117). The
specificity floor is not merely reached, it is exceeded by the control.

**Ceiling arm** (mine human L1 → score human L2, the direct load-bearing test): unchanged for
every arm except `c2_episode_m3`, which is selected twice and moves the ceiling **down**
(full 0.3514 → 0.3486, moveset 0.5283 → 0.5254). No arm moves it up.

## 5. Cross-game (step 4)

`c2_episode` injected into all 24 games, store counters joined from each game's own passing
rerun, feature present on both sides in every game: **every delta is exactly 0.0000 on both
targets and both modes; the feature is selected 0 times in every game.** No regressions — and
no improvements, including g50t and sc25, the two games with real live aliasing.

## 6. Verdict on m0r0

- **(A) Aliasing — the latent is REAL, and it is `c2_episode`'s base, not its parity.** The
  outcome of an action at a fixed board is a deterministic function of `(board, in-episode
  action count)`: 72/72 targets vary with the count, 0 same-length disagreements over 582
  executions, and RESET zeroes it (0/15 vary with the global count over 90 executions). The
  model's *counter* claim is confirmed and its *reset scope* is now pinned (in-episode, which
  neither cell said). The model's **parity** claim is **refuted**: 0/72 falsifiable targets are
  explained by `mod 2`.
- **(B) Load-bearing — NO.** Zero effect at full dose on every arm, a loss at dose 125 for
  every selected arm, a loss on the ceiling arm for the one arm that reached it, zero effect
  across 24 games, and the seeded random control performs at least as well as every real arm.
  Under this rule model the counter buys nothing for predicting competent play.

So this is the note's middle outcome — **A holds, B does not** — with one sharpening it did
not anticipate: A holds for the *counter*, not for the *parity*, and the verify step is what
separated the two. The 4/4 was not adjudication error, but it was **partially credited**: a
human reading "hidden action counter whose parity drives a mode switch" against game source
scored the whole sentence on the strength of its correct half.

As the note requires: m0r0 is the only game whose digest *showed* alias-conflict lines, so the
model answered from real evidence in its context. This is not evidence of discovery from
nothing, and it should not be cited as such.

## 7. Addendum — g50t, the one game where the passive census works

Follow-up, same day, operator-requested. Numbers: `logs/e2_hidden_state_g50t.json`. g50t is the
only game whose store holds enough repeated `(pre, action)` observations for step 1 as written
to mean anything: **89 repeated groups, 43 aliased**, against m0r0's 6 and 3. Its explorer run
is routing-heavy (1544 routing vs 1455 test actions, against m0r0's 37) and logged **654** live
alias conflicts over 43 conflicted edges and 40 suspect nodes. The passive census over the
transitions log is still **0 repeated / 0 aliased** — same construction, same emptiness; all 43
come from the rerun's routing actions.

**Passive census, 43 aliased groups, full control set:**

| arm | cells | separates | conflicts remaining |
|---|---:|---:|---:|
| baseline (digest only) | — | — | 43 |
| **`c2_episode`** | 2 | **40/43 (0.930)** | **3** |
| `c2_episode_incl` | 2 | 40/43 | 3 |
| `c2_episode_m3` / `_m4` | 3 / 4 | 40/43 | 3 |
| `c1_global_m4` | 4 | 26/43 (0.605) | 17 |
| `c1_global_m3` | 3 | 25/43 (0.581) | 18 |
| `rand1`–`rand5` (control) | 2 | 18–22/43 (0.419–0.512) | 21–26 |
| `c1_global` | 2 | 17/43 (0.395) | 26 |

This is what a passive census looks like when it has the power to say something. The
in-episode count separates 40 of 43 and collapses conflicts from 43 to 3; the five binary
random controls reach 18–22; and **global parity (17/43) performs *below* the random controls**
— so it is specifically the in-episode count doing the work, not "any alternating feature".
Adding cells to the episode base buys nothing (m3 and m4 also 40/43), so the binary split
already captures everything the finer ones do — but see the falsifiability caveat below before
reading that as "parity".

**Active probes on g50t** (P1 55 targets / 36 usable; P2 24 states, 48 targets, 250 executions):

- **P1: 0/36 vary with the count since environment creation**, parity falsifiable on all 36.
  The counter does not survive RESET here either — consistent with the census, where global
  parity sank below the random controls.
- **P2: 48/48 targets vary with the in-episode count.** The count matters, causally, not just
  associationally.
- **But the content control fails on 5 of 48.** Distinct routes of the *same* length to the
  same board give *different* outcomes on 4 targets, and 1 more has no length with two routes
  to test. So on g50t the outcome is **not** a function of `(board, in-episode count)` alone —
  43/48 are, and the remaining 5 carry hidden state this pair does not capture. That is a
  weaker structural result than m0r0's clean 72/72 with 0 disagreements.
- **Parity is unfalsifiable on g50t: 0/48 targets.** The path search finds no digest reachable
  at three lengths even at depth 14 (282 digests, 207 at exactly two, band never wider than
  adjacent), and with counts like `{2, 3}` every function separating them agrees with parity.
  The raw `parity_explains 44/48` is therefore **not** a parity finding and must not be cited
  as one.

**A metric error found and fixed here, which changes nothing about §3 but would have.** The
first version of `parity_falsifiable` counted any parity class holding two or more
observations — but repeated observations at the *same* count are the route-content control,
not a parity test. Corrected to require two *distinct* counts in one class. m0r0 is unaffected
(still 72/72 falsifiable, 0/72 explained, because its band is `[6, 7, 8]` and 6 and 8 share a
class); g50t drops from an apparent 47/48 falsifiable to **0**.

**g50t verdict.** Half A holds, and more legibly than on m0r0: a hidden in-episode action
counter gates the outcome, it is zeroed by RESET, and it separates 40 of 43 genuinely aliased
outcomes against controls that reach 22. Its functional form is unresolved — the instrument
cannot offer two same-parity counts — and unlike m0r0 the `(board, count)` pair is not the
whole hidden state. Half B was not run for g50t: the note scopes the mining test to m0r0, and
m0r0's result (zero effect at full dose on every arm, and zero cross-game delta for
`c2_episode` **including g50t's own row**) already says what this rule model does with the
feature. That cross-game zero is worth restating with §5 in view: g50t is the game where the
counter demonstrably gates the environment, and injecting it *still* moved nothing.

## 8. Verdict on the template

**The loop closes, and its value is in the disagreement.** "Model proposes latent → machinery
encodes → measured acceptance" ran end to end and returned a verdict finer than the proposal:
confirmed the counter, pinned its reset scope, refuted its parity, and rejected it as
load-bearing — all against controls that would have caught a spurious win, and one of which
(`rand3`) actually beat the real arms. The interface slice 2 needs from the model is
**executable definitions, not prose**. Every hour of this task went into deciding what "a
hidden action counter whose parity drives a mode switch" *means* operationally — global or
in-episode, does RESET increment, counter at pre or post — and each choice was a separate arm
because the model did not say. A slice-2 cell should emit a named latent with a computable
definition over the recorded action stream (a small expression, `f(actions_since_reset)`),
which the machinery injects verbatim; then the arms are the model's hypotheses rather than the
harness's guesses at them. Two further requirements this task exposed: the **store must record
repeated `(pre, action)` observations** or no passive aliasing test is possible at all, and
acceptance must be **two-part and adversarial by default** — a latent can be genuinely present
in the environment and worth nothing to the rule model, and only a design that reports both
halves against a matched random control will say so.
