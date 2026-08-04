# E0 — offline L1 → L2 rule survival

**Run 2026-08-04. Zero model calls.** Pre-registered as `gate_manifest.yaml → rs` (frozen
2026-08-04, errata RS-E1…RS-E5). **All 25 public games**, of which 24 carry engine truth; the
seal on the nineteen non-iteration games was lifted by operator decision after the six-game
result (RS-E2).

Artifacts: `logs/e0_row_m_all.json`, `logs/e0_row_c_all.json`, `logs/e0_fidelity.json`,
`logs/e0_fidelity_rest.json`. Six-game first pass retained at `logs/e0_row_m.json`,
`logs/e0_row_c.json`.
Harness: `agent/harness/rs_transitions.py`, `rs_e0.py`, `rs_completion.py`, `rs_fidelity.py`.

## What was asked

Whether a rule induced from level-1 evidence is still true at level 2 — the standing objection
to spending the evidence budget on L1. It had been an assumption on both sides; this is the
first measurement of it.

## Headline

**The objection is right about the dynamics and wrong about the goal, and the split is sharp.**

Across 24 games:

| | within-L1 (median) | L1 → L2 (median) | median gap |
|---|---|---|---|
| **liveness** — does the action do anything | 0.941 | 0.932 | **+0.003** |
| **detailed dynamics** — what exactly it does | 0.327 | 0.164 | **+0.182** |

Which actions are live survives the level change essentially intact. What they *do* does not.

**And the loss concentrates exactly where there was something to lose.** Split the 24 games by
whether L1 supported a good detailed model at all:

| | n | median drop, L1 → L2 |
|---|---:|---|
| within-L1 ≥ 0.6 (a good L1 model existed) | 9 | **+0.523** |
| within-L1 < 0.6 (it never did) | 15 | +0.155 |

Seven of the nine games with a good L1 model lose ≥ 0.28. Only `tn36` (−0.025) and `sp80`
(+0.041) hold. Reading the flat rows as "transfer works" inverts the finding: they are flat
because their L1 model was already poor.

**Memorizer floor: 0.000 on every game, both splits.** Exact 64×64 pre-states essentially never
recur across sessions or levels, so nothing here is memorization — every point of accuracy is
generalization by the rule model.

## Engine truth — passed on 24 of 25 games

Every session of all 25 games replayed through the frozen source via `ReplayDriver` over
`arcengine`. Two comparisons: all frames, and only the **role-bearing** frames E0 actually reads
(settled, solved_terminal, next_level_initial).

- **s5i5 excluded entirely.** All 11 sessions diverge on role-bearing frames at step 2, on
  ACTION6, inside the L1 window. The frozen source is not the build those recordings came from.
- **Three sessions excluded** — `cn04/ce770223`, `lf52/72a712db`, `sp80/add9ed90` — one each,
  all on RESET, divergence inside the window.
- **Not excluded:** divergences falling *after* the L1/L2 window (13 sessions across 12 games)
  cannot affect a result read from levels 1–2. `bp35` (2/14 sessions all-frame exact) and `vc33`
  (3/10) fail badly on all-frame comparison but pass on role-bearing — their divergence is
  confined to intermediate animation frames, which no transition endpoint is ever drawn from.
  This is the accepted vc33 settled-frame erratum, and bp35 turns out to share it.

Over every frame E0 reads, the 24 retained games reproduce byte-exactly.

## Row M — mechanics

Rules are `action [+ one guard] → effect` over object events. `within-L1` trains on half the L1
sessions and tests on the other half — the ceiling this game's evidence supports, so the **gap**
is what the level change costs rather than what thin evidence costs. Sorted by detailed-dynamics
drop.

| game | detailed: within-L1 → L1→L2 | drop | liveness: within-L1 → L1→L2 | drop |
|---|---|---|---|---|
| vc33 | 0.879 → 0.097 | +0.783 | 1.000 → 0.990 | +0.010 |
| lp85 | 0.837 → 0.068 | +0.769 | 0.993 → 0.960 | +0.033 |
| ft09 | 0.845 → 0.177 | +0.668 | 0.903 → 0.867 | +0.036 |
| ar25 | 0.667 → 0.058 | +0.609 | 1.000 → 0.749 | +0.251 |
| lf52 | 0.718 → 0.195 | +0.523 | 1.000 → 0.928 | +0.072 |
| sb26 | 0.684 → 0.380 | +0.304 | 0.891 → 0.671 | +0.219 |
| sc25 | 0.328 → 0.027 | +0.301 | 0.884 → 0.946 | −0.062 |
| tu93 | 0.872 → 0.588 | +0.284 | 1.000 → 0.929 | +0.071 |
| tr87 | 0.279 → 0.000 | +0.279 | 1.000 → 1.000 | +0.000 |
| wa30 | 0.233 → 0.001 | +0.232 | 0.913 → 0.999 | −0.086 |
| ka59 | 0.274 → 0.076 | +0.198 | 0.863 → 0.911 | −0.048 |
| su15 | 0.347 → 0.164 | +0.183 | 0.919 → 0.633 | +0.286 |
| cd82 | 0.302 → 0.121 | +0.181 | 0.822 → 0.841 | −0.018 |
| re86 | 0.184 → 0.007 | +0.177 | 1.000 → 1.000 | +0.000 |
| sk48 | 0.195 → 0.040 | +0.155 | 0.940 → 0.969 | −0.029 |
| dc22 | 0.203 → 0.059 | +0.144 | 0.832 → 0.890 | −0.059 |
| cn04 | 0.289 → 0.164 | +0.125 | 0.990 → 0.904 | +0.086 |
| sp80 | 0.676 → 0.635 | +0.041 | 1.000 → 0.886 | +0.114 |
| g50t | 0.233 → 0.240 | −0.007 | 0.923 → 0.951 | −0.028 |
| ls20 | 0.435 → 0.451 | −0.016 | 0.949 → 0.979 | −0.030 |
| tn36 | 0.815 → 0.839 | −0.025 | 0.996 → 0.991 | +0.006 |
| bp35 | 0.326 → 0.438 | −0.113 | 0.814 → 0.997 | −0.183 |
| m0r0 | 0.238 → 0.351 | −0.113 | 0.913 → 0.935 | −0.022 |
| r11l | 0.203 → 0.333 | −0.130 | 0.942 → 0.896 | +0.046 |

`moveset` (movement vectors dropped) tracks `full` closely on most games, so the collapse is not
about *how far* things move — it is about *which objects* change at all.

### The failure split

Mispredictions at `full` granularity, L1 → L2, pooled over 24 games:

| category | count | share |
|---|---:|---|
| guard-fixable (`adj` — something is in the way) | 4403 | **25.4%** |
| separable by census (`count`/`present` only) | 8588 | 49.6% |
| unpredicted (indistinguishable and still different) | 4338 | **25.0%** |

Three categories, not two, and the middle one is the correction that matters (RS-E4). A first
pass scored 100% guard-fixable on four of six games; the separating feature was per-colour
*count* in essentially every case — "L2 has a different number of objects", which distinguishes
without explaining. Requiring the feature to be constant across the rule's supporters, and
counting only a mechanical `adj` guard as a repair, gives the table above.

**A quarter of mispredictions are genuinely repairable; a quarter are not repairable by any
guard in this vocabulary.** The `unpredicted` mass is concentrated: `wa30` 1328, `sk48` 1171,
`m0r0` 1026, `cn04` 246, `ls20` 206. m0r0 also fails *within* L1 (0.238), so its unpredictability
is a property of the game — hidden state — not of the level change.

## Row C — completion conditions

*(run in progress at time of writing; six-game result stands below and will be superseded by
`logs/e0_row_c_all.json`)*

Frozen ES visual grammar, hash asserted at run time. Outcomes are three-way; `vacuous` (never
definite at L2, terms unbound) is kept separate from `survived`, so grammar silence cannot be
reported as goal stability.

Six-game pass:

| game | universe | L1 survivors | L1→L2 survived / falsified / vacuous | rate |
|---|---:|---:|---|---|
| dc22 | 177 | 13 | 12 / 1 / 0 | **0.923** |
| tu93 | 150 | 12 | 12 / 0 / 0 | **1.000** |
| ft09 | 70 | 0 | — | UNDEFINED |
| ls20 | 168 | 0 | — | UNDEFINED |
| m0r0 | 43 | 0 | — | UNDEFINED |
| vc33 | 70 | 0 | — | UNDEFINED |

**Where the goal is expressible, it transfers.** dc22 loses one hypothesis of thirteen across
1014 L2 transitions; tu93 loses none. Within-L1 rate is 1.000 for both, so there is no gap to
explain, and nothing survives vacuously — every survivor made definite correct L2 predictions.

**Expressibility is the binding limit.** An empty L1 survivor set means the visual grammar cannot
express that game's completion condition *at all* — 0/0, reported UNDEFINED, never 0%. The
early 24-game returns (ar25, bp35, cd82, cn04 all UNDEFINED) suggest the six-game rate of 4-in-6
is optimistic rather than pessimistic. This independently reproduces the ES screen's
coverage-blocked closeout from a different direction: worth something as corroboration, worth
nothing as reassurance.

## What this licenses, and what it does not

- **L1 as an evidence budget buys the action inventory, not the dynamics.** Liveness survives on
  every game, with a median gap of +0.003. An explorer that spends L1 to learn *what the buttons
  do* is buying something durable.
- **The X phase's plan-then-execute assumption is the exposed one.** BFS/A* over a mined forward
  model needs `full`-granularity dynamics, and that is the row that collapses — hardest, and this
  is the uncomfortable part, on precisely the games where L1 looked most informative.
- **Repair-vs-invalidate defaults can now be bounded, not set.** 25.4% of mispredictions admit a
  mechanical guard repair; 25.0% admit none. A repair policy built on the remaining 49.6% —
  object-census differences — would be fitting noise.
- **This says nothing about whether anything can FIND these rules.** It measures only whether
  rules that are true at L1 stay true. A miner with perfect L1 evidence is assumed throughout.

## Known limits

1. **One guard, not conjunctions.** Deliberate — a richer hypothesis space fits any split and
   destroys the survival number — but "unpredicted" is relative to this vocabulary.
2. **L1 → L2 only.** Whether the L2 → L3 gap resembles the L1 → L2 gap is untested, and the
   levels are not obviously exchangeable.
3. **Human replays are not explorer trajectories.** Humans do not sweep the action space; a real
   E phase will have different coverage — probably better for liveness, worse for rare events.
4. **Row C's `survived` is not `correct`.** A survivor is a hypothesis never definitely
   contradicted, not the true completion condition. dc22 ends with twelve distinct survivors: the
   goal is *stable* under level change, not *identified*.
5. **s5i5 is unmeasured**, and its exclusion is itself a finding: one public game's shipped
   source does not reproduce its own recorded sessions.
