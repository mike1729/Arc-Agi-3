# E2 slice 2 — design: three channels, each against a mechanical control

**2026-08-05. Status: design, not run. Revised same day** after the S1 end-to-end
correction (`aca2d47`): channel A's seeding rationale, schema (test action added),
control percentage, and readout were updated — dated markers inline. Synthesis of five readouts: slice 1
(`notes/e2-slice.md`), slice 1.1 + budget check (`notes/e2-variance-arm.md`,
`notes/think-budget-recheck.md`), trace autopsy (`notes/e2-trace-autopsy.md`), probe
channel (`notes/e2-probe-channel.md`), hidden-state loop closure
(`notes/e2-hidden-state.md`), S1 clear-vs-stall (`notes/s1-clear-vs-stall.md`). All
model-bound priors here are **(3.6)** claims; the protocol is written model-agnostic
(see the 3.8 contingency at the end).

## What slice 2 is for

One question: **is there any channel where Qwen beats a mechanical control on its own
evidence?** Slice 1/1.1 answered it for rule proposals (no — twice), today's tasks
answered it for probes (no) and settled how latents must be posed (executably). Slice 2
poses it for the three channels still standing, each with a control that hardcodes the
"no capability" hypothesis. If every channel loses its control, the (3.6) M-phase is
machinery-only and the question re-opens on 3.8. Any channel that wins becomes the
M-phase and integrates with X.

**Dropped, by measurement:** rule proposals in the miner vocabulary (slice 1: 1/82
substantive; slice 1.1: repaired display, same nothing) · the probe/directive channel
(26/31 arms already answered, 8 unreachable, 0/4 predictions realized). The probe
channel does not return in any form. The rule drop carries one conditional (added after
external review): the **retroactive re-grade** (`notes/e2-regrade.md` — zero-model,
runs before the night) re-scores the ~190 recorded proposals under repair semantics
against a mechanical tolerance-mining control. Negative → the drop is final, with data.
Positive → a repair-bar rule request returns as channel D, with the model-vs-mechanism
credit question settled by the control.
**RESOLVED 2026-08-05 — negative. The drop is FINAL and there is no channel D.** The
re-grade ran (`logs/e2_regrade.json`): the mechanical control beats both model arms at
every ε on every game, by 10–15×; tolerance moves the model arms by +0.011 total; only
13 of 190 proposals sit in the near-miss band. The control's win is a zero-model miner
improvement (partial tier 1), filed as its own follow-up — see the result section of
`notes/e2-regrade.md`.

## The three channels

### A — Goal as falsifiable predicate (redesigned per S1 contrast)

**Output schema per game:** a completion-condition **predicate** (row-C grammar where
expressible, else a short executable expression over census handles), **its refuter** —
the single observation that would falsify it — **and its test action**: one concrete
(precondition, action) in the guard vocabulary whose outcome bears on the predicate.
Prose goals score zero. The test action is the S1 end-to-end read's joint goal+action
scoring (`aca2d47`): ft09 held a fully solved goal for ten actions because nothing
connected it to an untried action; a predicate without its next action is not yet
knowledge the system can use. Executability of the test action is scored mechanically
through the probe-executor machinery, which exists and is otherwise idle. **The test
action is a diagnostic count, never the channel verdict** — given the probe-channel
result we *expect* executability to be low; it is measured because the check is free
and calibrating, not because anything downstream relies on it.

**Scoring (mechanical first, adjudication last):**
1. consistency with every store transition (negatives; own completion positive where one
   exists);
2. refuter validity: a refuter already satisfied by the store self-refutes the proposal
   — counted, per the S1 finding that unapplied falsifiers are the channel's failure mode;
3. correctness vs game source (adjudicated, labels only, same rubric as the autopsy);
4. novelty vs the control.

**Control — the prior library.** The five stock goal shapes the S1 contrast extracted
from the reference's own wins (avatar→salient target · every X into/onto its Y ·
clear/collect all X · copy the displayed template · align the two matching objects),
instantiated *mechanically* on each game's census and filtered by the same store
consistency check. The channel is alive only where the model's predicate is correct **and is
not one the library also produced** — the corrected S1 read (`aca2d47`) puts the prior firing
at **50%** of reference wins (21/42), so matching the library is worth nothing. *(This
sentence read "and the prior library's is not" until 2026-08-05, which is not decidable
against a set of 24–252 surviving candidates. The readout's amended clause 1 says what binds
and why.)*

**Scope guard: the library is a measurement control on public games, not a deployed
strategy.** Its hidden-set hit rate is irrelevant to its role here (adjudication happens
on public games where truth is checkable), the standing caution that public numbers are
never evidence of hidden generalization applies to it like everything else, and the S1
cross-tab already shows the priors failing on trivially prior-shaped public games (dc22,
sc25 — 0/6 episodes). The deployed goal supply is the evidence-driven disambiguation
loop in `notes/e3-executor.md` §5; the library at most orders which candidates get
tested first.

**Seeding (revised same day after the end-to-end S1 read, `aca2d47`):** the
**inert-object inventory** — objects that never changed across the entire store — is the
primary seed. Both reference discoveries read a *static* object as a specification: sb26
stated the correct goal from layout alone at analysis step 1, before any action; ft09's
encoding hypothesis appears at step 5. The digest currently hides inert objects precisely
because they never move. The earlier claim that discovery is *triggered by accumulated
negative evidence* is **refuted** by that read and is withdrawn as a design rationale.
The **negative-evidence section** stays with a different job: its "candidate G satisfied
at step t, level did not advance" lines (evaluated against row-C survivors) are the
**re-specification test** — ft09's L2 recoveries went through exactly that contradiction
("matches my decoded pattern, but the level is not complete — so my decoding is wrong")
while sb26's L2 passes never re-specified and burned their whole budget enumerating
inside the stale schema. Scoring counts whether the emitted predicate *respects the
recorded contradictions* rather than re-proposing a refuted candidate. Null-effect-run
lines are kept as data with no elicitation claim attached.

### B — Latents as executable definitions (per the validated template)

**Output schema per game: up to 3 candidate latents**, each `{name, definition}` where
the definition is a computable expression over the recorded action stream in a small
declared grammar: counters over `actions_since_reset` / `actions_total` / per-action-type
counts, with `mod k`, thresholds, and a resets-on-RESET flag. Prose is rejected at
extraction — the hidden-state task spent its hours resolving what one prose sentence
meant operationally; slice 2 makes the model do that work.

**Scoring:** each definition injected **verbatim** as a guard feature through the
`e2_hidden_state.py` machinery (generalized to arms-from-spec): half A (aliasing
separation, where the census has any volume — g50t is the only game with passive volume;
elsewhere half A is reported as unmeasurable, honestly) and half B (mining delta vs the
v2 floor on human L1/L2, plus the ceiling arm).

**Control:** 5 seeded random binary/ternary features per game (seeds 1–5, never
20260804). A latent is accepted only if it beats **every** random control on the same
metric — the hidden-state task showed a random bit outperforming real-but-irrelevant
latents, so this floor has teeth.

**Optional half-A extension (w):** the prefix audit (`logs/e1_prefix_audit.json` +
machinery) makes navigational value measurable beyond the census games — re-derive
per-state verified/diverged labels and score whether the latent-augmented hash separates
diverged from verified prefixes. A latent that *explains replay divergence* is
navigationally load-bearing even if mining-inert; half B alone would miss it (m0r0's
counter is exactly this case). Implement only if the verifier sub-task has room; report
as its own column, never pooled with half A.

### C — Vocabulary critic (the promoted channel)

The one channel with a realized payoff: slice 1's ft09 output named a missing word that
became `clicked_adjacent_to` and moved the zero-model floor 0.2522 → 0.3017. The
budget-check traces (n=3, unscored) show the lifted-cap digest elicits this unprompted —
dc22 attributing unresolved keys to needing feature *combinations*, m0r0 to a counter
absent from the vocabulary.

**Output schema per game: up to 2 vocabulary proposals**, each `{name, definition sketch
computable from the pre-frame object catalogue, the unresolved keys it should resolve,
expected direction}`.

**Scoring, two-stage:** in-slice, **targeting** — does the proposal point at keys whose
measured failure split (`failure_split` in the dose files) is guard-fixable /
census-separable, i.e. where a vocabulary gap demonstrably is, versus keys that are
noise? Post-slice, the top distinct proposals get implemented and measured exactly as
vocab v2 was (E0 + dose reruns; deltas decide; no regression elsewhere). Implementation
is a separate task; the slice records the queue.

**Control:** the measured failure-typing itself — a critic that points where the typing
already points adds targeting confirmation; one that points elsewhere and is *validated
by implementation* adds capability. Both outcomes are recorded; only the second is a win.

## Digest v3 (build task)

Keep everything slice 1.1 added (complete value sets, witness, guard grammar, honest
majority text) plus the lifted cap. Add:

1. **Coverage ledger** — per unresolved key and feature stratum, how many stored
   transitions exercised it, and per object, which actions have been tried on it. Two
   independent readouts demand exactly this: the probe task (26/31 probe arms asked for
   evidence already held) and the S1 end-to-end read (what finally unblocked ft09 was
   the model printing its own action history and reading off the gap — "I have NOT
   tried clicking the blue cells");
2. **Inert-object inventory** (channel A's raw material);
3. **Negative-evidence section** (null-effect runs; satisfied-but-not-advanced events);
4. The three **request schemas** above, replacing the rule-proposal request and the
   `next_probe` field entirely;
5. **Observed invariants** (added after external review) — joint constraints among
   census features holding in every stored state (constant sums/differences/complements
   of count features; minable in seconds). The digest shows per-feature *marginals*, and
   the probe task's impossible requests (ft09: two counts whose sum is fixed) were
   reasonable inferences from marginals alone — this line removes that failure mode and
   feeds channel A's test-action executability.

## Protocol

- **Games: the six iteration games + sp80 and lf52** — the two E1-completed games give
  channel A its only own-positive completion examples (none of the six has one).
- **Dose: full store only.** The dose axis was flat for rules and none of the three
  channels has a dose hypothesis; the axis bought nothing in two slices.
- **Seeds: 1 and 2** (never 20260804). 8 games × 2 seeds = **16 calls ≈ 4.8 h** at the
  measured 18 min/cell — one night.
- **Temperature: 0.6** (comparability with everything measured). Optional declared arm,
  only if the night has room: 2 cells rerun at 0.9 for channel B's propose-N diversity —
  labelled, never pooled with the 0.6 cells.
- **Instrument: unchanged and settled** — Qwen3.6-27B-8bit, direct `mlx_lm`, two-phase
  decode, first token never constrained, `THINK_BUDGET = 16384` (re-verified against the
  larger digests today), per-call mechanical thinking verdict, unclosed think voids the
  cell.
  ⚠ **The budget was re-verified against the v1.1 digests, not the v3 ones.** v3 grew them
  by a median +51% (worst ft09, +129%) and the two grammars plus the three asks add a
  further 5,536 chars of scaffold to every prompt — 5,111 before the argument-order widening
  was printed on 2026-08-05, +425 for that line. A budget re-probe is a NAMED FOLLOW-UP that
  has not run; if the night voids cells on unclosed think blocks, this is the first place to
  look.

## Pre-committed readout (comparisons, not thresholds)

Decided now, before any call runs; each is a direction, no invented numbers:

1. **A**: count of games where the model's predicate is store-consistent ∧
   source-correct ∧ **not a member of the prior library's surviving set** (canonical-string
   comparison, `e2_slice.channel_a`'s `in_prior_library`). Zero → channel dead. Also
   reported: self-refuting-refuter count (the calibration read) · test-action executability
   count (the joint goal+action read) · contradiction-respect count (predicates consistent
   with recorded satisfied-but-not-advanced events — the re-specification read).

   ⚠ **Amended 2026-08-05, before any call ran — the original sentence read "and the prior
   library's is not [correct]", which is not decidable.** The library is a SET, not a
   prediction: the built control keeps 24 (m0r0) to 252 (dc22) surviving candidates per
   game. Under the set reading the channel wins only where *no* library survivor is
   source-correct, which on the five games with >100 survivors is near-impossible by
   construction, and a "channel A dead" verdict would carry no information about the model.
   The membership reading above is decidable mechanically, before any adjudication, and it
   is the one that matches the S1 phenomenon: the reference brings ONE default guess per
   game, so "matching a stock prior is worth nothing" is a statement about the proposal, not
   about the library's exhaustive reach.

   Measured today, so the reading is not taken on faith — of the store-consistent row-C
   predicates per game, the fraction the library's surviving set already contains:
   dc22 40/118 · ft09 14/48 · ls20 23/67 · m0r0 6/27 · tu93 31/77 · vc33 10/38 ·
   sp80 44/123 · lf52 8/24. **20–36% covered; 16–79 consistent predicates per game sit
   outside the control.** The membership test is a real test, not a formality.

   **Two-level, because a novelty hit has two readings** (`in_prior_shape_space` /
   `novel_shape`, `e2_dsl.skeleton`): a predicate outside the library by canonical string
   may still be one of the five stock SHAPES under a colour binding the library did not
   enumerate. That is a re-binding of a prior the reference already brings, not a goal
   capability the prior vocabulary cannot reach. The headline count is the membership
   criterion above; the shape split is reported beside it and a win carried entirely by
   re-bindings is stated as such in the verdict sentence.

   **How much this second level is worth, measured rather than assumed: little, and it is
   kept as insurance.** Splitting the 522 store-consistent row-C predicates across the 8
   games three ways — in-library / re-binding / novel-shape — gives **176 / 19 / 327**. The
   re-binding band is 3.6% of the space and is EMPTY on four games (m0r0, tu93, sp80, lf52);
   it is 11 predicates on dc22 and ≤4 elsewhere. So the string criterion and the shape
   criterion almost always agree, the flag costs nothing to carry, and its whole job is to
   stop a dc22-sized edge case being written up as new goal capability. It is not a
   correction to the headline count and must not be presented as one.

   **One asymmetry recorded, not acted on:** the library implements five shapes, but only
   FOUR fire in the S1 evidence (`notes/s1-clear-vs-stall.md` §`prior-match` — avatar→salient
   target, every X into/onto its Y, collect/remove all X, align two matching). *Copy the
   displayed template* has no measured firing and contributes 0–40 survivors per game
   (ft09 40, dc22 35, vc33 20, tu93 19, m0r0 10, and none on ls20/sp80/lf52). It widens the
   control on five games beyond what S1 observed. It stays in — the shape list is the note's
   own — but a channel-A loss decided only by `copy_the_template` collisions is not a loss to
   a measured prior and must be reported separately.
2. **B**: count of accepted latents (beats all 5 random controls on half B; half A where
   measurable). Zero → channel dead on 3.6; the template survives regardless.
   **Guard against grammar-artifact false negatives** (added after external review):
   every `prose_rejected` item is listed verbatim in the readout and adjudicated into
   *garbage* vs *coherent-but-out-of-grammar* (a reading task on ≤24 items). A
   preponderance of coherent out-of-grammar proposals reads as a DSL expressiveness gap
   — the fix is growing the grammar, not a channel death sentence. Parse failure and
   reasoning failure are never pooled.
3. **C**: targeting rate vs the measured failure-typing, and the implementation queue.
   C's final verdict lands only after the post-slice implementation measurements.
4. Every channel's full output is logged and committed; negative results same-day; the
   verdict sentence names each channel alive/dead separately.

## Build tasks this spawns (all zero-model, in order)

1. **Digest v3** — coverage + inert inventory + negative evidence + schemas (edits
   `e2_slice.py`; owner must coordinate: the file is shared, currently quiet).
2. **Prior-library control** — the five shapes as mechanical predicate generators over
   the census + store-consistency filter (new file).
3. **Latent verifier generalization** — `e2_hidden_state.py`'s arms driven from a spec
   file instead of hardcoded definitions (its author's natural follow-up).
4. **Predicate/expression evaluator** — the small DSL for channel A predicates and
   channel B definitions, with the extraction-side rejection of prose.

Not blockers: the prefix repair (no probes are executed in slice 2) and the
repeat-observation store change (affects only half A's measurability, reported honestly).

## The 3.8 contingency

If Qwen3.8 lands before slice 2 runs: run the bring-up gate first
(`notes/qwen-3.8-upgrade.md`), then **run slice 2 on 3.6 anyway** (one night) before
switching — it anchors the new protocol on the old model, so the generation contrast
exists on both protocols (1.1R covers the old one). If 3.8 slips, slice 2 runs on 3.6 as
soon as the build tasks land, and reruns on 3.8 under the upgrade note's P1.

## Non-goals

No rule proposals, no probe execution, no X-phase integration (that waits on X1/X2), no
training, no submissions off this line before E3 reads out.

---

# RESULTS — 2026-08-05. **All three channels lose to their controls on Qwen3.6.**

Run of record: `notes/e2-slice2-run.md`, executed same day. Machine records
`logs/e2_slice2_seed{1,2}.json` (format_version 2), `logs/e2_slice2_latent_verify.json`,
`logs/e2_slice2_latents.json`, `logs/e2_slice2_budget_probe.json`; traces
`logs/e2_slice_traces/*_s2r{1,2}.{think,extract0}.json`. Zero model calls after the night.

## Run log

- **Pinned run commit `0dea91a`** in a throwaway worktree; `data/` and the gitignored
  `logs/` directories symlinked from main. Main advanced twice during the run (concurrent
  agents) — the pin is why that cost nothing.
- **Digest re-render (zero model)** reproduced the recorded lengths exactly on all 8 games:
  dc22 43,185 · m0r0 26,180 · lf52 21,441 · sp80 21,371 · tu93 18,906 · vc33 16,335 ·
  ls20 15,870 · ft09 11,372 chars.
- **Digest variant live: v3, rule request OUT, no channel D** — verified in the rendered
  PROMPT text, not from a commit message. `notes/e2-regrade.md`'s negative result stands.
- **THINK_BUDGET gate (required, dc22/full > 40k): PASS.** One probe call, seed 1:
  prompt 48,778 chars / 19,405 tok, think 26,145 chars / 8,178 tok, `</think>` at
  generation token 8,179, total generation **8,411 of 16,384 — 8,205 tokens spare**, wall
  996.7 s, prefill 354.6 tok/s, decode 8.93 tok/s. Against the pre-v3 check on the same
  cell (`notes/think-budget-recheck.md`): prompt +59%, think −3%, total generation −2%,
  wall +0.9 s. **The v3 growth lands entirely in prefill; output length does not track
  prompt length.** Budget unchanged at 16,384.
- **One deviation, recorded**: `run_cell`'s trace tag was `{game}_{dose}_s{seed}`, which for
  slice 2 at seed 1 collides byte-for-byte with twelve COMMITTED slice-1/1.1 trace names. Changed
  to `_s2r{seed}` before launch (the tag the run note names). Same failure class as the
  `--out` default that overwrote the slice-1.1 result file earlier the same day.
- **One incident, verification-only**: the first latent-verifier reproduction gate FAILED
  ("latent not computable on both sides") because the worktree lacked the gitignored
  `logs/e2_hidden_state_rerun/`. Symlinked; the gate then reproduced the committed
  `c2_episode` numbers exactly (L1 0.2624 / L2 0.3988, rejected). **The night itself never
  reads that directory** — channel B only parses at run time — so no cell is affected.

## Instrument

**16/16 cells scored · 16/16 mechanical thinking verdicts passed · 0 voided · 0 unparsed
extractions · 0 extraction retries.** Wall per cell min 739 s, mean 906 s, max 1,033 s;
4.03 h of model wall for the night (11:33–15:48Z). Think blocks 19,607–27,604 chars
(mean 24,703). No call approached the budget.

## Channel A — goal as falsifiable predicate

**16/16 parsed** in the predicate grammar; no prose. Store consistency (negatives only —
see the limitation below): **7 survived · 8 falsified · 1 vacuous**.

| game | seed 1 | seed 2 |
|---|---|---|
| dc22 | falsified | falsified |
| ft09 | survived, in library | survived, outside library |
| ls20 | survived, novel shape | falsified, **re-proposed a digest-refuted candidate** |
| m0r0 | vacuous | survived, outside library |
| tu93 | survived, in library | survived, in library |
| vc33 | falsified | survived, in library |
| sp80 | falsified | falsified |
| lf52 | falsified | falsified |

Of the 7 survivors, **4 are predicates the prior library also produces**, leaving three
cells — ft09/s2, ls20/s1, m0r0/s2 — as the only candidates for clause 1.

### Adjudication: an added mechanical instrument, then the source read

The pre-registered clause 1 needs *source-correct*. The frozen v2 store cannot supply the
positive half at all (`positives_evaluable = 0` on all 16 cells: both completion-carrying
games lost the completing row's post frame), so **an addition to the pre-registered readout
was made and is flagged as one**: every predicate was evaluated against the **human
replays**, which do contain completions, on the same transition representation the floors
are scored on. A completion condition must be TRUE at every completing transition and FALSE
elsewhere. Verdicts over 8 games × 2 seeds × human L1 and L2:

- **EXACT (true at every completion, false everywhere else): 1** — tu93/s2. **It is in the
  prior library.**
- **necessary but too weak** (true at every completion, also true at many non-completions):
  4 — dc22/s1, vc33/s1, sp80/s1, sp80/s2.
- **partial**: 1 — lf52/s1 (true at 9 of 10 L1 completions, 5 of 8 on L2).
- **wrong** (false at every completion): 10 — including **all three** clause-1 candidates.

A source read of those three (labels and paraphrases only, per PUBLISHING.md) agrees with
the mechanical verdict in each case: ls20 completes on collecting every target, not on a
colour count reaching one; m0r0 completes when every pair of matching objects has been
brought together, not on a single object of one colour remaining; ft09 completes when a
per-clue match/differ constraint is satisfied across the board — the model correctly
identified the operative 36-object set (the digest's `count:8 + count:9 = 36` invariant) and
then proposed making all of them one colour, which satisfies the match clues and violates the
differ ones.

**Headline (clause 1): 0 of 8 games.** No predicate is store-consistent ∧ source-correct ∧
outside the prior library. The one predicate that is exactly correct is one the mechanical
control produces by itself.

Diagnostics (never the verdict): ~~self-refuting refuters 10/16~~ **WITHDRAWN — see the
erratum below** · malformed test actions 5/16 · re-proposed a digest-refuted candidate
1/16 · in prior library 4/16 · novel shape 7/16 · **seeds agreed on the store outcome in
only 5 of 8 games**.

> **Erratum 2026-08-05 (external review, verified): the self-refuting-refuter diagnostic
> is withdrawn.** The request asked for "the single observation that would falsify your
> predicate", and scoring counted a refuter *already satisfied anywhere in the store* as
> self-refutation. For a completion condition G that is not a refutation: the
> discriminating observations are **G true ∧ level did not advance** or **completion ∧ G
> false**. The 10/16 therefore measures a malformed request, not the model's
> calibration, and must not be cited. **The channel-A verdict is unaffected** — clause 1
> was 0/8 on store-consistency, source-correctness and novelty independently of any
> refuter. Fixed in slice 3 (`notes/e2-slice3.md`, frozen-interface fixes).

## Channel B — latents as executable definitions

**12 distinct latents** proposed on 3 games (dc22 4, m0r0 2, sp80 6); the other five games
proposed none — correct behaviour, not silence: on those games every stored state replays to
itself, and the prompt asks for none in that case. **`prose_rejected` = 0 across all 16
cells**, so the grammar-artifact guard has nothing to adjudicate and the DSL is not hiding a
reasoning result behind a parse failure.

**Accepted: 0 of 12.** Every latent ties its five random controls to four decimal places on
every arm (e.g. dc22 L1 0.2278 / L2 0.0552 for latent and all five controls), because the
miner **never selects any of them** (`selected = 0` everywhere) — the mining outcome is the
floor whatever is injected. Ties do not beat, so all 12 are rejected.

Half A is measurable on m0r0 only (3 aliased groups; dc22 and sp80 have 0 — reported as
absence of instrument, never as a separation rate of zero). There, the one computable latent
separates 1 of 3 groups — **identical to all five random controls**. The optional
prefix-divergence extension ran on all three games and shows no latent splitting verified
from diverged prefixes better than the controls (e.g. sp80 `click_parity_s1`: 197/76 and
161/64 verified/diverged across its two values — the same ratio twice).

## Channel C — vocabulary critic

**31 proposals, 29 distinct, 6 (19%) targeting a key the miner actually left unresolved** —
ft09 4/4 across both seeds, sp80/s2 2/2, everything else 0. Two of ft09/s1's four are
`clicked_adjacent_to:11` and `clicked_adjacent_to:12`: **features the v2 vocabulary already
contains** — the one previous model suggestion that ever paid out, re-invented rather than
read off the guard grammar printed in its own prompt.

Implementation queue recorded for the follow-up task, ranked by targeting: the four ft09
adjacency variants and sp80's `same_col:0:9` / `min_dist:0:9` first; then the geometry the
vocabulary genuinely lacks — click row/column (m0r0/s1), clicked-component size (dc22/s2),
bounding-box spans (vc33/s2), Manhattan distance between colour classes (tu93/s2),
enclosure and same-shape (ls20/s2). C's final verdict lands only after those are implemented
and measured as vocab v2 was.

## Verdict sentences

- **Channel A: dead against its control.** Zero games where the model's predicate is
  store-consistent, source-correct, and outside the prior library; the single exactly-correct
  predicate of the night (tu93/s2) is one the library also produces, and 10 of 16 refuters
  were already satisfied by the evidence the model was shown.
- **Channel B: dead against its control.** 0 of 12 latents beat their five random controls
  on any arm, and none was ever selected by the miner. The executable template itself
  survives — 0 prose-rejected — so the negative is about the proposals, not the grammar.
- **Channel C: no in-slice win; verdict deferred by design.** 19% targeting, and the
  highest-targeting cell re-proposed a feature the vocabulary already has. The queue is
  recorded; only implementation can turn this channel positive.

**Read together: on Qwen3.6 the M-phase is machinery-only, and the question re-opens on
3.8** (`notes/qwen-3.8-upgrade.md`) — every verdict above is a (3.6) claim.

## Limitations

- `positives_evaluable = 0`: the store's completion half is unmeasurable, which is why the
  human-replay test was added. That test is an addition to the pre-registered readout, made
  after the night ran and before any adjudication label was assigned; it is mechanical and
  reproducible, and the source read agrees with it on all three cells that decide clause 1.
- Two seeds, one model, eight public games. Seeds disagreed on the store outcome in 3 of 8
  games, so single-seed channel-A counts would mislead in either direction.
- Public games are materially easier than hidden ones; nothing here is evidence about
  hidden generalization.
- Test-action executability was NOT executed (slice 2 runs no probes) — only
  well-formedness is scored, as designed.
