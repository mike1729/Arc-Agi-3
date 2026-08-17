# Qwen3.8-27B night 1 — bring-up gate + slice 3R, the generation contrast

**2026-08-16. Execution plan for tonight; nothing below has run.** Working numbers labelled
(w). This executes the pre-planned rerun (`notes/qwen-3.8-upgrade.md`) as amended by what
happened after that note was written: slice 3 ran on 3.6, its grader was found
one-directional and fixed, and the night was re-graded (`notes/e2-slice3.md`, FIXES
2026-08-06). The highest-value 3.8 night is therefore **slice 3's protocol under the fixed
two-directional grader** — not the original slice-1.1R, which slice 3 supersedes as the
strongest instrument with an existing 3.6 baseline. Slice 3's own cautions section already
says this: *"whatever tonight says, this protocol reruns on 3.8 as the generation
contrast."*

**The question, stated so either answer closes it:** on the best evidence record this
system can assemble, graded by an instrument that can see a correct answer, does Qwen3.8
move any channel Qwen3.6 failed — in particular the goal channel, which is S1's deployed
bottleneck (`goal_unknown`)? With 3.6 the M-phase synthesizer contributes ~nothing beyond
the mechanical miner; tonight decides whether that verdict is about the generation or
about the approach.

## What is already known, and what tonight must beat

**3.6 baselines under the FIXED grader** (the 08-05/06 night, re-graded 08-06 — computed,
not re-run):

| metric | Qwen3.6 |
|---|---|
| channel A two-direction correct | **1/16** (lf52 s2) — 1/11 of answerable cells |
| channel A vacuous (fires at no solved board) | 10/16 |
| unreachable (no separator exists in grammar) / prose_rejected | 4 / 1 |
| free-form goal correct-in-kind | 3/13 (+3 partial) — the field was conditional then, always-on now |
| channel C targeting (real unresolved key) | 16/31 (52%) |
| channel C value (features built, miner adoption) | **failed** — v3 39/48 clean, v2 stays floor |
| arm FB substantive repairs | 0/5 (old arm — **redesigned since; tonight's FB has no 3.6 baseline, report only**) |
| instrument | 16/16 verdicts · 0 voids · parse 15/16 · think 19.8k–36.7k chars · decode 8.3–8.6 tok/s · prefill 335–379 tok/s · mean 1,317 s/cell |

**Zero-model machinery the model must add value over:** `e2_expressibility.py` finds
separators without any model on 6/8 games (4–323 candidates each); ft09 and m0r0 are
inexpressible in vocab v2 (closest miss 12.9% / 3.0%). `e2_positives.py` holds 4–11
distinct solved L1 boards per game. A model that merely re-finds an enumerable separator
adds nothing; the value would be selection among ambiguous candidates, coverage of the
inexpressible games via free-form, or repairs under contradiction.

**Weights: NOT on disk** (`~/models/mlx/` has only 3.6). Available:
`mlx-community/Qwen3.8-27B-8bit` and `-4bit` on Hugging Face; lmstudio-community has a
4-bit too. ⚠ **Qwen3.8-27B is a vision-language model** (262k native context), and the
community MLX conversions were produced with **mlx-vlm** — the same library family whose
server path caused the July non-thinking disaster. Whether `mlx_lm` loads the text tower
directly is unknown until tried. **The thinking probe is the arbiter, not the loader's
documentation.** Nothing about tonight uses the vision tower; text rendering only, as
always.

## Phase 0 — prep (afternoon; start the download FIRST, everything else while it streams)

0. Download both quants to `~/models/mlx/Qwen3.8-27B-{8bit,4bit}` (~30 + ~18 GB (w);
   583 GB free). Record the HF repo revisions here when done.
1. Prep patches on main, small and committed BEFORE the worktree is cut:
   - `e2_regrade_slice3.py` hardcodes `logs/e2_slice3_seed{seed}.json` (`:119`) — add a
     `--results` path template so 3.8 outputs are gradable without touching 3.6 files.
   - Verify the result JSON records the model path (comparability rule: model column
     everywhere). If it doesn't, add it.
   - Verify `--dry-run --model <3.8>` threads `args.model` into `chat_tokens()` /
     `tokenizer()` (`e2_slice.py:1196`) so cap accounting uses the **3.8 tokenizer**.
     Tokenizer-only load — this runs before weights finish downloading.
   - Nothing else in `e2_slice.py` changes. The protocol is frozen for the contrast.
2. Worktree: `git worktree add ~/Workspace/ship-38night <prep-commit>` and **symlink
   `data/` and `logs/`** (gitignored, absent in a fresh worktree; every harness fails
   without them). The slice-3 lesson: commit first, pin, then re-verify inside the
   worktree — never run uncommitted code at night.
3. In-worktree zero-model gates: `--selftest` · slice-2 byte-repro 8/8 · contamination
   grep 0 hits across the 8 rendered prompts.
4. **Chat template inspection**: diff 3.8's `tokenizer_config.json` template against
   3.6's — think-tag handling, `enable_thinking` semantics, image-slot tokens a VLM
   template may inject. Do not assume anything carried over. **Never constrain the first
   decoded token.**
5. Optional filler while the download runs: the prose→DSL search from the slice-3 fixes
   (zero-model, model-independent, still undone). It does not gate tonight.

## Phase 1 — bring-up gate (early evening, ~1.5 h; no gate pass → no night)

> **Executed variant, 2026-08-16 (operator asleep before weights landed):** the gate and
> the night run as one self-gating chain — `agent/harness/night38_chain.sh` (committed,
> pinned in the worktree) waits for the download, then probe → budget probe → seed 1 →
> seed 2, aborting on any gate failure. **Deviations, recorded:** the 4-bit probe and
> the quant comparison are deferred — 8-bit is pinned (w) on the deploy-fidelity
> rationale alone, and gate step 3's 8v4 envelope contrast moves to a day task; the
> slice-2 byte-repro gate was not re-run (the unframed path is not exercised tonight);
> the probe runs `--max-tokens 4000`, not 1500 — 3.8's template defaults
> `reasoning_effort` to xhigh and a trivial-prompt think outrunning 1500 would fail the
> gate for the wrong reason.

1. **Load check**: does `mlx_lm.load` accept the conversion? If not, the fallback
   (mlx-vlm text-only path) must **still pass the probe** — the July failure lived in
   exactly that neighbourhood, so a fallback loader gets zero benefit of the doubt.
2. **Thinking probe**, one output file per quant — every 3.8 command in this note names
   an explicit `_38` output; the probe/budget-probe/regrader defaults all point at
   tracked 3.6 artifacts, and a defaulted run has already eaten a result file once
   (2026-08-05):
   `e2_probe.py --model ~/models/mlx/Qwen3.8-27B-8bit --out logs/e2_probe_38_8bit.json`
   then `--model .../Qwen3.8-27B-4bit --out logs/e2_probe_38_4bit.json`.
   PASS = template opens `<think>`, no pre-filled empty think block, substantive body,
   closed, answer present.
3. **Envelope**, both quants, standard probe: think length, decode tok/s, prefill tok/s.
   On 3.6, 8bit thought 2.7× longer than 4bit on the identical prompt — quantization
   changes reasoning *behaviour*; re-measure, don't inherit.
4. **Quant pin (w)**: default 8bit (deploy-fidelity rationale, same as the line's 3.6
   pin) unless the probe shows pathology; rationale recorded here either way.
5. **Budget probe** (`e2_budget_probe.py --model <3.8-8bit>
   --out logs/e2_slice38_budget_probe.json`) on the largest re-rendered cell:
   think must close inside `THINK_BUDGET = 16384` (`e2_slice.py:112`). If it doesn't:
   set it to measured closure ×1.25 (w), commit in the worktree pin, record as a
   deviation. Never truncate thinking silently; never raise unilaterally beyond that.
6. **Re-render all 8 cells with the 3.8 tokenizer** (`--dry-run --model <3.8>`): the
   token counts and trim-ladder steps **will** differ from the 3.6 table — different
   tokenizer, expected, recorded. Caps stay **F ≤ 40,000 / FB ≤ 45,000** (protocol
   identity). All 8 must fit; a cell still over cap after the full ladder is skipped and
   recorded — `--allow-over-cap` is not used at night. The rendered table lives in
   `logs/e2_slice38_dryrun.json` (worktree) with stdout captured beside it — the
   pre-launch assertion, 3.8 edition; the morning readout copies it into this note.
7. **Wall go/no-go (w)**: window ≈ 9 h. Projection = 16 × (40k/prefill + think·answer/
   decode) + up to 16 FB turns. At 3.6 speeds the night was ~7.5 h with 5 FB turns; the
   fixed FB arm can fire on more cells (up to one per failed channel-A cell, both seeds),
   so budget FB ≈ 2–3 h (w). If the projection exceeds the window: protocol order already
   protects the result — **seed 1 complete including its FB turns first**; a truncated
   seed 2 is a smaller readout, not a void. If projection > 2× window (e.g. VLM decode
   overhead), run seed 1 only and say so.

## Phase 2 — the night

```
cd ~/Workspace/ship-38night
nohup caffeinate -is .venv/bin/python agent/harness/e2_slice.py \
  --frames --feedback --seed 1 \
  --model ~/models/mlx/Qwen3.8-27B-8bit \
  --latent-spec logs/e2_slice38_latents_seed1.json \
  --out logs/e2_slice38_seed1.json > logs/e2_slice38_seed1.nohup 2>&1 &
```

then seed 2 → `--seed 2 --latent-spec logs/e2_slice38_latents_seed2.json --out
logs/e2_slice38_seed2.json`, sequential, only after seed 1 finishes. `--out` **and**
`--latent-spec` explicit always — the spec file is written only when the flag is given,
and channel B's readout is impossible without it (`_38` paths; **3.6 artifacts are never
overwritten**). Voids are logged and never rerun mid-night; no mid-night code
edits; the worktree pin is the code that ran.

## Phase 3 — morning readout (zero-model)

- Regrade both seeds two-directionally against the human corpus:
  `e2_regrade_slice3.py --results "logs/e2_slice38_seed{seed}.json"` — the default
  output derives to `logs/e2_slice38_regraded.json` (never the 3.6 path), and cells the
  night never answered (over-cap skip, thinking void, unparsed extraction) come out as
  **missing observations** — `skipped`/`void`/`unparsed` verdicts outside every
  denominator — not as model failures.
- Channel B latents through the verifier, explicit paths per seed:
  `e2_latent_verify.py --spec logs/e2_slice38_latents_seed{n}.json --out
  logs/e2_slice38_latents_seed{n}_verified.json`, against the 5 seeded controls, with
  the REFERENCE_ARMS line printed (on m0r0 the bar rejects the expert hypothesis — a
  3.8 rejection there is still evidence about the game, not the model).
- Free-form goals adjudicated against source (labels/paraphrase only), same as 08-06.
- Contrast table with a **model column** (the comparability rule is absolute):
  A correct / vacuous · free-form correct-in-kind · C targeting · FB substantive repairs
  + `retreat_into_library` counts (3.8-only line) · instrument counters · think length ·
  tok/s. Per-game coverage caveats (`unresolved keys shown/total`) attach to any
  budget-starved cell, not pooled — same rule as the 3.6 night, and the 3.8 tokenizer may
  starve *different* cells.

## Decision rules — written now so the morning doesn't rationalize (all (w); operator may reset them before launch, not after the readout is open)

- **Denominators are pre-committed.** The /16 thresholds below apply only to a
  **complete night**: every cell graded or explicitly missing-marked, both seeds, FB
  wherever eligible. **Seed 1 alone but complete (8 cells):** improvement = A ≥ **2/8**
  spanning ≥2 games, or free-form correct-in-kind ≥ **4/8**; feasibility signals (a)
  and (c) are existence proofs, valid on any completed subset; (b) stays ≥4 games (each
  game runs once per seed). **Any smaller fragment, or more than 2 missing observations
  on a seed: descriptive only — no threshold fires in either direction.** Missing
  observations (skipped / void / unparsed — the regrader marks them) join no
  denominator, ever; "flat" must never be an artifact of absent data.
- **"Improvement over 3.6"** = channel A ≥ **4/16** two-direction correct spanning ≥2
  games (vs 1/16), **or** free-form correct-in-kind ≥ **8/16** (vs 3/13 when the field
  was conditional). Channel C targeting is secondary — it was already alive on 3.6 and
  its value half failed miner adoption; a targeting delta alone changes nothing.
- **"Feasibility signal"** — the M-phase synthesizer earns a place only if it adds
  something the zero-model machinery lacks. Any one of:
  - **(a)** a source-correct goal on an enumeration-inexpressible game (**ft09, m0r0**),
    free-form counts;
  - **(b)** DSL predicates two-direction correct on ≥ **4 games** — selection value over
    the enumerator's 4–323-candidate ambiguity;
  - **(c)** ≥1 substantive FB repair with `retreat_into_library = false`.
- **Improvement + ≥1 feasibility signal →** next nights, in order: **3.6 rerun on the
  identical fixed interface** (attribution — tonight's interface has +351 tokens,
  always-on free-form, and the extended grammar the 3.6 night lacked; a 3.8 *win* is
  unattributable without this rerun; a *loss* closes the operational question without
  it, though a paper-cited contrast needs it too — next bullet), then mini-S1 (P3 of
  the upgrade note: does `goal_unknown` persist with 3.8 as actor?), then probe
  regeneration (P2).
- **Flat on a complete night →** the *operational* verdict: the synthesizer role closes
  for 3.8 as it did for 3.6, every (3.6) verdict gains a (3.8-checked) tag, and the
  line continues zero-model — miner v2 floor, separator enumerator, E3 executor/search.
  Reported as what it is: **no improvement under a strictly more permissive interface
  than 3.6 ever ran.** Flat on an incomplete night → inconclusive; finish the missing
  cells the next night before any closing verdict.
- **What is frozen across generations is the GRADER, not the inference interface.** The
  3.6 night ran conditional free-form and the pre-08-06 grammar; regrading its answers
  does not retroactively give it tonight's interface. A **paper-citable generation
  contrast** — win *or* flat — therefore requires the 3.6 rerun on this exact
  interface. Until that runs, tonight's number is an upper-bound comparison (3.8 on the
  better interface vs 3.6 on the worse one): decision-grade for the operational calls
  above, not claim-grade.
- **Gate fail** (no real thinking on either quant on any load path): no night; logged
  same-day with the failing path's evidence, and the model verdict is "3.8 bring-up
  failed on <path>" — a serving-path fact, never a capability claim. The July lesson,
  applied in the direction that protects 3.8 this time.

## Not tonight (pre-stated)

mini-S1 (gated on tonight's result) · probe-executor regeneration (P2) · vision tower in
any form · any training on public games · budget raises beyond the gate's measured
closure rule · new features for the miner (a fresh 3.8 channel-C queue is a *day-after*
zero-model task, and only if targeting holds).

## Cautions carried forward

- **PUBLISHING**: prompts and thinks contain rendered boards — raw traces stay in the
  worktree; only scored JSONs (counts + structured answers, no grids) are committed.
  Check the diff before pushing.
- Every number tonight is tagged **(3.8, quant as pinned)**; envelope numbers stated per
  quant; never mix generations in a table without a model column.
- Concurrent sessions: `git status` before committing; stage own files only.
- `[verify]` discipline: the ~9 h window, download sizes, and FB-hour budget are (w)
  until measured tonight.

---

# PHASE 0 EXECUTION RECORD — 2026-08-16, dispatched before the operator slept

**Weights, pinned:** `mlx-community/Qwen3.8-27B-8bit` rev `815b83c0df8ffd1d1b5244cf75fd6ef14fca9ef9`
(29.5 GB) · `-4bit` rev `3e6447f082e89cc7f0bc6e5441afd38dfce760ff` (16.1 GB) →
`~/models/mlx/Qwen3.8-27B-{8bit,4bit}`, snapshot pinned to those revisions; 8-bit first,
4-bit chained after (its arrival does not gate anything tonight).

**Chat template, diffed 3.6 vs 3.8 before weights landed (config-only download):**

1. **The generation tail is identical** — `<|im_start|>assistant\n` then `<think>\n`,
   with the empty-think prefill only under `enable_thinking=false`. The
   `enable_thinking` semantics carried over; the probe still arbitrates.
2. **New `reasoning_effort` knob, default `xhigh`** when thinking is on, which injects
   an instruction sentence into the system turn — creating that turn when absent, so
   **every 3.8 prompt gains a system message no 3.6 prompt had**. Decision (w): leave
   the knob at its default; `chat_tokens()` and `Qwen.generate` render through the same
   template, so accounting matches generation. Filed under the grader-vs-interface rule.
3. **`preserve_thinking` default flipped to true** (3.6 stripped assistant-history think
   text; 3.8 keeps it) — **inert here**: the FB assistant slot carries only the
   post-think answer (`e2_slice.py:2290`), so there is nothing to preserve.
4. transformers 5.14.1 verified to load 3.8's **separate** `chat_template.jinja` (3.6
   carried the template inline): renders the xhigh sentence, opens `<think>`, no
   prefilled empty block, honours the `reasoning_effort` kwarg.
5. **3.6-27B is itself a VLM** (same preprocessor/video configs on disk) — `mlx_lm`
   loading a VLM's text tower is already this stack's working state, which de-risks the
   3.8 load; the probe still decides.

**Prep patches (committed with this note):** `e2_regrade_slice3.py` gains `--results`
(input template; default `--out` derives `_seed{seed}.json → _regraded.json`, so a 3.8
regrade can never land on the 3.6 path) and missing-observation verdicts —
`skipped`/`void`/`unparsed`/`no_answer` for cells with no `channel_a`, outside every
denominator, no crash on absent fields. Verified: default 3.6 regrade byte-identical
(modulo the new `results` provenance field); a synthetic file exercising all four
missing shapes grades cleanly; a template without the `_seed{seed}.json` suffix refuses
to guess an output. Struck off as already correct: the result JSON records the model
(`e2_slice.py:2622`); cap accounting threads `args.model` (`:2478`, `:2503`).

**Review round (operator, five findings, pre-launch):** P1×3 fixed — explicit `_38`
outputs on every command including per-quant probes, `--latent-spec` added to the launch
command, regrader missing-observation support. P2×2 folded into the decision rules —
pre-committed denominators for truncated nights, and the frozen-GRADER-vs-interface
distinction with the paper-citable-contrast requirement.

**In-worktree gates and dispatch log follow in the morning readout.**

---

# NIGHT-OF DEVIATIONS — 2026-08-16 22:27–23:0x, recorded as they happened

1. **Budget gate FAILED under xhigh (22:27).** m0r0: the think block was still open at
   **55,674 chars** when the 16,384-token budget exhausted; no answer was reached. The
   same cell on 3.6: closed at 6,177 tokens / 21,284 chars. First real 3.8 behavioral
   datum of the night: **xhigh-default thinking is ≥2.6× 3.6's volume on identical
   input, and does not fit the slice-3 envelope.**
2. Closure re-measurement at 32,768 was launched per phase-1 step 5, then **stopped
   before completion** — superseded by the operator decision below; no output written.
3. **Operator decision (awake, ~22:45): pin `reasoning_effort="medium"`.** Rationale:
   xhigh is unaffordable at ARC evaluation regardless of what it would score tonight,
   so the measured regime should be the affordable one. Supersedes phase-0's "leave the
   knob at template default (w)". Bonus recorded at pin time: **medium injects no
   instruction sentence** (xhigh and low both do), so the phase-0 injected-system-turn
   confound disappears — medium is the 3.8 interface closest to what 3.6 ran. `low`
   is fallback only: it instructs brevity, and suppressed thinking is the July failure
   direction. Implemented as `REASONING_EFFORT = "medium"` passed at both template call
   sites (`Qwen.generate`, `chat_tokens` — accounting and generation stay consistent).
   Verified before commit: medium renders no system turn and still opens `<think>`;
   the 3.6 template is byte-identical with and without the kwarg.
4. **THINK_BUDGET stays 16,384, un-raised.** The relaunch runs the FULL chain — the
   budget gate must re-pass under medium; `SKIP_GATES` exists but is not used, because
   the knob changed the thinking regime and tonight's earlier gate results describe
   xhigh. The thinking probe's envelope numbers (4,554-char think) are xhigh-era too.
5. **Model column for every number tonight: (3.8, 8bit, medium effort).** The xhigh
   dry-run table above records a superseded render; the relaunched budget probe's
   per-game sizing under medium is the operative count (~40–60 tokens lighter per
   cell). If medium reads flat in the morning, an xhigh one-off contrast is a possible
   day-after decision — it is not tonight's question.

6. **Medium also failed the gate (23:38), and the effort ladder was measured to closure
   (00:4x).** The full m0r0 series, one cell, one prompt (39,681 tokens), all measured
   tonight — Qwen3.6's same-cell baseline: closed at 6,177 tokens / 21,284 chars:

   | regime | at 16,384-token cutoff | closure |
   |---|---|---|
   | 3.8 xhigh (default) | think open at 55,674 chars | not reached |
   | 3.8 medium | think open at 46,823 chars | not reached |
   | 3.8 low | — | **CLOSED at 15,735 tokens** / 49,856 chars, answer 6,143 chars |

   **The knob works but weakly, and even brevity-instructed 3.8 thinks 2.4× 3.6's
   volume.** The suppression worry that made `low` "fallback only" is empirically
   retired for this content — 49,856 chars is not a suppressed think. Escalating to
   `low` executes the operator's affordability directive at its own next step; the
   deviation from "medium, low as fallback" is this record.
7. **THINK_BUDGET re-pinned 16,384 → 19,669** = measured closure × 1.25, the note's own
   phase-1 remedy. 15,735 against 16,384 is 4% headroom; per-cell variance (3.6's
   thinks spanned ±40% around their median) would void cells all night.
8. **Relaunch (~00:5x, pin `<this commit>`) uses `SKIP_GATES=1`**: the thinking probe
   passed twice tonight on these weights, and the low-regime closure measurement IS the
   budget-gate evidence — re-running the gate would re-prove tonight's own record at
   ~45 min a pass. Chain edit records this in its log line.
9. **Envelope caution (w, inferred, morning must confirm from the cells' recorded
   `prompt_tps`):** the gate cycles' wall times imply warm prefill ≈ **44 tok/s** on
   this conversion — ~7.5× slower than 3.6's measured 331 tok/s. If real, per-cell wall
   ≈ ~15 min prefill + ~30 min decode ≈ **~45–50 min**, seed 1 with FB lands
   mid-morning and seed 2 is a day continuation, not a night one. The denominator rules
   already cover every completion level; nothing is decided tonight on projected walls.

10. **Deviation 9's prefill inference was WRONG — corrected same-night (01:33).** The
    medium gate cycle's own JSON records warm **prefill 274.7 tok/s** (0.83× of 3.6's
    331) and long-context **decode 6.67 tok/s** (3.6: 8.4). The ~44 tok/s figure
    inferred from wall times is retracted; the extra cycle time was load/overhead, not
    prefill. Revised per-cell wall (w): ~2.5 min prefill + ~40 min decode ≈ **~45
    min/cell** → seed 1's eight F cells land ~06:30, FB follows, seed 2 runs into the
    day. First-cell health at 01:33: 0 voids, dc22 in flight at F 39,998/40,000 —
    trim step 9, one step lighter than the xhigh render, all 12 unresolved keys shown.

11. **FB turns void on an instrument false-positive under 3.8's template — found at the
    first FB turn (02:19), diagnosed from the trace, no mid-night code change.**
    3.8's template renders the HISTORY assistant turn as
    `<|im_start|>assistant\n<think>\n\n</think>\n\nanswer` (3.6 never inserted that
    block — its five FB turns ran clean); `Qwen.generate`'s prefilled check scans the
    whole prompt string, flags the history block, and voids the turn before extraction.
    **The generation itself is unaffected** — dc22's FB trace holds a complete
    57,626-char think, closed, with a 1,871-char answer; the generation tail correctly
    opened `<think>`. Every FB turn tonight will void this way, each SAVING its full
    think+answer to `logs/e2_slice_traces/*.fb.think.json`. Morning tasks, in order:
    fix the check to scan only the region after the last `<|im_start|>assistant`;
    re-verdict the saved FB traces (zero-GPU); extract + score the saved FB answers
    (GPU, ~2 min each). The FB repair-rate line is DELAYED, not lost, and F cells are
    untouched (single-turn prompts carry no history block).
    Two more numbers from the same trace: FB wall ≈ 50 min (prefill 295 tok/s, decode
    6.6 — consistent with the F-cell envelope), and the FB think ran to ≈18.7k tokens,
    1,013 under the 19,669 ceiling — **FB turns press the budget edge; a real
    truncation void (think_closed=false in the trace) remains possible and is
    distinguishable from this false-positive kind.** Revised wall (w): a cell that
    fires FB costs ~100 min; seed 1 with FB runs well past dawn; morning likely holds
    5–6 F cells + their FB traces, "descriptive only" under the denominator rules
    until the seed completes.

12. **Operator stop-order (~08:15): the run was killed mid-sp80 — "no point letting
    this run finish; redetermine the token cap for 3.8 low/medium first."** Right on
    the data: 3 of 6 completed F cells (ls20, tu93, vc33) plus m0r0's FB turn voided
    at exactly 19,669 tokens, thinks still open — the cap, calibrated on ONE draw, was
    the broken instrument, and seed 1 was already descriptive-only (>2 missing).
    **Exact closure table (tokenized from saved thinks, 3.8-8bit-low, seed 1):**

    | cell | F think | FB think |
    |---|---|---|
    | m0r0 | **10,293 closed** | >19,669 truncated |
    | ft09 | 13,498 closed | 8,202 closed |
    | dc22 | 15,734 closed | 18,092 closed |
    | ls20 / tu93 / vc33 | all >19,669 truncated (58–62k chars) | — |

    **Correction to deviations 6/7: the low-closure calibration ran on dc22, not m0r0**
    (driver log: low-render sizing made dc22 the largest at 39,998; the run's dc22 F
    think is the identical generation, 15,734). The corrected one-cell ladder on m0r0 —
    xhigh >16,384 · medium >16,384 · **low 10,293 closed** — shows the effort knob
    working strongly there; deviation 6's "works but weakly" compared truncated char
    counts across different cells. The real lesson: the low-regime spread is 10,293 to
    >19,669 across cells, so closure×1.25 **of a single cell** was structurally doomed.
13. **Recovery design (running):** `max_tokens` is pure truncation — identical
    prompt+seed+sampler reproduce the identical token stream — so rerunning voided
    cells at a raised ceiling completes the same generations. Completion run: games
    ls20, tu93, vc33, sp80, lf52 + m0r0 (last — its F redo is the price of its FB
    turn), seed 1, **measurement ceiling 32,768** (worst lower bound +66%), FB check
    fixed (generation-region scan; history is not prefill), `--out
    logs/e2_slice38_seed1b.json`. Each completed cell doubles as a closure
    measurement; the **production cap re-pins afterward as max-closure ×1.25 over the
    completed fleet**, per regime. dc22/ft09 FB thinks are closed on disk and recover
    by re-verdict + extraction (no re-generation). Watch the first cell for memory
    pressure (40k prompt + up to 32,768 think ≈ 73k KV, above the night's 59k max).
    **Medium-cap measurement queued after** (m0r0 + the worst low-thinker, ceiling
    32,768) — the operator asked for low AND medium; medium re-enters if its measured
    cap prices affordably. Then the day's GPU decision: mini-S1 vs seed 2.
