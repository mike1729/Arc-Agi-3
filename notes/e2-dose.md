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
lineage and is not used), template rendered with `enable_thinking=True`. Mechanical pass
criteria: no pre-filled empty think block · template opens `<think>` · substantive think
body · block closed · answer present.

**The slice model is Qwen3.6-27B-8bit** (`~/models/mlx/Qwen3.6-27B-8bit`) — **PASSED**,
raw trace `logs/e2_thinking_probe_8bit.json`: think body 16,228 chars, closed, answer
present. Pinned for fidelity, not preference: the deploy reference stack is FP8 (8-bit
class) and S1's standing measurements — the `goal_unknown` bottleneck E2 attacks — were
made on it; 4-bit was also what the voided July server loaded. The 4-bit probe
(`logs/e2_thinking_probe.json`, also passed) stays as comparison: on the identical prompt
8bit thought **2.7× longer** (16,228 vs 6,075 chars) — quantization changes reasoning
behaviour, not just marginal accuracy, which is exactly why the slice must not mix them.
The A3B-4bit speed fallback is withdrawn (different model *and* lower precision).

Measured speeds, 27B-8bit: generation **9.3 tok/s**, prefill 28–35 tok/s (cold; 4-bit
warmed to ~153, no warm 8-bit number yet), load ~5 s. The toy probe consumed ~5.7k output
tokens before closing — **per-call output budget ≥16k tokens (w)**; a 5k budget produced
an unclosed think block and no extractable answer.

Feasibility arithmetic (w, measured rates): a 12k-token digest ≈ 6–7 min prefill + ~6k
thinking tokens ≈ 11 min → **~15–20 min/call**. The full 24-game × 4-dose grid ≈ 96 calls
≈ 24–32 h — do not start there. **First slice: the six iteration games × 2 doses (125 +
full store) = 12 calls ≈ 3–4 h**, the flat median dose curve is what licenses collapsing
the dose axis to its endpoints.

## The Qwen slice (the actual E2 — next)

Per game × dose: an **organized store digest** (object census; mined rules with support and
counterexample counts; unresolved keys with their conflicting evidence; alias conflicts
with prefixes; completion row if any) → Qwen thinking → propose (a) rules in the miner's
vocabulary — machine-verified against the store, survivors kept; (b) goal candidates —
grammar predicates where expressible, else executable predicates over catalogue handles;
(c) when saturated-without-completion: exploration directives over handles. Scoring: rule
proposals on the same held-out human targets as the miner (the zero-model curve above is
the floor at every dose); goal candidates against game source. Instrument rules baked in:
Qwen3.6-27B-8bit only (see the gate above) · two-phase decode (free thinking, then
extraction) · output budget ≥16k tokens (w) · per-call trace logged · per-call mechanical
thinking check identical to the probe, an unclosed think block voids the call.

## Limits

- Single explorer run feeds everything; no variance estimate at any layer.
- Human replays measure fit-to-competent-play, not correctness of rules per se; L2 numbers
  inherit E0's accuracy-over-covered semantics.
- The flat median dose curve is measured for THIS miner's vocabulary; a synthesizer with a
  richer vocabulary (census-conditioned guards, hidden-state splits) may well not be flat —
  that is precisely what the Qwen slice measures.
- Goal positives: 4 games, 1 example each, excluded this run (frame retention fixed
  forward).

---

## Addendum 2026-08-04 — the floor definition changed

**Guard vocabulary v2 adopted** (`notes/miner-vocab-v2-results.md`): `clicked_adjacent_to:C`
is now in the miner's vocabulary and `rs_transitions.vocab()` defaults to it. The floors
above were measured under v1.

**Floor file of record: `logs/e2_dose_vocab_v2.json`.** `logs/e2_dose.json` is retained as the
v1 measurement and is still reproducible — `e2_dose.py --vocab v1`.

**What actually moved: 2 of 24 games per target, median delta 0.0000.**

| target | game | v1 → v2 |
|---|---|---|
| on-human-L1 | ft09 | 0.2522 → **0.3017** |
| on-human-L1 | sb26 | 0.5308 → 0.5330 |
| on-human-L2 | lf52 | 0.2011 → 0.2050 |
| on-human-L2 | lp85 | 0.0590 → 0.0594 (`full`), 0.2396 → **0.2505** (`moveset`) |

Every other game and every other cell is byte-identical, and no cell moved down. Slice
comparisons made against the v1 floors are therefore still valid except on those four games,
where the v2 floor is the one to beat. The claim above that **the dose curve is flat in the
median** is unaffected: v2 changes no median at any dose.

`clicked_adjacent_to:*` is selected in **8 of 23 tier-1 rules on the explorer store** across
ft09, lf52, lp85 and sb26 — against 2 of 60 on human replays. The explorer's click evidence
exercises the feature far harder than human play does.

Census-scoped firing (mechanism 2 of the same note) was **rejected** and changes no floor:
on the explorer store it leaves on-human-L1 coverage near-intact (−0.046 median) while
collapsing on-human-L2 coverage by 0.780. `logs/e2_dose_scoped.json` records it.

---

## Addendum 2026-08-05 — model horizon: Qwen3.8-27B expected ~08-12 (w) [verify]

The 8bit pin above and **every model-bound number and verdict in this note are claims
about Qwen3.6**, not about "the model". When 3.8 lands: bring-up gate first (new chat
template — re-verify thinking; re-measure budget/speeds; re-pin quantization), then the
pre-planned reruns — **`notes/qwen-3.8-upgrade.md`**. Zero-model floors and curves here
are model-free and stand.
