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
consistency check. The channel is alive only where the model's predicate is correct **and
the prior library's is not** — the corrected S1 read (`aca2d47`) puts the prior firing at
**50%** of reference wins (21/42), so matching the library is worth nothing.

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

## Pre-committed readout (comparisons, not thresholds)

Decided now, before any call runs; each is a direction, no invented numbers:

1. **A**: count of games where the model's predicate is store-consistent ∧
   source-correct ∧ the prior library's is not. Zero → channel dead. Also reported:
   self-refuting-refuter count (the calibration read) · test-action executability count
   (the joint goal+action read) · contradiction-respect count (predicates consistent
   with recorded satisfied-but-not-advanced events — the re-specification read).
2. **B**: count of accepted latents (beats all 5 random controls on half B; half A where
   measurable). Zero → channel dead on 3.6; the template survives regardless.
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
