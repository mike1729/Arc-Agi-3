# E2 slice — Qwen as batch synthesizer over explorer evidence

**2026-08-04. First model-bearing measurement of the line.** Qwen3.6-27B-8bit, direct `mlx_lm`,
thinking on, two-phase decode. Six iteration games × 2 doses (125 / full store) = 12 cells,
3.59 h wall. Code `agent/harness/e2_slice.py` · results `logs/e2_slice.json` · raw traces
`logs/e2_slice_traces/` (24 files, every call).

## Headline

**82 rules proposed. 9 survived the evidence they were shown. 1 survives that game's full
evidence.** The union of miner + verified proposals beat the mechanical floor in 1 of 12 cells
on human L2, by 0.0172 — and that gain comes from a rule which fuller evidence refutes.

| cell | prop | rej | ver | L1 floor | L1 union | ΔL1 | L2 floor | L2 union | ΔL2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dc22/125 | 8 | 0 | 2 | 0.1997 | 0.2028 | +0.0051 | 0.0641 | 0.0641 | 0 |
| dc22/full | 7 | 0 | 0 | 0.2278 | 0.2278 | 0 | 0.0552 | 0.0552 | 0 |
| ft09/125 | 0 | 2 | 0 | 0.2522 | 0.2522 | 0 | 0.0885 | 0.0885 | 0 |
| ft09/full | 5 | 0 | 1 | 0.2522 | 0.2522 | 0 | 0.0885 | 0.0885 | 0 |
| ls20/125 | 4 | 0 | 0 | 0.4396 | 0.4396 | 0 | 0.3466 | 0.3466 | 0 |
| ls20/full | 4 | 0 | 0 | 0.4396 | 0.4396 | 0 | 0.3466 | 0.3466 | 0 |
| m0r0/125 | 17 | 0 | 2 | 0.2362 | 0.2362 | 0 | 0.3422 | 0.3422 | 0 |
| m0r0/full | 10 | 0 | 0 | 0.2624 | 0.2624 | 0 | 0.3988 | 0.3988 | 0 |
| tu93/125 | 6 | 0 | 1 | 0.4778 | 0.4963 | +0.0212 | 0.5431 | **0.5581** | **+0.0172** |
| tu93/full | 12 | 0 | 0 | 0.7296 | 0.7296 | 0 | 0.5768 | 0.5768 | 0 |
| vc33/125 | 6 | 0 | 3 | 0.9197 | 0.9416 | +0.0323 | 0.0870 | 0.0870 | 0 |
| vc33/full | 3 | 0 | 0 | 0.4891 | 0.4891 | 0 | 0.2367 | 0.2367 | 0 |

Δ columns are accuracy-over-all on **exactly the transitions whose key the miner could not
resolve** — the subset the slice is about. The union is **never worse than the floor** in any
cell: verification prevents harm even where it delivers no gain.

## The dose asymmetry is an artifact, and the check kills the result

8 of 9 verified rules are at dose 125; all three L1 improvements are at dose 125; every `full`
cell verified zero rules but one. The tempting reading — thinner evidence synthesizes better —
is wrong, and one zero-model check settles it.

**Re-verifying each dose-125 survivor against the SAME game's full store:**

| game | rule | sup@125 | sup@full | contra@full |
|---|---|---:|---:|---:|
| dc22 | `A6:3 \| adj:13:right=None` | 2 | 22 | 13 |
| dc22 | `A6:13 \| count:0=14` | 1 | 8 | 6 |
| m0r0 | `A6:0 \| adj:12:left=11` | 2 | 129 | 97 |
| m0r0 | `A:3 \| adj:12:left=11` | 4 | 82 | 34 |
| tu93 | `A:4 \| adj:9:right=4` | 16 | 312 | 7 |
| vc33 | `A6:0 \| adj:7:down=0` | 14 | 91 | 2 |
| vc33 | `A6:5 \| adj:7:down=0` | 13 | 92 | 2 |
| vc33 | `A6:9 \| count:0=1` | 5 | 31 | 1 |

**All eight are refuted by their own game's fuller evidence.** They passed at dose 125 because
125 transitions did not contain the counterexample, not because they were right. The dose
asymmetry measures the strength of the verification bar, not the quality of synthesis; two of
them (m0r0) are contradicted more often than supported.

So the honest count is **1 of 82 proposals survives its own game's full evidence** — ft09/full's
single rule, which produced a delta of exactly 0.

## The one result worth keeping is a vocabulary extension

ft09/125 proposed 0 rules. Not a refusal, not a parse failure — both its rules were rejected
because their guard names are not in the miner's vocabulary. Qwen said so itself, unprompted:

> The miner's feature set (`present:C`, `count:C`, `adj:C:direction`, `click_colour`,
> `click_on_background`) cannot express this condition. `adj:C:direction` only tracks neighbors
> of *single-object* colours from a fixed reference point, and lacks a `clicked_adjacent_to:C`
> or per-component neighbor feature. The split is almost certainly driven by spatial adjacency
> between the clicked colour-9 tile and the colour-12 object.

That is exactly what the prompt asked for — name the limit rather than fit a rule to it — and
the harness scores it **zero**, because a proposal outside the vocabulary cannot be represented,
let alone verified.

This reframes the slice. The question asked was "can Qwen fill gaps in the miner's language?"
The answer is no. The answer that came back instead is **"here is the missing word":** a
per-component `clicked_adjacent_to:C` guard, which is a concrete, testable, zero-model change
to `rs_transitions.guard_features` — and E0's failure split already said the largest bucket is
census-separable, i.e. keys where the *existing* vocabulary separates only incidentally.

## Zero tolerance may be the wrong bar

`tu93 A:4 | adj:9:right=4` is 312 support / 7 contradictions at full dose — **97.8% accurate**,
and the only rule in the run that moved human L2 (+0.0172). Zero-tolerance verification kills
it. The miner holds itself to the same bar, so the comparison is fair, but a mechanic that is
right 97.8% of the time is exactly what a repair policy is supposed to carry, with the residual
handled as misprediction rather than as grounds for rejection.

Not changed here — the bar was pre-committed and changing it after seeing which rule it killed
is how a measurement becomes a story. Recorded as the first candidate amendment for the next
slice, to be set before running.

## Instrument

Every one of the 24 calls passed the mechanical thinking check: no pre-filled empty think
block, block opened and closed, substantive body, non-empty answer. **Zero voids, zero unparsed
extractions**, so the extraction retry never fired. Median think length 28,375 chars (~7k
tokens) against a 16,384-token budget — no cell approached truncation. Phase 1 seeded (20260804)
and sampled at 0.6/0.95; phase 2 greedy at temp 0.

The instrument that voided the July screens is clean here: direct `mlx_lm`, no server, first
decoded token never constrained, raw trace written before any scoring.

## Limits

- **6 games, 2 doses, one sample per cell.** No variance estimate; a second seed could move
  every count.
- Only the `full` effect layer was asked for. `moveset` — the layer E0 found transfers at
  median 0.985 — was not, and is the more likely place for a model to help.
- Goals, hidden-state and next-probe answers are **logged verbatim and unscored**. Nothing here
  evaluates them; the row-C grammar channel does not exist yet.
- The overfit check re-verifies dose-125 survivors on the same game's full store — a strictly
  larger superset of their training evidence, so it can only refute, never confirm.
- `parse_rejected` counts vocabulary rejections separately from "no rules stated"; the run had
  2 of the former and 1 cell of the latter (ft09/125 is the same cell — its only two proposals
  were both rejected).
