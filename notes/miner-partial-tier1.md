# Partial tier 1 — the zero-model miner improvement the E2 re-grade turned up

**Filed 2026-08-05 by the E2 re-grade (`notes/e2-regrade.md`, readout direction 2). Not
started. Zero model calls.** This is a real win that belongs to the *mechanism*, not to
Qwen — it is the control arm of the re-grade, measured while answering a different question.

## The defect

`rs_e0.mine` tier 1 is **all-or-nothing**: a guard feature is selected only if EVERY cell of
its partition holds exactly one effect. A feature that resolves most of a key purely and one
cell impurely is discarded entirely, the key falls back to its majority effect, and the
feature leaves no trace in the rule count. `rs_e0.key_purity` documents exactly this and
deliberately declines to act on it ("lowering the tier-1 bar is a rule-model change, out of
scope for this measurement") — which was right there and is now measured.

## What the re-grade measured (arm C)

Per key the miner left unresolved: pick the single guard with the **fewest contradictions**
over the key, emit its cells as rules with their own contradiction rates, keep the cells at
or under ε, and let the majority rule cover the rest. Scored as a union with the miner's
rules on held-out human L1/L2 replays, against the miner-only floor, over 12 (game, dose)
cells and six games:

| ε | L1, summed delta | L2, summed delta |
|---|---|---|
| 0 % (pure cells only, **no tolerance**) | **+0.5303** (+7/−1) | **+0.1390** (+5/−0) |
| 2 % | +0.5451 | +0.1427 |
| 10 % | +0.7732 (+8/−1) | +0.1890 (+7/−0) |

Most of the effect needs **no tolerance at all** — it is the partial-tier-1 change. Best
single cell: tu93 dose-125, floor 0.4778 → 0.7963 from two kept rules. tu93's full store has
four unresolved keys each carrying one `adj:9:*` feature at a 1.9–2.8 % contradiction rate.

## Read `notes/miner-conjunction-tier.md` FIRST — it is the nearest prior, and it failed

The conjunction tier (tier 1.5, two-guard zero-contradiction rules over the same unresolved
keys) was built and **rejected on 2026-08-05**, and its failure mode is structurally the one
this proposal risks: a new specific rule outranks the majority fallback, coverage does not
change, so the whole effect is the new tier *taking edges from the majority rule* — measured
at 0.58 accuracy within distribution and **0.033 across a level change**, with rule counts
inflating 11.5 → 103 median and 41 % of new rules at support 1 (sp80 L1→L2 0.6350 → 0.3145).

Partial tier 1 is a weaker, single-guard version of the same move, so its prior should be set
accordingly: it is not a fresh idea, it is the one-guard case of an idea that just lost on
24 games. Two differences that make it worth measuring anyway — it selects one feature per
key on a whole-key contradiction criterion rather than searching pairs per cell (far less
hypothesis space, so far less memorization), and the re-grade's numbers are E2-protocol
(explorer store → human replays), a setting the conjunction run also covered and where it
regressed badly on sp80. Those are reasons to measure, not reasons to expect a different
answer.

## What must happen before adoption

* **Measure on E0's own protocol** (`rs_e0.run_game`: within-L1 and L1→L2, all three effect
  modes, both vocabularies). The numbers above come from mining the explorer store and
  scoring on human replays — E2's protocol, a different question from E0's survival claim.
  Adopting a rule-model change on the strength of the pass that motivated it is how a
  measurement becomes a story.
* **Report the survival rate, not just accuracy.** A partial tier-1 rule is by construction
  less pure than a tier-1 rule; if accuracy rises while `rule_survival_rate` falls, the
  change is buying coverage with brittleness and that trade has to be stated.
* **Watch the three cells where it hurts** (dc22 dose-125, −0.0047 on L1): a partially pure
  guarded rule outranks the majority rule in `_fire` by support, so a bad cell can displace a
  correct fallback. Whether that needs a support floor is an open question, not a fix to
  assume.
* Keep tier 1 as it is and add the partial tier BELOW it, so a fully separating feature is
  still preferred and v1/v2 results stay reproducible.
* **Report the same diagnostics the conjunction run used** — rule-count inflation, support
  distribution, per-tier firing shares, and coverage (identical coverage means the effect is
  purely fallback displacement). Reuse `agent/harness/e0_conjunction.py`'s scoring wrapper
  rather than editing `rs_e0.py`; the two candidates should be comparable line for line.

Harness to lift the mechanism from: `agent/harness/e2_regrade.py` → `tolerance_tier()`.
