# What the screening experiments train, and whether the data exists — 2026-07-28

Sizing for every learned component in S2 → S3 → S4, against measured corpora. Companion to
[`evaluator-training-data.md`](evaluator-training-data.md), which covers the **build-phase** evaluator
(W3); this note covers the **sprint**. All corpus numbers are reproducible via
`agent/harness/s2_corpus_census.py` → `logs/s2_corpus_census.json`, one streaming pass over the 6.4 GB
replay archive. Where a number is a judgment rather than a measurement it is marked **[judgment]**, and
anything that should bind belongs in `gate_manifest.yaml`, not here.

---

## 0. Verdict

| Trained component | Sprint | Data source | Verdict |
|---|---|---|---|
| F1/F3 three ceilings ×2 families | S2 | procedural | **fine** — data is generated, and prevalence is a design parameter |
| A / B / C encoders + predictors, ×rollout, ×2 seeds | S3 | procedural | **not data-limited, but throughput-limited and compute-underbudgeted** |
| observation-only A · affordance/no-op control | S3 | procedural | fine |
| degeneracy probes, ranking readouts | S3 | procedural held-out | fine — cheap |
| A / B / C retrained on ARC replays | S4 | replays, 180,144 transitions | **epoch-limited**; game-level split leaves 79k–156k |
| advisor readout — changed-region | S4 | replays | **solved**, 701M cell labels |
| advisor readout — no-op avoidance | S4 | replays | **8,945 positives, 5 games supply almost none** |
| advisor readout — candidate pruning | S4 | replays | **the real gap — 204 progress-bearing counterfactual pairs in the whole corpus.** Obtainable locally — §5b |
| advisor readout — reversibility (W3, listed for completeness) | — | replays | 5,065 positives, **zero** demonstrated-irreversible; the negative class must be searched for — §5b |
| closed-loop advisor delta | S4 | live games | not a data problem; **the replicate count is unregistered and it is what decides the verdict** |

**One-line answer.** Nothing in screening is starved of *transitions*. S3 is starved of a *generator
that does not exist yet* and is quietly over its compute budget; S4 is starved of *counterfactuals*,
which is a kind of data replays structurally cannot contain — **but which the local game sources plus
`arcengine` can manufacture, subject to a leakage constraint that decides how much of it is usable
(§5b).**

---

## 1. What screening actually trains — 20+ artifacts, not three

| Sprint | Trained | Count |
|---|---|---|
| **S2** | ceiling models per family: observation-only · history-oracle decoder · hidden-state oracle | **6** (3 × F1/F3) |
| **S3** | main runs: {A latent, B reconstructive, C exact-delta} × {rollout, no-rollout} × 2 seeds | **12** at ~21.2M params |
| **S3** | cheap controls: observation-only variant of A · affordance/no-op classifier | **2+** |
| **S3** | downstream ranking readout, matched fitting budget, one per configuration | **12** |
| **S3** | degeneracy probes — control-variable probes per learned representation, **symmetric across arms** | **≥ 3 sets** |
| **S4** | the three objectives **retrained on ARC replay training games** | **3** (× replicates) |
| **S4** | frozen advisor readouts: candidate pruning · no-op avoidance · changed-region | **3 heads** |

The oracle-successor ranking ceiling (S3) and the F1 hidden-state oracle are not learned from data —
they read the generator's ground truth.

---

## 2. One arithmetic governs S3

From `notes/local-compute-options.md`, the benchmark that produced 7.22 steps/s: **K = 16 transitions,
batch 32**. So one gradient step consumes **512 transitions**, and:

| | |
|---|---:|
| transitions per gradient step | 512 |
| per run at the budgeted 100k steps | **51.2M** |
| across all 12 S3 runs | **614M** |
| generator throughput to keep the GPU fed, at 138 ms/step | **3,710 transitions/s** |

Two consequences, neither currently written down anywhere:

**(a) The generator must sustain ~3,700 transitions/s, or S3 becomes data-bound.** A single-process
Python gridworld typically does not. The alternatives are to parallelize generation across cores, or to
pre-generate a fixed corpus — but a pre-generated corpus reintroduces the epoch question S3 otherwise
escapes. **[judgment]** at ≤ 20 epochs for a 21.2M model that means ≥ **2.56M** distinct pre-generated
transitions.

**(b) Distinct *instances* decide the result, not distinct transitions.** F1 asks whether history
resolves an aliased observation. Generate 51.2M transitions from 20 hidden-mechanic parameterizations
and a 21M-parameter model memorizes the mapping, producing a clean, well-controlled, meaningless
positive. The held-out set must be disjoint **at the instance level**, mirroring SPEC §9.4's ban on
random transition splits. The instance count and the held-out instance count are both unregistered —
`gate_manifest.yaml → s2` currently covers only the value criterion, the F1 ceiling margins, and F3's
delay length and bit sparsity.

---

## 3. What exists — measured 2026-07-28

### Human replays — 340 recordings, 6.4 GB

| | | share |
|---|---:|---:|
| rows | 180,484 | |
| **transitions** | **180,144** | |
| changed | 171,199 | 95.03% |
| **no-op** | **8,945** | **4.97%** |
| **terminal (progress positive)** | **1,614** | **0.90%** |
| distinct settled frames | 142,501 | 79% of rows |
| **64×64 grids** | **516,260** | mean **2.86** per observation |
| ACTION6 | 56,347 | 31.2% |

Action mix: ACTION6 31.2% · ACTION4 18.5% · ACTION3 17.2% · ACTION1 14.9% · ACTION2 13.5% ·
ACTION5 3.4% · RESET 1.1% · ACTION7 0.2%.

**The frame-count distribution is far heavier-tailed than the earlier spot-check suggested.** 71.0% of
observations are a single grid; the rest run to **N = 404**. This is a cost fact, not a curiosity — see
§5(a).

### Reference-agent logs — three Kaggle runs

| | v2 | v3 | v4 | total |
|---|---:|---:|---:|---:|
| transitions | 3,866 | 4,776 | 3,833 | **12,475** |
| changed | 3,501 | 4,102 | 3,426 | 11,029 |
| no-op | 365 | 674 | 407 | 1,446 (11.6%) |
| terminal | 15 | 18 | 16 | **49** (0.39%) |

Exact labels for free — `board`, `board_changed`, `level_completed`, `reward` per action, all 25 games.
**But `board` is a single 64×64 grid, not the frame list.** The agent corpus is frame-collapsed and
cannot teach the 1–N convention; it is usable for the factual heads and OOD calibration, not for the
observation-shape question.

### Procedural F1/F3 — **does not exist yet**

Built A2–A5 (Jul 29 – Aug 3). Unbounded in principle; progress-event prevalence and counterfactual
labels are design parameters rather than observations. **The whole of S3's training set is a thing that
gets written next week**, which is why §2(a)'s throughput requirement is worth pricing now rather than
discovering on A6.

---

## 4. Component by component

### S2 — the six ceiling models

**Need:** enough matched data to separate observation-only from history-oracle from hidden-state-oracle
by more than noise, and enough held-out *instances* that the separation is not memorization.
**Have:** generated on demand. **Verdict: fine.** The risk here is not data volume — it is that the F1
ceiling margins in `gate_manifest.yaml → s2` are unwritten, so "the required pattern was observed" has
no threshold to be judged against.

### S3 — the twelve main runs

**Need:** 51.2M transition presentations per run, fixed by the 100k-step budget. **[judgment]** ≥ 2.56M
distinct transitions if pre-generated; distinct hidden-mechanic instances in the hundreds-to-low-
thousands per family, with a disjoint held-out instance set.
**Have:** zero today; unbounded from Aug 3. **Verdict: not data-limited. Throughput-limited, and over
budget on compute — see §5(a).**

### S3 — controls and probes

The observation-only A control and the affordance/no-op classifier inherit the matched-information
rule, which requires a matched *optimization* budget with no number attached to it (flagged in
`local-compute-options.md`). Degeneracy probes need only a few thousand held-out transitions per
control variable. **Verdict: fine, not binding.**

### S4 — the three objectives on replays

This is where a finite corpus starts to bite.

| Step budget | Presentations | Epochs over 180,144 transitions |
|---:|---:|---:|
| 10k | 5.12M | **28** |
| 50k | 25.6M | **142** |
| 100k | 51.2M | **284** |

And the split is at the **game** level ("evaluate on held-out games"), so the training half is smaller
still — **79,329 to 155,842 transitions** depending on which games are held out. With K = 16 windows,
180,144 transitions is only ~11,300 non-overlapping windows; sliding windows give more start positions
but heavily autocorrelated ones, which is exactly the condition the feasibility analysis §8.1 names as
the trigger for silent EMA degeneracy.

**Verdict: epoch-limited.** **[judgment]** S4 should run at a materially smaller step budget than S3,
or a smaller model, and the choice must be identical across A/B/C or it breaks matched information.
There is no registered S4 step count.

### S4 — advisor readout: changed-region prediction

171,199 changed transitions × 4,096 cells ≈ **701M dense cell labels**. **Verdict: solved.**

### S4 — advisor readout: no-op avoidance

**8,945 positives corpus-wide**, and badly concentrated: dc22, lp85, sk48 and ar25 supply 54% of them,
while **lf52, r11l, tu93, bp35 and tr87 supply fewer than 50 each** — three of those have a measured
no-op rate of 0.0%. The agent logs add 1,446 at a higher prevalence (11.6%), which helps.
**Verdict: adequate, partition-sensitive.** See §6.

### S4 — advisor readout: candidate pruning

**This is the gap, and it is a gap in kind, not in amount.** Replays are on-policy: one action per
state, every alternative unobserved. The only counterfactual evidence is a state visited twice with
different actions.

| | frames | pairs |
|---|---:|---:|
| ≥ 2 distinct discrete actions (ACTION1–5) | 5,135 of 98,233 (5.2%) | **6,795** |
| ≥ 2 distinct ACTION6 coordinates | 4,572 of 44,129 (10.4%) | **56,811** |

The coordinate total looks generous and is mostly not what it appears. Split by what each click
actually did:

| pair type | count | share |
|---|---:|---:|
| change \| change | 22,883 | 40.3% |
| change \| no-op | 16,977 | 29.9% |
| no-op \| no-op | 16,747 | 29.5% |
| **any pair involving a terminal** | **204** | **0.36%** |

So **59.5% of the coordinate counterfactuals only teach dead-cell rejection**, which is useful but is
the no-op head's job. The pairs that answer *"which of these two effective actions is better"* number
**23,032**, and the pairs that answer *"which one makes progress"* number **204 in the entire 6.4 GB
corpus.**

The per-game concentration is severe: lp85 alone supplies 35,772 of the 56,811 coordinate pairs, and
sk48 and ar25 are 99% and 97% dead-cell pairs respectively.

**Verdict: replays cannot train counterfactual ranking, and no larger replay corpus would fix it.**
This is why SPEC §5 stages supervision honestly — 4a factual, 4b weak/biased/declared, and
**no unbiased-ranking claim before evaluator v2 post-R1** — and why §13.1 buys counterfactuals from the
branching rounds instead: 3 rounds × 17 dev games × 40 disagreement slots = 2,040 nominal, plus 15
ACTION6 slots per game-round at n=20 candidates. For S4, which runs before any branching, the
consequence is direct: **candidate pruning must be reported as an evaluation stratified by observed
outcome, never as a trained ranking objective** — consistent with the screening document's existing ban
on treating the human's next action as ground-truth action quality.

### S4 — the closed-loop advisor delta

Not a training-data problem. The binding resource is **replicates**, at a measured 36% run-to-run
disagreement floor (§3.4), and the replicate count is unregistered with S4 starting Aug 11. This is the
single measurement that can retain or kill Tier 3, and its power is currently undefined.

---

## 5. Three findings that change the plan

### (a) S3's compute estimate assumes one grid per transition. The convention says 2.86.

`bench_training.py` measured 7.22 steps/s at "K = 16 transitions, 64×64 grid" — **one** grid each. But
the S2 generators are *required* to emit variable-length frame sequences matching the real
distribution, and any encoder is *required* to consume 1–N frames. At the measured mean of 2.86 grids
per observation, honouring the convention multiplies the encoder's input volume by the same factor:

| Frame cap | Observations fully covered | Mean grids | 12 runs × 100k steps |
|---:|---:|---:|---:|
| 1 (as benchmarked) | 71.0% | 1.00 | 46 h — fits |
| 2 | 80.3% | 1.29 | 60 h — fits |
| 4 | 85.0% | 1.64 | 76 h — fits |
| **8** | **92.5%** | **2.10** | **97 h — fits, 23 h slack** |
| uncapped | 100% | 2.86 | **132 h — over the 120 h budget** |

**The honest reading: S3 at 21.2M / 100k steps / uncapped frames does not fit in its 5 days.** A cap of
8 frames covers 92.5% of observations and lands at ~97 h. That cap is a real modelling decision, not a
convenience — the screening document's §7 point 3 notes that when an observation is itself a sequence,
part of the history F1 is about lives *inside* a single observation, so truncation interacts with what
F1 measures. Decide it deliberately on A2 and register it; do not discover it as an OOM on A6.
(Superlinear attention over a concatenated sequence would be worse than this table; the table assumes
per-frame encoding with pooling.)

### (b) The generator throughput requirement is unpriced

§2(a): ~3,710 transitions/s to keep S3 compute-bound. Nothing in the schedule, the spec, or the
manifest mentions generator throughput. If it lands an order of magnitude low, the 46.2 h estimate is
wrong by that order and S3 overruns the sprint's only decision-bearing block.

### (c) Progress-bearing counterfactual pairs: 204

Reported above. Worth restating separately because it is the number that justifies both the branching
budget and SPEC §5's staged-supervision honesty, and it is much smaller than the 56,811 headline.

---

## 5b. What actually lacks data, and where it comes from

Three shortages, three different kinds, three different answers.

### Kind 1 — exists, never extracted. One pass each, no new data.

| Signal | Status |
|---|---|
| exact deltas | derivable, free — 701M cell labels |
| **demonstrated reversible** | **counted 2026-07-28: 5,065 positives** (2.81% of transitions) |
| goal predicates per game | **already extracted, 25/25** by `s2_goal_predicates.py`; all 25 records are `unlabelled` — the outstanding work is *rating*, not acquisition |

### Kind 2 — a generator that gets written next week

S3's entire training set. Scheduled A2–A5. The risks are throughput (§5b) and instance diversity
(§2b), not availability.

### Kind 3 — replays structurally cannot contain it, at any volume

Two signals, and they fail for the same reason: **a recording of what one human did contains no
information about what a different action would have done.**

| Signal | From replays |
|---|---:|
| counterfactual ranking — which of two effective actions is better | 23,032 pairs, of which **204** involve progress |
| **demonstrated irreversible** — verified *absence* of a return route | **0** |

**There is a source, and it is already on disk.** `data/environment_files/<game>/<hash>/<game>.py`
holds readable Python for **all 25 public games** (3.9 MB, verified present), and the engine they run
against — **`arcengine`, currently 0.9.3 — is on PyPI.** Nothing here needs the platform. The source
exposes `step`, `_get_valid_actions`, `_get_hidden_state` and `next_level()`, so a local harness that
forks game state yields, on demand:

- **exact successor for every legal action from any reachable state** — the counterfactual ranking
  labels replays cannot hold, at whatever volume is wanted;
- **verified no-return-route search** — the reversibility head's missing negative class;
- **progress events at a chosen prevalence** rather than the observed 0.90%;
- **oracle hidden state on the real games**, which is F1's ceiling 3 measured on ARC rather than only
  on procedural families;
- **per-state action availability** — currently recorded as "permitted by the interface but NOT
  evidenced", held fixed per game on an assumption that this settles directly.

**Four constraints, and the third is not optional.**

1. **Licensing.** `arcengine` is third-party (bucket 2 — separate sharing requirements, *not* required
   to be CC0/MIT-0) and the game sources are competition-provided. Local use is not redistribution;
   this interacts with open item 5 exactly as the replays do, and inherits the same unanswered
   question about shipping weights trained on it.
2. **Version fidelity.** The local source is version-hashed per game. Whether it matches what the
   platform runs is unverified, and a mismatch silently makes every generated label wrong.
3. **Leakage — the binding one.** Exhaustively branching the 25 public games and training on the
   result builds a lookup table for the public set, and public is materially easier than hidden
   (13.33% vs 7.78%). **SPEC §13.5 applies with full force: dev partition only, and the 8 validation
   games are never touched.** Even on dev games this is training on an oracle, so it belongs in the
   supervision-honesty ladder of SPEC §5 as a declared stage — not folded silently into 4a.
4. **It does not replace R1–R3.** The branching rounds measure the *agent's own* branch yield under
   the real cost model; a local oracle measures none of that.

**Highest-value uses, in order.** *(a)* Build **S4's counterfactual evaluation benchmark** — the
outcome-stratified ranking set S4 currently cannot construct, on dev games, evaluation-only, which
sidesteps constraints 1 and 3 entirely. *(b)* Validate that S2's F1/F3 generators match real-game
conventions before A5 freezes the interface. *(c)* Harvest demonstrated-irreversible labels for the
W3 evaluator. *(d)* Settle the per-state action-availability question — descriptive, all 25 games
permitted under §13.5.

**Cost and risk.** This is a capability discovered on Jul 28, one day before A2. It is not on the
schedule, and it is the kind of work that can eat a sprint. The 7 float weekdays exist; spending them
here is a real trade against S3 overrun risk (§5a). **[judgment]** *(a)* and *(d)* are cheap and
high-value; *(c)* is worth a day; a full counterfactual-training pipeline is not sprint work.

---

## 6. Partition sensitivity — five signals, not one

[`evaluator-training-data.md`](evaluator-training-data.md) and SPEC §5 both recommend drawing the
§13.5 partition **stratified by terminal-transition count**. That is necessary and **provably not
sufficient.** The 17/8 draw moves five signals independently:

| Signal | Total | Dev, worst draw | Dev, best draw | Swing |
|---|---:|---:|---:|---|
| **no-op positives** | 8,945 | **1,920 (21%)** | 8,679 (97%) | **4.5×** |
| **ACTION6 transitions** | 56,347 | **12,613 (22%)** | 55,686 (99%) | **4.4×** |
| discrete counterfactual pairs | 6,795 | 32% | 96% | 3.0× |
| transitions | 180,144 | 79,329 (44%) | 155,842 (87%) | 2.0× |
| terminal transitions | 1,614 | 850 (53%) | 1,287 (80%) | 1.5× |

**Terminal count is the *least* volatile of the five.** Stratifying on it alone can still leave the dev
partition with 21% of the no-op supervision or 22% of the coordinate supervision — six games contain
**zero** ACTION6 at all (g50t, ls20, re86, tr87, tu93, wa30) and five contain almost no no-ops.

**Recommendation, strengthened:** draw the partition under a **multi-criterion balance constraint** —
terminal count, no-op count, ACTION6 count, and total transitions each within a declared tolerance of
the 17/8 proportional share — rather than stratifying on one. Reject-sample draws until all four hold,
and record the realized shares. It is one-shot, frozen at W1, never backfilled.

---

## 7. What to register before it binds

Ordered by when it is needed. None of these numbers exist yet; none should be invented here.

| # | Number | Needed by | Currently |
|---|---|---|---|
| 1 | F1 three-ceiling margins; F3 delay length and bit sparsity | **A1, Jul 28** | named in `s2: NOT_STARTED` |
| 2 | **Generator instance count and held-out instance count** per family | A2 | absent |
| 3 | **Frame cap** for the encoder, and whether the generator's frame-length distribution matches the measured one | A2 | absent — §5(a) |
| 4 | **Procedural progress-event prevalence** (observed is 0.9%; generating at 0.9% wastes the one degree of freedom procedural data offers) | A2 | absent |
| 5 | Generator throughput target | A5 | absent — §5(b) |
| 6 | S3 matched optimization budget — the step count, stated once, identical across arms | A6 | "matched" with no number |
| 7 | S3 primary metric + threshold per screening question; \(T_v\), \(T_r\); rescue coefficients | A6 | named in `s3: NOT_STARTED` |
| 8 | **S4 step budget and model size** — smaller than S3's, identical across A/B/C | A11 | absent |
| 9 | **S4 replicate count** at the 36% noise floor | A11 | absent — flagged in schedule §5 |
| 10 | S4 train/held-out game split — and whether it is drawn as the §13.5 partition so the same 8 games stay clean through the build | A11 | absent |

Item 10 is worth a decision rather than a default: if S4 draws its own split, either the build's
validation games get evaluated on before W1, or two different splits coexist and the sprint's held-out
result says nothing about the build's held-out set.
