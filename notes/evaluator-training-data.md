# How much data the cheap evaluator needs, and where it comes from — 2026-07-28

Sizing for [SPEC §5](../docs/arc-agi-3-implementation-spec.md), written when the §5 amendment
(`EVAL-SCOPE-2026-07-28`) pinned the architecture. Numbers below are **measured** unless marked
otherwise; targets that would need to be pre-registered are flagged as such rather than asserted here.

---

## 1. The heads are not equally hungry

| Head | Label | Labels per transition | Verdict |
|---|---|---:|---|
| changed-region estimate | exact delta | **4,096** (one per cell) | data-rich by three orders of magnitude |
| P(no-op) · P(visible change) · P(persistent change) | settled-frame comparison | 1 | data-rich; roughly balanced in agent logs |
| reversibility, 3-valued | return route observed, same level, ≤ 30 actions | 1, **but only when a return happens** | sparse on-policy; *unknown* is never trained as negative, so absence gives nothing |
| **P(progress event)** | level / score marker or registered progress signature | 1, **positive ~0.5–0.9% of the time** | **binding constraint** |
| candidate value | frozen formula over the above | derived | n/a |
| uncertainty / OOD | — | — | n/a |

**One transition yields 4,096 dense cell labels and ~0.007 progress positives.** That ratio is the
whole sizing problem. The changed-region head is solved by any corpus at all; the progress head governs
how much data the component actually needs.

---

## 2. What exists today — measured

### Human replays — a full transition corpus, not just a list of outcomes

**Corrected 2026-07-28, same day:** an earlier version of this note treated the replays as supplying
1,613 terminal transitions. That understated them by two orders of magnitude. Each
`*.recording.jsonl` row carries `frame` (a list of 64×64 grids, 1–N, matching the measured
variable-length convention), `state`, `action_input`, `available_actions`, `levels_completed` and
`full_reset` — so **consecutive rows are a complete (observation, action, next-observation) transition
with exact deltas derivable.** 340 files, 6.4 GB on disk.

**Refined 2026-07-28 by a full streaming pass** (`agent/harness/s2_corpus_census.py` →
`logs/s2_corpus_census.json`): the 180,836 figure quoted here is the raw **line** count. It is not an
observation count and not a transition count. Exactly: 180,836 lines − 340 session-summary tails − 12
rows carrying `"frame": []` = **180,484 observations**, and after 340 chain starts, **180,144
transitions.** Of those, 171,199 changed, 8,945 were no-ops, 1,614 were terminal, and the corpus holds
516,260 grids at a mean of **2.86 frames per observation** — an encoder honouring the 1–N convention
reads 2.86× the volume any per-grid benchmark assumed. Full sizing in
[`screening-training-data.md`](screening-training-data.md).


`logs/s2_replay_sessions.json`, ingested 2026-07-28 by `agent/harness/s2_replay_ingest.py`:

| | |
|---|---:|
| sessions | **340** |
| games covered | 25 (all public) |
| total human actions | **180,173** |
| **levels completed = terminal transitions** | **1,613** |
| winning sessions | 144 |
| resets | 1,663 |
| sessions with per-level action segmentation | 300 of 340 |

Terminal-transition prevalence: **0.90%, or 1 in 111 actions.**

**So the corpus supplies two very different quantities**, and conflating them is what produced the
original error: **180,836 fully-labelled transitions** (abundant) and **1,613 progress-event
positives** (scarce). Only the second is a constraint.

Distribution is uneven — `lp85` alone contributes 204 terminals from 54 sessions; the thinnest games
(`g50t`, `ft09`, `sp80`) contribute ~31–33 each.

**After the §13.5 partition this shrinks, and the amount depends on which games are quarantined:**

| Dev-partition scenario (17 of 25 games) | Terminals available |
|---|---:|
| worst case — the 8 richest games land in validation | **849** |
| even split | 1,097 |
| best case — the 8 poorest land in validation | 1,286 |

**A ±25% swing in the project's scarcest training signal is decided by how the partition is drawn.**
The partition is frozen at build step 1 (W1) and never backfilled, so this is a one-shot, irreversible
choice.

> **⚠ Superseded 2026-07-28 — stratifying on terminal count alone is not sufficient.** The full census
> shows the draw moves **five** signals independently, and terminal count is the *least* volatile of
> them: no-op positives swing **21%–97%** of the total and ACTION6 transitions **22%–99%**, against
> terminal's 53%–80%. Six games contain zero ACTION6 and five contain almost no no-ops, so a draw
> perfectly balanced on terminals can still strip four-fifths of the coordinate or no-op supervision.
> The recommendation is now a **multi-criterion balance constraint** — terminal count, no-op count,
> ACTION6 count and total transitions each within a declared tolerance of the 17/8 proportional share,
> reject-sampled until all four hold, realized shares recorded. See
> [`screening-training-data.md` §6](screening-training-data.md).

### The agent's own logs — free labels, but progress-poor

Three Kaggle runs (v2/v3/v4) at ~3,800 actions each ≈ **11,400 executed transitions**. Every one gives
exact factual labels at zero cost. But the reference cleared 18 levels in 3,806 actions — **0.47%, 1 in
211**, roughly half the human rate — so the whole agent corpus contributes on the order of ~50 progress
positives. Negligible for that head; genuinely useful for the factual heads and for OOD calibration.

### Procedural suite F1/F3 — unbounded, and prevalence is a design parameter

Exact ground truth by construction: successor for every legal action, terminal predicate, hidden
mechanic state, causal-relevance labels. Two properties nothing else has:

- **progress-event prevalence is chosen, not observed** — generate at 5% or 20% instead of 0.9%;
- **counterfactual labels are free** — the generator knows what every unexecuted action would have done.

This is why F1/F3 sit in Tier 1 as "procedural suite core" rather than with the research arms. **The
evaluator's training set at W3 is mostly whatever S2 builds in early August**, and that dependency is
currently unpriced in either the spec or the schedule.

### Branching rounds R1–R3 — the only counterfactual labels from the real environment

Budget per SPEC §13.1: 24,000 attempted actions/game/round · 3 rounds · 17 dev games · 40 valid
disagreement slots per game-round → **nominal ceiling 2,040 valid states**, against a requirement of
**n_causal ≥ 800**, i.e. end-to-end validity must run ≥ 39%. If R1's pilot projects short, the causal
tier is declared unfundable and the learned gate falls back.

---

## 3. The actual gap

**Factual heads: solved several times over.** 180,836 replay transitions × 4,096 cells ≈ **740 million
dense cell labels** for the changed-region head, plus 180,836 binary labels each for no-op, visible
change and persistent change — before the ~11,400 agent transitions and before any procedural data. For
a 4M-parameter encoder this is a large dataset, not a marginal one. Nothing to do.

**Progress head: ~1,100 real positives, and the split rule spends them fast.** SPEC §9.4 forbids random
transition splits — splits must be held-out *levels*, *trajectories*, *procedural instances*, *goal
parameters*, or *family* (Fork G-F). Each of those partitions the same ~1,100, and a held-out-family
split under Branch A divides it across four families. Real-world positives are the scarce resource in
this entire build, and they cannot be manufactured.

**Reversibility: counted 2026-07-28. One of the three classes is empty.**

| Class | From replays |
|---|---:|
| demonstrated reversible — return to the same state, same level, ≤ 30 actions | **5,065** (2.81%) |
| demonstrated irreversible — *verified* no return route within the horizon | **0** |
| unknown — never trained as negative | 166,134 (92.2%) |

So the head is not data-starved on positives — 5,065 is three times the progress head's 1,614 — but
**`demonstrated irreversible` cannot be observed at all.** It requires *verified absence* of a return
route, and a recording of what one human did contains no such verification. Labelling the 166,134
unknowns as negatives would hand the head 33 fabricated negatives per real positive; SPEC §5 forbids
exactly that, which is why the class is three-valued in the first place.

The negative class therefore has to be *searched for*, not observed — see §5 of
[`screening-training-data.md`](screening-training-data.md), which identifies a source.

### Consequences worth acting on

0. ~~Count demonstrated-reversible pairs in the replays.~~ **Done 2026-07-28: 5,065 positives, and
   zero demonstrated-irreversible.** The remaining action is on the negative class, not the positive.
1. **Draw the public-game partition under a multi-criterion balance constraint**, not stratified on
   terminal count alone. One-shot, irreversible; worth ~250 progress positives, ~6,800 no-op positives
   and ~43,000 ACTION6 transitions in the worst case. Superseded box above; measurement in
   [`screening-training-data.md` §6](screening-training-data.md).
2. **Size S2's generators against the evaluator, not only against S3.** The generator is the progress
   head's and the reversibility head's primary supervision, not merely an instrument for objective
   screening. Neither the spec nor the schedule currently prices this.
3. **Set the procedural progress-event prevalence deliberately and register it.** Generating at the
   observed 0.9% wastes the one degree of freedom procedural data offers; generating at 50% builds a
   detector whose calibration is meaningless in deployment. The right value is a judgment and belongs in
   `gate_manifest.yaml → s2`, not in this note.
4. **A minimum positive count for the progress head should be pre-registered** before training, so that
   "the head underperformed" can be distinguished from "the head was starved." No such number exists
   yet, and inventing one here would corrupt the pre-registration.

---

## 4. One licensing flag, unresolved

`paper/methods/s2-human-replay-corpus.md` records that the replay archive **carries no licence file**,
and that platform mirrors carry declarations from uploaders who do not hold the rights they purport to
grant. Provenance is settled; **redistribution permission is not.**

Training on it locally is not redistribution. **Shipping model weights trained on it inside a
submission may be**, and that question is not answered anywhere in the project. It touches the progress
head, the click-salience generators in §4.5, and G0's training data — i.e. most of what the replays are
for. Worth resolving before W3, not after.
