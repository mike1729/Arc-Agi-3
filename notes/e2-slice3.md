# E2 slice 3 — the maximal-context 3.6 night: a deduplicated, object-linked causal record

**2026-08-05. Design + build spec + run protocol. One GPU night, operator-requested:
the last 3.6 experiment. Revised after external review** (`f2564e6` → this) — the first
draft spent its budget on repeated full frames and underspecified the two most
diagnostic exhibits; the review's redesign is adopted almost entirely, with the token
arithmetic corrected and one addition the review could not have known was needed.

The question, stated so either answer closes it: **given the best evidence record this
system can assemble, do any of the three channels beat their controls on Qwen3.6?**
Controls, scoring, and the pre-committed bar are slice 2's, unchanged.

## What the review corrected, verified before adopting

1. **Token arithmetic was wrong in the first draft.** I counted the digest (12.7k),
   not the templated prompt. Measured today on the real slice-2 trace: **dc22's full
   templated prompt = 19,396 tokens** (48,721 chars). The review's 19,405 is right.
   The old plan's ~28k frame section would have landed at ~47.4k with ~2.6k of slack —
   and the FB turn (prior answer + counterexample) does not fit in that.
2. **"Full ascii boards are proven readable" was too strong.** The reference harness
   (`logs/kaggle_v4/prompts/`) supplied an *image*, a segmentation object, and a Python
   tool, and its own instructions say: *use segmentation as the primary view; use ascii
   only to read a small specific region; never scan the whole board with it*. The
   evidence supports **entity tables + targeted crops**, not three or four full 64×64
   text renders. Adopted.
3. **The refuter request is logically malformed** (`e2_slice.py` §A): it asks for "the
   single observation that would falsify your predicate", and scoring counts a refuter
   *already satisfied by the store* as self-refutation. For a completion condition G,
   the discriminating observations are **G true ∧ level did not advance**, or
   **completion ∧ G false** — a bare predicate being true somewhere refutes nothing.
   So slice 2's "self-refuting 10/16" measured a broken instrument, not calibration.
   **Recorded as a slice-2 erratum** below and fixed here.
4. **The prompt anchors the vocabulary channel** — it names `clicked_adjacent_to:C` as
   the previous success (`e2_slice.py:841`), and slice 2 duly re-proposed it. Removed.
5. **`_Objects` has no persistent IDs, shape hashes, containment or tracking** —
   verified: it is a per-grid colour→components cache with cells and bbox only. The
   entity map therefore needs a **real tracking layer**, which is now a build item, not
   an assumption.

**And the one the review could not know:** its highest-value item — a real completion
transition with its animation frames and the next-level frame — **cannot be built from
the frozen store.** Verified: sp80's and lf52's completing rows have no post frame in
`states.json`, and the engine returned **20 and 27 frames** at the completing action of
which only the *count* was kept. The system has never retained a single completion
frame. It is recoverable, cheaply: the prefix repair gives verified walked routes for
all 24 games and the engine is deterministic, so **re-executing the completion route
live and capturing everything the engine returns** is a small day task (build item 0).
Without it, slice 3 would again ask the model what winning looks like while never
having looked itself.

## Provenance discipline (applies to every section)

Every block is tagged **OBSERVED** (recorded frames/actions), **REPLAY-VERIFIED**
(re-executed today and confirmed), or **MINER-INFERRED** (rules, effect classes,
failure typing). Slice 2 blurred these, so a mined majority rule read as ground truth.
The prompt states the distinction once, in one sentence, and every section header
carries its tag.

## The record (arm F) — allocation to a ≤ 50k templated prompt

Worst case is dc22; sparse games (sp80) land far lower. Budget from the measured 19.4k
base, which the v3 digest already occupies:

| block | tokens (w) | tag |
|---|---:|---|
| digest v3, unchanged | ~19.4k | mixed, tagged per section |
| 1. initial scene + entity map | 6–7k | OBSERVED + MINER-INFERRED |
| 2. causal episode | 5–7k | REPLAY-VERIFIED |
| 3. completion & goal contrasts | 3k | OBSERVED (new capture) |
| 4. matched action/unresolved contrasts | 7–9k | OBSERVED + MINER-INFERRED |
| 5. alias exhibits with histories | 1–2k | OBSERVED |
| 6. reasoning contract + index | <1k | instruction |
| **total** | **42–48k** | |

**1. Initial scene + persistent entity map.** The initial board **once**, letter-coded
with rulers, plus an explicit **numeric↔letter colour legend** (the DSL quantifies over
`cN`; without the legend the board and the grammar are two disconnected worlds — this
is the join slice 2 never had). Then a table over stable entity IDs: colour, bbox,
area, normalized shape hash, containment/children, adjacency, and status
(inert / touched / HUD-suspected). **Inert objects are a column, not a second full
board render.**

**2. The causal episode.** Not "the deepest route": the verified walked route
maximizing coverage of distinct `(action key, effect class)` pairs and structural state
novelty. Rendered as per-step lines — action, clicked entity ID, gameplay changes by
entity lineage, HUD-only changes flagged separately, completion flags — referencing the
initial frame rather than repeating it, with a **full snapshot only when topology or
scene phase changes**. Where the game has a completion route (sp80, lf52), that route
is the episode.

**3. Completion and goal contrasts** — the priority exhibit, from the new capture:
last incomplete state · the completing action and its target entity · **every returned
intermediate/animation frame** · the `level_completed` metadata · the next-level frame,
labelled unambiguously as a different level. Plus the negative half: stored states
where a row-C candidate was **satisfied and the level did not advance**, rendered as
crops. A positive/negative pair beats any static frame.

**4. Matched contrasts, not arbitrary examples.** Per important action key: an
**effect / no-effect pair** under otherwise similar visible conditions, or two different
effects; one example per distinct effect class where feasible. Per unresolved key: the
miner's **actual no-separation witness** — same recorded guard values, same action,
different outcomes. Crops are **adaptive to the union of changed cells** (11×11 is wrong
for global effects); a global effect gets a full snapshot and says so. Each pair carries
the miner's resolved rule where one exists, tagged MINER-INFERRED, so the model spends
its reasoning on what is unsolved.

**5. Alias exhibits with histories.** The board **once**, beside the two histories that
reach it: reset boundary, action count since reset, per-action-type counts, recent
action suffix, click-colour sequence — then the same next action and its two different
outcomes. The suspected cause is the history, which the first draft omitted while
rendering the identical board twice.

**6. Reasoning contract.** Headers — World model / Goal candidates / Action model /
Hidden state / Contradictions / Open questions — plus: generate several hypotheses
internally, eliminate those contradicted by the supplied evidence, emit one; and
**cite frame / entity / transition IDs for every conclusion** (citation rate is a
mechanical diagnostic, never a verdict).

**Contamination rule, unchanged and hard:** the prompt must never name the five stock
goal shapes — they are channel A's control. Grep-gated before the night.

## Frozen-interface fixes (a deliberate scope change — read this)

The review's third point is decisive: with the elicitation defects frozen, a loss means
only *"visual context did not rescue a defective interface."* Since this is the
best-shot final 3.6 experiment, the defects are fixed:

- **Refuter → discriminating observation.** Asked as: a stored or reachable situation
  where **your predicate holds and the level does not advance**, or a **completion where
  it fails**. Scored the same way — self-refutation now means the *correct* thing.
- **One out-of-DSL goal slot.** The DSL cannot express ft09-class per-clue
  match/differ constraints, so a model can read the board correctly and still be forced
  into a wrong aggregate predicate. Slice 3 accepts **one additional free-form
  completion condition** per cell, adjudicated by source read (labels only), reported
  as its own line and **never mixed into clause 1's mechanical count**.
- **Anchor removed**: no mention of `clicked_adjacent_to` or of any past channel-C win.

**Attribution, stated honestly:** slice 3 is therefore *not* a single-variable contrast
with slice 2. What is preserved is the thing that matters for the verdict — the
**controls** (prior library, five random features, measured failure typing) and the
pre-committed bar. A win would need a follow-up ablation on 3.8 to attribute; a loss is
interpretable exactly as intended: best record, fixed interface, controls unchanged.

## Build (day task, zero-model except item 0's live replay, ~6–8 h)

0. **Completion capture** (`agent/harness/e3_completion_capture.py`, new): replay the
   verified walked completion routes (`logs/e1_prefix_v2/`) for sp80 and lf52 — and
   lp85, r11l for the record — capturing **every frame** the engine returns at the
   completing action, the metadata, and the next-level frame. Store local-only
   (`logs/e1_completions/`, gitignored). Gate: the route must reproduce its recorded
   pre-state before the completing action.
1. **Entity tracker** (`agent/harness/e2_entities.py`, new): stable IDs across frames
   (match by colour + shape hash + bbox proximity + area), normalized shape hashes,
   containment, adjacency, inert/touched status. `_Objects` supplies none of this.
2. **Renderer** (`agent/harness/e2_frames.py`, new): letter board + legend + rulers ·
   entity table · adaptive crops around changed-cell unions · per-step diff lines ·
   alias history blocks.
3. **Digest v4 assembly** behind `--frames` (default off; slice-2 behaviour bit-exact
   without it), with the provenance tags and the episode-selection criterion.
4. **Interface fixes** in the request text and extraction schema (three items above).
5. **Token accounting on the templated prompt** (tokenizer, chat template applied — the
   defect that caused the first draft's error). Trim order if a cell overshoots 50k:
   episode diff span → matched contrasts (keep one per class) → entity-table columns.
   **Never** trim blocks 3 or 5.
6. **Contamination grep** + **budget probe** on the largest v4 prompt
   (`notes/think-budget-recheck.md` protocol): confirm think closure at 16,384 and
   measure warm prefill tok/s at ~50k, which the wall estimate needs. No unilateral
   budget raise.

## Run

16 F cells ≈ 6.5–7 h (decode ~15 min + prefill ~2 min/cell) + up to 8 FB turns ≈ 2.5 h
→ **~9 h**. Seeds sequential, **seed 1 first and complete, including its FB turns** —
if the window runs out, a complete seed 1 with both arms is a result; a truncated seed 2
is not a loss. `nohup` + `caffeinate`; voids logged, never rerun mid-night.

**Arm FB** (seed 1, cells whose predicate fails verification): one revision turn with
the concrete counterexample rendered — the falsifying transition, or the completion
frame where the predicate evaluated wrongly — then fresh think + extract, same budget,
same machinery. Readout adds the repair rate (failed → survived/correct).

## Readout

Slice 2's structure verbatim — channel A clause 1 (store-consistent ∧ source-correct ∧
outside the prior library), channel B (beats all five random controls), channel C
(targeting + implementation queue) — plus four slice-3 lines: **FB repair rate** ·
**out-of-DSL goal verdicts** (separate) · **citation rate** · and the three instrument
counters (**parse rate · think length · verdict passes**) reported as a possible
**context-length cost** against slice 2's ~19.4k matched control, never folded into the
capability verdict.

## Cautions

- **PUBLISHING.md, tightened for this slice:** prompts and think-traces will contain
  rendered boards. Frames live in local logs only — **traces from this night are not
  committed** (commit the scored JSONs, verdicts, counts; keep raw traces local, or
  scrub grids before committing). Check the diff before pushing; git history counts as
  redistribution.
- Vision tower stays out of scope: text rendering only, direct `mlx_lm`, the verified
  instrument.
- Concurrent agents: new files plus the flagged section; stage own files; `git status`
  first.
- Working numbers labelled (w); the 19.4k base and frame/patch costs are measured.
- Whatever tonight says, this protocol reruns on 3.8 as the generation contrast
  (`notes/qwen-3.8-upgrade.md`); tonight is its 3.6 baseline.

## Slice-2 erratum (filed here, referenced from the slice-2 note)

The **self-refuting refuter diagnostic (10/16) is withdrawn**: the request asked for a
predicate whose truth anywhere in the store counted as self-refutation, which is not
what refutes a completion condition. The channel-A verdict does not depend on it —
clause 1 was 0/8 on store-consistency, source-correctness and novelty independently —
but the diagnostic itself must not be cited.
