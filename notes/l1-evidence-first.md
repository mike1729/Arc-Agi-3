# L1 evidence-first line — explore → synthesize → execute

**Status: exploratory. Started 2026-08-04.** Not pre-registered; nothing here is citable as
confirmatory evidence. Working numbers are labelled as such and may change without errata.

## Why this line

1. **The Qwen screens are void as capability evidence.** The local serving path never produced
   real thinking (non-thinking decode path; guided JSON additionally forces the first token into
   the schema). VP, GI-1 and MU Qwen-measured cells are non-representative — operator
   determination 2026-08-04. Zero-model results stand: GI-2 representability bound, ES closure
   infeasibility, the mechanical floors (greedy tracker ≈ 0.86 identity, constant-answer 0.736
   mechanics).
2. **S1 stands** (reference FP8 stack, thinking on): the deployed failure is goals, not
   mechanics — `goal_unknown` primary in 76% of episodes, present in 92%, and present in 100%
   of the 13/25 episodes that stalled on level 1.
3. **The scorer makes L1 exploration nearly free** (verified against the core implementation and
   the taaf mirror, `game.py:381`): per level `min(115, (baseline/actions)² × 100)`, completed
   levels only, weight = 1-indexed level position, **no action cutoff**. Exploration cost is
   **local to the level it happens on**; L1 is the minimum weight of any game (1/21 of a
   6-level game). Completions dominate score; efficiency only multiplies inside the completed
   envelope.
4. **Deterministic replay + accumulating resets** (REPLAY-DET / RESET-ACCT, S1): branch-and-
   deviate probing works on hidden games at ~2× action cost — cheap on L1.

**Strategy: burn L1 for evidence, synthesize a verified model, plan L2+.** Qwen moves from
autoregressive actor (one generation per action; few-shot induction — its worst regime) to
**batch synthesizer** over a saturated, organized evidence store (long-context pattern
completion — its best regime).

## The loop

- **E — explore (no LLM calls).** Frontier-directed coverage: state graph with exact hashing,
  route to the nearest untested (state, action); click candidates from segmentation;
  state-frequency counting is part of the saturation definition, so loops register as
  saturation rather than burning budget. Every transition recorded. An E phase ends in exactly
  one of {completed, saturated, closed-without-completion} — never silent budget exhaustion.
- **M — synthesize (batch).** Mechanical rule miner over object events (precondition → effect,
  support + counterexample bookkeeping, complexity-bounded). Qwen (thinking on, two-phase
  decode) reads the organized catalogue and proposes: rules, goal candidates, and — when E
  saturated without completing — **exploration directives as executable heuristics over
  catalogue handles** (a directive referencing an unknown handle is rejected; step-budgeted,
  abort on no progress). Every proposal is verified against the store; survivors persist across
  turns marked verified/assumed.
- **X — execute.** BFS/A* over the mined **object-level** forward model (a step is O(objects),
  never O(64×64); closed set via state hash). Plan offline — long strict sequences are found by
  search over the model, not by exploration — then execute. First misprediction → local guard
  repair (few targeted probes at the failure context) or rule invalidation + re-synthesis on
  pooled evidence; the repair-vs-invalidate split is set from E0's measured guard-fixable rate,
  not invented. Worst case: re-explore level k, taxing only level k.

## Experiments (in order; **all public games are usable** — operator decision 2026-08-04:
E0–E3 train nothing on them, so the old one-shot/reserved seals don't apply. Two caveats
travel with that: design-naivety on the public set is spent — the only honest holdout left is
the hidden set, and public numbers were never evidence of hidden generalization anyway; and
the split question returns the moment any learned component appears. Practical discipline:
debug against the six iteration games' detailed traces, read the rest aggregate-first.)

**E0 — offline L1→L2 rule survival (zero model calls; first).** From human replays via the
replay driver (settled frames — the vc33 trap applies): mine complexity-bounded rules on a
train split of L1 transitions; validate on held-out L1 transitions with the pure memorizer
reported as floor; then score the L1 rules on that game's L2 transitions.
Metrics: held-out-L1 accuracy · L2 survival rate · failure split (guard-fixable false positive
vs unpredicted change). Purpose: price the OOD/transfer risk and set repair-policy working
defaults before anything online exists.

**E1 — explorer outcome distribution.** On L1 of each game: {completed, saturated, closed} ×
actions-to-outcome, plus incidental-completion rate. No model calls.

**E2 — evidence-dose curve.** Goal-candidate quality (true goal ∈ survivors — scoreable from
game source) and synthesis quality as a function of exploration dose. First Qwen experiment of
the line; verify from logged traces that thinking actually fires before trusting any number.

**E3 — transfer payoff.** L2 clear rate and efficiency with the L1-built model vs vendored taaf
on the same games; misprediction frequency, repair cost (actions and seconds), full-fallback
frequency; wall-clock priced against the (unverified, ~8 h) envelope.

## Reuse

Replay driver + fork tables + observation layer/handles (GI-2 estate) · object-event extraction
(MU gold machinery) · segmentation (taaf) · exact-hash frontier search (ES closure engine, ran
to 242k states locally) · renderers (MU). The screening-line estate lives on
`archive/screening-line-2026-08-04` (see `RESTART.md`) — resurrect via
`git show archive/screening-line-2026-08-04:<path>`, don't rewrite it.

## Standing instrument rule

**Never constrain the first decoded token.** Structured output = think freely, then extract
(second pass or parse-from-text). This is the mechanism that voided the screens; it must not
recur in any harness, probe, or eval.

## Non-goals right now

Manifest freezes and spec amendments (until a line beats the reference) · training anything on
public games without first declaring a split · Qwen-vs-no-model decision tests (Qwen is the
substrate; floors are reported as diagnostics only) · submissions off this line before E3 reads
out.
