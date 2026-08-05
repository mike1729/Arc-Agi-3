# E3 follow-up — grounded-delta feasibility: is a cell-level forward model learnable?

**2026-08-05. Task note for agent execution. Zero model calls, 4–6 h.** The X1 gate
failed: the position-free effect grammar pins the next state on 0 of 35,568
board-changing edges, so no planner can step. The proposed fix is a second, grounded
layer — but *"whether the delta can be predicted at all is an open question this stage
did not ask"* (`notes/e3-executor.md` results). This task asks it, with three
measurements of increasing strength. It decides whether the executor line continues,
and in what form.

## Inputs

Store `logs/e1_store_v2/` (all 24 games; loader = `e2_dose.load_store` pattern —
completion rows lack post frames, skip them here). Human replays via
`rs_transitions.load_game` as the held-out set for step 3. Known latents for the
augmentation arm: in-episode action count (m0r0, g50t, cn04 — from the hidden-state
results; join via the rerun logs or `step` field per that task's method).

## Step 1 — grounded determinism

For repeated `(pre_grid, action)` observations (use the rerun census, which includes
routing actions — the store alone has no repeats): fraction with **identical post
grids**. Report per game; expect failures exactly on the counter games — run the
**latent-augmentation arm** there: determinism of `(pre_grid, action, in-episode
count)`. This bounds what any grounded model can achieve and quantifies how much the
known latents buy at the grounded level (they bought nothing at the signature level —
half B — so this is their second chance to matter).

## Step 2 — locality radius (the load-bearing measurement)

For every changed cell in every transition: the smallest radius r such that the
(2r+1)² pre-grid patch around it, plus the action (and click position relative to the
cell, for ACTION6), **determines the cell's change** across the whole store — group by
(patch hash, action, relative click), flag groups with divergent outcomes, increase r
until convergence or a cap (r ≤ 8, (w); report when the cap binds). Also the converse:
unchanged cells whose patch matches a changed cell's patch (false-positive pressure).

Report per game: the r distribution, the fraction of changes determined at r ≤ 2 /
≤ 4 / ≤ 8 / never, and the same **per event kind** (`reshape` / `appear` /
`assignment` / `move` — the kinds that blocked X1, 31,988 / 18,387 / 12,475 edges).
Small r dominating → cellular-automaton-style local rules are learnable and the
grounded layer is a mining problem. r unbounded on the mass of edges → the dynamics
are global (gravity columns, counters, whole-board maps) and the grounded layer needs
structured mechanisms, not patches — a different, harder build.

## Step 3 — patch-rule generalization (the feasibility number)

At the measured dominant radius: mine patch→delta rules on a train split of each
store, score **exact grounded next-state accuracy** on (a) the held-out store split
and (b) human replays — the external test. Report alongside a **memorizer floor**
(exact (pre,action) lookup) per the house convention. This number — grounded held-out
accuracy vs its floor — is what the X-phase redesign consumes.

## Report (append here)

1. Determinism table (with and without latent augmentation).
2. Locality distributions per game and per event kind.
3. Grounded held-out accuracy vs memorizer floor, store and human.
4. Verdict, two sentences: is a grounded layer learnable from this store, and is it a
   patch-mining problem or a structured-mechanism problem? Feeds the X-phase redesign
   directly.

## Cautions

- Compute: patch hashing over ~50k transitions × changed cells is fine; report timing;
  cap radii, not games.
- Concurrent agents: new files only (`agent/harness/e3_grounded.py`,
  `logs/e3_grounded.json`); no edits to shared harness files; `git status` before
  commits, stage only own files.
- No invented thresholds — the r cap and split fractions are (w) and reported.
- Everything here is model-free and survives the Qwen 3.8 transition untouched.

---

# Results — 2026-08-05

Code `agent/harness/e3_grounded.py` (new file, no shared-harness edits). Numbers
`logs/e3_grounded_s1.json`, `logs/e3_grounded_s2.json`, `logs/e3_grounded_s3.json`.
Zero model calls, zero game contact. Store `logs/e1_store_v2/` frozen; census
`logs/e2_hidden_state_rerun/`; human replays via `rs_transitions.load_game`.

```
.venv/bin/python agent/harness/e3_grounded.py --stage s1 --jobs 4 --out logs/e3_grounded_s1.json
.venv/bin/python agent/harness/e3_grounded.py --stage s2 --jobs 8 --out logs/e3_grounded_s2.json
.venv/bin/python agent/harness/e3_grounded.py --stage s3 --jobs 8 --out logs/e3_grounded_s3.json
```

**Two things stated once, because both change how every number below reads.**

*The action-key variant.* A cell's rule key is (pre-grid patch, action). For ACTION6 the note
specifies "click position relative to the cell", and that specification is not neutral: the raw
offset is a global coordinate smuggled into a local rule, and it makes keys rare. Both are
carried throughout. **`local`** — the offset when the click falls inside the patch, the single
symbol `out` when it does not, so a radius-r rule sees the radius-r neighbourhood and nothing
else. **`rel`** — the raw offset for every cell, the note's literal reading. `local` is quoted
as the headline everywhere; `rel` is reported beside it and is uniformly the more flattering.

*What "determined" is measured against.* Unchanged cells are in the grouping. A forward model
does not get told which cells will change, so a patch that must stay put competes with one that
must move; grouping changed cells only (the note's literal reading) is the looser question and
is also reported (`r_min.<variant>.changed` in the JSON). Determination rates are additionally
reported over cells whose group has support ≥ 2, since a group of size 1 is determined
vacuously — that correction is small here: 99.8% of queried cells have support ≥ 2 at r = 1 and
85.7% still do at r = 8, and the determination rate restricted to them differs from the headline
by ≤ 0.01 at every radius.

Unchanged cells are **sampled** — 32 per transition, seeded — because 50,330 transitions ×
4,096 cells is 206M cells. Changed cells are never sampled: all 1,131,532 are used. Sample and
seed are in the JSON's `working_defaults`.

## 1 — Grounded determinism (the upper bound)

Repeated `(pre_grid, action)` observations exist only in the instrumented rerun census
(routing actions included); the v2 store's own log cannot disagree with itself, and the run
confirms it — **0 repeated groups in the store on all 24 games**.

Across the census: **342 repeated groups, 288 of them deterministic — 0.842**. Weighted by
observation rather than by group (the rate a forward model would actually meet): **2,613 /
4,032 = 0.648**. All 54 aliased groups sit on five games:

| game | repeated groups | deterministic | aliased | resolved by in-episode count | …with a supported cell |
|---|---:|---:|---:|---:|---:|
| g50t | 89 | 46 (0.517) | 43 | 40 | 10 |
| cn04 | 9 | 5 (0.556) | 4 | 4 | 0 |
| m0r0 | 6 | 3 (0.500) | 3 | 3 | 1 |
| sc25 | 4 | 1 (0.250) | 3 | 3 | 3 |
| cd82 | 4 | 3 (0.750) | 1 | 1 | 1 |
| other 19 games | 230 | 230 (1.000) | 0 | — | — |

The failures land where predicted — the three counter games (g50t, cn04, m0r0) plus sc25 and
one cd82 group — and the latent augmentation does what it was asked to: **51 of 54 aliased
groups (0.944) are resolved by conditioning on the in-episode action count**, 48 by its parity
alone. This is the latents' second chance and, unlike the signature level (half B, where they
bought nothing), they cash it.

**But the honest number is smaller.** The raw counter is close to a per-observation identifier:
splitting two observations into two cells of one observation each "resolves" nothing. Requiring
at least one cell that held ≥ 2 observations and still agreed leaves **15 of 54 (0.278)**. Read
the 0.944 as an upper bound on what the latent could be doing and the 0.278 as the part that is
demonstrated.

**Sample size is the binding limitation of this step, not the rate.** 342 repeated groups over
24 games — the census is nearly empty by construction (`e2_hidden_state`'s standing note: the
explorer pops each candidate from a state's frontier exactly once, so only routing actions
repeat). This bounds nothing tightly. What it does establish: repeated observations are mostly
consistent, and where they are not, the known latent covers almost all of it.

## 2 — Locality radius (the load-bearing measurement)

1,131,532 changed cells over 50,330 store transitions (35,568 state-changing); 299 s wall clock
on 8 jobs. Smallest radius r ≤ 8 at which the (2r+1)² pre-grid patch plus the action determines
the cell's new value across the whole game store, `local` variant, unchanged cells in the
grouping:

| game | changed cells | r=0 | ≤1 | ≤2 | ≤4 | ≤8 | never | median r | edges fully determined ≤8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ar25 | 72,966 | 0.004 | 0.371 | 0.702 | 0.970 | 0.994 | 0.006 | 2 | 0.657 |
| bp35 | 74,472 | 0.003 | 0.167 | 0.276 | 0.473 | 0.732 | 0.268 | 3 | 0.953 |
| cd82 | 84,701 | 0.000 | 0.149 | 0.286 | 0.618 | 0.868 | 0.132 | 3 | 0.296 |
| cn04 | 245,704 | 0.001 | 0.105 | 0.305 | 0.596 | 0.807 | 0.193 | 3 | 0.472 |
| dc22 | 15,184 | 0.000 | 0.158 | 0.235 | 0.318 | 0.504 | 0.496 | 3 | 0.363 |
| ft09 | 3,344 | 0.024 | 0.103 | 0.432 | 0.800 | 0.952 | 0.048 | 3 | 0.000 |
| g50t | 49,747 | 0.000 | 0.045 | 0.256 | 0.567 | 0.818 | 0.182 | 3 | 0.458 |
| ka59 | 11,271 | 0.002 | 0.423 | 0.733 | 0.858 | 0.890 | 0.110 | 2 | 0.448 |
| lf52 | 1,265 | 0.002 | 0.497 | 0.719 | 0.904 | 0.957 | 0.043 | 1 | 0.835 |
| lp85 | 1,758 | 0.000 | 0.010 | 0.030 | 0.418 | 0.687 | 0.313 | 4 | 0.000 |
| ls20 | 116,538 | 0.000 | 0.318 | 0.529 | 0.819 | 0.964 | 0.036 | 2 | 0.935 |
| m0r0 | 63,502 | 0.000 | 0.211 | 0.550 | 0.849 | 0.989 | 0.011 | 2 | 0.676 |
| r11l | 2,908 | 0.011 | 0.334 | 0.623 | 0.826 | 0.929 | 0.071 | 2 | 0.892 |
| re86 | 124,878 | 0.000 | 0.077 | 0.145 | 0.526 | 0.870 | 0.130 | 4 | 0.289 |
| sb26 | 21,283 | 0.005 | 0.153 | 0.429 | 0.748 | 0.910 | 0.090 | 3 | 0.846 |
| sc25 | 8,691 | 0.000 | 0.423 | 0.553 | 0.849 | 0.887 | 0.113 | 2 | 0.502 |
| sk48 | 29,845 | 0.000 | 0.352 | 0.576 | 0.780 | 0.999 | 0.001 | 2 | 0.980 |
| sp80 | 23,764 | 0.226 | 0.389 | 0.555 | 0.820 | 0.961 | 0.040 | 2 | 0.919 |
| su15 | 534 | 0.000 | 0.519 | 0.549 | 0.607 | 0.764 | 0.236 | 1 | 0.360 |
| tn36 | 4,444 | 0.061 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 1 | 1.000 |
| tr87 | 58,854 | 0.346 | 0.354 | 0.410 | 0.879 | 0.994 | 0.006 | 3 | 0.946 |
| tu93 | 27,215 | 0.013 | 0.481 | 0.524 | 0.689 | 0.979 | 0.021 | 2 | 0.783 |
| vc33 | 12,138 | 0.000 | 0.071 | 0.081 | 0.147 | 0.350 | 0.650 | 5 | 0.823 |
| wa30 | 76,526 | 0.007 | 0.131 | 0.397 | 0.955 | 0.992 | 0.007 | 3 | 0.777 |

**Aggregate.** r=0 0.025 · r=1 0.175 · r=2 0.183 · r=3 0.189 · r=4 0.123 · r=5 0.081 · r=6
0.053 · r=7 0.030 · r=8 0.025 · **never 0.117**. Cumulative: **≤2 0.383 · ≤4 0.694 · ≤8 0.883**.
Under the `rel` variant: ≤2 0.534, ≤8 0.949. Per-game median r is **2 or 3 on 18 of 24 games**
(1 on three, 4 on two, 5 on vc33).

**Per event kind** (changed cells, each counted under every kind whose component covers it;
`assignment` has no per-cell analogue and is reported at the edge level below):

| kind | cells | ≤2 | ≤4 | ≤8 | never |
|---|---:|---:|---:|---:|---:|
| move | 148,987 | 0.676 | 0.978 | **0.995** | 0.005 |
| reshape | 452,507 | 0.393 | 0.698 | 0.893 | 0.107 |
| disappear | 495,087 | 0.388 | 0.628 | 0.831 | 0.169 |
| appear | 487,418 | 0.228 | 0.590 | 0.848 | 0.152 |
| unattributed | 4,335 | 0.029 | 0.175 | 0.467 | 0.533 |

`move` is the local kind and is essentially solved by small patches. The three kinds that
blocked X1 are exactly the three that are not: `appear` is the worst at small radius (0.228 at
≤2) and `reshape`/`disappear` carry the residue that never converges.

**Edge level — the number that matters for stepping.** An edge is grounded-determinate only if
*every* one of its changed cells is (necessary for an exact next state; sufficiency is step 3).
Over the 35,568 state-changing edges: **≤2 0.296 · ≤4 0.425 · ≤8 0.693 · never 0.307**. Split by
the X1 blocker that sank the edge in the position-free grammar:

| X1 blocker | edges | ≤2 | ≤4 | ≤8 | never |
|---|---:|---:|---:|---:|---:|
| reshape | 31,988 | 0.325 | 0.414 | 0.677 | 0.323 |
| appear | 18,387 | 0.078 | 0.250 | 0.647 | 0.353 |
| assignment | 12,475 | 0.051 | 0.166 | 0.562 | 0.438 |

**Against X1's 5 / 35,568 (0.014%), grounding buys three and a half orders of magnitude: 69.3%
of board-changing edges become locally determinate at r ≤ 8.** `assignment` — "which of the m
same-colour components" — is the kind grounding helps least with, which is what one would
expect: naming cells answers *where*, and assignment ambiguity is about *which*, so the two
overlap only partly.

**False-positive pressure.** Fraction of sampled unchanged cells sharing a key with a changed
outcome: **0.453 at r=0 · 0.283 at r=1 · 0.236 at r=2 · 0.126 at r=3 · 0.054 at r=4 · 0.014 at
r=8**. At small radii a large minority of the board looks locally exactly like a cell that
moved. This is why the "≤2" column overstates a usable model and why step 3's exact-next-state
number is the one to read.

## 3 — Patch-rule generalization (the feasibility number)

Rules mined on the first 70% of each store in step order, scored on the last 30% and on human
replays (up to 400 transitions per level, sampled, seeded). Prediction is per cell: look up
(patch, action key), take the training majority (ties to the smaller colour), and **predict no
change when the key is unseen** — the only default that invents nothing. An edge counts as
correct only when the whole 64×64 grid is exact.

Two floors, per the house convention. **Memorizer** — exact `(pre grid, action)` lookup in the
train split, identity on a miss. **Identity** — always predict no change; it is worth naming
separately because it is what the memorizer degrades into. On the store split the two are
*numerically identical on every game*, and that is itself a finding: **the memorizer's hit rate
on the held-out store split is 0.000 on all 24 games** — the explorer never revisits a
`(state, action)` pair, so the memorizer has nothing to recall and the floor it contributes is
exactly the no-op rate. On human L1 it hits 6.3% of the time and does contribute.

Per game at r = 3, `local` (the aggregate radius sweep follows):

| game | held-out | exact | on changing | memo = identity floor | human L1 exact | human L1 memo | human L2 exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| ar25 | 892 | 0.867 | 0.643 | 0.727 | 0.564 | 0.105 | 0.050 |
| bp35 | 862 | 0.813 | 0.813 | 0.000 | 0.204 | 0.094 | 0.030 |
| cd82 | 877 | 0.458 | 0.617 | 0.283 | 0.153 | 0.233 | 0.064 |
| cn04 | 866 | 0.301 | 0.135 | 0.291 | 0.123 | 0.060 | 0.038 |
| dc22 | 882 | 0.503 | 0.743 | 0.379 | 0.273 | 0.195 | 0.045 |
| ft09 | 370 | 0.914 | 0.000 | 0.914 | 0.255 | 0.255 | 0.089 |
| g50t | 435 | 0.101 | 0.014 | 0.198 | 0.008 | 0.168 | 0.003 |
| ka59 | 877 | 0.511 | 0.674 | 0.254 | 0.300 | 0.183 | 0.060 |
| lf52 | 44 | 0.705 | 0.705 | 0.000 | 0.458 | 0.013 | 0.255 |
| lp85 | 13 | 0.846 | 0.000 | 0.846 | 0.233 | 0.513 | 0.050 |
| ls20 | 864 | 0.022 | 0.022 | 0.004 | 0.018 | 0.160 | 0.000 |
| m0r0 | 883 | 0.361 | 0.067 | 0.412 | 0.026 | 0.117 | 0.055 |
| r11l | 39 | 0.436 | 0.436 | 0.000 | 0.097 | 0.000 | 0.047 |
| re86 | 874 | 0.124 | 0.124 | 0.005 | 0.078 | 0.085 | 0.003 |
| sb26 | 896 | 0.821 | 0.527 | 0.710 | 0.548 | 0.465 | 0.275 |
| sc25 | 482 | 0.701 | 0.315 | 0.591 | 0.228 | 0.178 | 0.063 |
| sk48 | 899 | 0.812 | 0.078 | 0.843 | 0.123 | 0.225 | 0.055 |
| sp80 | 304 | 0.645 | 0.645 | 0.000 | 0.122 | 0.119 | 0.000 |
| su15 | 108 | 0.630 | 0.963 | 0.500 | 0.439 | 0.121 | 0.160 |
| tn36 | 863 | **1.000** | **1.000** | 0.000 | 0.738 | 0.025 | 0.000 |
| tr87 | 878 | **0.000** | 0.000 | 0.000 | 0.000 | 0.048 | 0.000 |
| tu93 | 772 | 0.352 | 0.352 | 0.000 | 0.059 | 0.330 | 0.086 |
| vc33 | 240 | 0.725 | 0.725 | 0.000 | 0.460 | 0.029 | 0.140 |
| wa30 | 888 | 0.115 | 0.010 | 0.134 | 0.088 | 0.113 | 0.003 |

The two extremes were re-derived independently before being quoted. **tn36 1.000**: 60/60 of the
first held-out edges exact, mean delta 1.4 cells — a game whose dynamics are a single local
recolour, and the one place a patch model is the whole answer. **tr87 0.000**: 0/60 exact, ~10 of
20.6 changed cells wrong per edge — not a near miss but a wholesale failure, consistent with
S2's tr87 row (0.346 of cells determined at r = 0, then almost nothing until r = 3).

**Aggregate, edge-weighted** (`local`; `rel` in parentheses, uniformly worse here — the raw
click offset does not transfer):

| radius | store held-out exact | on changing edges | floor | human L1 exact | on changing | human L1 memo / identity | human L2 exact | on changing | human L2 floor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.432 (0.409) | 0.315 (0.253) | 0.289 | 0.167 (0.137) | 0.116 | 0.169 / 0.121 | 0.078 (0.047) | 0.058 | 0.053 |
| 2 | 0.461 (0.442) | 0.347 (0.291) | 0.289 | 0.200 (0.157) | 0.151 | 0.169 / 0.121 | 0.061 (0.046) | 0.037 | 0.053 |
| 3 | **0.490** (0.467) | **0.388** (0.321) | 0.289 | **0.229** (0.186) | **0.187** | 0.169 / 0.121 | 0.063 (0.046) | 0.037 | 0.053 |

**The headline, stated plainly.** At r = 3 a patch model mined from the explorer's own store
predicts the **exact** next 64×64 state on **38.8% of held-out board-changing edges**, where
both floors score **0.000** by construction (the memorizer never hits, and identity is wrong on
every changing edge). Per-game median 0.394; it beats its floor on 17 of 24 games. Against X1's
0 / 35,568 this is the difference between a model that cannot be stepped and one that can be
stepped roughly a third of the time.

**On human replays it is weaker but real at L1, and barely off the floor at L2.** Human L1:
0.229 exact vs 0.169 memorizer and 0.121 identity — above both, and 0.187 on changing edges vs
the memorizer's 0.056; above its floor on 13 of 24 games. Human L2: 0.063 against an identity
floor of 0.053 over all edges, and 0.037 of changing edges exact against a floor of 0.000 —
non-zero, but an order of magnitude below L1. **38.3% of L2 cells present a key never seen in
training** (against 0.2% on the store split and 4.3% on human L1). The L2 board is largely
outside the patch vocabulary, which is the same transfer cliff E0/E2 measured for the signature
layer, now in grounded coordinates.

**The self-consistency ceiling is the most informative number here.** Re-scored on its own
training data the model reaches only **0.514 exact / 0.412 on changing edges**: at r = 3 patch
keys genuinely conflict, so the majority vote loses more than a third of its own edges before
generalization is even at issue. S2's "88% of cells determined at r ≤ 8" and this 0.41 are the
same fact from two directions — per-cell determinacy is high, and an exact next state needs
*every* cell right at once.

**Cost.** 445,346 rules across 24 games at r = 3 (≈18.5k per game) against the signature miner's
4–18. The grounded layer is a different kind of object: a large lookup table, not a small rule
set, and nothing about it transfers by construction the way a position-free rule does.

### Does it turn over? — the r = 5 supplement

S2's median radius is 2–3, so r ≤ 3 is where the sweep was pre-committed. Because the trend was
still rising at r = 3, one further radius was scored to find out whether the gain is learning or
memorization (`logs/e3_grounded_s3_r5.json`, `--radii 5 --variants local`, 322 s):

| | store held-out exact | on changing | human L1 exact | on changing | human L2 exact | on changing | unseen keys (store / L1 / L2) | rules | train refit (changing) |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| r=3 | 0.490 | 0.388 | 0.229 | 0.187 | 0.063 | 0.037 | 0.002 / 0.043 / 0.383 | 445k | 0.412 |
| r=5 | **0.585** | **0.527** | **0.309** | **0.271** | 0.066 | 0.034 | 0.008 / 0.071 / 0.576 | 1.58M | 0.597 |

**No turnover through r = 5** on the store split *or* on human L1 — a bigger patch keeps buying
accuracy on both, which is the signature of genuine locality rather than of memorization (a
memorizing table would gain on the store and lose on the external set; 7 of 24 games do lose on
human L1, but only ar25 does so while clearly gaining on the store — 0.867 → 0.915 there against
0.564 → 0.406 on human L1). **Human L2 does not move at all** (0.063 →
0.066, and 0.037 → 0.034 on changing edges) while its unseen-key rate climbs from 38% to 58%.
The cost is 3.5× the table for that gain. The radius that maximizes transfer was not searched
past 5 and is not claimed; what is claimed is that the r ≤ 3 numbers are a floor on what
patch-mining achieves, not a ceiling.

Timing: S1 0.3 s, S2 299 s, S3 559 s (+322 s for the r = 5 supplement), all on 8 jobs.

## 4 — Verdict

**A grounded layer is learnable from this store, and the gap it closes is the one X1 opened:**
patch rules mined on 70% of a store predict the exact next 64×64 state on 38.8% of held-out
board-changing edges at r = 3 and 52.7% at r = 5, against floors of 0.000, where the
position-free signature pinned 0 of 35,568 — so the executor line continues, with the two-layer
split (signature for transfer, grounded delta for stepping) intact.

**It is a patch-mining problem on the levels the store covers and a structured-mechanism problem
across levels:** locality is real (median determining radius 2–3, `move` essentially solved,
88.3% of changed cells determined at r ≤ 8) but it does not survive a level change — human L2 sits
at its identity floor with 38–58% of cells presenting unseen keys — so mining buys a
steppable L1 model and buys nothing for L2, which is exactly where the E3 executor was supposed
to earn its score.

## Caveats

- **S1 is small.** 342 repeated groups over 24 games; the latent's 0.944 resolution rate rests on
  54 aliased groups, 43 of them one game (g50t), and drops to 0.278 under the non-degeneracy
  requirement. It bounds nothing tightly.
- **The store split is a time split of one trajectory**, so "held out" means later, not
  independent — later states are reachable from earlier ones and share structure. Human replays
  are the only genuinely external test here, and they are the weaker result.
- **Unchanged cells are sampled** (32/transition, seeded); every false-positive-pressure number
  and the `all`-grouping determination rates inherit that sampling. Changed cells are complete.
- **`assignment` is edge-level only** — it has no per-cell analogue, so the per-kind cell tables
  cover `move`/`reshape`/`appear`/`disappear` and `assignment` appears only in the edge split.
- **Patch keys are exact byte matches**, with no invariance (no rotation, reflection, colour
  permutation, or object identity). A grounded layer with those invariances is a different and
  probably better model; this measurement is the un-generalized baseline for it.
- Human test sets are capped at 400 transitions per level (sampled, seeded) for cost.
- Everything here is miner output — model-free, not (3.6)-bound, unaffected by the Qwen 3.8
  transition.
