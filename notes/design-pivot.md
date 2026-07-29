# Design-phase pivot + GI-1 (goal-inference viability sprint) — 2026-07-29

## 1. GI-1 — goal-inference viability

**Question.** Can the reference agent's goal belief be made *correct and actionable* on games it
has not seen — **including before any completion has been observed** — by (i) narrowing the
prediction to a closed hypothesis space, (ii) feeding it structured evidence it currently lacks,
and (iii) updating a posterior from observed completions — without any trained goal-carrier?

**Duration.** PROPOSED 4–5 days offline — E1–E3 plus the parameter-gold normalization (~1 day,
**built unconditionally**: the verdict needs it either way) — + gate + optional E4
(1 day + quota).

**Models (per the recorded DEV-11 evaluation, not S1-E5's original switch).** The MoE
(35B-A3B 4-bit) is a **throughput vehicle only** — rejected as a measurement vehicle
(vc33: 0/7 levels, 742 actions, 0.00; `local-compute-options.md` verdict "Rejected"). GI-1
measures model capability, so the split follows `s1-measurements.md`'s recommendation:
**MoE for development only** — writing and debugging prompts, packets, retrieval; none of its
outputs select anything, because treatments can interact with the model and champion selection
is itself a quality measurement. Once implementations freeze, **all conditions run once on the
six iteration games on `Qwen3.6-27B-8bit`** — the recorded local agent vehicle of choice — the
champion is selected from that pass, and only then does the one-shot set open. Every measured
number in GI-1 comes from the 8-bit model. Price the measured grid against its ~8.3 tok/s before freezing checkpoint
counts; the Kaggle FP8 notebook (exact reference artifact + engine) is the escape hatch if the
grid doesn't fit local throughput. The 8-bit build is still a different artifact lineage than the
reference FP8 — E4 on the Kaggle stack bounds that substitution. Consequence unchanged:
condition (a) is **rerun** on the measurement model at the same checkpoints — the existing S1
rationales are a cross-reference only, never the measured baseline.

### Evidence packets — three layers, so c−b measures the compiler and not formatting

**1 · Canonical packet** — condition-independent data, a function of **the session prefix up to
the checkpoint only**:

- initial settled board · within-level settled-frame deltas · actions taken · `available_actions`;
- per completion observed so far: **pre-terminal settled grid + completing action + the
  within-level deltas that led to it + the `levels_completed` increment**. The post-terminal
  frame is the *next level's board* — a level reset, not a solved-state image — and is
  **excluded** from goal evidence;
- zero-completion packets exist by construction: initial board + early deltas, nothing else.

**2 · Baseline rendering** (conditions a/b): the packet rendered the way the reference harness
itself presents history — current grid at upscale 4 plus its native history format — reproduced
as closely as offline replay allows. (a) and (b) share it exactly and differ only in output
structure.

**3 · Compiled digest** (conditions c/d): the evidence compiler's rendering — object/count
inventories, delta summaries, terminal-packet abstracts. It may add **no information not
derivable from the canonical packet**: it changes representation and computation, never
evidence. So b−a isolates output structure and c−b isolates the compiler.

**Retrieval (conditions d/f) — spec frozen before the one-shot read:** features, distance
metric, neighbour count, tie-breaking, and index membership are fixed while still on the
iteration slice; no retrieval knob moves afterwards. Pool: earlier-in-this-session terminal
packets (the deployment mechanism) + other games' terminal packets, **leave-one-game-out over
the 21 non-reserved games — declared transductive**, and deployment-faithful: a shipped library
carries all public games and a hidden game is never in it, which LOGO reproduces. **Never other
sessions of the same game** (other humans' solutions would smuggle in the answer), and
**reserved games appear in no index**. Cross-game retrieval is the only pool at zero
completions, which is exactly the deployment shape. (Shipping a replay-derived library inside a
submission touches the open replay-licensing question — flag before E4's payload becomes a
submission.)

### Conditions — a small factorial, so lifts attribute cleanly

| id | LLM | output structure | digest | retrieval |
|---|---|---|---|---|
| (a) | qwen | free-form goal statement (S1 status quo, rerun) | – | – |
| (b) | qwen | hypothesis set over the 10-class codebook | – | – |
| (c) | qwen | hypothesis set | ✓ | – |
| (d) | qwen | hypothesis set | ✓ | ✓ |
| (e) | none | leave-one-game-out class prior | – | – |
| (f) | none | prior + nearest-terminal retrieval vote | – | ✓ |

Marginal reads: b−a = output structure · c−b = evidence compiler · d−c = retrieval-for-qwen ·
**d−f = qwen's incremental value over the best programmatic floor** · f−e = retrieval alone.

**Output structure (b–d):** not a single forced choice — a **top-3 hypothesis set**, each with
class + parameter sketch, evidence for and against, and the cheapest action that would
discriminate the top two. Premature single-goal commitment is the measured failure shape (sc25:
confidently wrong goal preserved), so commitment itself is part of the treatment. The proposed
discriminating probes are **logged and reviewed, not gated** — verifying their discriminating
power needs the fork and belongs to a later sprint.

**Scoring — class is a filter, predicates are the verdict.** Every condition's raw outputs are
logged once and all endpoints are scored from the logs, so later annotation never re-queries.
Class: mechanical, top-1 and top-3, against the per-game primary labels (κ 0.947) — necessary,
never sufficient: right class with wrong bindings is exactly the sc25 failure. **Parameter gold
does not exist in mechanical form** (the labelled file carries prose + coarse class, nothing per
level), so the normalized layer is **built unconditionally** — the verdict needs it either way,
and gating it on a class proxy could kill a treatment that fixes bindings while class stays
saturated. Order: **iteration-slice gold before champion selection** (so selection reads binding
quality, not class alone) · one-shot-game gold after implementation freeze · reserved games
never annotated. **Actionable predicate correctness** — does the hypothesis imply the level's
true terminal condition — is the endpoint both champion selection and the offline verdict read,
and for b–d it is scored **mechanically**: structured field-wise comparison against the
normalized gold. Raters remain in exactly two places — **blinded mapping of (a)'s free text**
(unavoidable; S1-E10 posture, caveat recorded) and **adjudication of an enumerated list of
equivalence cases** the mechanical scorer cannot resolve, the list frozen with the scorer and
every invocation logged. The primary verdict no longer depends on an S1-E10-type rater.

**Discipline, in three lines.** Identical packets, checkpoints, model, sampling and scoring
across conditions; only the declared treatment differs. Source is labels only, never runtime
input. Public ≠ hidden (13.33% vs 7.78%) stated on every result.

### Game ledger — who may look at what

| state | games | use |
|---|---|---|
| iteration slice | 6 — drawn + accepted, see Draws | all prompt/digest iteration |
| one-shot read | 15 | final E1/E2/E3 pass, once, no iteration after |
| **reserved** | 4 — drawn + accepted | **untouched by GI-1 entirely, E4 included; in no retrieval index** — clean external validation for whatever gets built later |

Once the one-shot games are read they are tainted for prompt/system design too; the ledger
records date and what was exposed. E2 excludes reserved-game episodes (75 → 63). lp85 flagged
(preview-build recordings), not excluded.

### E1 — Recognition ladder (human evidence)

Per non-reserved game: 3 completion-bearing sessions, checkpoints at **zero completions (after
10 and 30 actions)** and after the 1st/2nd/3rd completion — accepted 2026-07-29. All six
conditions at every checkpoint. Reads: is the goal recoverable at all, from how little, and
which treatment recovers it. The zero-completion rows are the hardest and most deployment-like
case — S1's stuck-on-level-1 regime — and are reported as their own endpoint, never averaged
away.

### E2 — Recognition under the agent's own evidence

Evidence streams replayed from the S1 failure corpus (request logs via DEV-6), conditions
{a, champion, f} — the champion frozen from the iteration slice — at three checkpoints: **10
and 30 actions into the stalled level attempt, and the episode's final state**. **Selection
effect handled:** `goal_unknown` episodes were selected for the agent not knowing the goal, so
(a) is ~floor there by construction. Run all non-reserved episodes — **63, holding 39
`goal_unknown` primaries across 18 games** — reporting `goal_unknown` and complement
separately; the primary metric is K4's paired rescue, scored mechanically against gold ((a) via
blinded rater mapping).

### E3 — Adaptation (runs inside E1's grid, no separate corpus)

Two reads from the same grid: the **ladder slope** (marginal lift per additional completion,
0→1→2→3) and a **completion-ablation arm** — same checkpoints, with the terminal-packet
**content** removed (pre-terminal grid, completing action, preceding deltas) while the
`levels_completed` increments stay visible. The increment is free platform metadata, hidden in
no deployment regime, so the deployment-relevant question is what the content adds; hiding the
event itself would answer a question with no referent and is not run. Conditions {d, f}: does
adaptation need qwen, or does the programmatic posterior carry it alone?

### E4 — Does it move actions? (unlocked by K1, not by K4)

Paired advisor-on/off on the Kaggle reference stack, **on the 21 non-reserved games only** —
the reserved four stay clean even here, and excluding them is free because runs are
budget-bound, not game-bound (any ≤28 games costs one full ~2.37 h budget). The goal-hypothesis
digest is injected where the solver currently free-forms. k=3 replicates/arm ≈ 14.2 h, read
against the measured run-to-run noise floor (36% / 20% of games change cleared-level count
between identical runs). Primary: per-game level completions, paired over 21 games, permutation
test. Its payload is the natural first method-bearing submission.

### Gate (forms fixed now; numbers set before the run)

**Selection freeze, against winner's curse:** the champion is chosen **from conditions b–d
only** — (e)/(f) are attribution floors, ineligible because they emit class votes rather than
bindable predicates, so K4 could not score them — on the six iteration games, **from the
27B-8bit measured pass, never from MoE outputs, primarily on actionable predicate correctness
against the iteration-slice gold with class top-3 as tiebreak**, and frozen before the one-shot
set is opened.
The one-shot confirmatory contrasts are pre-declared — champion-vs-(a), champion-vs-(e),
(d)-vs-(f); every other comparison on one-shot games is descriptive only, no CI claimed.

- **K1 — class recoverability: diagnostic + non-inferiority guard, never a kill on its own.**
  Reported: champion vs the rerun status quo (a) and the prior floor (e) on one-shot-game class
  accuracy — mean over sessions within game, game-level bootstrap (10,000 draws), 90% CI —
  **separately at the 30-action zero-completion and first-completion regimes**. Required, per
  SPEC §9.5's existing non-inferiority posture (no new standard): champion top-3 point
  regression vs (a) **≤ 3 pp** and one-sided 90% lower confidence bound **> −5 pp**, at both
  regimes — a treatment may match a saturated class metric while fixing bindings, so class
  superiority is neither demanded nor sufficient. **The early kill needs both axes to fail:**
  the champion neither beats the floors on class *nor* shows positive actionable-predicate
  signal over (a), in either regime. Failure confined to zero completions with predicate signal
  at ≥1 routes to probe design, not death.
- **K2 — attribution (routes, never kills).** (d) vs (f): qwen adds value over the programmatic
  floor, or it doesn't. If (f) wins on class, that is still a *positive* result, claimed
  precisely: the **class-identification** job doesn't need qwen. It does **not** show retrieval
  can bind the current game's objects and parameters — (f) emits a class vote, no predicate —
  so the routed design is a programmatic classifier with qwen doing bindings only, and
  extending (f) with a transferred-predicate template + deterministic binding procedure becomes
  the named follow-up experiment.
- **K3 — adaptation.** Positive per-completion marginal lift (ladder + content-ablation agree
  on sign), same CI form.
- **K4 — actionable predicate correctness: the offline viability verdict, as paired rescue.**
  Scored mechanically against the gold layer. Denominator: **baseline-incorrect** `goal_unknown`
  episode-levels — the cases the rerun (a) gets wrong. Pass: champion actionable top-1 predicate
  on **≥ 25%** of them, episode outcomes aggregated within game before inference, and the
  game-clustered 90% lower bound on the paired champion−(a) improvement **> 0**; non-regression
  on baseline-correct cases per the K1 rule (≤ 3 pp, lower bound > −5 pp). The pairing bars
  three false passes: correctness the baseline already had, concentration in repeated episodes
  of one game, and absolute rates with no incremental value. Offline viability is decided
  **here or by K5 — never by K1**.
- **K5 — behaviour (E4, 21 non-reserved games).** Average the three paired-replicate deltas
  within each game; one-sided sign-flip permutation across the 21 game-level deltas. Pass:
  **p < 0.10 and pooled mean level-completion delta > 0**, with **≥ 2 of 3** replicate-pair
  means nonnegative as the stability check — requiring all three would be brittle under the
  measured 20–36% run noise. **A failed K4 does not block E4** — K5 is the behavioural rescue
  (offline actionability scoring can be pessimistic about behavioural value); K4 and K5 both
  failing is the kill. Whether to spend the 14.2 h on a rescue attempt after a K4 fail is an
  operator call at gate time.

Gate verdict written by script from logs, same posture as `s1d_rollup.py --verify`.

### Draws + numbers — RESOLVED 2026-07-29 (draw, sessions, checkpoints, regimes, aggregation, CI, pilot accepted; scoring mechanics and K1/K4/K5 replaced by operator)

**Game draw** — `agent/harness/gi1_game_draw.py`, seed 20260729, **first attempt adopted, no
re-draw** (a re-draw without a recorded reason is cherry-picking); stratified by primary
predicate class;
lp85 barred from iteration/reserved; iteration forced to span both action regimes. On disk:
`logs/gi1_game_draw.json`, `--verify` clean.

| bucket | games |
|---|---|
| iteration (6) | dc22 · ft09 · ls20 · m0r0 · tu93 · vc33 |
| reserved (4) | g50t · r11l · su15 · tr87 |
| one-shot (15) | ar25 · bp35 · cd82 · cn04 · ka59 · lf52 · lp85 · re86 · s5i5 · sb26 · sc25 · sk48 · sp80 · tn36 · wa30 |

Two draw observations, favourable and one caveat: the two most-inspected games (vc33, tu93 —
S1-b exit, quantization arm, RESET-ACCT) landed in iteration, where prior taint is harmless,
and sc25 — the spec §9 motivating episode — landed one-shot, so it is confirmatory. Caveat:
g50t (reserved) is the game whose human data is short two sessions, so its later external
validation leans harder on fresh play. E2 drops the reserved games' episodes: 75 → 63. Repo
state: draw script, draw artifact, packet builder, inventory and this note are committed as
`c0fd2e3` (2026-07-29).

**Packet inventory, measured 2026-07-29** (`agent/harness/gi1_packets.py --inventory` →
`logs/gi1_packet_inventory.json`; `--selftest` green on ls20/vc33/m0r0): all 21 non-reserved
games supply 3 sessions at tier 3 (≥3 completions) — no shortfall anywhere. Checkpoint validity
**275/315**; every one of the 40 invalid rows is a zero-completion offset on a fast-completion
session, concentrated in vc33 and lp85 (first human completion at steps 6–10, so both offsets
invalid in all their sessions). Those two games contribute no zero-completion rows — the
validity rule reporting honestly, not a defect. vc33 being an iteration game, the slice's
zero-completion development signal comes from its other five games. One data quirk found and
handled: cn04 records 1–2 empty-`frame` lines per session, always `state: GAME_OVER` — the step
carries the previous settled grid with `n_frames=0`.

**Numeric candidates** (rationale · cost if wrong):

- **Sessions/game: 3**, picked deterministically — sessions with the most completions, ties by
  fewer total actions then guid; fall back to ≥2/≥1-completion sessions where 3 don't exist,
  shortfall recorded. *(Matches the 3-replicate posture used throughout S1 · more costs
  linearly, fewer leaves session variance unmeasured.)*
- **Zero-completion checkpoints: after 10 and 30 actions.** 30 sits just under the human p25
  per-level cost (32) — the most evidence a pre-completion state plausibly holds; 10 is the
  early-probe regime, descriptive only. A checkpoint is **valid only if the session has no
  completion before that offset**; invalid rows dropped and counted. *(Too small → floor
  effects; too large → mass invalidation on fast sessions.)*
- **Gate regimes:** zero-completion = the 30-action checkpoint · ≥1-completion = the
  after-1st-completion checkpoint. The 2nd/3rd-completion checkpoints feed E3's ladder, not the
  gate. *(Averaging regimes would mix evidence levels the design deliberately separates.)*
- **Aggregation:** per (game, regime): mean over sessions of the 0/1 outcome (class-top-3 hit;
  predicate actionable) → game-level bootstrap, resampling games, 10,000 draws, **90% CI**
  two-sided. *(Screening posture at n=15 games; 95% is confirmatory-grade power the sprint
  doesn't have.)*
- **K1 non-inferiority margin — REPLACED by operator:** the SPEC §9.5 posture — point
  regression ≤ 3 pp, one-sided 90% lower bound > −5 pp, per regime, reusing the existing
  standard. The earlier 1-SE proposal was rejected as anti-conservative: a noisier estimate
  would *widen* the tolerated regression.
- **K4 — REPLACED by operator (paired rescue):** denominator = **baseline-incorrect**
  `goal_unknown` episode-levels; champion actionable top-1 on ≥ 25% of them; within-game
  aggregation before inference; game-clustered 90% lower bound on paired improvement > 0;
  3 pp/−5 pp non-regression on baseline-correct cases. Corpus figures corrected: E2 holds
  **63 episodes — 39 `goal_unknown` primaries across 18 games** (not 44 across ~11). The
  pairing bars crediting correctness the baseline already had, one-game concentration, and
  absolute rates with no incremental value.
- **K5 — stability check REPLACED:** within-game average of the three replicate-pair deltas →
  one-sided sign-flip permutation over the 21 game-level deltas, p < 0.10, pooled mean > 0;
  stability = **≥ 2 of 3** replicate-pair means nonnegative (requiring all three is brittle at
  the measured 20–36% run noise and can reject a real effect the game-clustered test supports).
- **Call/runtime budget:** measured passes ≈ **1,830 8-bit calls** (iteration 6·3·5·4 = 360 ·
  one-shot 15·3·5·4 = 900 · E2 63·3·2 = 378, the ×3 being the E2 checkpoints defined above ·
  E3 ablation 21·3·3 = 189; floors ≈ free). Budgeted **separately from measurement**: gold
  generation (source annotation, no 8-bit calls) and rater passes — ≈ 504 blinded (a)-mappings
  (E1 90 + 225, E2 189) plus enumerated-equivalence adjudications, all logged. Before the
  iteration pass: a **20-call pilot** measures s/call at achievable concurrency; the grid must
  fit **≤ 3 overnights**, else the one-shot pass moves to the Kaggle FP8 notebook (which also
  upgrades it to the exact reference artifact).

---

## 2. Candidate GI-2, for pipeline continuity (one paragraph, undesigned)

`action_semantics_unknown` (20% primary, 49% episode share): a per-game **action-effect
catalogue** built online — programmatic delta summaries per (action, context) accumulated during
play and injected into the prompt. No training data needed (within-game accumulation, so the
17-domain cap does not bind), same E-series shape: offline replay of S1 episodes with/without
catalogue, then paired runs. The discriminating probes logged by GI-1's condition (b–d) outputs
feed this design. Design only after GI-1's gate is read.
