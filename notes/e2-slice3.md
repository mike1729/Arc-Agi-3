# E2 slice 3 — the maximal-context 3.6 night: a deduplicated, object-linked causal record

**2026-08-05. Design + build spec + run protocol. One GPU night, operator-requested:
the last 3.6 experiment. Revised twice after external review** — rev 1 (`f65729d`)
replaced repeated full frames with an object-linked causal record and fixed three
elicitation defects; **rev 2 (this) resolves the four remaining blockers**: the
completion block renders three full frames plus compressed intermediate diffs (not all
20/27), the refuter field is **removed** in favour of mechanically derived
falsification, the caps become **F ≤ 40k / FB chat ≤ 45k with the reserve stated**, and alias exhibits are held to strict identical-board semantics — which
leaves **3 of them, all on m0r0** (measured), so the block is absent on seven of eight
games and says so. **The current implementation is superseded — see the stop-work
section before running anything.**

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

## The record (arm F) — allocation to a ≤ 40k templated prompt (FB chat ≤ 45k)

Worst case is dc22; sparse games (sp80) land far lower. Budget from the measured 19.4k
base, which the v3 digest already occupies:

| block | tokens (w) | tag |
|---|---:|---|
| digest v3 — **evidence content unchanged**, section headers gain provenance tags | ~19.4k | mixed, tagged per section |
| 1. initial scene + entity map | 6–7k | OBSERVED + MINER-INFERRED |
| 2. causal episode | 5–7k | REPLAY-VERIFIED |
| 3. completion & goal contrasts | 3k | REPLAY-VERIFIED (new capture) |
| 4. matched action/unresolved contrasts | 7–9k | OBSERVED + MINER-INFERRED |
| 5. alias exhibits with histories — **m0r0 only** (see below) | 0–1.5k | OBSERVED |
| 6. reasoning contract + index | <1k | instruction |
| **F prompt total — HARD CAP 40k** | **36–40k** | |

**Two caps, with the reserve stated explicitly: F ≤ 40k, FB ≤ 45k.** A 45k F prompt
cannot also yield a ≤45k FB chat — the FB turn appends the model's own answer (~4–6k
at measured think/answer lengths) plus a rendered counterexample (~1–3k) to the *same*
chat, so the reserve must exist before F is rendered, not after. **5k reserve** covers
both. Build item 5 measures each prompt separately with the chat template applied: F
against 40k, the full FB chat against 45k; **either breach triggers the trim order**,
and a cell whose FB chat cannot fit after trimming runs F-only (recorded, not silently
dropped). Slack released by an absent block (below) is **not** re-spent — prompts get
shorter, which is a fine outcome.

**1. Initial scene + entity map.** The initial board **once**, letter-coded with
rulers, plus an explicit **numeric↔letter colour legend** (the DSL quantifies over
`cN`; without the legend the board and the grammar are two disconnected worlds — this
is the join slice 2 never had). Then a table: colour, bbox, area, normalized shape
hash, containment/children, adjacency, status (inert / touched / HUD-suspected).
**Inert objects are a column, not a second full board render.**

**Identity scope (tightened per review): entity IDs are stable within one episode or
one transition pair, never globally across unrelated store branches** — cross-branch
matching by colour+shape+proximity fabricates identity where none is recorded. Where
an entity's lineage changes (split / merge / recolour), the change is stated
explicitly with a confidence tag; unmatched entities get fresh IDs rather than a
speculative link.

**2. The causal episode.** Not "the deepest route": the verified walked route
maximizing coverage of distinct `(action key, effect class)` pairs and structural state
novelty. Rendered as per-step lines — action, clicked entity ID, gameplay changes by
entity lineage, HUD-only changes flagged separately, completion flags — referencing the
initial frame rather than repeating it, with a **full snapshot only when topology or
scene phase changes**. Where the game has a completion route (sp80, lf52), that route
is the episode.

**3. Completion and goal contrasts** — the priority exhibit, from the capture
(`logs/e1_completions/`, all four games passed their gates).

**Three full frames only** (the capture keeps every frame locally; rendering them all
would blow the block), taken by the capture's own **role labels — never by position**:

- **`last_incomplete_frame`** — the board before the completing action;
- **`solved_terminal`** — the frame where the level is solved. For a non-WIN completion
  this is the **penultimate** returned frame, not the last: the engine advances within
  the same response, so the final frame already belongs to the next level. Measured:
  sp80 roles `[…×18, solved_terminal, next_level_initial]` of 20; lf52 `[…×25,
  solved_terminal, next_level_initial]` of 27; r11l 23; lp85 just `[solved_terminal,
  next_level_initial]`. Reading "the last frame" as solved would have shown the model
  **the wrong level's board as the winning state** on all four games — the single most
  corrupting error available in this block.
- **`next_level_initial`** — labelled unambiguously as a *different level*.

Every *unique* intermediate frame appears as a **compressed diff** against its
predecessor (changed cells by entity, one line each). Plus the completing action and
its target entity, and the completion metadata verbatim (`levels_completed`, `state`,
and the run's `win_levels` total, so "level solved" is never confused with "game won").
The negative half: stored states where a row-C candidate was **satisfied and the level
did not advance**, as crops. A positive/negative pair beats any static frame.

**Renderer contract:** consume `completion.roles` from the capture JSON and fail loudly
if the expected roles are absent (`role_error` non-null) — never fall back to indexing.

**4. Matched contrasts, not arbitrary examples.** Per important action key: an
**effect / no-effect pair** under otherwise similar visible conditions, or two different
effects; one example per distinct effect class where feasible. Per unresolved key: the
miner's **actual no-separation witness** — same recorded guard values, same action,
different outcomes. Crops are **adaptive to the union of changed cells** (11×11 is wrong
for global effects); a global effect gets a full snapshot and says so. Each pair carries
the miner's resolved rule where one exists, tagged MINER-INFERRED, so the model spends
its reasoning on what is unsolved.

**5. Alias exhibits with histories — exactness is the whole point, and it makes the
block nearly empty.** An exhibit qualifies only as **identical visible board + same
action + different outcome**. Same action with matching *miner features* on *different
boards* is a vocabulary gap (channel C's business), not evidence for a history latent,
and must never appear here.

**Measured availability across the eight slice-3 games (rerun census, today):
m0r0 3 · dc22, ft09, ls20, tu93, vc33, sp80, lf52 — zero.** (For the record, the games
that do have them are outside this set: g50t 43, cn04 4, sc25 3, cd82 1.) So the block
renders **on m0r0 only**; on the other seven the prompt states *"no state in this store
produced two different outcomes for the same action — this game shows no evidence of
hidden state"*, and channel B's request is suppressed there rather than inviting
invention. **Tokens are not reallocated** — those prompts are simply shorter.

Where it renders: the board **once**, beside the two histories that reach it — reset
boundary, action count since reset, per-action-type counts, recent action suffix,
click-colour sequence — then the same next action and its two different outcomes. The
suspected cause is the history; the first draft rendered the one part known to be
identical and omitted it.

*Optional, only if the day has room:* **controlled dual-history probes** — the P2
method from `notes/e2-hidden-state.md` (execute distinct routes of different length to
one digest, same next action) generates exhibits on demand for games that have none.
This is live game contact and its own gated step; skip rather than rush it.

**6. Reasoning contract.** Headers — World model / Goal candidates / Action model /
Hidden state / Contradictions / Open questions — plus: generate several hypotheses
internally, eliminate those contradicted by the supplied evidence, emit one. Grounding
is captured **in the extraction schema as `evidence_ids`** (frame / entity / transition
IDs per claim), **not scored from free-form thinking** — free-text citation counting is
a text-matching exercise, while a schema field is checkable against the record.

**Contamination rule, unchanged and hard:** the prompt must never name the five stock
goal shapes — they are channel A's control. Grep-gated before the night.

## Frozen-interface fixes (a deliberate scope change — read this)

The review's third point is decisive: with the elicitation defects frozen, a loss means
only *"visual context did not rescue a defective interface."* Since this is the
best-shot final 3.6 experiment, the defects are fixed:

- **The refuter field is removed entirely.** "Discriminating observation" was still
  asking the model to invent a second predicate; there is no need. The model supplies
  **`evidence_ids`** (the states/transitions it claims support the predicate) and its
  **test action**; the checker derives falsification **mechanically** from the record —
  false positives (predicate true, level did not advance) and false negatives
  (completion occurred, predicate false). Slice 2's refuter diagnostic dies with the
  field; what replaces it is computed, not claimed.
- **One out-of-DSL goal slot, as an understanding diagnostic.** The DSL cannot express
  ft09-class per-clue match/differ constraints, so a model can read the board correctly
  and still be forced into a wrong aggregate predicate. Slice 3 accepts **one free-form
  completion condition** per cell, adjudicated by source read (labels only). It is
  reported on its own line and is **never a win against the prior-library control** —
  that control has no free-form output, so the comparison would be unmatched. It
  measures understanding, not channel-A victory.
- **Anchor removed**: no mention of `clicked_adjacent_to` or of any past channel-C win.

**Attribution, stated honestly:** slice 3 is therefore *not* a single-variable contrast
with slice 2. What is preserved is the thing that matters for the verdict — the
**controls** (prior library, five random features, measured failure typing) and the
pre-committed bar. A win would need a follow-up ablation on 3.8 to attribute; a loss is
interpretable exactly as intended: best record, fixed interface, controls unchanged.

## ⛔ STOP-WORK: the current implementation is the superseded draft

**A build is already in progress against rev 1 — do not run it.** Audited 2026-08-05,
19:30, re-checked while writing this section (the tree moved mid-audit):

| file | state at audit | required by rev 2 |
|---|---|---|
| `e2_frames.py` (uncommitted) | builds the **most-explored frame**, the **full static inert overlay**, and **repeats the episode board** — all three deleted by this revision | rewrite against blocks 1–6 |
| `e2_slice.py` (modified) | still requests the malformed **REFUTER** (`:895`, `:900`, schema `:954`, scoring `:1225`+) and still carries the **`clicked_adjacent_to:C` anchor** (`:917–918`) | delete the refuter field and its scoring; delete the anchor sentence; add `evidence_ids`; derive false positives/negatives mechanically; suppress channel B where no alias exhibit exists |
| `e2_entities.py` | appeared mid-audit — **check against the identity-scope rule** (episode/pair-local IDs, explicit lineage, no global matching) | build item 1 |
| `e3_completion_capture.py` | appeared mid-audit — capture all frames locally is right; **the prompt renders 3 + diffs** | build item 0 |

Anything rendered before those land implements the design this note replaced. Whoever
owns the build should re-read this note from the top: the deltas are the four blockers
in the header, not a diff against rev 1's prose.

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
5. **Token accounting on BOTH templated prompts** (tokenizer, chat template applied —
   the defect that caused the first draft's error): the F prompt, and the full FB chat
   (F + the model's answer + the rendered counterexample). **F ≤ 40k and FB chat ≤ 45k —
   both checked, either breach triggers the trim.** Trim order if a cell overshoots: episode diff span → matched contrasts
   (keep one per effect class) → entity-table columns. **Never** trim block 3, and
   never trim block 5 (it is 3 exhibits on one game).
6. **Contamination grep** + **budget probe** on the largest v4 prompt
   (`notes/think-budget-recheck.md` protocol): confirm think closure at 16,384 and
   measure warm prefill tok/s at ~40k, which the wall estimate needs. No unilateral
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

## Measured cost of the caps (review, 2026-08-05 — carry into the readout)

Dry-run of all 8 cells with `--frames --feedback`. **Every cell fits both caps**
(F 28,574–39,929 of 40,000 · FB 31,682–42,901 of 45,000), and the unframed path was
verified **byte-identical to slice 2** (dc22, 48,721 chars) — the context isolation is
real. But 7 of 8 cells trim, four of them deep (ladder steps 9–11), and the cost is
concentrated where it is least convenient:

| game | F tok | unresolved keys shown | ex/key | episode steps |
|---|---:|---|---:|---:|
| ft09 | 28,574 | 1 of 1 | 2 | 60 |
| sp80 | 37,571 | **3 of 12** | 1 | 12 |
| vc33 | 38,811 | 7 of 7 | 2 | 20 |
| ls20 | 38,622 | 4 of 4 | 2 | 45 |
| m0r0 | 39,288 | 10 of 10 | 1 | 12 |
| lf52 | 39,018 | 6 of 6 | 1 | 12 |
| dc22 | 39,617 | 12 of 14 | 1 | 12 |
| tu93 | **39,929** | 4 of 4 | 2 | 45 |

**Readout caveat, pre-committed:** a null channel-C result on **sp80** is partly a
budget artifact — it shows 3 of its 12 unresolved keys — and dc22 shows 12 of 14. Those
two games' channel-C numbers are reported with the shown/total fraction attached and are
**not** pooled with the games shown in full. Blocks 3 and 5 were never trimmed, as
specified.

**Pre-launch assertion (do this, it is 30 seconds):** tu93 sits **71 tokens** under the
cap and m0r0 712. F counts are exact (chat template applied), so there is no runtime
surprise — but any later edit to the shared preamble silently re-triggers trimming on
those cells. Re-render all 8 immediately before launch and confirm the same trim ladder
steps as the table above; a changed step means the prompt moved and the cell is no
longer the one reviewed.

> **EXECUTED 2026-08-05 21:3x — PASSED.** All 8 cells reproduce the table exactly: same
> F tokens, same FB-chat tokens, same ladder steps. Parse and `--help` clean.
>
> **And it caught a real one.** The implementation was **uncommitted** — 283 lines
> across `e2_slice.py`, `e2_frames.py`, `e2_entities.py` sitting on top of the build
> commit `ad540a9`. `git worktree add <commit>` would have pinned `ad540a9` and run code
> that was never reviewed, silently. The verified state is now committed as **`1f76bbc`**
> — **pin the worktree at that hash**, and re-run the assertion inside the worktree
> before launching, so the pin is confirmed rather than assumed.

## Readout

Slice 2's structure verbatim — channel A clause 1 (store-consistent ∧ source-correct ∧
outside the prior library), channel B (beats all five random controls; **on m0r0 only**,
absence reported as absence elsewhere), channel C (targeting + implementation queue) —
plus four slice-3 lines: **FB repair rate** · **out-of-DSL goal verdicts** (separate
line, understanding diagnostic, never a control win) · **`evidence_ids` validity**
(do the cited states/transitions exist and support the claim — computed, not counted
from prose) · and the three instrument counters (**parse rate · think length · verdict
passes**) reported as a possible **context-length cost** against slice 2's ~19.4k
matched control, never folded into the capability verdict. Mechanical falsification
(false positives / false negatives derived from the record) replaces the withdrawn
refuter diagnostic.

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

---

# BUILD RESULTS — 2026-08-05, against rev 2.1

Build items 0–6 complete; the night is runnable. Every number below is measured today.
Working choices are labelled (w). **Two findings changed the design and are called out
as such** — block 5's premise, and the completion frame roles.

## Item 0 — completion capture (`agent/harness/e3_completion_capture.py`) ✅

Live replay of the verified walked routes. **All four gates passed** — each route
reproduced its recorded pre-action board cell for cell — and the frame counts match the
explorer's own recorded counts exactly, which is independent confirmation the replay is
the same episode:

| game | route | frames returned | explorer recorded | roles |
|---|---:|---:|---:|---|
| sp80 | 16 actions | 20 | 20 | 18 intermediate · solved_terminal · next_level_initial |
| lf52 | 71 actions | 27 | 27 | 25 intermediate · solved_terminal · next_level_initial |
| r11l | 9 actions | 23 | 23 | 21 intermediate · solved_terminal · next_level_initial |
| lp85 | 38 actions | 2 | 2 | solved_terminal · next_level_initial |

**This project now holds a solved board for the first time.** Local-only in
`logs/e1_completions/` (`/logs/*/*` already ignores it).

Two consequences beyond block 3. The positive half of channel A's clause 1 becomes
measurable — `positives_evaluable` was 0 on all eight games in every prior slice because
the explorer never retained the completion's post frame — and the FB arm gains a second,
sharper counterexample type (**false negative**: the level completed and your condition
is false of the solved board).

**Rev 2.1's role rule is confirmed and it mattered.** On every one of the four, the
solved board is the **penultimate** frame; the last already belongs to the next level.
The renderer selects by role and raises on `role_error` or a role/frame length mismatch —
it never indexes.

## Item 1 — entity tracker (`agent/harness/e2_entities.py`) ✅

Stable ids, normalized shape keys, bbox containment (the grammar's `bbox_contains`, not
cell enclosure — a relation the model can see but cannot write would be worse than none),
4-adjacency, and status. Matching is same-colour, exact-cell-set first, then scored on
(identical shape, area ratio, centre distance); a match worse than "different shape and
half the area" is refused and a **fresh id issued instead** — an id forced onto an
unrelated component would assert a movement nothing observed.

**Identity scope per rev 2:** ids are episode-local or pair-local, never global. Blocks 4
and 4b build a fresh tracker per pair; the prompt states that ids are not comparable
across blocks.

`status` is `inert` / `touched` / `hud?`. The HUD guess is the bbox of the largest
never-changing structure, stated as a guess wherever it is printed.

## Item 2 — renderer (`agent/harness/e2_frames.py`) ✅

Letter board + numeric↔letter legend + absolute rulers · entity table · **adaptive crops
sized to the union of changed cells** · per-step entity-named diff lines · alias history
blocks. Round-trip checked: the letters decode back to the exact 64×64 grid.

**Measured, and it forced a cap.** Crops fall back to a full board when a change is too
spread out to window. On dc22 that produced **28 full boards across blocks 4 and 4b —
163k of a 248k-character record, four times the entire budget.** The fallback is now
rationed (`global_examples`, shared across both blocks): the first board-wide changes are
shown in full, and after that the cell list and the changed bounding box carry it, with
the record saying so. dc22 went 248k → 129k chars.

Block 3b is rendered as **crops** per the note — cropped to the entities of the colours
the refuted condition names.

## Item 3 — digest v4 behind `--frames` ✅

**Regression gate: all 8 slice-2 prompts reproduce byte-for-byte** without the flag,
asserted against last night's committed traces. *(Recorded honestly: this held when first
measured, then a later edit in the same build — splitting `PROMPT_V4` out — left a stale
`{frames_preamble}` slot in the v3 template and broke the unframed path outright. I did not
re-run the gate before committing `ad540a9`. The review round below re-ran it, it failed
loudly, and it is 8/8 again. The lesson is the gate's, not the code's: a regression gate
run once at the start of a build is a gate run at the wrong time.)* The v3 evidence is unchanged; its section
headers gain provenance tags (`OBSERVED` / `REPLAY-VERIFIED` / `MINER-INFERRED`) only in
the v4 path. Traces are tagged `_s3r{seed}`, and `.gitignore` now excludes them —
slice-3 prompts and traces embed rendered boards, and git history counts as
redistribution.

## Item 4 — interface fixes ✅

Refuter field **deleted**; falsification is derived (`falsification()`): false positives
from row-C survivorship, false negatives from the captured solved board. `evidence_ids`
added to the schema and checked against the record's own step numbers and entity ids —
the check verifies the referent **exists**, not that it supports the claim, and says so.
One free-form out-of-DSL condition per cell, recorded and scored nowhere mechanically.
Anchor removed. Reasoning contract with rev 2's six headings.

## Item 5 — token accounting, both prompts ✅

F ≤ 40,000 and FB chat ≤ 45,000, tokenizer with the chat template applied, FB counted as
the assembled chat plus a **measured** worst-case counterexample plus a 1,000-token answer
allowance (measured: slice 2's sixteen answers were 151–289 tokens).

**Superseded by the review round below** — these counts predate the wrong-frame fix and
the chat-template accounting. See the REVIEW ROUND 1 table for the numbers of record.

**All eight fit both caps; none runs F-only.** The ladder runs episode span → matched
contrasts → entity-table columns → episode snapshots → unresolved-key count; blocks 3 and
5 are never on it.

## Item 6 — gates ✅

**Contamination: PASS**, 0 hits across all eight prompts. The 306 `clicked_adjacent_to`
hits found on the first pass were all in the DIGEST — value sets, strata tables and
no-separation witnesses, i.e. the guard vocabulary as evidence, which a channel-C
proposal needs in order for "missing" to mean anything. The anchor rev 2 removed was the
sentence in the *request*, so the gate now checks the request (the templated prompt minus
the digest) for it. Request is 6,313 chars on seven games, 6,371 on m0r0 (channel B).

**Budget probe: PASS** — m0r0, the largest prompt.

| | |
|---|---|
| prompt | 101,240 chars / **38,315 tokens** |
| think | 21,284 chars / 6,177 tokens; `</think>` at generation token 6,178 |
| total generation | **6,454 of 16,384 — 9,930 spare** |
| wall | 883.5 s |
| **warm prefill** | **331 tok/s** (the wall estimate needed this) |
| decode | 8.4 tok/s |

The block closes with 61% of the budget unused. Slice 2's precedent repeats: doubling the
prompt again did not lengthen the think block — 6,177 think tokens here against slice 2's
8,178 on a 19.4k prompt, so it got *shorter*. No budget change.

**Revised wall estimate (w), from measured numbers:** prefill 38k/331 ≈ 116 s, decode
≈ 6.5k/8.4 ≈ 13 min → **~15 min/cell**. 16 F cells ≈ 4 h, plus up to 8 FB turns ≈ 2 h →
**~6 h**, comfortably inside the window and below rev 2's ~9 h estimate.

## ⚠ Block 5: rev 2's premise did not survive checking, and the block was rebuilt

Rev 2's availability census — "m0r0 3, the other seven zero" — is the `conflicted` count
in `logs/e1_store_v2/*.graph.json`, and it is confirmed (m0r0 3; dc22, ft09, ls20, tu93,
vc33, sp80, lf52 all 0). **But the store retains only ONE outcome for each of those
pairs.** For all three m0r0 conflicts, `graph.json`'s own `edges` hold exactly one post
state, the transitions log holds exactly one row, and `conflict_records` carries only
`{state, action, step}`. The passive census over the transitions log is 0 repeated / 0
aliased on all twelve games checked — which `notes/e2-hidden-state.md` already recorded.

So **block 5 was unrenderable from stored data on all eight games**, m0r0 included. The
flag records that a conflict was seen live; the other board was never kept. Rendering the
one retained outcome twice would have fabricated exactly the thing the exhibit exists to
show.

Taken the note's own optional path (`agent/harness/e2_alias_probe.py`, the P2 method of
`notes/e2-hidden-state.md`): drive two verified histories of different length to the same
board, gate on both reproducing it cell for cell, then take the flagged action from each.

**Result — 2 genuine REPLAY-VERIFIED alias exhibits on m0r0, and 1 flag confirmed an
artifact:**

| flagged pair | routes | gate | outcome |
|---|---|---|---|
| origin, ACTION1 | 0 vs 1 actions | both reproduced the board | **DIFFER, 2 cells** |
| origin, ACTION6(9,19) | 0 vs 1 actions | both reproduced the board | **DIFFER, 2 cells** |
| 639318dd, ACTION1 | 6 vs 7 actions | both reproduced the board | IDENTICAL — artifact |

The third is what `notes/e1-prefix-audit.md` suspects this list of in both directions,
now demonstrated rather than suspected. Block 5 renders on m0r0 with 2 exhibits and their
histories; on the other seven it states that no pair of histories in the record reaches
one board and diverges, and **channel B's request is suppressed there** — verified in the
rendered prompts.

## What is NOT done

- **The night has not run.** `--frames --feedback`, seeds 1 then 2, `--out` explicit.
- Source adjudication of channel A, the free-form conditions, and the readout are
  post-night work, as in slice 2.
- The optional dual-history probes for games with no flags at all were not attempted:
  every non-m0r0 protocol game has zero flagged pairs, so there is nothing to probe.

---

## REVIEW ROUND 1 — 2026-08-05, five findings, all fixed and re-gated

All five reproduced before being fixed. The build ran again from the gates afterwards.

### [P1] Refutation exhibits rendered the wrong board — confirmed, and it was the serious one

`dsl.transition_contexts` builds `context["objects"]` from the **post** frame, so a
condition is evaluated on the board an action PRODUCED. Block 3b and the FB counterexample
both rendered `transition.pre`. Reproduced exactly as reported:

| game | step | condition | on the rendered pre | on the post |
|---|---:|---|---|---|
| dc22 | 1606 | `all x in c14: exists y in c11: adjacent(x, y)` | **false** | true |
| dc22 | 1606 | `all x in c14: exists y in c11: bbox_contains(x, y)` | **false** | true |
| ft09 | 305 | `appears(c9)` | **false** | true |
| ft09 | 305 | `disappears(c8)` | **false** | true |

Every displayed refutation would have shown the model a board and asserted a condition that
is visibly false on it — worse than showing nothing. Both sites now render the post board
and name it as the board *after* the action. Because `appears`/`disappears`/`changes`/
`persists` are about the TRANSITION rather than a single state, each exhibit also carries a
one-line cell diff from the previous board, which costs a line instead of a second board.

### [P1] The FB prompt asked for the deleted refuter — confirmed

`REVISE` still said "one predicate, its refuter, and one test action" while `PROMPT_V4` and
`EXTRACT_V4` had replaced it with `evidence_ids` and `free_form`. The cell's one revision
turn would have been spent partly on a field the extractor discards, and the arm would have
measured a schema mismatch instead of re-specification under contradiction. Added
`REVISE_V4`, matching the v4 schema; slice 2's `REVISE` is untouched for the unframed path.

### [P2] The ceilings were reported, not enforced — confirmed, now enforced at both ends

- `feedback_possible` is now consumed: a cell whose FB chat will not fit runs **F only**, and
  the reason is recorded on the cell.
- A cell whose **F** prompt is still over cap after the full ladder is **skipped** and
  recorded as skipped, with `--allow-over-cap` as the explicit override. A hard cap that
  runs anyway is not a cap.
- Accounting now counts the **assembled chat**, not concatenated text: `chat_tokens()`
  applies the chat template, the same call `Qwen.generate` makes.
- The FB chat is **re-counted for real** inside the cell, once the answer and the actual
  counterexample exist, and the turn is refused if it exceeds the ceiling. That is the only
  point at which the FB chat's true size exists.

### [P2] Entity ids claimed continuity the tracker could not support — confirmed, tightened

The matcher scored area and proximity and could keep an id across a change of shape, while
the prompt told the model an id denotes the same entity. Rather than expose a confidence the
model would have to weigh, ids are now kept **only on exact evidence** — identical cell set,
or identical normalized shape in the same colour (a rigid translation, whose vector is
reported). Everything else gets a **fresh id**, and the episode prints a `lineage:` line
naming the plausible partner and explicitly declining to assert it:

> `#1 is gone and #57 is new — same colour c1, 60 cells then 61 now, nearby. POSSIBLY the
> same thing changing shape; NOT asserted, which is why it has a new id`

Two ids may name one thing; one id never silently names two. The prompt's identity paragraph
now says exactly this.

### [P3] `--print-digest --frames` passed the `(caps, report)` tuple — confirmed, unpacked

### Re-gated after the fixes

| game | F ≤ 40,000 | FB chat ≤ 45,000 | trim step |
|---|---:|---:|---:|
| dc22 | 39,617 | 42,786 | 9 |
| ft09 | 28,574 | 31,682 | 0 |
| ls20 | 38,622 | 41,691 | 1 |
| m0r0 | 39,288 | 42,496 | 9 |
| tu93 | 39,929 | 42,901 | 1 |
| vc33 | 38,811 | 42,518 | 3 |
| sp80 | 37,571 | 41,259 | 11 |
| lf52 | 39,018 | 42,767 | 10 |

**All eight fit both ceilings and all eight can run FB.** The margins are thinner than
before — tu93 has 71 tokens of headroom — because the lineage lines and the change summaries
are real additions, and because the chat template is now counted rather than approximated.

Slice-2 prompt reproduction **8/8 byte-for-byte**. Contamination **0 hits across 8 prompts**.

---

# RUN RESULTS — night of 2026-08-05/06

Ran in worktree `/Users/michal/Workspace/ship-slice3` pinned at **`1f76bbc`**, as the
assertion required. 16 F cells + 5 FB turns, ~7.5 h wall. Outputs
`logs/e2_slice3_seed{1,2}.json` (`format_version 3`), latents specs
`logs/e2_slice3_latents_seed{1,2}.json`, verified
`logs/e2_slice3_latents_seed{1,2}_verified.json`. The result JSONs carry counts and the
model's structured answer only — **no prompts, no think text, no grids** — so they are
committed; raw traces stayed in the worktree, per the tightened PUBLISHING rule.

**Pre-flight deviation, accepted:** the run agent re-ran the think-budget probe on
**tu93** (the largest cell, 39,929 F tokens) rather than m0r0, and overwrote
`logs/e2_slice3_budget_probe.json`. Stricter than specified and it passed — think closed
at token 6,376 with 9,674 spare of 16,384. The m0r0 probe it replaced is in git history.

## Instrument — held, and that is a real result

16/16 mechanical thinking verdicts pass (opened · closed · substantive · answer
non-empty · no prefilled empty think). **0 voids, 0 extract retries** (`extract_attempts`
= 1 on every cell). Parse 15/16 — one `prose_rejected` (sp80 seed 2, `col_aligned(c9, c4)`,
a two-object form the grammar does not take).

Think length 19.8k–36.7k chars (slice 2: 19.6k–27.4k) — **up ~15% at the median under 5×
the prompt.** Decode 8.3–8.6 tok/s, prefill 335–379 tok/s, mean 1,317 s/cell.

> **The context-length cost is not a capability cost.** At ~100k-char prompts the
> instrument did not degrade: no truncation, no void, no retry, thinking longer rather
> than shorter. Whatever slice 3 failed at, it did not fail because 40k tokens broke the
> decode path.

## Channel A — **0/16 on clause 1. Dead, same as slice 2.**

| | slice 2 (~19.4k, no boards) | slice 3 (~39k, boards + record) |
|---|---:|---:|
| store-survived | 7/16 | **9/16** |
| ∧ novel (outside prior library and its shape space) | 2/16 | **4/16** |
| ∧ source-correct | **0/16** | **0/16** |

The mechanical numbers moved; the verdict did not. Adjudication against source (labels
and paraphrase only) killed all four survivors:

- **ft09** (`count(c9) = 12`, both seeds) — the real condition is a **per-tile
  constraint-satisfaction check**: every tile carries, in its own pixel pattern, a
  same/different requirement for each of its 8 neighbours, and the level clears when
  every tile satisfies all eight. A global colour count is not close.
- **vc33** (`count(c7) = 32`) — the real condition is a **cross-class relational match**
  (each object of one class must be matched by an object of another sharing a colour and
  a coordinate relation, with a reachability side-condition).
- **sp80** (`count(c14) = 30`) — real condition is a **containment property of a spreading
  region**. Also the one predicate the completion frames could grade positively, and it
  is **false at the true completion** (`false_negative: true`).
- **lf52** (`empty(c14)`) — in the prior library, and also `false_negative: true`.

### The two findings that matter more than the verdict

**1. The DSL cannot express roughly half of these goals.** Adjudicated per game — real
condition vs the row-C predicate grammar:

| game | real completion condition (paraphrase) | expressible? |
|---|---|---|
| tu93 | every token stands exactly on an exit tile | yes (as `all…exists…bbox_overlap`) |
| dc22 | the player sprite coincides with the goal sprite | **approximable only** — grammar has overlap, not coincidence |
| ls20 | every collectible walked onto and removed | approximable (`empty`) |
| m0r0 | every target collected / made intangible | approximable (`empty`) |
| ft09 | per-tile 8-neighbour same/different constraints all satisfied | **no** |
| vc33 | cross-class relational match + reachability | **no** |
| sp80 | spreading region contained in an allowed set | **no** |
| lf52 | flag set by an internal state machine | unresolved (likely no) |

Zero-tolerance grading against a language that cannot state the answer measures the
language. **Three of eight games were unwinnable by construction**, and this was not
known when the caps and the grader were pre-registered.

**2. Zero-tolerance killed a structurally correct answer.** dc22 seed 2 answered
`all x in c14: exists y in c8: bbox_overlap(x, y)` with the free-form gloss "the green
block must be maneuvered until it overlaps the red block" — that **is** the real
condition (player-onto-goal coincidence), and it is the closest the grammar can get.
Graded **falsified**: 3 false positives in 2,939 transitions (0.10%), first at step 1578
— exactly the gap between *overlap* and *coincidence*. A contradiction **rate** would
have reported this as the near-miss it is; the binary reported it as a failure
indistinguishable from `count(c0) = 11`.

### Free-form goal — the understanding diagnostic (never a control win)

Given on 13/16 (missing: ft09 s2, sp80 s2, lf52 s2 — a slot the model silently skipped).
Adjudicated against source: **3/13 correct in kind** (dc22 s2, ls20 both), **3 partial**
(tu93 both — right objects and right mechanism, wrong relation: *adjacent* where the
truth is *coincident*, and *exists* where the truth is *all*), 7 wrong.

> **The prose is better than the predicate.** 3 right and 3 near-right in prose against
> 0/16 in the DSL, on identical evidence in the same generation. The bottleneck exposed
> tonight is **expression, not perception.** Slice 2 had no such slot, so this has no
> baseline — but it is the first positive signal from Qwen3.6 in this line.

## Channel B — 5/5 latents rejected, and **the rejection is about m0r0, not about Qwen**

m0r0 is the only slice game with an alias exhibit, so the request fired there and was
suppressed on the other seven, as designed. 5 latents proposed across seeds, **0
`prose_rejected`** — all five parsed in the counter grammar. All five lose to at least
one of the 5 seeded random controls (`logs/e2_slice3_latents_seed{1,2}_verified.json`).

But seed 2's first proposal was `actions_since_reset[reset_excluded] mod 2` — **verbatim
the `c2_episode` arm** that `e2_hidden_state` was built to test, i.e. the hypothesis a
human expert wrote down by hand. It is rejected on the same criterion. So the honest
reading is: **the model produced the right hypothesis and the environment does not reward
it.** Channel B as specified cannot distinguish "the model proposes badly" from "m0r0 has
no load-bearing latent to propose", and on this evidence it is the latter.

## Channel C — **the one channel that measurably improved**

Proposals naming a genuinely unresolved forward-model key:

| | slice 2 | slice 3 |
|---|---:|---:|
| targeting a real unresolved key | 6/31 (19%) | **16/31 (52%)** |

Seed 1 6/16, seed 2 10/15. **Not pooled for the two budget-starved games**, per the
pre-committed caveat: sp80 was shown 3 of its 12 unresolved keys (its 1 hit is out of 2
proposals) and dc22 12 of 14 (1 of 2). The other six were shown their keys in full and
carry the result.

Nothing over the cap; 0 malformed. Implementation queue (distinct, worth building):
`min_row/min_col` of the moving object (m0r0, ls20, tu93 — four independent proposals),
`size(clicked)` (lf52), `enclosed_by(c4)` (ft09), `col_aligned(c9, c6)` (sp80).

## Arm FB — mechanically 3/5, substantively **0/5**

| game | before | after | mechanical | what actually happened |
|---|---|---|---|---|
| dc22 | `count(c0) = 11` falsified, 49 fp | `empty(c0)` survived | repaired | **into the prior library** |
| m0r0 | quantified form, 2,943 fp (true everywhere) | `exactly_one(c10)` survived | repaired | **into the prior library** |
| sp80 | `count(c14) = 30`, false at completion | `empty(c11)` survived | repaired | **into the prior library** |
| ls20 | `empty(c0) and empty(c1)`, 13 fp | `empty(c11)`, 90 fp | not repaired | worse |
| lf52 | `empty(c14)` survived, false at completion | `empty(c2)`, 91 fp | not repaired | **survived → falsified** |

Every "repair" is a retreat to a stock shape that survives because it is nearly never
true. The counterexample turn as specified teaches *avoid contradiction*, not *be right*
— and with no positive example to satisfy, the vacuous predicate is the optimal play.
**The arm is not neutral, it is anti-correlated with correctness. Do not carry it
forward unchanged.**

## The structural defect this night exposed

**Six of eight games have no captured completion**, so `store_consistency` only ever
checked the negative direction — "never true at a non-terminal state". A predicate that
is essentially never true passes. Of the 9/16 "survived" cells, **7 were graded on the
negative direction alone.** The two that could be graded both ways — sp80 and lf52 — are
**both false at the real completion**, caught only by the new mechanical falsification.

That is the finding: on every cell where the grader could actually check correctness,
the model was wrong, and on every cell where it could not, the model "passed".
`e3_completion_capture.py` has completions for sp80, lf52, lp85, r11l. **Extending it to
the remaining six is zero-model, and it is the highest-value single change available.**

## Evidence ids

Cited 3–11 per cell; resolvable 55/64 seed 1 and near-total seed 2; 0 malformed. The
unresolvable ones are category names rather than ids ("OBJECT CENSUS", "negative
evidence", "causal episode"). m0r0 seed 1 is the outlier — 0 of 4 resolvable, all four
prose descriptions. The check is existence, not support; no cell fabricated an id.

## Verdicts, one line each, each against its control

- **Channel A: dead** — 0/16 source-correct, unchanged from slice 2 under 5× the context.
  But the verdict is **partly uninterpretable**: 3 of 8 games could not be answered in the
  grammar, and one structurally correct answer was failed by a binary threshold.
- **Channel B: no verdict available** — 5/5 rejected, but the expert hypothesis is among
  the rejected, so the control is measuring the game.
- **Channel C: alive** — 52% vs 19% targeting, on the same games and the same key lists.
- **Instrument: passed** — 16/16 verdicts, 0 voids, longer thinking at 5× context.
- **Arm FB: harmful as specified** — 0/5 substantive repairs, 1 regression.

---

# FIXES — 2026-08-06, and what they overturned

Everything below is zero-model. The night's answers are on disk, so the corrected verdicts
are computed, not re-run.

## 1 · Positives exist for every game (`agent/harness/e2_positives.py`)

Not from the engine — from the corpus the miner already reads. `rs_transitions` marks
`completed` on the transition whose response incremented `levels_completed` and keeps the
`solved_terminal` frame as its `post`. Measured, distinct L1 boards after dedup by grid
digest:

| dc22 | ft09 | ls20 | m0r0 | tu93 | vc33 | sp80 | lf52 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 9 | 4 | 9 | 11 | 5 | 8 | 8 | 10 |

8–13 independent sessions each. `e3_completion_capture.py` could never have reached six of
these — it replays what the *explorer* walked, and the explorer completed a level on two
games. The positive half of goal grading was available the whole time in a file we were
already loading.

## 2 · The grammar was mostly adequate. **My source-read adjudication was wrong.**

`agent/harness/e2_expressibility.py` enumerates the grammar and asks whether ANY predicate
is definite-true at every solved board and definite-false at every non-completing
transition. Per game, at L1, against the human corpus:

| game | v1 (as graded) | v2 (extended) | simplest separator | closest miss |
|---|---|---|---|---|
| dc22 | **expressible** (46) | expressible (145) | `empty(c11)` | — |
| ls20 | **expressible** (8) | expressible (16) | `count(c9) = 3` | — |
| tu93 | **expressible** (28) | expressible (87) | `empty(c14)` | — |
| sp80 | **expressible** (180) | expressible (323) | `empty(c9)` | — |
| lf52 | **expressible** (4) | expressible (4) | `count(c1) = 37` | — |
| vc33 | inexpressible | **expressible** (4) | `none x in c0: exists y in c11: col_aligned(x, y)` | 4.7% under v1 |
| ft09 | inexpressible | inexpressible | — | 12.9% |
| m0r0 | inexpressible | inexpressible | — | 3.0% |

**Six of eight were expressible under the vocabulary that graded slices 2 and 3.** The
readout above claimed ft09, vc33 and sp80 were unwinnable by construction and dc22
approximable only; the machine check says sp80 had 180 separators and dc22 46. Reading the
win condition out of source gives the *mechanism*; it does not tell you what the board
LOOKS like when the mechanism fires, and a much simpler observable often separates. Only
ft09 stands as claimed. That correction cuts against the model, not for it.

**Read the two directions differently.** `inexpressible` is the strong result — nothing in
the grammar fits even this evidence. `expressible` is the weak one: it says the evidence
does not rule the grammar out. sp80's 180 separators over 8 positives is a statement about
how little 8 boards constrain, not about how well the goal is identified.

The DSL extension is measured, not asserted: `none` is what flipped vc33, and it is the only
game it flipped.

## 3 · The night re-graded: **1 correct, and the grader could not see it**

`agent/harness/e2_regrade_slice3.py` re-grades the predicate each cell actually wrote,
character for character, in both directions against the human corpus.

| verdict | cells |
|---|---:|
| **correct** — fires at every solved board, no false positives | **1** |
| vacuous — fires at **no** solved board | 10 |
| unreachable — no separator exists in the grammar | 4 |
| prose_rejected | 1 |

**lf52 seed 2 was right.** It fires at 10 of 10 solved boards with 0 false positives over
302 human transitions. The night recorded it as `survived` — the same word, the same column,
as the ten answers that fire on nothing at all. Channel A was not 0/16 on the night; it was
**1/11 on the cells that were answerable**, and the instrument could not tell the difference.

And the shape of the failure is now visible: **ten of sixteen predicates are true at no
solved board.** Not subtly wrong — never true at the goal. The one-directional grader scored
six of those ten as `survived`, because a condition that is never true is never wrongly true.

## 4 · The channel-C queue was built, and it makes the miner **worse**

`rs_transitions` vocab **v3** implements exactly the six features Qwen proposed —
`min_row`/`min_col`, `size(clicked)`, `enclosed_by`, `row_aligned`/`col_aligned` — and
`agent/harness/miner_vocab_v3.py` measures them under the rule v2 was adopted by (zero
losses anywhere, gains somewhere).

**39 of 48 arms clean → v3 fails adoption. `v2` stays the floor of record and the default.**

| game | full/L1 | full/L2 | verdict |
|---|---:|---:|---|
| bp35 | −0.085 | −0.191 | large loss (moveset/L2 −0.452) |
| sp80 | **+0.015** | **−0.243** | trains up, transfers down |
| ft09 | −0.041 | −0.035 | loss |
| cn04 | −0.005 | 0.000 | loss |
| dc22 | 0.000 | −0.001 | loss |
| ar25 | +0.014 | 0.000 | the only real gain |
| lf52 | 0.000 | +0.007 (moveset) | marginal gain |

The overfitting signature named in advance appeared exactly where predicted — sp80 gains on
held-out L1 and loses a quarter of L2 — but the positional features are not the main
culprit: dropping `min_row`/`min_col` only halves sp80's damage (−0.160) and changes bp35
and ft09 not at all. The pairwise alignment and containment guards do most of it, and
positional features were selected in only 6 of 48 arms.

> **Channel C's verdict splits.** As a *targeting* signal it is alive — 52% vs 19%, that
> number stands. As a *value* signal it is dead: the features it named, built faithfully and
> measured under the pre-committed rule, lose. Naming a plausible missing feature and naming
> a useful one are different capabilities and slice 3 only measured the first.

## 5 · The other four fixes

- **Grader** (`e2_slice.graded_verdict`): both directions on the human corpus,
  `dsl.contradiction_scan` for a rate instead of a first-contradiction boolean, and
  `distance_to_target` against the oracle's ceiling. `store_consistency` is unchanged and
  unmoved so the slice-2/3 comparison stays like for like.
- **Arm FB**: the counterexample turn now carries the solved boards and states that a
  condition true of none of them is scored a failure, not a repair — the vacuous escape the
  night's 3/5 "repairs" all took. `_repair_quality` adds `retreat_into_library` and
  `positives_before/after`, so a retreat into a stock shape is a field rather than something
  someone notices by reading five rows.
- **Free-form**: no longer conditional on the model admitting the grammar failed it. It was
  requested only under "IF THE GRAMMAR CANNOT SAY IT", which is why 3 of 16 cells skipped
  the field the model is *best* at. Now always required, with a targeted second extraction
  pass that re-reads the analysis for the sentence and is told in as many words not to
  compose one.
- **Channel B**: `REFERENCE_ARMS` runs the hand-written `c2_episode` hypothesis in the same
  table under the same controls. It is rejected too, and the verifier now says so on its own
  line — the bar rejects the expert, so a model latent failing it is not evidence about the
  model.

## 6 · What this changes about the plan

The bottleneck is not context and it is not, mostly, the language. Six of eight goals were
sayable and the model said something true at no solved board on ten of sixteen tries. The
one it got right, it got right — so the capability is not zero, and the instrument that
could not distinguish it from vacuity was the thing most in need of repair.

Still worth doing, in order: the **prose→DSL search** (13 free-form sentences and a
separator enumerator now exist on the same disk — this is a zero-model experiment), then
**re-run slice 3's protocol on 3.8** with this grader, which will report a number that means
something.

`--selftest` extended: strictness witnesses for the new relations (`coincident` differs from
`bbox_overlap` on 17,818 real object pairs, `covers` from `bbox_contains` on 8,909,
`strictly_inside` on 1,971) and 1,572 `none`/`exists` negation checks. Row-C agreement and
the counter reproduction are unchanged and still pass.

## 7 · Cost of the fixes to the prompt — re-asserted, and one cell moved

The grammar text gained the four relations, the `none` form and the strongest-relation
instruction; the free-form request is no longer conditional. That is **+351 tokens on every
cell**, and the pre-launch assertion was re-run against it:

| game | F was | F now | FB was | FB now | trim ladder |
|---|---:|---:|---:|---:|---|
| dc22 | 39,617 | 39,968 | 42,786 | 43,137 | 9 → 9 |
| ft09 | 28,574 | 28,925 | 31,682 | 32,033 | 0 → 0 |
| ls20 | 38,622 | 38,973 | 41,691 | 42,042 | 1 → 1 |
| m0r0 | 39,288 | 39,639 | 42,496 | 42,847 | 9 → 9 |
| **tu93** | 39,929 | **36,751** | 42,901 | 39,723 | **1 → 2** |
| vc33 | 38,811 | 39,162 | 42,518 | 42,869 | 3 → 3 |
| sp80 | 37,571 | 37,922 | 41,259 | 41,610 | 11 → 11 |
| lf52 | 39,018 | 39,369 | 42,767 | 43,118 | 10 → 10 |

All eight still fit both ceilings. **tu93 paid for it**: it had 71 tokens of headroom, the
+351 pushed it over, and the ladder took another step — its causal episode drops from 45
steps to 30. Seven cells absorbed the addition unchanged. That is the trade recorded rather
than discovered later: the relations that flipped vc33 cost tu93 fifteen episode steps.
