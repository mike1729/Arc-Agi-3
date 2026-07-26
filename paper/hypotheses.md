# Hypotheses

**Status:** Working document. Hypotheses are recorded **before** the corresponding implementation or
submission, so that a result cannot be quietly reinterpreted as a prediction after the fact.

Each entry states what would count as confirmation *and* what would count as refutation. An entry with
no refutation condition is not a hypothesis.

---

## Resolved by measurement — 2026-07-26

### H1 — Replay determinism (R1)

**Stated before running.** After a level reset, an identical scripted action prefix produces an
identical observation sequence.

**Refutation condition:** any divergence in the frame sequence across replays, with the first-divergence
index distinguishing a re-randomised initial state (step 0) from stochastic dynamics (later).

**Outcome: CONFIRMED, within a stated scope.** Two games, two prefix lengths, three replays each,
byte-identical throughout. Scope limit recorded and not exceeded: this is the offline environment files,
which is evidence about the game code and **not** a test of competition mode. The supported claim is
"these tested prefixes replay exactly, offline" — not "everything learned transfers".

### H2 — Action accounting across resets (R2)

**Stated before running.** Either the scored action count restarts after a reset, or it accumulates.
The two imply different agents, so the experiment was designed to separate them by a factor of two.

**Refutation condition:** a ratio outside both pre-registered bands, or a within-arm spread above 0.10,
or a failed waste-validity check — any of which yields `inconclusive` rather than a forced reading.

**Outcome: ACCUMULATES.** Two independent estimators agreed to four decimal places — the pre-registered
score ratio and the directly observed action counts. A quantity the pre-registration had planned to
*absorb* was instead measured: **the reset is itself a scored action.**

**Consequence:** the controller is *surgical information-per-action*. Every probe costs score directly.
This is the conservative branch, but it was measured rather than defaulted to.

---

## Open — to be tested by the breadth run

### H3 — The bottleneck is levels solved, not efficiency on solved levels

**Basis.** The reference baseline is near-human-efficient on levels it clears (median ≈1.2× the human
action count) but clears the first level of most games, the second of very few, and never a third.

**Prediction.** Failure-frequency mass will concentrate on categories describing *not knowing what to do*
— unknown goal, exploration exhaustion — rather than on categories describing *doing it inefficiently*.

**Refutation condition:** efficiency-flavoured categories dominate the later-level band, or the
later-level ranking is statistically indistinguishable from the first-level ranking.

**Why it matters.** If confirmed, work aimed at action efficiency optimises a 1.2× gap while the actual
loss is games that never progress. That would reorder the construction queue.

### H4 — The reference halts rather than thrashes — **REFUTED, 2026-07-26**

**Basis.** On the level it cannot solve, the reference spends a median of roughly twice the human budget
and then stops.

**Prediction.** Failure episodes will show bounded action counts and terminate through exhaustion of
ideas, not through budget exhaustion; the latency/budget category will be rare as a *primary* label.

**Refutation condition:** the budget category is frequently primary, or episodes routinely run to the
action cap.

**Outcome: REFUTED, and by the stronger of the two conditions.** The reference does not terminate
through exhaustion of ideas at all. Measured from its own `benchmark.json`: **0 of 25 games finished
early.** All 25 ran 7920.8–7921.3 s against a 7920 s per-game budget — every one of them ran to the
wall-clock limit.

The hypothesis was built on the recorded state `gave_up`, which reads as a decision by the agent. It is
not. `gave_up` versus `cancelled` is decided by whether a request happened to be in flight when the
budget expired, which is a function of generation length — see erratum S1-E9. Under that mechanism the
reference's `gave_up` and our `cancelled` describe the *same* event.

**What survives.** The efficiency measurement is untouched: on the level it stalls on, the reference
spends a median 2.03× the human action count, and 1.19× on levels it clears. Those are measured ratios
and do not depend on why the run ended.

**What does not.** "Halts rather than thrashes" — and with it the reading that the latency/budget
category should be rare. Every reference episode is right-censored at 132 minutes, so *no* claim about
voluntary stopping can be drawn from this data, in either direction. H3's contrast between "not knowing
what to do" and "doing it inefficiently" is unaffected, since it rests on category frequencies rather
than on termination.

**Consequence for the taxonomy.** `latency_or_budget` cannot be interpreted from a budget-terminated
corpus without stating the bound, because every episode in it hit that bound by construction.

**Already partly informative.** A locally substituted mixture-of-experts model failed the same level by
expending roughly 100× the human budget without halting — a qualitatively different failure mode, which
is why it was rejected for taxonomy work despite being ~5× faster.

### H5 — Quantisation and model substitution shift *which* failures dominate

**Basis.** Development runs a 4-bit local conversion; a submission would run the reference at FP8. Two
models from the same family already differ by two orders of magnitude in actions spent on an unsolved
level.

**Prediction.** Failure-frequency rankings differ materially between models, not merely in magnitude but
in ordering.

**Refutation condition:** rankings agree in ordering across models, which would license using a faster
substitute for taxonomy work.

**Status: untested and consequential.** It is the reason the breadth run was placed on the model closest
to the reference rather than on the fastest available one.

---

## Standing hypotheses for the research question (not yet testable)

### H6 — Latent prediction is insufficient under sparse delayed causal memory (F3)

**Basis.** A reconstruction-free latent objective has little gradient pressure to preserve a bit whose
consequence falls outside the training horizon; an exact target retains it structurally.

**Prediction.** The latent arm degrades relative to the exact-delta arm as the delay between a causal bit
and its consequence grows, while the two are comparable at short horizons.

**Refutation condition:** the latent arm matches the exact-delta arm at long delays under matched
information.

**Independent corroboration to date.** The strongest published agents on this benchmark maintain an
*explicit, executable* world model and verify it by exact replay — the far end of the axis the latent
arm occupies. That is not evidence against the latent approach, but it does mean the field's current
successes sit on the opposite side of the contrast this project is testing, which is the honest starting
position.
