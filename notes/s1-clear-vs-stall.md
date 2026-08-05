# S1 clear-vs-stall contrast — what the reference did when it worked

**2026-08-05. Task note for agent execution. Zero model calls, zero compute** — trace
reading plus one mechanical cross-tab. S1 here is the sprint stage (the reproduced
reference agent on the FP8 stack, thinking on — its measurements are VALID; do not
confuse with the voided VP/GI-1/MU screens).

## What and why

S1's stall side was analyzed (the standing `goal_unknown` result: 76% primary, 92%
present, 100% of L1 stalls). Its **success side never was**: nobody has read the traces
of the games it actually cleared. A quick scan (re-derive in step 0) says S1 cleared at
least one level on **4 of 18 games it ran — ar25, sp80, tn36, vc33** — and never scored
on 14, including five of the six slice iteration games.

> **Superseded 2026-08-05 — kept because H was framed on it.** Those figures are the
> *local MLX replication*. On the reference stack the positive set is **17 of 25 games,
> 42 of 75 passes**. The success side is an order of magnitude larger than this paragraph
> assumes, and "never scored on 14" is false of the reference. See Inputs and results §0.

**The hypothesis under test (H):** the cleared set is exactly the set where the default
goal prior — the "clear the board"/obvious-visual-goal shape that the slice autopsy
showed dominating Qwen's goal channel (2 right / 8 wrong) — happens to match the true
goal. I.e. **the reference never discovers goals; it occasionally gets one for free.**

Either outcome is decision-grade:
- **H holds** → the deployed bottleneck and the slice goal-channel failure are one
  mechanism (same model, same prior, two harnesses); our system only needs to beat the
  reference where the prior fails, which defines the target set.
- **H breaks** → some cleared trace contains real in-context goal discovery. Describe its
  mechanism in detail — what evidence flipped the model off the prior. That is the
  template the M-phase must reproduce, and the first observed instance of the capability.

Feeds: the slice-2 goal-channel decision and the E3/X target-set framing. Recommendation
only — no design decisions in this note.

## Inputs (verified to exist)

> **Lineage corrected 2026-08-05.** As first written, this section named `logs/runs/` as
> "the runs" and gave its 4-of-18 split as the working split for S1. That is the **local
> MLX replication line, not the reference stack** — the error is corrected in place below
> because the note had not yet been acted on, and the superseded claim plus its
> consequences are recorded in results §0. The task's own step 0 lineage check is what
> caught it.

- **Runs — two corpora, not one. `ref` carries the analysis.**
  - **`ref` (reference stack, use this):** `logs/kaggle_v2`, `logs/kaggle_v3`,
    `logs/kaggle_v4` — duck-harness on Kaggle, vLLM **FP8**, reasoning parser on
    (`[THINKING]` present in every turn). 3 passes × 25 games = 75 game-passes. Each dir
    has `artifacts/*_events.jsonl` (+ `*_viewer_data.json`), `transcripts/`, `prompts/`,
    per-game `*_requests.jsonl`, `benchmark.json`, `summary.txt`, `per_game_analysis.json`,
    `vllm-openai-server.log`. No `run_config.json`/`deploy_meta.json` in these dirs.
    **This is the corpus the standing `goal_unknown` result is keyed to** — every episode
    id in the s1d corpus is `kaggle_v{2,3,4}::<game>_p0::L<n>`.
  - **`local` (replication, report but do not generalize from):** `logs/runs/` — 29
    directories with `artifacts/`, `transcripts/`, `prompts/`, `requests.jsonl`,
    `run_config.json`, `deploy_meta.json`, `stdout.log`; 36 game-passes over 18 games.
    `run_config.json` names local MLX weights (`Qwen3.6-27B-4bit`, 28 passes;
    `-8bit`, 8 passes) and `deploy_meta.json` gives
    `target_class: taaf.deploy_inline.InlineTarget` on the laptop. Arms are heterogeneous
    (`a6c1`, `8bit`, `kb2`, `c2`, `d13c2`, `l2c2`) and passes per game are uneven (1–4).
  - `logs/quarantine/` excluded. `logs/kaggle-reference` (2026-07-26, the first
    duck-harness measurement) is **summary only — no event artifacts, no transcripts**, so
    it cannot enter step 1; cite it for context only.
- **Working split (w)** — derive from the `score` field in events.jsonl and verify the
  semantics (score increment = level completed) against viewer_data on one known case:
  - **ref:** 17 of 25 games clear L1 in ≥1 of 3 passes; 42 of 75 passes clear L1 (5 also
    clear L2). Never cleared in any pass: cn04, dc22, g50t, ls20, sc25, sk48, tr87, wa30.
  - **local:** cleared ar25, sp80, tn36, vc33 (max score 1 each) · stalled at 0: bp35,
    cn04, ft09, g50t, ka59, lf52, lp85, ls20, m0r0, r11l, re86, tr87, tu93, wa30 · 7
    public games never ran in these dirs (cd82, dc22, s5i5, sb26, sc25, sk48, su15).
  - ⚠ The two disagree on more than volume: tu93 clears 3/3 in `ref` and 0/2 in `local`.
    Never carry a `local` outcome into a claim about the reference.
- **Stall labels**: `s1d_*` files in `logs/` (draw, pass2, worksheet, result lock) and
  the labeling harness on the archive branch. Inventory what the final labeled corpus is;
  read the archive via `git show archive/screening-line-2026-08-04:<path>` — **do not
  check out the branch** (concurrent agents on main).
- **Slice goal-channel results** for the cross-tab: `cells[].goal` in
  `logs/e2_slice.json`, `logs/e2_slice_seed{1,2}.json`; adjudications in
  `notes/e2-trace-autopsy.md` and `notes/e2-variance-arm.md` §6.
- **True goals**: game source under `data/` — read freely, **never quote into committed
  artifacts** (PUBLISHING.md; git history counts as redistribution; labels/paraphrases
  only). Quoting **S1's own reasoning traces is fine and encouraged** — they are our
  artifacts.

## Step 0 — verify the split, name the arms

Re-derive per-game outcomes from `events.jsonl` across **both** corpora — the 3 `ref` runs
and the 29 `local` run dirs (script it — a small committed
`agent/harness/s1_contrast.py` is welcome; tables from scripts, not by hand). For `local`,
group runs by prompt variant from `run_config.json` (kb2, a6c1, d13, dense, supervisor, …)
and report coverage per arm — passes per game are uneven (1–4); for `ref` the arm is the
run dir. Confirm the lineage of everything analyzed — `run_config.json`/`deploy_meta.json`
where present, the server log otherwise — and flag anything that is not the reference stack
rather than silently including it. **This check is what caught the Inputs error above; do
not skip it on the assumption that the section is now right.**

## Step 1 — the positive set (the new work)

For each cleared pass on ar25, sp80, tn36, vc33: locate the clearing moment in
events.jsonl, then read the transcript window leading to it. Per clear, answer with
quotes:

1. Did the agent **state a goal before clearing**? Quote the statement and its step.
2. Was the stated goal the **default prior shape** or **evidence-derived**? If derived,
   name the evidence in the trace that produced it.
3. **Efficiency split**: actions before vs after the goal articulation. A goal stated
   only after the score moved counts as post-hoc, not discovery.
4. Or was it **accidental** — no articulation, completion stumbled into?

Classify each clear: `prior-match` / `evidence-derived` / `accidental`. This
classification is the heart of the task; support every label with trace text.

## Step 2 — true-goal shapes

From game source, classify the true L1 completion condition of **all 25 games in `ref`**
(not just the ones that cleared) as prior-compatible ("clear/remove/fill all X"-shaped or visually
self-announcing) or not. Both directions matter: a **prior-compatible game that
stalled** weakens H unless its stall label says the block was mechanics, not goal —
check the label.

## Step 3 — the cross-tab

One table, one row per run game: S1 outcome (per arm) × true-goal prior-compatibility ×
primary stall cause (existing s1d labels; no re-labeling) × slice goal-channel outcome
(where the game is in the slice six). Call out the two anti-examples explicitly:

- **tu93** — S1's largest action budget (294 events), never cleared; yet the only game
  where the slice goal channel ever reasoned to a correct goal (colour-14 inertness).
- **m0r0** — stalled after 36 events; the game whose hidden state the slice channel
  identified 4/4.

> **Both figures corrected 2026-08-05, same lineage error.** They are `local` counts.
> In `ref`, tu93 clears L1 in **all three passes** (and L2 in two) and is never labelled
> `goal_unknown` — so it is a *concordance* case with the slice channel, not an
> anti-example. m0r0's 36 events is one local pass; in `ref` it stalls with
> `goal_unknown` at 206 and 219 actions and clears once, accidentally. m0r0 survives as
> the anti-example; tu93 does not. Details in results §3.

## Step 4 — verdict

State per-game support/refutation of H, then one verdict sentence. If refuted, the
refuting trace's discovery mechanism gets its own subsection (what evidence, what
reasoning move, how many actions it took). Close with ≤1 paragraph of implications for
the slice-2 goal channel — a recommendation, not a decision.

## Report

Append a results section to this note: (1) verified split + arm coverage table;
(2) per-clear classifications with quotes; (3) goal-shape table for all 18 games;
(4) the cross-tab; (5) verdict; (6) implications paragraph.

## Cautions

- Judgments (goal-shape classes, clear classifications) are adjudications by one reader —
  label them as such; counts and quotes are mechanical.
- Arms are heterogeneous: never pool cleared/stalled across prompt variants silently.
- No invented numbers; working values labelled (w).
- Concurrent agents share the tree: `git status` before committing, stage only files this
  task created (this note, the script, any small derived JSON in `logs/`).
- Read-only toward everything existing: modify no harness files, no stores, no notes but
  this one.

## Non-goals

No re-running S1, no model calls, no re-labeling of the stall corpus, no slice-2 design,
no game-source quotations anywhere in committed text.

## Estimate

3–5 h agent time (mostly step 1's close reading), zero compute.

---

# Results — 2026-08-05

Script: [`agent/harness/s1_contrast.py`](../agent/harness/s1_contrast.py)
(`split` · `clears` · `clearctx` · `goals` · `reason` · `window`). Zero model calls.
All tables below are script output; all classifications are adjudications by one reader
and are labelled as such.

## 0. Lineage correction — the note's premise was about the wrong corpus

**The task note's "Inputs" section is wrong about which runs are the reference stack, and
the whole 4-of-18 framing is an artefact of that.** Two corpora exist:

| corpus | dirs | stack | passes | model |
|---|---|---|---|---|
| **ref** | `logs/kaggle_v2`, `_v3`, `_v4` | duck-harness on Kaggle, vLLM **FP8**, reasoning parser on (`[THINKING]` blocks present in every turn) | 3 × 25 games = 75 | server-side, FP8 |
| **local** | `logs/runs/` (29 dirs) | local MLX replication, `taaf`/`inference` runner | 36 game-passes over 18 games | `Qwen3.6-27B-4bit` (28) and `-8bit` (8) |

`logs/runs/` is **not** the reference-stack lineage: `run_config.json` names local MLX 4-bit
and 8-bit weights, and `deploy_meta.json` gives `target_class: taaf.deploy_inline.InlineTarget`
on the laptop. The standing S1 `goal_unknown` result is keyed to the *ref* corpus — every
episode id in the labelling corpus is `kaggle_v{2,3,4}::<game>_p0::L<n>` (75 episodes, one per
game-pass, at the level where that pass stalled). So the note's working split describes the
local replication, not "the reference".

There is also `logs/kaggle-reference` (2026-07-26, the first duck-harness measurement): summary
only, **no event artefacts and no transcripts**, so it cannot enter step 1. It cleared L1 on two
further games (dc22, sc25) that never cleared in v2–v4 — see §3.

Everything below is reported for **both** corpora, ref first.

### Score semantics — verified

`level_completed == (score increment) == (level increment)` on **all 111 episodes** across both
corpora, 0 inconsistencies. Cross-checked against `viewer_data.json` for tn36/kaggle_v4
(`levels_completed: 1`, `final_score: 3.571…`) and against `per_game_analysis.json`. A score
increment is a level completion.

### The verified split (ref)

17 of 25 games cleared L1 in at least one of three passes; **42 of 75 passes** cleared L1
(5 also cleared L2). Never cleared in any pass: **cn04, dc22, g50t, ls20, sc25, sk48, tr87,
wa30**.

Per-game-pass L1 clears (action number of the clearing action):

| game | v2 | v3 | v4 | | game | v2 | v3 | v4 |
|---|---|---|---|---|---|---|---|---|
| ar25 | — | a133 | a112 | | s5i5 | — | a50 | a66 |
| bp35 | a48 | a41 | a115 | | sb26 | a9 | a16 | a10 |
| cd82 | — | a174 | a68 | | sc25 | — | — | — |
| cn04 | — | — | — | | sk48 | — | — | — |
| dc22 | — | — | — | | sp80 | a193 | a77 | a11 |
| ft09 | a17 | a31 | a17 | | su15 | a19 | a17 | a23 |
| g50t | — | — | — | | tn36 | — | — | a11 |
| ka59 | a34 | a30 | — | | tr87 | — | — | — |
| lf52 | a73 | — | a20 | | tu93 | a72 | a38 | a120 |
| lp85 | a8 | a14 | a8 | | vc33 | a15 | a10 | a7 |
| ls20 | — | — | — | | wa30 | — | — | — |
| m0r0 | — | a47 | — | | | | | |
| r11l | a78 | a19 | a13 | | | | | |
| re86 | a27 | a34 | a22 | | | | | |

Arm coverage is even here: three passes per game, one configuration per run directory
(`kaggle_v2/v3/v4`), never pooled silently below.

### The verified split (local) — the note's numbers reproduce

4 games cleared, 14 stalled at 0, 18 games run, passes uneven (1–4 per game). Reproduced
exactly as the note states: **ar25 (a30, arm `s1e-a6c1-c11`), sp80 (a26, `s1e-8bit-c07`),
tn36 (a11, `s1e-8bit-c01`), vc33 (a8, `s1e-8bit-c05`)** — max score 1 each. Arms are
heterogeneous (`a6c1`, `8bit`, `kb2`, `c2`, `d13c2`, `l2c2`); the four clears fall in three
different arms and three of the four are the 8-bit arm. Seven public games never ran locally
(cd82, dc22, s5i5, sb26, sc25, sk48, su15).

The note's tu93 figure checks out as a pooled count: 175 + 119 = 294 events over two local
passes.

## 1. Per-clear classification (step 1)

Method: for each clearing action the script prints three turns — **PRIOR** (last transcript
before the clear), **ISSUER** (the turn whose tool call fired it; the action event is logged
*before* the transcript that produced it — verified on vc33/v4 and sp80/v4), and **REACT**
(how the model read the completion). All 42 ref first-clears and all 4 local clears were read.
Quotes are from S1's own traces.

> **Corrected twice, 2026-08-05. Read the adjudication rule below before using these
> numbers.** Pass 1 used `clearctx` with a 1700-char cap applied to the *whole* turn, which
> truncated the `[ASSISTANT]` block — the one place a turn states its World/Goal/Plan. Pass 2
> (after the full ft09/sb26 read, §6) reclassified 5. Pass 3 re-verified **all 40 remaining
> clears** with the ISSUER turn untruncated **and the PRIOR turn's `[ASSISTANT]` block added**,
> because a goal is often stated one turn before the batch that executes it; that reclassified
> 6 more. Every correction moved in the same direction — `accidental` → deliberate. The cheap
> three-turn read has a **systematic bias against detecting articulation**, and any label in
> this table that has not survived pass 3 should be assumed to under-report it.

**Adjudication rule** (needed once the boundary cases dominate; applied uniformly in pass 3):

- `prior-match` — a goal was stated **before** the clearing action (in the ISSUER turn or an
  earlier one), the clearing action was taken **in service of it**, and the goal shape is a
  default prior. An inexact estimate of the *end state* does not disqualify: what matters is
  that the action was goal-directed and the goal approximately right.
- `evidence-derived` — as above, but the goal was inferred from in-context evidence rather
  than supplied by the prior.
- `accidental` — no goal stated, **or** the clearing action was an explicit probe ("let me
  see what happens"), **or** the goal pursued was not the condition that actually fired.

**Ref corpus, 42 first-clears (all L1):**

| class | n | share | pass 3 | pass 2 | pass 1 |
|---|---:|---:|---:|---:|---:|
| `prior-match` | 26 | 62% | 25 | 21 | 17 |
| `accidental` | 10 | 24% | 11 | 15 | 20 |
| `evidence-derived` | 6 | 14% | 6 | 6 | 5 |

`accidental` — r11l/v2, sp80/v2, bp35/v3, cd82/v3, lp85/v3, r11l/v3, cd82/v4,
lp85/v4, sp80/v4, tn36/v4.
`prior-match` — bp35/v2, ka59/v2, lp85/v2, lf52/v2, re86/v2, su15/v2, tu93/v2, vc33/v2,
ar25/v3, ka59/v3, m0r0/v3, re86/v3, **s5i5/v3**, sp80/v3, su15/v3, tu93/v3, vc33/v3, ar25/v4,
bp35/v4, lf52/v4, re86/v4, r11l/v4, s5i5/v4, su15/v4, tu93/v4, vc33/v4.
`evidence-derived` — ft09/v2, ft09/v3, ft09/v4, sb26/v2, sb26/v3, sb26/v4.
(Bold = reclassified in pass 4. Pass 3: lf52/v2, vc33/v2, ar25/v3, ar25/v4 + ar25/local,
sp80/local. Pass 2: lp85/v2, re86/v2, m0r0/v3, r11l/v4, ft09/v3.)

**ft09 and sb26 are 3/3 each** — every pass of both games reaches the goal by inference, with
no exceptions. That is what makes the two games worth the M-phase's attention.

**Local corpus, 4 clears** (also re-verified in pass 3): ar25, vc33, sp80 `prior-match`;
tn36 `accidental`. ar25 and sp80 were `accidental` before pass 3.

### Pass 4 — closing the "goal stated 3+ turns back" hole

Pass 3 left one hole: it read only PRIOR+ISSUER, so a goal committed earlier and still in
force at the clear would be invisible. Reading all 40 remaining clears end-to-end was not
affordable (2.06M chars of model reasoning); what was done instead:

1. **9 episodes read in full** — su15/v2, su15/v3, re86/v3, re86/v4, sp80/v4, vc33/v4,
   tn36/local, r11l/v3, s5i5/v3. **Eight confirmed pass 3 unchanged; one changed.**
2. **A complete mechanical scan of the hole across all 40** — every pre-clear turn *except*
   the PRIOR turn, matched for goal-commitment language, then hand-read. This covers exactly
   what pass 3 could not see, for every episode, with no sampling.

The scan's main result is itself a finding: **early turns contain goal *questions*, not goal
*commitments*.** The overwhelming majority of hits are "let me think about what the goal might
be", "Goal model: Unknown", "maybe the goal is…" — the model reliably flags goal uncertainty
and rarely commits early. Only two `accidental` episodes contained a committed early goal:

- **r11l/v3 — confirmed `accidental`.** It does commit early ("Goal model: Navigate the agent
  from the ring position to the dark gray square destination … by clicking on intermediate
  waypoints") but then discovers the objects merely swap — "This is a loop! I'm going in
  circles" — clicks the ring to reset the board, and restarts exploration from scratch. The
  goal in force at the clear is not that one. **An abandoned goal does not count**, which is
  the rule's intent and is now stated.
- **s5i5/v3 — reclassified to `prior-match`.** This one is a real miss, and of the most
  expensive kind: the model fits a linear model to observed states —
  `tracker_col = 28 + (value-5)/3` — checks it against three measured bar values, solves it
  for the red cross's column, gets a required bar value of 77, computes the click counts
  ("Increase green from 32 to 77: 5 more clicks … yellow from 23 to 77: 6 more clicks … that's
  11 clicks total. Let me batch them"), and clears on the last click of the batch. The ISSUER
  turn opens with "Let me check if the green bar changed when clicking at max value", which is
  why the cheap read filed it as a probe.

Final counts are in the table above. **Coverage is not uniform and should not be reported as
such:** 15 of 46 clears (ft09 ×3, sb26 ×3, plus the 9 above) have been read end-to-end; the
other 31 rest on untruncated PRIOR+ISSUER plus the complete early-goal scan. The residual risk
is now narrow — a goal committed early, never restated, and executed by a turn whose own text
reads as a probe — and s5i5/v3 was exactly that case, so the risk is real but bounded to
episodes the scan already cleared by hand.

**What pass 3 found, by case.** Two kinds of miss:

- *Goal stated in the PRIOR turn, executed by the ISSUER.* **vc33/v2** — PRIOR: "The goal
  likely involves positioning the shape to align with the yellow gap in the black bar (cols
  38-39). Plan: Move the shape all the way left"; the ISSUER turn then only says "Let me check
  the current state after 5 left clicks." Reading the ISSUER alone makes a deliberate clear
  look blind. **lf52/v2** and **sp80/local** are the same shape.
- *Computed multi-action plans that land exactly, invisible because the batch precedes its
  own transcript.* **ar25/v4** derives two different mirror-sum formulas by fitting observed
  face→P positions, solves for the face column that puts P on top of Γ, computes "move LEFT by
  6", and clears on the 6th of 6. **ar25/local** derives that LEFT/RIGHT are inverted, computes
  "6 LEFT + 10 DOWN", and clears on the 16th of 16. Both were filed `accidental`.

### `accidental` — the model did not know what it had done

The purest case is **sp80/kaggle_v4**, cleared in 11 actions (the fastest clear on that game;
the same game took v2 193 actions). The ISSUER turn states no goal at all:

> "Maybe the goal is to use the yellow blocks as platforms or to move them into position. Or
> maybe SPACE triggers some kind of interaction. Let me try SPACE."

and the REACT turn learns the outcome from the frame, not from a prediction:

> "SPACE triggered a level transition! The scene completely changed. Level 1 was completed by
> pressing SPACE."

> **ar25/kaggle_v3 was used here as a second example and is withdrawn (pass 3).** I wrote that
> it "completes on move 1 of 16" of its stated plan, making the stated mechanism impossible.
> That was a miscount: the batch ran a127–a133, i.e. it cleared on **move 7 of 16**, the batch
> being cut short by the completion itself. The goal ("make the F overlap the yellow L") was
> stated before the action, the LEFT moves were taken in service of it, and it advanced the
> level — only the end-state estimate was long. Under the rule above that is `prior-match`,
> and it has been moved. What survives is the narrower point that its REACT turn still
> over-claims ("The key was to move the F to overlap with the yellow L" — the overlap was
> never reached), which is why **REACT turns are not counted as articulation anywhere in this
> table**.

**cd82/kaggle_v4** is the same failure in the other direction: the plan was to stamp white over
the top half to reproduce a half/half reference, and the stamp filled the *whole* block, which
is what actually completes L1. The model concedes it in REACT: "the white center stamp filled
the entire target block with white, which completed the level."

**lf52/kaggle_v2** clears while the model believes it is three steps from the goal — ISSUER:
"Started with 5 crosses, now 3 remain … Need to repeat pattern 3 more times to activate all
crosses. Level completes when all crosses activated." It completed at 3 remaining.

**tn36/kaggle_v4** (and identically tn36 in the local 8-bit arm) cleared while the model was
debugging its own node-selection code, not pursuing a goal: "I keep clicking the top blue timer
bar. Need to specifically target the bottom blue blob."

### `prior-match` — an articulated goal, taken from the default prior, that happened to be right

Four prior shapes cover all 17: **avatar→salient target** (bp35, su15, tu93), **put every X
into/onto its Y** (ka59, s5i5, lf52/v4), **collect/remove all X** (re86), **align the two
matching objects** (vc33, sp80/v3).

**vc33/kaggle_v4** is the cleanest: 4 probing actions, then the goal is stated and a 3-click
plan executed, and the third click clears.

> "If the goal is to align the yellow bar with the yellow gap, I need to move the yellow bar
> LEFT by 12 columns … each click of the bottom blue square moves 4 columns left, I'd need 3
> clicks."

Note what the derivation rests on: both objects are yellow. The mechanics (blue squares shift
by 4) were genuinely learned from the trace; the *goal* was a colour-pairing prior. Nothing in
the trace was evidence about the win condition. The same hypothesis, stated in the same words,
appears in vc33/kaggle_v3 and in the local 8-bit pass:

> "Goal model: Move the moving yellow block from cols 50-51 to cols 38-39 by clicking bottom
> blue 3 times (each shifts left by 4)." — vc33, `s1e-8bit-c05`

**tu93** (all three passes) is the strongest prior-match: the model parses the maze, learns the
2-cell-jump slide rule from failed moves, runs BFS to the green tile and executes the path.
Real mechanics work, entirely conventional goal ("reach the goal at (10, 10)").

**bp35/kaggle_v4**: "Now I can move the player LEFT to reach the pink cross! Let me try that."
— one action, clear. The true L1 condition is a horizontal move entering the gem cell.

**sp80/kaggle_v3** is the hardest call in this group and is classified `prior-match` with the
alternative reading recorded. After exhausting every probe the model enumerates geometric
relations and picks one:

> "What if the blue block needs to be at a position where it's EQUALLY DISTANT from two objects
> … the midpoint between them is col 34 … 3 RIGHT moves from initial position gives cols 24-43."

It executes the plan and it clears. This is hypothesis-driven and confirmed — but the
hypothesis came from a prior over goal shapes selected by exhaustive search, not from evidence
in the trace, so it does not count as discovery. Corroborating: v4 reached the *same* blue
position (cols 24-43) by wandering and cleared on a blind SPACE.

**Efficiency split** (actions before the goal statement / after it), for the clears where the
articulating turn is unambiguous: vc33/v4 4/3 · vc33/v3 9/1 · vc33 local 7/1 · bp35/v4 114/1 ·
ka59/v3 29/1. Within `prior-match` the pattern is uniform: near-all actions precede
articulation, and the clear follows within 1–3 actions of it. Where a prior-shaped goal is
stated, it converts almost immediately; the cost is entirely in the undirected phase before it.

> **Corrected 2026-08-05.** This paragraph originally also gave sb26/v2 as 8/1 and ft09/v2 as
> 14/3, and generalised the pattern to the `evidence-derived` class. Both figures were wrong
> and the generalisation does not hold — sb26/v2 is **0 before / 9 after** (the goal is stated
> before the first action) and ft09/v2's goal is fixed at ~action 5, about ten actions before
> the clear. See §6.

### `evidence-derived` — the two games where the model read a goal off the board

Only two games produce this class, both 3/3, and both display the target. **Summarised here;
the full six-episode read and its corrections are §6, which supersedes any timing claim in
this subsection's first version.**

**ft09** (all three passes) decodes an on-board encoding. It treats the grid centre
decorations as a specification rather than decoration —

> "Maybe these patterns represent the 3x3 grid pattern itself! The 6x6 center could be a
> scaled-up version of the 3x3 grid, where each cell is 2x2 pixels."

— verifies the mapping against three grids it can check, and reads the target off the fourth:

> "The center cell decorations encode the grid pattern! Each 2x2 block in the 6x6 center maps
> to one cell in the 3x3 grid (gg=blue, WW=red, RR=red). Goal model: The bottom-right center
> cell encodes the TARGET pattern: R b b / R R R / R b b" — ft09/v3, the turn that cleared

It then clicks exactly the cells the decode names. Same route, same intermediate reasoning, in
three independent passes (v2 a17, v3 a31, v4 a17).

**sb26** (all three passes) infers the goal from static layout **before taking any action**:

> "Hypothesis: drag bottom colors to match top order into gray slots. Top order: b, N, Y, p.
> Need to place: blue at col22, green at col28, yellow at col34, purple at col40"
> — sb26/v2, analysis step 1, action count 0

and then, once the board matches, reasons that the state must be *committed*:

> "All 4 slots filled correctly (blue, green, yellow, purple) matching the top pattern. Level
> not yet completed - need to submit. Plan: Press SPACE to submit the solution."

That last step — "the board is right but the level has not advanced, therefore an explicit
commit action is required" — is the only place in 46 clears where the model reasons about the
*win predicate* rather than about the board.

## 2. True L1 goal shapes (step 2)

Source: `logs/s2_goal_predicates.json` / `_labelled.json` (25/25 games, advance-site predicates
extracted from game source and labelled), paraphrased here — no source text is quoted, per
PUBLISHING.md. "Prior-compatible" (P) means the true condition is reachable by pursuing one of
the default goal shapes the model brings: avatar→goal co-location · every X onto/into its Y ·
clear/collect all X · copy a displayed template · align two matching objects. N means it needs
an unadvertised relation.

**Caveat, load-bearing:** the s2 extraction is of the *advance-site* predicate, which is
level-generic. Several N games have an L1 instance that degenerates into something simpler.
Where a trace settles it, that is noted.

| game | true condition (paraphrase) | class |
|---|---|---|
| ar25 | every target cell covered by the movable set **plus its mirror images** across mirror axes | N |
| bp35 | a horizontal move / resolved fall enters the gem cell | P |
| cd82 | edited sprite equals the displayed reference off both diagonals | P |
| cn04 | every marker pixel paired rotation-aware with another sprite's marker | N |
| dc22 | avatar co-located with the goal sprite (needs support underfoot) | P |
| ft09 | every clue's same/different 3×3 template satisfied by its 8 neighbours | P− |
| g50t | avatar stands on the exit | P |
| ka59 | every container has a block nested exactly inside it | P |
| lf52 | undetermined from the extracted evidence (win() call site not captured) | ? |
| lp85 | every object of each type on its type-matched goal cell | P |
| ls20 | avatar co-located with each goal tile **and** its mutable (shape, colour, rotation) triple matches | N |
| m0r0 | all mirror-linked movers paired off (active-mover count → 0) | P− |
| r11l | each piece dragged onto its own identity-matched target | P |
| re86 | flood-fill regions to reproduce the displayed overlay template | P |
| s5i5 | every target has a matching sprite at exactly the same (x, y) | P |
| sb26 | an edited instruction **program** reproduces an ordered target strip | N |
| sc25 | avatar walks into the exit | P |
| sk48 | paired lanes' colour sequences equal index-by-index | N |
| sp80 | a committed spill simulation fills every receptacle, no hazard contact | N |
| su15 | **exact counts** of each object kind inside goal zones | N |
| tn36 | right-hand object's pose exactly equals its displayed ghost target | P |
| tr87 | rotated output row equals the rule-table translation of the input row | N |
| tu93 | every surviving mover at an exit sprite | P |
| vc33 | every falling item matched by a colour-and-column-matching receptacle | P |
| wa30 | every box delivered onto a goal-pad cell and released | P |

15 P (incl. 2 P−), 9 N, 1 undetermined.

## 3. Cross-tab (step 3)

Ref corpus, one row per game. "cleared" = passes clearing L1 of 3. Stall label = s1d
`primary_label` per pass, at the level where that pass stopped (no re-labelling).

| game | goal class | cleared | clear classes | stall labels (v2/v3/v4) | slice goal channel |
|---|---|---|---|---|---|
| ar25 | N | 2/3 | acc, acc | goal_unknown L1 / goal_unknown L2 / action_semantics L2 | — |
| bp35 | P | 3/3 | prior, acc, prior | goal_unknown / action_semantics / goal_unknown (all L2) | — |
| cd82 | P | 2/3 | acc, acc | goal_unknown L1 / action_semantics L2 / action_semantics L2 | — |
| **cn04** | N | 0/3 | — | goal_unknown ×3, all L1 | — |
| **dc22** | **P** | **0/3** | — | **goal_unknown ×3, all L1** | 0/2 correct |
| ft09 | P− | 3/3 | **evid**, acc, **evid** | latency L3 / latency L3 / exploration L2 | 0/2 correct |
| g50t | P | 0/3 | — | latency / exploration / hidden_state, all L1 | — |
| ka59 | P | 2/3 | prior, prior | goal_unknown L2 / action_semantics L2 / goal_unknown L1 | — |
| lf52 | ? | 2/3 | acc, prior | goal_unknown L2 / goal_unknown L1 / goal_unknown L2 | — |
| lp85 | P | 3/3 | acc ×3 | goal_unknown ×3, all L2 | — |
| **ls20** | N | 0/3 | — | goal_unknown / goal_unknown / action_semantics, all L1 | 0/2 correct |
| **m0r0** | P− | 1/3 | acc | goal_unknown L1 / goal_unknown L2 / goal_unknown L1 | 1 partial / 1 wrong |
| r11l | P | 3/3 | acc ×3 | goal_unknown L2 / action_semantics L2 / latency L2 | — |
| re86 | P | 3/3 | acc, prior, prior | goal_unknown L3 ×2 / action_semantics L3 | — |
| s5i5 | P | 2/3 | acc, prior | goal_unknown L1 / goal_unknown L2 / latency L2 | — |
| sb26 | **N** | 3/3 | **evid ×3** | goal_unknown L2 / exploration L2 ×2 | — |
| **sc25** | **P** | **0/3** | — | **goal_unknown ×3, all L1** | — |
| sk48 | N | 0/3 | — | action_semantics ×2 / goal_unknown, all L1 | — |
| sp80 | **N** | 3/3 | acc, prior, acc | progress_signal L2 / goal_unknown L2 / action_semantics L2 | — |
| su15 | **N** | 3/3 | prior ×3 | goal_unknown L2 ×2 / irreversible L2 | — |
| tn36 | P | 1/3 | acc | goal_unknown L1 ×2 / latency L2 | — |
| tr87 | N | 0/3 | — | goal_unknown / latency / goal_unknown, all L1 | — |
| **tu93** | P | **3/3** | prior ×3 | action_semantics L3 / latency L3 / action_semantics L2 | **2/2 correct** |
| vc33 | P | 3/3 | acc, prior, prior | goal_unknown ×3, all L2 | 0/2 correct |
| wa30 | P | 0/3 | — | action_semantics ×2 / latency, all L1 | — |

### The two anti-examples named in the note both invert

**tu93** — the note calls it "S1's largest action budget, never cleared." That is true of the
*local* corpus (294 pooled events over two passes, no clear). On the reference stack tu93 is
one of S1's **best** games: L1 cleared in all three passes and L2 in two, by BFS to the exit
tile, and every stall label is `action_semantics`/`latency` at L2–L3 — never `goal_unknown`.
The slice goal channel independently reasoned to the same condition (movers onto the colour-14
exit tile, the only correct goal inference in that corpus). tu93 is therefore a **concordance**
case, not an anti-example: the two harnesses agree, and they agree on the game whose goal is
the most prior-compatible in the set.

**m0r0** — survives as an anti-example, but the correction in §1 sharpens it in the opposite
direction to what was first reported. The deployed agent stalled in 2 of 3 passes with
`goal_unknown` primary at 206 and 219 actions (baseline 30). The one clear (v3, a47) was first
labelled `accidental` on a truncated turn; read untruncated it is **`prior-match` and fully
deliberate** —

> "World model updated: RIGHT moves left eye RIGHT and right eye LEFT (towards each other).
> LEFT moves them apart. … Plan: Send RIGHT twice to bring eyes to same columns (34-38), then
> UP to bring right eye to head."

— which is the mirror-linked movement rule learned from evidence, aimed at bringing the two
movers together, i.e. m0r0's actual advance condition (movers paired off). So m0r0's model
*did* solve it once, on purpose, and then failed the same game twice at 7× the human baseline.
Meanwhile the slice channel identified m0r0's hidden state 4/4 and got the goal only
*partially*. The anti-example is therefore about **reproducibility, not capability**: the same
model on the same game finds the mechanism in one pass out of three and never recovers it in
the other two.

### The cases that decide H

- **Prior-compatible and still stalled on goals**: **dc22** and **sc25** are the two most
  prior-compatible conditions in the whole set — walk the avatar into the exit — and S1 scored
  **zero on all three passes of each**, with `goal_unknown` primary on all six episodes. The
  label rules out "it knew the goal but couldn't act". g50t is a third avatar-to-exit game with
  0/3, but its labels are mechanics (`latency`, `exploration`, `hidden_state`), so it does not
  bear on H. wa30 likewise (`action_semantics` ×2).
- **Not prior-compatible and cleared anyway**: **sb26** 3/3, **sp80** 3/3, **su15** 3/3,
  **ar25** 2/3. Four of the nine N games clear L1 reliably. For sp80/su15/ar25 the L1 instance
  plausibly degenerates (their L1 clears are `accidental` or search-selected, consistent with
  "L1 is a tutorial"), but **sb26 does not degenerate away** — its three clears are the
  `evidence-derived` class, produced by reading the reference strip and reasoning that a commit
  action was needed.

## 4. Verdict

**H is refuted, in both directions, and by a wide margin.**

Per-game support/refutation of "the cleared set is exactly the set where the default prior
matches the true goal":

- **Supports H** (cleared, prior-compatible, clear driven by that prior): bp35, ka59, re86,
  s5i5, tu93, vc33, lf52, su15, m0r0 — 9 games.
- **Refutes H, direction 1** (prior-compatible, never cleared, stall labelled `goal_unknown`):
  **dc22, sc25** — 2 games, 6 episodes. The prior applies and does not fire.
- **Refutes H, direction 2** (not prior-compatible, cleared reliably): **sb26** (3/3, via
  evidence-derived goal inference), and more weakly sp80, su15, ar25 (3/3, 3/3, 2/3 — but
  after pass 3 most of those clears are deliberate rather than accidental, which *strengthens*
  this direction; their L1 instances may still degenerate).
- **Refutes the stronger claim inside H** ("the reference never discovers goals"): **ft09** and
  **sb26** contain genuine in-context goal discovery, reproducibly, across independent passes.
- **Neither** (cleared by accident on prior-compatible games, i.e. the prior was not the
  mechanism): cd82 2/2, lp85 2/3, r11l 2/3, tn36 1/1.

The single-sentence verdict: **the reference does not "never discover goals, occasionally get
one for free" — it does all three things (62% of its clears are the default prior firing
correctly, 24% are accidental, 14% are real in-context goal discovery), and, decisively, the
default prior fails to fire on the two games where it most obviously applies, so "where the
prior fails" does not define the target set.**

> **The four classification passes moved the numbers a long way and only in one direction**
> (accidental 20 → 15 → 11 → 10 of 42, converging). H is refuted more firmly at each pass, because the
> "occasionally gets one for free" half of it looks worse the more carefully the clears are
> read: most clears are deliberate. But the direction-1 refutation — dc22 and sc25 — is the
> load-bearing one and is untouched by any of this: it rests on stall labels and zero scores,
> not on reading clears.

### The refuting mechanism (required subsection): ft09 and sb26

> **Substantially revised 2026-08-05 by the full read (§6).** The first version of this
> subsection claimed both discoveries were *triggered by negative evidence* and that ft09's
> switch cost "14 actions before, 3 after". Both are wrong. sb26 states the correct goal
> before its first action, with no negative evidence of any kind, in all three passes; ft09
> fixes its goal at ~action 5 and then cannot act on it for ten more actions. The corrected
> account follows.

Both games share one move, and it is the move nothing else in the corpus makes: **the model
stops treating an on-board object as scenery and starts treating it as a specification.** What
differs is when, and what the remaining cost is.

*sb26 — specification read from static layout, zero actions in.* At analysis step 1, before
touching anything, the model notices the top strip and the bottom palette hold the same four
colours in different orders, and infers that the strip is the target and the palette the
supply. It emits the full assignment (which colour to which slot) as its first output. All
three passes do this; none needs a probe. Cost: **0 actions before articulation, 9–10 after**
(v2 cleared in 9, v4 in 10 with one wasted SPACE probe). This is the cheapest clear in the
corpus and the only goal in it that was correct before any interaction.

*ft09 — specification decoded from an encoding, then stranded.* The encoding hypothesis appears
at analysis step 5, after only four null clicks, and the mapping is verified against the three
grids whose answer is checkable. By analysis step 12 the model has decoded the target exactly
and written it down. **It then spends ten more actions unable to act on it**, because it cannot
find which element is clickable. What finally unblocks it is not a goal insight at all — it is
bookkeeping: the model prints its own action history, reads the list, and notices a gap.

> "13 clicks, all no change. I've tried clicking on red cells, center cells, borders,
> background, corner pieces, and the orange bar. **I have NOT tried clicking on the blue cells
> in the bottom-right grid.**" — ft09/v2, the turn that cleared

So ft09 splits cleanly into two failures with different causes: the goal was solved early and
cheaply; the **action model** cost ten actions and was solved by exhaustive coverage
bookkeeping, not by reasoning.

Three properties matter for the M phase, and they are not the ones first reported.

1. **Goal inference did not need pressure.** sb26 needed no evidence at all; ft09 needed four
   null clicks. Neither is the "accumulate failure until the model re-specifies" story. The
   trigger for treating an object as a specification was the object's *form* — a strip of
   distinct colours, a small patterned cell inside every grid — not the failure history.
2. **Knowing the goal is not the same as being able to pursue it.** ft09 held a correct,
   written-down target for ten actions while flailing on action semantics. A goal channel that
   emits correct predicates buys nothing unless the action model can be interrogated in the
   same breath. This is the single most transferable finding in the read.
3. **The cheapest fix in either trace was a coverage ledger.** ft09's unblock was "print what
   I have tried, find the gap" — mechanical, no model insight, and it is exactly the kind of
   state a store maintains for free and a per-turn actor forgets.

### What the discovery costs later: L1 success anchors and then traps

The full read covered these games past L1, and this is the finding with the largest
implication. **sb26 never cleared L2 in any pass** (156, 252, 203 actions; baselines 28).
Its L2 condition is an ordered instruction *program* run by ACTION5 — a different kind of
object from L1's fill-the-slots. All three passes carried the L1 schema forward unchanged
("arrange the colours, then SPACE to submit") and burned their entire budget enumerating
*orderings* within it — top-row order, bottom-row order, warm/cool split, reverse order,
rainbow/hue order:

> "New hypothesis: rainbow/hue order split - Red=[R, O, Y], Green=[N, b, p, M]"
> — sb26/v2 at action 156, still searching orderings

The L1 discovery fixed the goal *schema* and the model never questioned the schema again, only
its parameters. ft09 shows both outcomes of the same anchoring: v2 and v3 carried the
encode/decode scheme into L2, hit a contradiction ("This matches my decoded pattern, but the
level is not complete. So my pattern decoding is wrong"), **re-derived the encoding** and
cleared L2. v4 instead lost the channel, concluded only two cells were toggleable, and spent
its remaining budget on a 16-state brute force, timing out at state 15 of 16.

The distinguishing move in the passes that recovered is explicit: *the decode was treated as
falsifiable and refuted by the level not advancing.* That is the same discrimination sb26 never
made at L2 and the same one §5 recommends scoring for.

## 5. Implications for the slice-2 goal channel (recommendation, not a decision)

The autopsy's goal-channel result (2 right / 8 wrong, both right on tu93) and the deployed
bottleneck are **not** one mechanism, which is what H would have made them. The cross-tab
separates them: tu93 is prior-compatible and both harnesses get it; dc22, sc25 and vc33 are
prior-compatible and the *deployed* agent fails on them while the slice channel also fails on
dc22 and vc33; m0r0 splits (hidden state 4/4, goal partial). The common factor in the failures
is not "the prior didn't match" but that neither harness ever tries to *specify* the win
condition — the one exception being ft09/sb26, where the specification was printed on the
board. So I would score the slice-2 goal channel not on whether the emitted goal is correct but
on whether it commits to a **falsifiable predicate plus the probe that would refute it**.

> **Revised 2026-08-05 by the full read.** This paragraph originally also recommended seeding
> the channel with "the ft09/sb26 trigger" — a run of null-effect actions, or a board that
> looks solved but did not advance. **There is no such trigger.** sb26 infers its goal before
> acting, and ft09's decode starts after four null clicks and is complete ten actions before it
> can be used. Seeding on accumulated failure would have produced neither discovery. Three
> replacements, in order of how much the read supports them:
>
> 1. **Score the goal channel and the action channel jointly, not separately.** ft09's ten
>    stranded actions are the whole cost of that episode, and they are invisible to any metric
>    that only asks whether the emitted goal is right. A cell that emits a correct predicate
>    and no way to test it should score at or near zero.
> 2. **Score re-specification under contradiction, not first-shot correctness.** The passes
>    that cleared ft09's L2 are the ones that treated their own decode as refuted when the
>    level did not advance; sb26 never did this at L2 and lost 156–252 actions per pass inside
>    a schema it never re-opened. This is the sharpest measurable difference in the corpus and
>    it is a *second-goal* property, invisible at L1.
> 3. **Give the channel a coverage ledger.** ft09's actual unblock was reading back its own
>    action history and finding an untried target class. That is cheap, mechanical, and the
>    kind of state the accumulated store already holds.
>
> The reverse risk in the original still stands and is now better supported: dc22 and sc25 say
> a prior-compatible goal is not self-executing, so a channel gated on visible prior-failure
> will still miss them.

## 6. Full read of the ft09 and sb26 traces (2026-08-05)

Requested after the classification pass, because these six episodes are the only observed
instances of the capability the M phase has to reproduce. **What was read in full:** all six
L1 episodes (ft09 v2/v3/v4, sb26 v2/v3/v4) — every analysis turn, tool call and result from
RESET to the L1 clear, ~305k chars. **What was read selectively:** the L2/L3 continuations
(~1.3M chars) — sb26's three L2 stalls sampled at entry, mid-search and terminal turns; ft09's
L2 sampled at the decode-transfer turns, v2's L2 clear, and v4's terminal brute-force. Nothing
below rests on an unread turn, but the L2 characterisations are from samples, not a full pass.

Four things the full read changed, all now folded into the sections above:

1. **Five of 42 clears were misclassified** because the reporting script truncated the
   `[ASSISTANT]` block that states each turn's goal (§1). Corrected counts: prior-match 21,
   accidental 15, evidence-derived 6. ft09 and sb26 are 3/3 each. Script fixed.
2. **ft09's goal is solved early, not late** (§4). Encoding hypothesis at analysis step 5,
   target decoded by step 12, clear at action 17 — the gap is action semantics, and it closes
   on a coverage ledger, not an insight.
3. **sb26's goal is solved at step 1 with zero actions** (§4), in all three passes. There is
   no failure-pressure trigger for goal inference in either game — the claim that there was is
   retracted in §4 and §5.
4. **L1 discovery anchors and then traps** (§4, new subsection). sb26 carried its L1 schema
   into L2 and burned every pass inside it; ft09 v2/v3 re-derived under contradiction and
   cleared L2, v4 did not and brute-forced. This is the highest-value finding for the M phase
   and it is only visible past L1 — which is exactly the scope the first pass excluded.

**Reading note for anyone re-running this.** Post-hoc REACT turns are unreliable (§1), and
`[ASSISTANT]` blocks must never be truncated. Both failure modes bit this analysis; the second
one produced wrong numbers that survived a commit.

## Deviations from the task note

1. **Corpus.** Step 0's lineage check failed against the note's own inputs, so both corpora were
   analysed rather than only `logs/runs/`. The ref corpus carries the analysis; the local split
   is reported and reproduces the note's numbers exactly.
2. **Scope of step 1.** 42 ref clears + 4 local clears were read, not 4 — the positive set is
   an order of magnitude larger on the correct corpus. Four passes: (1) three diagnostic
   turns, truncated; (2) ft09 and sb26 read end-to-end (§6), 5 labels corrected; (3) all 40
   remaining clears re-verified with untruncated ISSUER **and** PRIOR `[ASSISTANT]` blocks,
   6 more corrected; (4) 9 more read end-to-end, plus a complete mechanical scan of every
   pre-clear turn in all 40 for committed early goals, 1 more corrected (§6, "Pass 4").
   **15 of 46 clears have been read end-to-end; the other 31 rest on untruncated
   PRIOR+ISSUER plus the pass-4 scan.** Do not describe the set as fully read.
3. `logs/kaggle-reference` could not enter step 1 (no transcripts) and is reported for context
   only.
4. Step 2 used the existing `s2_goal_predicates_labelled.json` extraction rather than re-reading
   game source; its level-generic caveat is flagged in §2 and again in §4.
