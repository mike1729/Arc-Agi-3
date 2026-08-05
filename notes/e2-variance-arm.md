# E2 variance arm — slice 1 rerun at seeds 1 and 2 (overnight)

**Task note 2026-08-04, lean mode. Self-contained; execute without further context.**
Qwen generation, ~3.6 h per seed; run overnight, unattended.

---

## ⚠ REPURPOSED 2026-08-04 late — this is now SLICE 1.1, the display-repair test

The autopsy (`notes/e2-trace-autopsy.md` §Results) landed before launch and explains
slice 1's failure **deterministically**: 59/84 proposals rest on reading the digest's
one-example row as a group constant, 55/84 on overriding the miner's unevidenced
no-separation assertion, and 5 of the 6 full-dose digests showed zero resolved rules
(majority-tier suppression; ft09/full — the one surviving cell — is the exception).
Rerunning slice 1 verbatim would measure the stability of diagnosed artifacts. The night
instead tests the autopsy's causal claims: **same protocol, only the digest/prompt
repaired** per its four recommendations.

**Already applied in the worktree** (on top of the seed patch; compile + digest renders
inspected):

1. Value SET per feature per effect group replaces the one-example row, with explicit
   "READ THE VALUE SETS LITERALLY" semantics (rec 1 — removes the 59/84 mechanism).
2. Every unresolved key ends with a NO-SEPARATION WITNESS: the best single feature shown
   failing on concrete counts, and the prompt says to treat these as constraints, not
   claims to argue with (rec 2 — removes the 55/84 mechanism).
3. The guard grammar is stated — `feature = literal`, equality only, no negation/
   threshold/combination (rec 3 — removes the 10 untestable-value deaths).
4. Each rule must state its support count and its refuter; extraction schema carries
   `support_claim` and `refuter` (rec 4 — logged, not used in verification).
5. The all-majority full-dose display now says so honestly instead of "none".

**Unchanged, deliberately:** worktree pinned at `25b44ce` with **v1 vocabulary** — vocab
v2 was adopted on main today (`notes/e2-dose.md` addendum), but tonight isolates ONE
variable (the display repair); v2 enters slice 2. Zero-tolerance verification unchanged.
Seeds, budgets, launch command, copy-back: all as below.

**Morning readout replaces the one below:**

1. Instrument: verdict pass count per seed (expect 12/12).
2. **The causal test:** per cell, do the traces still read example rows as constants or
   argue with the assertion? (The value-set display makes the first impossible to state;
   quote any recurrence.) Proposed / rejected / verified counts vs slice 1's 84/2/9.
3. Overfit check on every dose-125 survivor (`e2_overfit.py`) — the honest
   survives-full-evidence count, vs slice 1's 1/82.
4. `support_claim` vs measured support per proposal (is self-scoring calibrated?), and
   whether refuters are real observations.
5. Union deltas vs the **v1 floors** (in-worktree, comparable); ft09's cells additionally
   read against the v2 floor (0.3017 on-human-L1, `logs/e2_dose_vocab_v2.json`).
6. Goal/hidden-state/probe channels: any movement vs the autopsy's labels (2 correct
   goals / m0r0 hidden-state hit / 8 discriminating probes).
7. Verdict sentence: does repairing the display change what Qwen can contribute, or does
   failure persist through new mechanisms?

---

## What and why

E2 slice 1 (`notes/e2-slice.md`, commit `faa40ee`) is one sampled draw (seed 20260804,
temp 0.6): every limits section says a second seed could move every count. Two of its
findings are already being acted on — the 1-of-82-survives-full-evidence count and ft09's
missing-vocabulary diagnosis (now a build task, `notes/miner-vocab-v2.md`). This arm reruns
the identical protocol at 2 fresh seeds to measure whether those findings are stable or
luck. **Nothing about the protocol changes.** Deliverable = the cross-seed comparison.

## Pre-flight — ALREADY DONE, do not redo (2026-08-04 evening)

- Worktree `/Users/michal/Workspace/ship-variance`, detached at `25b44ce` — the slice-1
  code state. **Why pinned:** the main tree's `rs_e0.py`/`rs_transitions.py` are mid-rewrite
  (vocab v2); floors and verification must be byte-comparable to slice 1.
- Symlinks into the worktree: `data/` and `logs/e1_store_v2` (both gitignored, needed at
  load time).
- Seed patch applied **in the worktree only** (uncommitted there): `--seed` flag threaded
  through both phases; traces tagged `{game}_{dose}_s{seed}.think.json` (slice-1's
  committed traces cannot be overwritten); output defaults to `logs/e2_slice_seed{N}.json`
  with the seed recorded inside. Compile + `--dry-run` verified.
- The stray `mlx_vlm` server is killed; the 28 GB model has the machine to itself.

## Launch

```
cd /Users/michal/Workspace/ship-variance && nohup caffeinate -i sh -c \
  'for s in 1 2; do /Users/michal/Workspace/SHiP-JEPA-X/.venv/bin/python \
   agent/harness/e2_slice.py --seed $s >> logs/night_run.log 2>&1; done' \
  >> logs/night_run.log 2>&1 &
```

- `caffeinate -i` prevents idle sleep; `nohup … &` survives the launching session.
- Seeds are **1 and 2**. NEVER 20260804 (that is slice 1's draw). A third seed is allowed
  only if both finish with night left (~3.6 h each).
- Nothing else may load a model while this runs (RAM).
- If a seed crashes: rerun that seed whole — per-seed outputs are self-contained and
  overwrite their own files only. The JSON is written incrementally after every cell, so
  partial progress is inspectable in `logs/night_run.log` and the seed file.

## Morning readout (the deliverable — a results section appended to this note)

1. **Instrument:** thinking-verdict pass count per seed (expect 12/12; any void reported
   with its trace).
2. **Cross-seed table:** per cell — proposed / parse-rejected / verified, seed 20260804
   (from `logs/e2_slice.json`) vs seeds 1 and 2.
3. **Overfit check on every dose-125 survivor** (worktree `agent/harness/e2_overfit.py`,
   zero model calls): the honest survives-full-evidence count per seed. This is the number
   that decides stability of "1 of 82".
4. **ft09 reproducibility:** parse-rejection reasons per seed, and whether the trace again
   names a per-component adjacency gap — quote the trace verbatim if so. This decides
   whether the vocab-v2 feature rests on one draw or a stable diagnosis.
5. **Union-delta spread** on human L2 across seeds, and any high-support/low-contradiction
   kills à la tu93 (312/7) — collected as measured inputs to the slice-2 repair-bar
   decision, not judged here.
6. **Two verdict sentences:** is 1-of-82 stable? is the vocabulary diagnosis reproducible?

## Copy-back and cleanup (after the readout)

- Copy `logs/e2_slice_seed1.json`, `logs/e2_slice_seed2.json`, and all `*_s1.*`/`*_s2.*`
  trace files from the worktree into the main repo's `logs/` (the existing
  `e2_slice_traces` gitignore exception covers them).
- Apply the seed patch to the main repo's `e2_slice.py` (both day agents leave that file
  untouched) and commit patch + results + this note's results section together.
- `git worktree remove /Users/michal/Workspace/ship-variance` (force if the night log
  should not be kept; copy `night_run.log` first if a crash needs diagnosing).

## Non-goals

Protocol, prompt, budget or model changes · any interaction with the vocab-v2 or autopsy
tasks · conclusions beyond the seed comparison · running against the main tree.

---

# Results — slice 1.1, display repair, seeds 1 and 2 (2026-08-05)

Ran overnight in the pinned worktree, v1 vocabulary, unattended. Seed 1 finished 01:25,
seed 2 04:56, ~3.5 h each, no crashes and no reruns. Model Qwen3.6-27B-8bit, temp 0.6.

**A launch error worth recording:** the first launch (21:34) started before the display
repair was written to disk (21:44) and was therefore running slice-1 code. It was killed in
its first cell, before any output was written; no partial data entered this run. The
relaunch at 22:07 is the run reported here. *Check the mtime of the code against the process
start time, not just the file contents.*

## 1. Instrument — 24/24 pass

Every phase-1 trace: `think_opened` ✓, `think_closed` ✓, `prefilled_empty_think` false,
`think_substantive` ✓. Zero voids across both seeds. Think length 19.5k–35.4k chars
(median ~26k), generation ~9 tok/s. The instrument rule held.

## 2. The causal test — the diagnosed mechanism is gone; failure is not

Headline counts, against slice 1's 84 proposed / 2 parse-rejected / 9 verified:

| | proposed | parse-rejected | verified (at own dose) |
|---|---:|---:|---:|
| slice 1 (seed 20260804) | 82* | 2 | 9 |
| seed 1 | 57 | 0 | 4 |
| seed 2 | 51 | 0 | 7 |

\* the note's "84" counts the 2 parse-rejected; `logs/e2_slice.json` sums `proposed` to 82.

**Parse-rejections: 2 → 0 → 0.** Stating the guard grammar (rec 3) removed the
untestable-value deaths outright. This recommendation worked, cleanly and cheaply.

**Mechanism 1 (example row read as a group constant): displaced.** No trace states the
slice-1 inference. Where slice 1 said *"it only shows one value per feature. This implies
the feature was constant"*, the traces now read the sets as sets and quote the instruction
back — vc33/125 s2: *"Let's look at the feature sets literally: 'for each effect group,
each feature is shown with the COMPLETE set of values it takes within that group.'"*
Rec 1 did what the autopsy predicted.

**But an isomorphic mechanism replaced it: inference from absence.** The traces now reason
about features the display does *not* list, and assume unlisted ⇒ constant ⇒ cannot
separate. vc33/125 s2: *"It doesn't list `adj:0:down` etc. in the witness, meaning they were
constant across all 13 transitions. If they were constant, they can't separate."*
tu93/125 s2 and dc22/125 s1 make the same move. Present in 21/24 traces by pattern scan.

This inference is **unsound, and the prompt causes it.** `build_digest` shows only the
first `MAX_FEATURES_PER_GROUP = 6` *varying* features (`e2_slice.py:238`), while the prompt
asserts each feature is shown with its complete value set. Two mechanical proofs that the
display is incomplete:

- 436 of 534 effect-group feature lines show exactly 6 features — sitting on the cap.
- In **14 unresolved-key blocks the NO-SEPARATION WITNESS names a feature the display never
  shows** (dc22: witness `adj:14:up`, shown `adj:13:{down,left,right,up}`, `adj:14:{down,left}`).
  The witness selects from all varying features; the group rows are capped at 6.

So the repair traded a false claim the model could see for a false claim it cannot: slice 1
showed one value and let the model infer constancy; slice 1.1 shows six features and
asserts completeness that does not hold.

**Mechanism 2 (arguing with the miner's assertion): reduced but alive — 8/24 traces**
(slice 1: 55 of 84 proposals). The witness gives the assertion evidence and mostly works.
Where it fails, the trace has a *partially legitimate* complaint. ls20/125 s2:

> ACTION1: E1 (x24): adj:12:up={3}  E2 (x6): adj:12:up={None}  This is a perfect split!
> Why did the miner say it fails?

The display does show `adj:12:up` cleanly splitting the two dominant groups (24+6 of 32),
while the witness names a weaker feature (`adj:11:left`) as "the best". The miner is not
wrong — two singleton groups also carry `adj:12:up={3}`, so no single guard separates all
four effects — but "best single feature" is chosen by full separation, which makes the
witness look defeated by a partial split. The model over-reads a 2-of-4 comparison; the
display invites it.

## 3. Overfit check — the decisive number (`e2_overfit_seed.py`, zero model calls)

| | proposed | survives own dose | **survives FULL evidence** |
|---|---:|---:|---:|
| slice 1 | 82 | 9 | **1** |
| seed 1 | 57 | 4 | **3** |
| seed 2 | 51 | 7 | **3** |

Seed 1: 3 of 4 dose-125 survivors hold, 1 refuted (ft09 `A6:9|adj:12:right=11` — support 3
at 125, 118 support / **63 contradictions** on the full store). Seed 2: **all 4** dose-125
survivors refuted (tu93 ×3, vc33 ×1); its 3 come from dose-full, already full-evidence.

**The count went 1 → 3 → 3, and this is not an improvement.** Every one of the six new
survivors has **support 1** — a single backing transition:

```
s1 tu93/125  A:1|adj:6:right=edge   support 1     s2 tu93/full A:1|adj:6:right=edge  support 1
s1 tu93/125  A:2|adj:6:right=edge   support 1     s2 tu93/full A:2|adj:6:right=edge  support 1
s1 tu93/125  A:4|adj:6:right=edge   support 1     s2 tu93/full A:3|adj:6:right=edge  support 1
```

Slice 1's single survivor was `ft09/full A6:8|count:8=16` at **support 26**. A support-1
rule survives zero-tolerance verification because there is almost nothing for it to
contradict, not because it is right. On rule quality the repaired display did **worse**:
3 vacuous survivors per seed against 1 substantive one.

## 4. Self-scoring (rec 4) — well-formed and inert

102 of 108 extracted proposals carry both `support_claim` and `refuter`. Pairing each claim
against measured support on the store it was shown:

- **exact 65 · overclaim 37 · underclaim 0** — the error is one-directional.
- **17 proposals have zero measured support**; their median *claimed* support is **53**.
- Worst: vc33/full s2 `A6:None` claimed **736**, measured **0**. ls20/full s2 claimed 531,
  519, 479, 398 on four rules, all measured **0**.
- Claimed support median 11, measured 6.

Refuters are correctly *typed* — they name the observation that would kill the rule
("Any state where `adj:12:up = 3` but 9 and 12 do not move") — but they are negations of
the rule restated, not checks the model ran. Several rules whose refuter was already
satisfied by the store in front of them were proposed anyway. **The channel produces valid
falsifiers and never applies them**; logging it (as designed) is right, and it is not
evidence of calibration.

## 5. Union deltas vs the v1 floors — 23 of 24 cells move nothing

Human L2, union vs floor, per cell: **+0.0000 in 23 of 24 cells.** The single movement in
the entire run is **tu93/full seed 2: 0.5768 → 0.5843 (+0.0075)**. Unresolved-key delta is
0.0 in every cell of both seeds except that one (+0.008 on n=248).

ft09 against the v2 floor: all four ft09 cells sit at v1 floor 0.2522 with union = floor,
i.e. **no cell reaches the vocab-v2 floor of 0.3017** (`logs/e2_dose_vocab_v2.json`). The
vocabulary rebuild delivers, without the model, more than the model delivered on this game
at either dose or either seed.

## 6. Unscored channels — one stable hit, and it is the hidden-state channel

*My adjudication against each game's completion condition as characterised in the autopsy;
same rubric, but a different reader from the autopsy's, so treat the goal split as indicative.*

- **Goal: no stable reproduction.** Slice 1's 2 correct were both tu93, reasoning from
  colour 14's inertness. Here tu93 yields at most one partial hit (seed 2/125 — *"positioning
  6 (or 0) adjacent to 14"* — reaches the marker but not the movers-onto-exits condition);
  seed 1's two tu93 cells and seed 2/full miss, the last to the *clear the board* prior the
  autopsy flagged. That prior remains dominant across dc22, ft09, ls20, vc33 in both seeds.
- **Hidden state: m0r0 reproduces 4/4 — the most stable result in the run.** Every m0r0 cell
  in both seeds names the parity/turn-counter mechanism, and the game's declared hidden
  state is an action count whose parity drives a mode switch. Seed 1/full is the sharpest:
  *"step_count (or turn_index / phase), which advances with every action but is not hashed
  into the frame."* Seed 2/125: *"A global binary flag or turn parity counter."* m0r0 is
  the only game whose digest records alias conflicts — the channel answers correctly
  exactly where the display gives it something real to answer from.
  Counter-example worth noting: ft09/full s1 converts absence of conflicts into a positive
  claim — *"there are no hidden counters, timers, or off-screen variables"* — which is
  false for the game and unlicensed by the evidence.
- **Probes: 21 of 24 discriminating** (s1 11/12, s2 10/12), the rest out-of-band requests for
  instrumentation rather than actions (s1 ls20/full, s2 dc22/125 and dc22/full). Most name a
  genuine controlled contrast — s2 ls20/full: *"two carefully constructed states where
  `adj:12:up = 3` is true in both, but `count:3` differs."* Consistent with slice 1: the probe
  channel is the strongest output in the run, and `e2_slice.py` still does not score it.

## 7. Verdict

**Repairing the display changed the failure mode, not the outcome.** The two diagnosed
mechanisms behaved as the autopsy predicted — the example-row misreading is gone, the
grammar statement zeroed parse-rejections, the witness cut assertion-fighting from 65% of
proposals to 8 of 24 traces — and the measured contribution still rounds to nothing: 23 of
24 cells move the floor by 0.0000, the one that moves gains +0.0075, and the honest
survivor count rose from 1 substantive rule to 3 rules of support 1 per seed. Proposal
volume fell by a third, which is the repair working; what remains is not better.

**The bottleneck is not the model's reasoning and, on this evidence, not fixable by
display edits.** Each repair relocated the error: capping features at 6 while asserting
completeness turned "one row read as a constant" into "unlisted read as constant", and the
witness's full-separation criterion invites the model to beat it with a partial split.
Two candidate follow-ups, both cheap and neither run here: state the truncation honestly
(or lift the cap), and report the witness as *best partial* separation with its counts. But
the pattern across slice 1 and 1.1 is that the digest is not where the missing capability
is — ft09's v2 floor (0.3017) beating every ft09 cell the model produced (0.2522) says the
same thing from the other side.

## Copy-back — one deviation from the plan

The note assumed "both day agents leave `e2_slice.py` untouched". **They did not:** the
vocab-v2 agent added `clicked_adjacent_to:` to `GUARD_PREFIXES` and to the digest's
vocabulary sentence (`f025154`), overlapping the exact line the display repair edits. The
patch was applied to main as a **3-way merge, not a clobber**; the single conflict was the
vocabulary sentence and both changes are kept (v2's new feature *and* the grammar +
value-set semantics). Merged file parses and `--help` runs.

**Consequence to decide in slice 2:** main's `e2_slice.py` now produces the repaired digest
by default, including the completeness assertion that §2 shows to be false while
`MAX_FEATURES_PER_GROUP = 6` silently truncates. It was kept as-run for reproducibility of
these results. Fixing or reverting it is a slice-2 decision, not made here.

## Addendum 2026-08-05 — the §2 defect is fixed in `e2_slice.py` (not yet re-measured)

Operator direction after the readout: fix the completeness assertion and lift the feature
cap. Both done; **no model has been run against the fixed digest**, so nothing below is a
result.

**The cap was hiding most of the evidence**, not a tail of it — varying features per
unresolved key, against the cap of 6:

| game | dose 125 (min/med/max) | dose full (min/med/max) |
|---|---|---|
| dc22 | 7 / 12 / 16 | 11 / 11 / 19 |
| tu93 | 10 / 10 / 10 | 10 / 10 / 10 |
| m0r0 | 4 / 7 / 10 | 8 / 8 / 12 |
| ls20 | 5 / 5 / 6 | 6 / 6 / 6 |
| vc33 | 2 / 3 / 5 | 4 / 6 / 8 |
| ft09 | — | 5 / 5 / 5 |

dc22 showed 6 of up to 19. Only ft09 and vc33/125 were fully shown — which is consistent
with ft09/full being slice 1's one substantive survivor and the one trace the autopsy found
holding the correct semantics.

**Changes:**

1. `MAX_FEATURES_PER_GROUP = 6` → `None`; every varying feature is now listed. This does not
   merely remove a falsehood, it makes the traces' own inference-from-absence **sound**:
   absence now really does mean constant across the key.
2. The prompt states what the display does, and no more than that: absence ⇒ constant across
   the key *and nothing else*; `+N more` marks a truncated value set and an unmarked set is
   complete; only the {MAX_EVIDENCE_PER_KEY} largest effect groups appear, detectable by
   comparing against the distinct-effect count in the header.
3. The witness is relabelled from "the best single feature" to the one that comes **closest**,
   with the failure mode named: *"a feature that splits two groups cleanly can still fail the
   key, because separating the key means telling ALL of its effects apart."* That is the exact
   over-reading ls20/125 s2 made.

`MAX_VALUES_PER_FEATURE = 4` is kept — it never fired in the run (0 of 24 prompts contained
`+N more`) and it is now declared rather than silent.

**Cost, measured** (digest renders, no model): dc22/125 **11,760 → 17,741 chars (+51%)**,
tu93/125 5,367 → 7,066 (+32%), vc33/125 4,087 → 5,255 (+29%). Growth tracks how much the cap
was hiding, so dc22 — the game with up to 19 varying features — pays most. `THINK_BUDGET` (16384) is unchanged and
was not re-checked against the longer prompt.

**Open, and deliberately not decided here:** whether the larger digest helps, hurts, or
merely costs tokens is a slice-2 measurement, and it should be run as one — the lesson of
slice 1.1 is that a display change which is obviously correct on inspection moved nothing
measurable. Verified so far: the digest renders, the constants interpolate, `--help` runs.

## Limits

Two seeds, one temperature, one model, v1 vocabulary, public games. The goal/probe
adjudication in §6 is a judgment call by a different reader than the autopsy's, on 24 items;
the hidden-state and count results in §1–§5 are mechanical. `e2_overfit_seed.py` is a
seed-parameterised copy of `e2_overfit.py` with identical logic. The support-1 observation
in §3 is the load-bearing one and rests on the recorded `support_on_store` values.
