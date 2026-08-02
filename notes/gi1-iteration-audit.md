# GI-1 iteration audit and viability verdict

**Date:** 2026-07-30  
**Scope:** six iteration games only; the 15 one-shot and four reserved games remain unopened  
**Decision:** stop before champion selection and return GI-1 to design

## Outcome

The iteration computation completed all 450 planned rows:

- 234 Qwen rows across conditions (b)–(d);
- 156 programmatic-floor rows across (e)–(f);
- 60 recorded invalid-checkpoint exclusions;
- zero request errors.

No champion was selected. The result does not support selecting one:

| Condition | Parse valid | Top-1 class | Top-3 class | Top-1 fields | Best top-3 fields | Exact predicate |
|---|---:|---:|---:|---:|---:|---:|
| (b) structured hypotheses | 96.4% | 15.2% | 51.6% | 3.1% | 6.3% | 0% |
| (c) + compiled digest | 93.3% | 13.9% | 41.1% | 1.9% | 1.9% | 0% |
| (d) + retrieval | 92.7% | 15.1% | 39.0% | 1.9% | 2.5% | 0% |
| (e) leave-one-game-out prior | — | 33.3% | 83.3% | — | — | — |
| (f) retrieval floor | — | 23.6% | 64.0% | — | — | — |

Metrics are game-balanced over 78 valid rows per condition. Invalid parses remain failures in the
denominator.

The formal lexicographic rule would rank (b) first, but that ranking has no actionable meaning:
all eleven correct top-one fields are closed-set enums. Across the three Qwen arms, **0/440
top-one entity fields** were correct, and no arm produced an exact predicate at any rank.

## Integrity audit

The original implementation freeze was incomplete: it omitted both the predicate answer key and
`gi1_packets.py`. The raw observations remain usable because the log contains each exact request,
raw response, and score.

`agent/harness/gi1_iteration_audit.py` performed a retrospective, no-model audit:

- the anchored raw-log SHA-256 is
  `8568a616f5d5e614e018978a68d429ffad0a1acce379cf06aa13303456db6009`;
- all 450 recorded row identities and inclusion decisions validate;
- all 234 model requests regenerate byte-canonically;
- all 234 logged request digests match;
- all 156 programmatic outputs regenerate;
- all 234 raw model outputs re-score identically against the reviewed gold;
- no mismatch was found.

The machine-readable result is `logs/gi1_iteration_audit.json`. This salvages the iteration data
as exploratory evidence. It does **not** retroactively claim that the repaired contract was frozen
before the run.

## Is the zero predicate rate only scorer brittleness?

A treatment-blind semantic check used the first 36 unique incorrect entity pairs under SHA-256
ordering. Condition, game, checkpoint, and rank were hidden during classification.

- 2/36 were reasonable entity paraphrases:
  - `Player avatar (blue checkered cursor)` → `player`;
  - `Player avatar (white cursor)` → `player`.
- 34/36 bound the wrong object, scope, transformation, or terminal condition.

After unblinding, both reasonable paraphrases were rank-three dc22 hypotheses. Their relation and
object fields were also wrong (`adjacent`/`aligned` rather than `overlapping`, and the wrong target).
Granting both equivalences therefore changes neither top-one field accuracy nor the 0% exact-
predicate result.

The strict scorer undercounts a small amount of lexical equivalence, but it does not explain the
binding failure.

## What the checkpoints show

Additional evidence did not produce adaptation:

- For (b), top-three class accuracy fell from 93% at 10 actions and 88% at 30 actions to 28–33%
  after completions.
- Conditions (c) and (d) never improved actionable binding; their only nonzero top-one field
  signal at later checkpoints was enum matching.
- The programmatic prior remained at 83% top-three class across completion checkpoints.
- Retrieval reduced class accuracy relative to the prior and did not add entity binding.

This is not primarily a JSON-format problem. Parse validity remained 92.7–96.4%; correctly parsed
answers still failed to identify and bind the terminal objects and relations.

## Repaired controls

The implementation now:

- pins the exact predicate gold, game draw, packet extractor, and experiment runner in the freeze;
- gives E3 completion ablation a separate default log and refuses the normal measured log;
- drains and logs paid-for in-flight responses before propagating a fail-fast error;
- selects only from the row plan and exclusions recorded in the run log;
- provides a reproducible no-model audit and result summary.

Focused tests cover these changes, and mutation testing reports **153 killed / 0 survived** across
the freeze, runner, and audit modules.

## Viability decision

GI-1, as currently formulated, fails on the iteration set before one-shot exposure:

1. the structured Qwen arms do not produce actionable goal predicates;
2. digest and retrieval do not improve binding;
3. the programmatic methods help coarse class recognition but cannot bind entities;
4. completion evidence does not create a positive adaptation slope.

Therefore:

- do not create `logs/gi1_champion.json`;
- do not open the 15 one-shot games;
- do not run E3 ablation, E2, or E4/K5;
- return to design with the raw outputs as failure evidence.

The next design sprint should target object and relation binding explicitly. Coarse class
recognition is already better served by the programmatic prior; asking Qwen to emit a complete
predicate from the current packet is the unsupported step.
