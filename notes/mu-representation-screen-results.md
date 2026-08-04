# MU measurement results

**Run status: COMPLETE. S pass 420/420, C pass 72/72, zero errors, schema validity 1.000.**

**Verdict: `stop` (MU §5.1).** No funding cell among {T3, T4} is screen-positive on C. Under the
frozen decision contract the representation menu is exhausted for Qwen mechanics use, no
goal-inference continuation is funded, and advisor work on that axis proceeds programmatic-only.
Reopening any component result needs its own registered protocol.

492 measured calls, 3.55 h of GPU. The scope limits of §5.1 travel with this verdict: `stop` is
not a finding that Qwen is useless on this interface, and the read is conditional on the six
iteration games.

## Provenance

| item | value |
|---|---|
| freeze | `40fc3c5f34d72fe2…` (supersedes `a3e1f859e1aadbc0…` under erratum **MU-E1**) |
| inventory | `2b155cf0144e5f45…` |
| manifest | `gate_manifest.yaml → mu`, frozen 2026-08-03 |
| model | local `Qwen3.6-27B-8bit` (MLX), `temperature=0`, `top_p=1`, thinking disabled, guided JSON |
| started | 2026-08-03T17:18:41Z |

Configuration that produced these numbers, stated because the cohort was reduced at acceptance:
`cases_per_probe_per_game_per_role` **2/2/2/2/2**, `t3_executed_share` **1**, `prefix_window`
T1/T3/T4/T5 = 4 and T2 = 2, `t1_legibility_gate` **0.70**, `selection_margin` and
`screen_positive_margin` both **0.09**, `screen_positive_min_games` **4**.

Bring-up (12 discarded synthetic calls, non-evidentiary): guided-JSON decoding **validated
12/12**; p50/p95 90.6 s at 24,742 prompt tokens, from n=4 — a scale-setting figure, not a
latency distribution. The stack is **prefill-bound at ~276 tok/s**: thinking is off and guided
JSON emits ~8 output tokens, so per-call cost is `prompt_tokens / 276 + ~1 s`. This withdrew the
pre-bring-up VP-derived ~29 h estimate for the S pass, which described VP's thinking-enabled
decodes rather than this workload.

## MU-E1 — a scoring defect caught mid-pass, and what it cost

At 212/420 rows, first-pass schema validity fell to 0.920 and **every** invalid row was MU-T3.
Cause: `parse_answer` refused `{"kind":"unchanged","delta":[0,0]}`, but the guided schema sent
to the server lists `delta` as **required** and types it `["array","null"]` with no conditional.
The model was obliged to emit a value, `[0,0]` was compliant, and the scorer treated it as a
schema violation. 19 of 46 MU-T3 rows (41%) were zeroed while carrying correct content — 72 of
the rejected object entries were `(unchanged, [0,0])`, and some rows also contained correct
`moved` deltas that were discarded with them.

The loss was **unequal by arm** — grid 6, map 5, film 5 against card 2, verbal 1 — i.e.
concentrated on exactly the contrast MU exists to make, on one of the two probes that can fund
a continuation. What it did to the measurement:

| MU-T3 macro (4 games, partial) | events | verbal | card | objects | map | grid | film |
|---|---:|---:|---:|---:|---:|---:|---:|
| under the defective scorer | 0.938 | 0.750 | 0.583 | 0.889 | 0.139 | 0.167 | 0.222 |
| after MU-E1 | 0.938 | 0.938 | 0.896 | 0.875 | 0.854 | 0.833 | 0.771 |

The defect manufactured a ~0.65 advantage for table-bearing arms on a funding probe. Had it
shipped, MU would have reported a decisive and false result.

Handling: the run was stopped, erratum **MU-E1** recorded against the frozen block, the scorer
corrected to ignore `delta` off `moved` (a `moved` outcome still requires an integer pair and
the pair is still compared), and the instrument refrozen. **No gold, threshold, gate, margin,
arm, case, prompt, guided schema, or routing rule changed** — this repairs a contradiction
between what the instrument requested and what it scored, which is not a threshold change.

The 214 rows already collected were **re-scored, not re-collected**. `mu_screen --rescore`
rebuilds each row's request payload under the corrected code and fails closed unless it
reproduces the stored `request_sha256` byte-for-byte: **214/214 matched, 0 mismatches**, so the
stimulus is provably identical and the stored responses remain valid evidence. Re-scored rows
carry `rescored_from` and `rescored_at`. Exactly 19 scores changed, all from invalid to valid.
Schema validity returned to 1.000. Precedent: VP's implementation-conformance erratum of
2026-08-02.

**MU-T1 and MU-T2 are unaffected** — both were already at 1.000 validity, and re-scoring changed
no row in either. The tables below are post-MU-E1.

## MU-T1 — the legibility gate

Complete: 84 rows, all six games, **zero request errors, first-pass schema validity 1.000**.
Six-game macros; the gate is 0.70.

| arm | macro | gate | dc22 | ft09 | ls20 | m0r0 | tu93 | vc33 | count | bbox | size | relation |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `verbal` | 1.000 | PASS | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `card` | 0.938 | PASS | 1.00 | 1.00 | 0.88 | 0.88 | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | 0.75 |
| `events` | 0.938 | PASS | 1.00 | 1.00 | 0.88 | 0.88 | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | 0.75 |
| `objects` | 0.896 | PASS | 1.00 | 0.88 | 0.88 | 0.88 | 0.88 | 0.88 | 0.92 | 1.00 | 1.00 | 0.67 |
| `film` | 0.292 | FAIL | 0.38 | 0.38 | 0.00 | 0.12 | 0.62 | 0.25 | 0.25 | 0.00 | 0.42 | 0.50 |
| `grid` | 0.250 | FAIL | 0.25 | 0.38 | 0.12 | 0.12 | 0.50 | 0.12 | 0.08 | 0.00 | 0.25 | 0.67 |
| `map` | 0.229 | FAIL | 0.25 | 0.25 | 0.12 | 0.38 | 0.38 | 0.00 | 0.25 | 0.00 | 0.08 | 0.58 |

The separation is unanimous: no game where a failing arm passes, none where a passing arm fails.
**`bbox` is 0.00 for all three failing arms — 48 items each, not one correct.** Their `relation`
scores sit at 0.50–0.67 on a boolean item and are consistent with guessing.

### What this licenses

**Qwen3.6-27B-8bit cannot perform connected-component analysis on a 64×64 character grid.** The
two T1 items that require it — count the objects of a colour, and locate the object a rank alias
denotes — are at or near zero for every arm without a computed object table, on every game. The
identical board is answered essentially perfectly once such a table accompanies it.

### What it does not license

Not "raw grids are unreadable". The failing arms carry the same exact board as the passing ones;
what defeats the model is the *derivation*, not the pixels. A question posed in explicit
coordinates rather than through a rank alias might well be answerable from `grid`, and MU does
not measure that.

Not a reasoning result for those arms either. Per §2 their MU-T2–T5 rates are reported and
carry a not-interpreted flag; a low rate under a failed T1 is an illegibility result.

### Consequences already fixed by this block

1. **S-legible set = {`verbal`, `card`, `events`, `objects`}.** `grid`, `film` and `map` are
   ineligible for T2–T5 selection under §5's eligibility rule.
2. **§3's only matched-information pure-rendering contrast is dead at the gate.** `grid` vs
   `film` was the single pair differing purely in rendering; both failed. MU will therefore
   answer *which computed bundle wins* and will have **no** measurement of whether rendering
   format alone matters. This limitation must travel with the final result.
3. **`verbal` is simultaneously the best and the cheapest legible arm** — 1.000 at ~4.0k median
   prompt tokens against `events`/`card` at ~12.6k. Under the cheaper-arm rule inside the 0.09
   margin it is positioned to win selection outright if it holds on T2–T5. T1 measures
   legibility only; that is not yet a finding about reasoning.

## MU-T2–T5 — the S pass and selection

Six-game macros on S, 420 rows. Arms below the T1 gate are shown for completeness and carry the
not-interpreted flag (§2).

| probe | floor | verbal | events | card | objects | grid | film | map |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T2 identity | 0.865 | 0.823 | **0.875** | 0.865 | 0.865 | 0.062 | 0.073 | 0.000 |
| T3 mechanics | 0.681 | **0.833** | **0.833** | 0.819 | 0.806 | 0.750 | 0.708 | 0.764 |
| T4 control | 0.083 | 0.167 | **0.250** | 0.083 | **0.250** | 0.167 | 0.000 | 0.083 |
| T5 terminal-action | 0.417 | 0.417 | 0.500 | **0.667** | **0.667** | 0.500 | 0.417 | 0.583 |

Selection (S only, legible arms only) took **`verbal` for T2/T3/T4 and `objects` for T5**. On
every probe all four legible arms fell inside the 0.09 margin, so the cheaper-arm rule decided
it: `verbal` costs ~4.0k median prompt tokens against ~12.6k for `events`/`card`. On T4 this
selected 0.167 over `events`/`objects` at 0.250 — a one-quantum difference the margin is
designed to treat as a tie. **C therefore confirms the cheapest arm, not the highest-scoring
one**, which is the pre-registered rule operating as written.

## MU-T2–T5 — the C pass, and the verdict

72 rows. Both selected arms passed T1 on C (`verbal` 0.958, `objects` 0.938), so every cell is a
real confirmation — none reads `t1_unmeasured_on_C` or `arm_illegible_on_C`.

| probe | arm | C macro | floor | **trivial** | vs floor | **vs trivial** | games > floor | screen-positive |
|---|---|---:|---:|---:|---:|---:|---:|---|
| T2 | verbal | 0.833 | 0.802 | 0.062 | +0.031 | +0.771 | 2/6 | **no** |
| T3 | verbal | 0.736 | 0.681 | **0.736** | +0.056 | **+0.000** | 4/6 | **no** |
| T4 | verbal | 0.417 | 0.250 | 0.250 | +0.167 | +0.167 | 3/6 | **no** |
| T5 | objects | 0.417 | 0.417 | 0.333 | +0.000 | +0.083 | 1/6 | **no** |

`trivial` is a **reported diagnostic, not a gate** — added after the S pass and therefore never
allowed to decide anything. It is the score of a constant answer requiring no reading at all:
"unchanged" for every object (T3), "new" for every row (T2), always the first offered option
(T4/T5).

### What the diagnostic shows that the gate could not

**On MU-T3, `verbal` scores 0.736 — exactly what answering "unchanged" to every object scores.**
Zero separation from a constant reply on the primary mechanics probe. Its +0.056 over the frozen
floor was an artifact of the floor being *weaker than the trivial baseline*: the catalogue modal
effect (0.681) is beaten by the constant answer (0.736). The same holds on S, where the floor was
0.681 and the trivial baseline 0.750.

This is a defect in my floor choice, recorded and not repaired: the floors are frozen and were
computed before any model saw a case, so swapping a comparator after seeing results is precisely
what pre-registration forbids. **A future protocol should define each floor as the strongest
trivial strategy available, not merely a plausible one.** Here the consequence happened to be
conservative — the gate failed anyway — but on other numbers a weak floor would have certified a
cell that a constant answer matches.

MU-T2's +0.771 over trivial with only +0.031 over the floor says the opposite thing and is worth
keeping: the identity task is genuinely non-trivial, and a model-free greedy appearance match
without any tracker already solves it about as well as Qwen does.

### Why the verdict is `stop`, and how close it was

Each funding probe failed on a **different** one of the two screen-positive requirements:

- **T3** met the per-game consistency rule (4/6) and missed the margin (+0.056 < 0.09).
- **T4** met the margin (+0.167 ≥ 0.09) and missed consistency (3/6 < 4).

Had the rule required only the margin, T4 would have been screen-positive and the verdict would
have been `continue`. Had it required only per-game consistency, T3 would have. Requiring both —
fixed in the manifest before any call — is what produced the stop. That is the two-criterion
design doing the job it was added for in the 2026-08-03 review, and it is the single most
load-bearing pre-registration decision in this screen.

## Operational record

492 measured calls, **zero request errors, first-pass schema validity 1.000** after MU-E1, 3.55 h
of GPU. Latency was prefill-bound throughout, as bring-up predicted. 180 S-pass calls went to the
three arms that failed the T1 gate; the full factorial ran as pre-registered, because selection
depends on a complete S pass.

## What this does and does not settle

Settled, conditional on the six iteration games: **no interface bundle in this menu lets
Qwen3.6-27B-8bit demonstrate mechanics understanding above a model-free baseline.** The best
mechanics cell equals a constant answer, and the best control cell cannot hold its margin across
games.

Not settled: whether rendering format alone matters (§3's only pure-rendering contrast died at
the T1 gate); whether control from *ordinary* states differs from control near a completion
(`decision.anchor_scope` — T3-fork, T4 and T5 anchor only at completion pre-states); and whether
an accumulated session-prefix effect catalogue would beat the ≤4-sample `card` measured here.
Each needs its own registered protocol.
