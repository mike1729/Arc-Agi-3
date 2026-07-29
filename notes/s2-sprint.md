# S2 working file — the procedural suite

> **⚠ TEMPORARY. DERIVED. NOT AUTHORITATIVE.**
>
> This file exists so the S2 sprint is readable in one place. It **decides nothing** and **defines
> nothing**. Every component description here is derived from
> [`arc-agi-3-implementation-spec.md`](../docs/arc-agi-3-implementation-spec.md) §4.9, every number
> from [`gate_manifest.yaml → s2`](../gate_manifest.yaml), every date from
> [`arc-agi-3-execution-schedule.md`](../docs/arc-agi-3-execution-schedule.md) §2.
>
> **Where this file disagrees with any of those, it is wrong.** Do not cite it. Do not amend it
> instead of them — a working file that starts carrying decisions is how a fourth authority gets
> created, which is [open item 1](../docs/README.md) happening again.
>
> **Delete on 2026-08-03**, when A5-G records its verdict. Nothing downstream may depend on it.

---

## 0. Where we are — 2026-07-29, day A2

S1 closed yesterday (κ 0.7207, promoted, DEGRADED branch). S2 is the next thing and it starts today.

### 🔴 The blocker, first

**`gate_manifest.yaml → s2` is `DRAFT`, not `frozen`.** It was written yesterday with every number
SPEC §4.9 demanded, but **nine of them are `PROPOSED`** — suggested, not accepted. The standing
convention is that a block is frozen with numbers filled *before* the step it governs, and **the step
it governs is today.**

Two of them bind work that happens **today and tomorrow**, so they are not deferrable:

| Needed by | Value | Why it cannot wait |
|---|---|---|
| **A2 — today** | `instance_diversity_per_family: 2000` | The Alias generator's parameterisation space is built today. Building it for 200 and discovering 2,000 was registered means rebuilding the mechanic, not tuning a constant |
| **A2 — today** | `frame_cap.encoder_frames_max: 8` | Decides whether S3 fits its 120 h budget (~97 h capped vs ~132 h uncapped). `notes/screening-training-data.md` says decide it on A2 rather than discover it as an OOM on A6 |
| **A3 — tomorrow** | Alias three-ceiling margins | A3's entire deliverable is "required pattern observed" — against margins that do not yet exist |
| **A4** | Delay `delay_length_steps` 12–24, `bit_sparsity`, distractors | The Delay mechanic is built to these |

The rest (held-out instance count, progress prevalence, pre-generated-corpus threshold, value
criterion + families, the fidelity two-sample test) are needed by A5-G.

**What to do:** read `gate_manifest.yaml → s2.open_before_A2`, accept or replace each PROPOSED value,
then flip `status: DRAFT` → `frozen` with `frozen_on: 2026-07-29`. It is one pass over one block.
Every proposal states its rationale and what it costs if wrong, so this is a review, not a design task.

**Do not build against PROPOSED values and backfill the manifest afterwards.** That inverts the
pre-registration and makes A5-G's acceptance meaningless — the gate would be reading numbers chosen
after seeing the generator.

---

## 1. What S2 is, in one paragraph

S2 builds **two procedural environment generators** — Alias and Delay — plus the interface, verification and
acceptance harness around them. It runs no experiment and decides no component. It is the only Tier 1
substrate delivered before the build phase (**SPEC §12.1 step 0**), and it is *inherited*, never
rebuilt. Everything else the screening sprint leaves behind is measurement scaffolding around the
vendored reference and ships nowhere.

**3.5 days budgeted** — A2 through A5, with acceptance at A5-G on Mon Aug 3.

> ⚠ **The 3.5-day budget predates the interface.** Three requirements were added by SPEC §4.9 on
> 2026-07-28 (ground-truth state IDs, seed/random-stream control with CRN declared, on-demand
> generation) and the budget has not been re-examined since. This is the third item in
> `s2.open_before_A2`.

### Why it is unconditional substrate and not an experiment fixture

Nine consumers, and the failure mode is not delay — it is unmeasurability:

| Consumer | What it reads from the suite |
|---|---|
| **S3** (A6–A10) | its entire training set — 51.2M transition presentations per run |
| **D0** (W1) | capability thresholds, measured on held-out procedural environments |
| **R0** (W5) | invariance across permuted-role environments; hidden-mechanics recovery |
| **§6 retention** | every retention decision rests on procedural paired runs |
| **§13.1 τ bounds** | \(\tau_{min}, \tau_{max}\) from procedural calibration |
| **§13.1 \(q_{hi}, q_{lo}\)** | 90th / 50th percentile of procedural held-out calibration error |
| **§6.4 clause 3** | ECE-verified calibration on procedural held-out data |
| **§9.4 splits** | held-out procedural instances · held-out goal parameters |
| **§5 progress head** | the one supervision source where progress prevalence is a *design parameter* |

Because instances are generated, **§13.5's leakage policy does not apply to them** — which is exactly
why procedural evidence *retains* while public validation only *vetoes*.

---

## 2. The two families

### Alias — history-required aliasing

**Visually identical observations require different actions**, because of a hidden switch, counter or
phase. The observation alone is insufficient; the history disambiguates it.

What the generator must control:

- a **hidden mechanic state** — switch / counter / phase — not visible in any frame;
- an **aliasing guarantee**: at least one pair of states in every instance is observationally
  identical (byte-equal serialized observation) while requiring different optimal actions;
- **history sufficiency** — the hidden state must be *recoverable* from the complete observable
  history. This is what the three ceilings test, and it is not automatic: a mechanic can be hidden
  *and* unrecoverable, which makes the family untestable rather than hard.

> **The timestep subtlety.** Observations are frame *sequences* (mean 2.86, max 404). Part of the
> "history" the aliasing test concerns therefore lives **inside a single observation**. Alias's timestep
> must be defined against this explicitly, or its ceilings measure something other than what they
> claim. — SPEC §4.9

### Delay — sparse delayed causal memory

**A one-cell change with no short-term effect that determines a later transition.**

This is the **central risk for reconstruction-free prediction** and the reason arm C is mandatory: a
latent objective has almost no gradient pressure to preserve a bit whose consequence lies outside the
training horizon, while an exact target retains it structurally.

**Alias alone sits in the short-horizon regime where a latent predictor looks good, so without Delay any
positive result is biased in favour of the latent arm.** Delay is not optional coverage.

Registered mechanic parameters (all `PROPOSED`, see §5):

| Parameter | Value | Set against |
|---|---|---|
| Causal-delay length | 12–24 steps, uniform per instance | §11.1 trains heads at 1/2/4 steps, names an 8-step rollout, K=16 window. 12 clears the rollout; 24 clears the window |
| Causal cells | **1** cell of 64×64 | This is §4.9's definition, not a tuning choice |
| Distractor cells changed | 8 | Without distractors Delay degenerates into change-detection |

**The delay is verified BY CONSTRUCTION** — the generator asserts the bit is written at *t*, has no
observable effect through *t+delay−1*, and determines the transition at *t+delay*. It is **never**
inferred from a trained model's behaviour. *(SPEC §4.9 acceptance, structural criterion — binding.)*

---

## 3. The components to build

Seven, and only the first two are "the generators". The spec's interface list is the governing one;
this groups it by what actually gets written.

### C1 · Observation layer *(shared, build first)*

Everything else emits through it. Every row here is **measured**, not chosen — 25/25 public games
(2026-07-26) and 340 replays (2026-07-28).

| Convention | Target |
|---|---|
| Grid shape | 64×64 at reset, **always** |
| Cell values | 0–15, **all sixteen occur** |
| Levels per instance | 6–10 (mode 6) |
| Action availability | **fixed per instance, not per state** (per-state variation is permitted by the interface but evidenced in no measured game) |
| Frames per observation | **variable-length**, matching the measured distribution: 71.0% single, mean **2.86**, max **404** |

> 🔴 **The frame-sequence requirement is load-bearing three times over.** A single-grid generator emits
> a distribution the real environment never produces · any encoder must consume 1–N frames or silently
> discard most of the observation at exactly the steps where something changed · Alias's timestep is
> defined against it.

**Cap asymmetry, and it is easy to get backwards:** the **generator emits the full uncapped
distribution**; the **encoder** truncates at 8 frames. Capping the generator would violate observation
fidelity by construction. The cap is an S3-side cost decision, not a suite property.

### C2 · Alias generator

The aliasing mechanic (§2), its parameterisation space, and the guarantee that aliased pairs exist and
are history-resolvable.

### C3 · Delay generator

The sparse delayed causal mechanic (§2), with by-construction delay verification.

### C4 · The §4.9 interface *(binding — this is the governing list)*

Per instance, the generator exposes:

1. **legal action set**
2. **exact successor for every legal action** — the counterfactual supply §4.1 delegates here. This is
   the single most valuable thing the suite produces: replays structurally cannot contain it at any
   volume, and six build artifacts depend on counterfactuals
3. **terminal / progress predicate**
4. **immediate action value or distance-to-goal** — the ranking criterion. **EVALUATION-ONLY** (C6)
5. **hidden mechanic state and parameters**, and **which state variables are causally relevant** —
   §10.2's hidden-mechanics recovery reads these
6. **recoloured and relaid-out variants with colour roles explicitly permuted** — §10.2 requires
   invariance across permuted-role environments *while requiring colour sensitivity within one*
7. **ground-truth state IDs** — §6.6's Jensen–Shannon divergence needs a policy-independent key
8. **instance seed and environment random-stream control**, with common-random-number support
   **declared per generator, never assumed**
9. **on-demand generation** — §13.1's insufficient-evidence rule extends procedural paired runs, which
   a fixed pre-generated set cannot serve. *This is an architecture requirement: the generator is a
   live reproducibly-seeded sampler, not a dataset.*

*(Items 7–9 are the three added 2026-07-28 that the 3.5-day budget predates.)*

### C5 · Three-ceiling verification harness *(Alias correctness)*

Runs Alias three ways and checks the required pattern:

```
observation-only  <  history-oracle  ≈  hidden-state-oracle
```

- **observation-only** — the current observation, nothing else
- **history-oracle** — complete observable history with an oracle decoder
- **hidden-state-oracle** — the true hidden mechanic state, handed over

**Why all three.** Oracle-hidden-state beating observation-only shows hidden information *matters*. It
does **not** show history contains enough to *recover* it. If the history oracle sits far below the
hidden-state oracle, **the task is not learnably history-resolvable and model failure on it is
expected rather than informative** — and without this ceiling that would be misread as a model result.

### C6 · Value / distance-to-goal criterion

Exact shortest-path distance to the nearest goal-satisfying state, in actions, computed from ground
truth. For **Delay**, computed on the **post-commit** state — conditioned on the value already written to
the causal cell, because before the bit is set the true distance is not a function of the observed
state at all, which is the entire point of the family.

> **EVALUATION-ONLY, and this is binding.** If it trains a value head, an objective comparison
> silently becomes supervised action ranking. Exposed to evaluation and ranking code only; it appears
> in **no** arm's training target. — SPEC §4.9

### C7 · Acceptance harness *(A5-G)*

Measures the six criteria against their registered values and writes a pass/fail artifact. Per the
project convention, this is **generated from logs by a script**, never hand-assembled — same pattern as
`s1d_rollup.py --verify`.

---

## 4. Schedule — what gets built, day by day

| Day | Date | Build | Done means |
|---|---|---|---|
| **A2** | Wed Jul 29 | **C1** observation layer · **C2** Alias generator: aliasing mechanic, parameterisation space, variable-length frame emission | **Alias emits, and the conventions are asserted in a test** — not inspected by eye. Every row of C1's table is a test case |
| **A3** | Thu Jul 30 | **C5** three-ceiling harness; run it on Alias | **Required pattern observed on the registered margins** — or Alias is declared not history-resolvable and the mechanic is redesigned. This is a real branch, not a formality |
| **A4** | Fri Jul 31 | **C3** Delay generator at the registered delay and bit sparsity | **Delay emits; delay verified by construction** — the assertion runs in the generator, not in an analysis afterwards |
| **A5** | Mon Aug 3 | **C4** interface completed to all nine §4.9 items · **C6** value criterion · methods prose | **Every §4.9 item present, so S4 needs no re-engineering.** The three late-added items are where this day will actually go |
| **A5-G** | Mon Aug 3 | **C7** acceptance harness; run it | **SPEC §12.1 step 0: pass recorded, or unmet criteria named** |

**Methods prose is written on A5, the day the thing is built** — into `paper/methods/`. Standing
obligation, not a nice-to-have; `paper/methods/s2-goal-predicate-extraction.md` and
`s2-human-replay-corpus.md` are already there and set the pattern.

### What happens on A6 depends on A5-G

**Start the first S3 training runs on A5, not A6** — the generators are ready a day before S3 formally
opens — **but only once A5-G passes.** Training on an unaccepted generator spends GPU hours that step 0
may invalidate, and S3 has no slack to repeat them.

S3 is **46.2 h of GPU against a 120 h budget**, ~9 h/day over five focused days. It must run unattended
overnight and cannot contend with other local GPU work.

---

## 5. The gate — SPEC §12.1 step 0, six criteria

Four numeric (acceptance reads exactly the registered value) and two structural (pass only on a stated
condition). Status as of 2026-07-29:

| # | Criterion | Registered | Status |
|---|---|---|---|
| 1 | **Throughput** | **3,710 transitions/s** sustained ≥ 60 s at the emitted frame distribution | ✅ **ACCEPTED** — arithmetic over the measured 7.22 steps/s benchmark: K=16 × batch 32 = 512 transitions/step at 138 ms |
| 2 | **Held-out instance count** | 200/family, 400 total; disjoint **at instance level**, never a random transition split | ⚠️ PROPOSED |
| 3 | **Instance diversity** | 2,000 distinct hidden-mechanic **parameterisations** per family (not seeds) | ⚠️ PROPOSED |
| 4 | **Progress prevalence** | 0.05 ± 0.01, per family, reported | ⚠️ PROPOSED — measured anchor is **0.0090** |
| 5 | **Generator correctness** | Alias's three-ceiling pattern on registered margins; Delay's causal delay verified by construction | ⚠️ pattern is binding; **margins** PROPOSED |
| 6 | **Observation fidelity** | every row of C1's table, including the frame-length distribution | ✅ **ACCEPTED** — all measured. Test statistic still unregistered |

### The three that will actually bite

**Criterion 3 is the dangerous one.** Unlike every other criterion it fails by producing a **result**
rather than an error:

> Generate 51.2M transitions from 20 hidden-mechanic parameterizations and a 21M-parameter model
> memorizes the mapping, producing a clean, well-controlled, meaningless positive.
> — `notes/screening-training-data.md` §2(b)

Nothing in the S3 output would look wrong. The failure is asymmetric — too few silently invalidates
the whole screening sprint, too many costs generation time, which criterion 1 already requires be
cheap. That asymmetry is why the proposal sits at the top of the documented range.

**Criterion 1 is the one most likely to be missed outright.** A single-process Python gridworld
typically does not sustain 3,700 transitions/s. Two escapes: parallelise across cores, or pre-generate
— but pre-generating reintroduces the epoch question S3 otherwise escapes, and triggers a ≥ 2.56M
distinct-transition floor.

**Criterion 4's real obligation is calibration, not prevalence.** A progress head trained at 5% and
deployed against the real 0.90% is miscalibrated by construction. SPEC §3.2 requires the prevalence be
registered *and* calibrated; setting the number does not discharge the second half.

### On failure — binding, and declared in advance

Reporting a failure does not discharge the dependency:

- **W1's non-dependent substrate continues** — harness, accounting, replay, terminal-transition
  logging, the §13.5 partition;
- **D0 and every procedural-dependent item are blocked** until acceptance passes;
- **Blocked means not attempted.** A D0 threshold that reads held-out procedural environments is
  recorded **`untested`**, never `passed`. §10.1's freeze-before-inspection rule is unaffected;
- What blocking costs the calendar is [open item 6](../docs/README.md) — deliberately *not* absorbed
  by these criteria.

---

## 6. Evidence already in hand

S2 measurement work that is **not** the generator, and that feeds the pre-registration rather than
being governed by it:

| Artifact | What it gives S2 |
|---|---|
| `logs/s2_arc_conventions.json` | C1's fidelity targets — 25/25 games, 2026-07-26 |
| `logs/s2_corpus_census.json` + `notes/screening-training-data.md` | the frame distribution (516,260 grids / 180,144 transitions) and the 0.90% progress anchor |
| `logs/s2_goal_predicates_labelled.json` | goal-predicate class per game, all 25, **blind re-rate κ 0.947** — the evidence behind C6's families |

### The goal-predicate distribution, and a caveat it raises

Measured primary class across the 25 public games:

| Class | Primary | Any |
|---|---:|---:|
| `quantified_object_conditions` | **9** | 13 |
| `state_relations` | **6** | 12 |
| `symmetry_and_template_match` | 5 | 6 |
| `all_instances_transformed` | 2 | 3 |
| `event_occurrence` | 1 | 4 |
| `ordered_event_programs` | 1 | 1 |
| `counts` | 1 | 2 |
| `region_membership` | 0 | 5 |
| `action_conditioned_terminal_triggers` | **0** | **0** |
| `cumulative_counters` | **0** | **0** |

C6 proposes instantiating the top two — 15 of 25 games between them.

> **⚠ This bears on the Aug 22 Fork G-F decision.** SPEC §9.6 Branch A proposes building the **Order**
> (ordered-event-program) and **Count** (cumulative-counter) families at ≥ 5 build-days. Those are the two
> the public set exercises *least*: Order is the primary goal class in **1 of 25**, Count in **0 of 25** —
> it is in the codebook's `unused_classes`. It does not settle the decision (the hidden set is not the
> public set, and testability has value independent of frequency), but the evidence did not exist when
> §9.6 was written.

---

## 7. Risks

| Risk | Reality | Where it lands |
|---|---|---|
| **Throughput miss** | A single-process Python gridworld typically misses 3,700/s. If it lands an order low, S3's 46.2 h estimate is wrong by that order | S3 overruns the sprint's only decision-bearing block |
| **Insufficient diversity** | Fails by producing a clean positive, not an error | The whole screening result is void, and nothing signals it |
| **Alias not history-resolvable** | A mechanic can be hidden *and* unrecoverable | A3 branch — redesign, mid-sprint, with no float allocated |
| **Frame cost** | Uncapped ≈ 132 h against a 120 h budget. It does not fit | Decide the cap today, not as an OOM on A6 |
| **Budget predates the interface** | 3.5 days priced before three §4.9 items were added | A5 is where it shows |
| **Building on PROPOSED values** | Inverts the pre-registration | A5-G's acceptance becomes meaningless |

---

## 8. Definition of done

S2 is done when **A5-G writes a verdict artifact** — pass, or unmet criteria named. Not when the
generators run.

- [ ] `gate_manifest.yaml → s2` is `frozen`, every PROPOSED value accepted or replaced ← **today**
- [ ] C1 observation layer, every convention row asserted in a test
- [ ] C2 Alias emits
- [ ] C5 three ceilings run; required pattern observed on registered margins
- [ ] C3 Delay emits; delay verified by construction
- [ ] C4 all nine §4.9 interface items present
- [ ] C6 value criterion, evaluation-only, in no training target
- [ ] C7 acceptance harness written; verdict artifact on disk
- [ ] methods prose in `paper/methods/`
- [ ] **this file deleted**
