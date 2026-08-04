# E2 — evidence-dose curve: zero-model substrate + thinking bring-up

**2026-08-04. Status: substrate measured (zero model calls) · thinking instrument verified ·
Qwen synthesis slice designed, not yet run.** Working numbers are labelled (w).

Code `agent/harness/e2_dose.py` · `e2_probe.py`. Data `logs/e2_dose.json` ·
`logs/e2_thinking_probe.json`. Consumes the E1 v2 store (`logs/e1_store_v2/`, local).

## Mechanics: explorer evidence vs the human-replay ceiling

Setup: E0 miner over E1-v2 store prefixes (doses 125 / 250 / 500 / 1000 / 2000 / full (w)),
validated on **human replays as an external test set** — L1 (does explorer evidence recover
the rules governing competent play?) and L2 (E0's transfer question). Ceiling = miner on
human L1 scored on L2, which is E0's own row — recomputed here and **cross-checked exact**
(vc33: 0.0966/0.9903 both ways). Memorizer floor per dose (median 0.042 — everything above
it is generalization, explorer states barely overlap human states).

**Full-dose, `full` mode, on L2: explorer wins 9 / ties 4 / loses 11 vs the ceiling; median
explorer/ceiling ratio 0.938.** Wins are large where they occur (vc33 0.237 vs 0.097, re86
0.039 vs 0.007, sc25 0.071 vs 0.027); worst losses g50t 0.115 vs 0.240, tn36 0.601 vs
0.839, ft09 0.088 vs 0.177. On the transferable `moveset` layer: median 0.188 vs ceiling
0.191 — parity. **Autonomous exploration is a near-full substitute for human replays as
rule-mining evidence** — the property hidden games require, measured on public ones.

**The dose curve is flat in the median.** Median on-human-L1 accuracy: 0.252 at dose 125 →
0.262 at 2000 → 0.289 full; L2 similarly flat (~0.08–0.13 throughout). The median game
yields most of its minable signal within 125 test actions. Individual games break the
pattern in both directions (vc33: L1 0.92 at dose 125 falling to 0.489 at full while L2
*rises* 0.087 → 0.237 — late deep-state evidence generalizes rules at the cost of
human-distribution fit). Consequence for the line: **more exploration is not where mechanics
synthesis quality is bottlenecked — synthesis itself is.** The E0 failure typing already
said where: census-separable and guard-fixable structure the miner's vocabulary cannot
resolve. That is the Qwen brief, not more actions.

## Goal curve (row-C grammar, zero model calls)

Universe tractable 24/24 (median 70 candidates). Explorer negatives prune it to a median 36
survivors, most of the narrowing inside the first 125 transitions. Scoring the survivors
against human L1 (whose completions are the positive evidence the store mostly lacks):
lf52 keeps 1 candidate consistent with both, sp80 keeps 3; lp85/r11l keep 0 — consistent
with row C's expressibility findings. The store's own positive examples: exactly one per
completed game, and this run **skips them in the goal stream** — the explorer never
retained the completion frame, so the positive had no post state (`e1_explorer.py` now
retains it for future runs; harness bug found by the 4 completed games all reporting 0
survivors).

## Thinking bring-up — the instrument gate (PASSED)

`e2_probe.py`, direct `mlx_lm` (NO server layer — the July mlx_vlm server is the voided
lineage and is not used), Qwen3.6-27B-4bit (`~/models/mlx/`), template rendered with
`enable_thinking=True`. Mechanical pass criteria, raw trace in
`logs/e2_thinking_probe.json`: no pre-filled empty think block · template opens `<think>` ·
think body 6,075 chars · block closed · answer present. **All pass.** Speeds: prefill ~153
tok/s (warm), generation ~16.6 tok/s, load 2–8 s.

Feasibility arithmetic (w): a 12k-token evidence prompt ≈ 80 s prefill; thinking 2–5k
tokens ≈ 2–5 min/call. A 24-game × 4-dose × 1-call slice ≈ 3–8 h wall. Options if too
slow: Qwen3.6-35B-A3B-4bit (MoE, on disk — must pass the same probe first), fewer doses,
smaller digests.

## The Qwen slice (the actual E2 — next)

Per game × dose: an **organized store digest** (object census; mined rules with support and
counterexample counts; unresolved keys with their conflicting evidence; alias conflicts
with prefixes; completion row if any) → Qwen thinking → propose (a) rules in the miner's
vocabulary — machine-verified against the store, survivors kept; (b) goal candidates —
grammar predicates where expressible, else executable predicates over catalogue handles;
(c) when saturated-without-completion: exploration directives over handles. Scoring: rule
proposals on the same held-out human targets as the miner (the zero-model curve above is
the floor at every dose); goal candidates against game source. Instrument rules baked in:
two-phase decode (free thinking, then extraction), per-call trace logged, per-call
mechanical thinking check identical to the probe.

## Limits

- Single explorer run feeds everything; no variance estimate at any layer.
- Human replays measure fit-to-competent-play, not correctness of rules per se; L2 numbers
  inherit E0's accuracy-over-covered semantics.
- The flat median dose curve is measured for THIS miner's vocabulary; a synthesizer with a
  richer vocabulary (census-conditioned guards, hidden-state splits) may well not be flat —
  that is precisely what the Qwen slice measures.
- Goal positives: 4 games, 1 example each, excluded this run (frame retention fixed
  forward).
