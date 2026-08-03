# VP — replay-grounded visual-perception screen

**Status: FREEZE 1 FROZEN 2026-08-02** — operator declaration recorded; all VP1–VP2 tasks,
values, formats, sampling rules, gates, routing, and budgets are frozen. **Freeze 1 covers
VP1–VP2 only**; VP3–VP4 stay design-stage, frozen separately and only if VP1–VP2 pass. Any
change to Freeze-1 scope requires a dated erratum before measurement.

**Pre-measurement operational erratum, 2026-08-02:** the first client launch made no model
call because the workspace sandbox denied its localhost connection. Four connection-error
records were archived outside the measurement log. The runner's cancellation loop was fixed
to preserve the originating operational error instead of raising `CancelledError`, and the
implementation manifest was refrozen before any model response. Questions, prompts, gold,
sampling, gates, routing, generation settings, and budgets are unchanged.

**Implementation-conformance erratum, 2026-08-02:** two VP1 bring-up responses were discarded
after revealing that the rendered instruction had abbreviated the governing contract's
requirements for legend color names, a nested 3×3 patch, and bare JSON. The rendered prompt
now states those already-frozen requirements verbatim; the two responses and old manifest are
excluded from measurement and preserved as bring-up evidence. No question, image, gold,
selection, gate, arm, generation setting, or routing rule changed. The implementation was
refrozen before restarting the measurement.

**Concurrency bring-up erratum, 2026-08-02:** concurrent lazy import of the vendored image
renderer failed before one row could make a request, while already-started bring-up requests
drained. The runner now initializes rendering before opening its worker pool and bounds queued
work to the concurrency setting, so interruption cannot leave a full experiment queued in
background threads. The error row and unscored drained requests are excluded. Measurement
content and scoring are unchanged; the implementation was refrozen before restart.

Provenance: operator proposal (render frames for multimodal Qwen; ceiling matters even where
deployment can't afford it) + external ChatGPT draft (four-level replay-grounded diagnostic) +
two Sol review rounds (six repairs §3.1; three repairs + value resolutions §3.2) + final
goal-relevance/deployment review (§3.3) + this repo's receipts on what GI-1 actually fed the
model.

**Corpus count.** `iter_trace` yields **9,913 rows bearing frames** across the 18 sessions; the
annotations artifact's `total_actions` sums to **9,895**. The 18-row gap is each session's
initial RESET row, which carries the initial board — a real frame, not a header line (the
"header" explanation previously given here was wrong). Verified in `logs/vp_inventory.json`.

---

## 1. Why this screen exists — the empty cell

GI-1 was already multimodal. Receipts:

- every model call attached the current frame as a PNG (`gi1_experiment_runner.py:457`
  `with_image=True`; `gi1_render.py:304` builds the `image_url` part);
- the model, `Qwen3.6-27B-8bit`, is image-text-to-text served via mlx_vlm; the S1 reference
  played live with `multimodal: current_grid, upscale: 4` (`notes/s1-reference-freeze.md:156`).

So "switch to multimodal Qwen" is already measured: 0/234 predicates, 0/440 entity fields —
with vision on. Never measured:

1. **Legibility.** Upscale 4 → 256×256 → 4-px cells, below a vision tower's ~14–16-px patch.
   No perception canary exists anywhere in GI-1 or its audit.
2. **Evidence as pixels.** Only the *current* frame was imaged; pre-terminal grids, deltas and
   completions were ASCII/digest text. The model never saw two frames as images.
3. **Gold-complete text.** The digest inventories come from vendored `segment_layer`
   (`gi1_digest.py:68`) — same-color segmentation, which GI-2 measured as unable to express the
   gold entities on ft09 and vc33.

The untested cell is **legible pixels × evidence frames**, with the ask reduced to perception
so failure localizes to the channel.

## 2. Governance

- §3.4 of `notes/gi2-grounded-binding.md` permanently stopped
  goal-inference-from-replay-evidence formulations. This screen is a **channel diagnostic**
  (same category as the forensics and diagnostic-identifiability passes): exploratory,
  non-funding, no formulation proposed.
- **Only VP4b prices reopening.** A VP4b pass creates the option, not the act: reopening
  requires an explicit dated operator decision superseding §3.4. VP4a can be won from
  HUD/terminal effects and is *never* a reopening case.
- Sealing unchanged: reserved games (g50t, r11l, su15, tr87) and the 15 one-shot games are
  never rendered, never queried. Corpus = the 6 iteration games' 18 sessions.
- Naming **RESOLVED**: levels are VP1–VP4 (the draft's V1–V4 collide with manifest
  verification items; S1-E17 precedent). This note is the screen's governing document.

## 3. Review repairs adopted

### 3.1 First round (Sol, 2026-08-02)

1. **VP2 purified** — the withheld-next-frame MCQ requires mechanics; moved to VP3. VP2 shows
   only true before/after pairs.
2. **Crop arm is oracle-only** — gold-derived attention; champion-ineligible; feeds nothing.
3. **VP1 split** — marked-target recognition (gated) · unmarked coordinate lookup (reported as
   spatial indexing) · global inventory (gated, banded).
4. **VP3 affordance gold is causal** — candidate actions re-executed from recorded states via
   the replay driver, not inferred from human no-ops.
5. **VP4 split** — VP4a detection (HUD legitimate, never a reopening case) / VP4b rule
   transfer (terminal effects and completion metadata removed); only VP4b prices reopening.
6. **Deterministic primary decoding**; effect-size floors, not significance alone.

### 3.2 Second round (Sol, 2026-08-02, value resolutions)

7. **I-A can never be the visual champion.** The champion is the best *pure-image* arm among
   I-4/I-8/I-16; I-A is a control, I-H and I-C are reported separately (§7). Otherwise ASCII
   could pass VP1 and accidentally advance the "visual" route.
8. **VP2 change-kind is report-only.** Movement-vs-recolor needs a defined correspondence
   rule; until that mechanical rule is specified and audited, no gate.
9. **Clustered statistics.** Questions within a board/game are correlated; nominal
   per-question binomial p-values exaggerate certainty. VP1–VP2 gate on absolute effect sizes
   and per-game floors; report 90% hierarchical bootstrap intervals (resample games, then
   sessions within games, then boards/pairs within sessions); chance baselines reported; no
   universal p<0.05 gate.

### 3.3 Final goal-relevance and deployment review (2026-08-02)

10. **A semantic bridge is gated inside VP2.** Pixel counts and delta boxes can pass while the
    model still fails the object identity and relation binding that broke GI-1/GI-2. VP2-S
    therefore tests only *observed* identity and relation transitions; prediction remains VP3.
11. **VP1 packet layout is frozen.** Clean and annotated views are separate, markers are keyed,
    and I-C supplies one keyed crop per marked query. Global questions never read a marked
    board. Packet layout and the full response schema are answerability-audited.
12. **Temporal packaging is selected before the full VP2 read.** Separate images and a labelled
    contact sheet compete on the same subset; the winner is then run on the remaining pairs.
    Video is removed. The packaging result is gate-eligible rather than an ambiguous add-on.
13. **Score-run channel viability is a separate gate.** A 48-call calibration uses the exact
    FP8/vLLM stack, score-run prompt/history/tools, and representative concurrency. Accuracy,
    first-pass validity, context fit, failure rate, and wall time all gate the phrase
    *deployable channel*.
14. **Sampling is session/level balanced.** VP2 uses eight pairs/session, maximizes level
    coverage, and has frozen shortage/stratum relaxation rules. Bootstrap resampling includes
    the session level.
15. **Duplicate arms are not rerun.** If I-4 is the VP1 champion it also supplies the VP2 I-4
    control row. Identical deterministic requests never consume calls twice.

The ladder: **VP1** board facts → **VP2/VP2-S** observed changes, identity and relations →
**VP3** effects and affordances → **VP4a** completion detection → **VP4b** rule transfer.

## 4. Sample inventory (measured, `logs/vp_inventory.json` v3)

By `agent/harness/vp_inventory.py` (deterministic, `--verify` clean; no RNG, no model calls).
"Pairs" are within-level settled before/after pairs; delta regions are 4-connected components
of the changed-cell set (same connectivity as the observation layer):

| Game | Rows | Pairs changed | Pairs no-op | Completions | Transfer | Clicks eff/no-op | Colors p50 | Region p50 | Regions >12 | Tiny-region share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dc22 | 3,006 | 2,595 | 386 | 18 | 15 | 874 / 283 | 15 | 1 | 130 (5%) | ~0.55 |
| ft09 | 537 | 459 | 49 | 18 | 15 | 394 / 45 | 8 | 2 | 0 | ~0.48 |
| ls20 | 1,614 | 1,573 | 12 | 21 | 18 | 0 / 0 | 10 | 4 | 0 | ~0.41 |
| m0r0 | 2,486 | 2,330 | 124 | 18 | 15 | 115 / 26 | 7–8 | 2 | 0 | ~0.45 |
| tu93 | 1,068 | 1,002 | **0** | 27 | 24 | 0 / 0 | 9–10 | 6–9 | 0 | ~0.17 |
| vc33 | 1,202 | 1,112 | 62 | 21 | 18 | 1,133 / 62 | 9 | 3 | 0 | ~0.22 |
| **Σ** | **9,913** | **9,071** | **633** | **123** | **105** | **2,516 / 416** | — | — | **130 (1.4%)** | — |

Consequences:

- **Multi-region changes dominate** (76% of changed pairs have ≥2 delta regions) — the review
  was right that a single union bbox is inadequate; VP2 scores a *list* of region boxes (§6).
- A naive ≤8-region eligibility cap would exclude 35% of tu93 and 20% of ls20 pairs —
  biased toward simple changes on exactly the keyboard games. **≤12 regions** covers ≥95% of
  pairs in every game (max counts: ls20 12, tu93 11, ft09 10, m0r0/vc33 8; only dc22's tail,
  max 37, is trimmed — 130/2,595 or 5.0%). Artifact v3 records `9-12` and `>12`
  separately and records eligible/excluded counts, so this claim is reproducible.
- Tiny regions (≤4 cells) are 17–55% of all regions — the tiny-region matching alternative
  (edge error ≤ 1 cell) is load-bearing, most of all on dc22.
- No-op pairs: tu93 zero, ls20 twelve → no-op family gates only on {dc22, ft09, m0r0, vc33}
  (pool floor 20, **RESOLVED**); ls20 report-only.
- Marked-target chance ≈ 1/(distinct colors) ≈ 0.07–0.14.

## 5. VP1 — board-fact recovery (Freeze 1)

**RESOLVED: 8 boards/game**, drawn 3/3/2 across the three sessions. Which session receives two
rotates by `int(sha256(env.encode("ascii")).hexdigest()[:8], 16) mod 3`. Selection maximizes
distinct levels, includes level 1 and the highest completed level where available, and permits
at most two boards from one level before relaxation. Within those constraints, boards/questions
are deterministically assigned across the probe strata (cells changed by next action · movement
src/dst · rare-color cells · smallest components/1-cell borders · never-changed background
controls · human-clicked cells on mouse games). Recorded MOUSE coordinates are canonicalized as
`(row, col) = (y, x)`.

Per board, **one request, 10 questions** (RESOLVED):

- **5 marked-target** (gated): "what color is marked cell A/B/C/D/E?" Markers are distinct
  keyed 2-px high-contrast dashed rings outside each queried cell's boundary and never cover
  the queried cell. Marker footprints may cover non-queried neighbours but may not overlap a
  different queried cell, the P patch, or another marker footprint. I-A uses keyed brackets.
  The annotated view has an exterior marker gutter so edge markers are never clipped; the 64×64
  board pixel matrix itself is neither modified nor resampled. Marker legibility scales with
  upscale and is part of what is measured.
- **1 marked 3×3 patch transcription** (gated): ring encloses the block; patch cells clean.
- **2 global banded** (gated): one pixel-count band + one component-count band (§8 bands).
- **2 unmarked coordinate lookups** (reported as *spatial indexing*, ungated).

**VP1 packet layout (RESOLVED):** every visual request has two ordered image parts: (1) the
clean unmodified board, used by the two global questions and U1/U2 lookups; (2) an annotated
copy carrying A–E and P, used only by marked questions. Text names the view used by every
question. I-A supplies matching clean and keyed ASCII blocks. I-H supplies the two I-16 images
plus the ASCII blocks. I-C supplies the clean I-8 board plus a single labelled 2×3 contact sheet
containing keyed 32× crops for A–E/P (four-cell margin, clipped/padded at board edges); crop
pixels are 32× and never share a panel. Thus "question region" is plural and mechanically
mapped, not inferred.

The first-pass schema is one object with exactly these keys:

```json
{"marked_cells":{"A":"<color>","B":"<color>","C":"<color>","D":"<color>","E":"<color>"},
 "patch_P":[["<color>","<color>","<color>"],["<color>","<color>","<color>"],["<color>","<color>","<color>"]],
 "pixel_count_band":"<band>","component_count_band":"<band>",
 "lookups":{"U1":"<color>","U2":"<color>"}}
```

The prompt names the counted color for each global question. Components are 4-connected
same-value components. Colors must be legend names and bands must be copied exactly from §8.

Yields per arm: 240 marked-cell, 48 patch, 96 global, 96 lookup questions.
**Calls: 8 × 6 games × 6 arms = 288.** Constant value→color-name legend in every arm.

## 6. VP2 — observed-change reading (Freeze 1)

**RESOLVED: 24 pairs/game** — eligible games 16 changed + 8 no-op; tu93 24 changed (no
no-op metric); ls20 16 changed + 8 no-op with its no-ops report-only. Exactly eight pairs come
from each session. For games with gated no-ops, the constrained allocation minimizes squared
distance from 5⅓ changed / 2⅔ no-op per session while satisfying 16/8; ls20 uses the same rule
subject to its session pools. Ties are resolved by canonical session then step order. tu93 uses
eight changed pairs/session.

Within session quotas, selection maximizes distinct levels before taking a second pair from a
level and limits any level to four pairs before relaxation. Changed pairs allocate at least two
examples to every available region-count band in {1, 2–3, 4–8, 9–12} whose corpus pool has at
least two; remaining slots fill smallest realized strata first. The deterministic constraint
solver relaxes in this order only: four-pair level cap → two-per-band floor → distinct-level
preference. Every relaxation and the eligible/excluded pool is written to the freeze artifact;
no post-result resampling is allowed.

One call per pair per arm; the questions share the pair (declared):

- **changed-cell count band** (gated; §8 bands; no-op pairs are band "0");
- **connected-region boxes** (gated; **RESOLVED**): list every changed region's bbox. Pair
  eligibility ≤ 12 delta regions (exclusion share reported; material only for dc22's tail);
  changed-pair sampling stratified over region-count bands {1, 2–3, 4–8, 9–12} where present.
  Strict output is `{"regions": [[row_min, col_min, row_max, col_max], ...]}`: zero-based,
  inclusive coordinates, canonical row-major order, at most 12 distinct boxes, and an empty
  list for a no-op. Every VP2 image has deterministic non-oracle row/column ticks outside the
  board; this rendering is available at deployment and prevents the gated localization score
  from silently becoming the unassisted spatial-indexing test separated in VP1.
- **Mechanical matching (RESOLVED):** construct bipartite edges where IoU ≥ 0.50 or, for a
  gold region of ≤4 changed cells, maximum corresponding bbox-edge error ≤1 cell. Select the
  maximum-cardinality matching, then maximum summed IoU, then lexicographic pairs as a
  deterministic tie-break. Precision/recall/**F1** use micro-aggregated matched, predicted,
  and gold region counts over **changed pairs only**; no-op pairs are evaluated by the
  separate no-op metric and must emit an empty region list. This is implemented once in
  `agent/harness/vp_regions.py`; input order cannot change the score.
- **no-op yes/no** (gated on eligible games);
- **change kind** appear/disappear/move/recolor/mixed — **report-only** (§3.2 item 8).

The first-pass VP2 response is exactly:

```json
{"changed_count_band":"<band>",
 "regions":[[0,0,0,0]],
 "no_op":false,
 "change_kind":"appear|disappear|move|recolor|mixed|none"}
```

`regions` follows the strict rules above; a no-op must use band `0`, `[]`, `true`, and `none`.
Cross-field disagreement is invalid rather than silently reconciled.

**Temporal packaging selection (RESOLVED):** before the full champion read, a fixed selector
subset takes eight of the 24 pairs/game: six changed + two no-op for games bearing no-ops and
eight changed for tu93. The same 48 pairs compare exactly two packagings:

1. two ordered `image_url` parts labelled BEFORE and AFTER;
2. one labelled horizontal contact sheet whose panels retain the champion's native cell scale
   (no panel downsampling; padding/labels are added outside the boards).

Score each packaging by
`min(changed_count_accuracy/0.80, region_F1/0.70, no_op_balanced_accuracy/0.85)`, omitting the
no-op term for tu93 and report-only ls20 before the game macro. Highest score wins; within one
pair-cluster standard error choose fewer reported server input tokens, then smaller encoded
payload, then the contact sheet. The chosen packaging runs on the remaining 16 pairs/game, so
it owns all 24 gated pairs.
The losing packaging is report-only. Video is outside Freeze 1 and cannot rescue VP2.

Full control arms are I-A and I-4. The I-4 row is not rerun if I-4 is champion. Worst-case VP2
calls: selector 96 + champion remainder 96 + I-A 144 + distinct I-4 144 = **480**; if I-4 is
champion, **336**. All packaging variants and all 24-pair identities are generated and frozen
before the selector is run.

### 6.1 VP2-S — observed semantic binding (Freeze 1)

The selected champion scale and temporal packaging must also read semantics that are necessary
for goal inference but do not require prediction. **Twelve cases/game = 72 calls**, split two
identity and two relation cases per session, maximizing distinct levels:

- **identity, 6/game:** two settled frames from one level use the selected temporal packaging.
  One object is ring-marked in the first frame and four candidate objects A–D are ring-marked
  in the second; return A/B/C/D. Gold is restricted to a unique persistent object under
  source/replay identity and unique visible color+shape within the level. Multicolor movers are
  included where available. m0r0 twins and any occluded/consumed ambiguity are ineligible, not
  adjudicated.
- **relation transition, 6/game:** the same two frames mark persistent objects A and B and name
  one mechanical visible-mask relation from `bbox_overlap`, `bbox_contains`, `row_aligned`,
  `column_aligned`, or `same_palette`. Return exactly one of `became_true`, `became_false`,
  `stayed_true`, `stayed_false`. `row_aligned`/`column_aligned` mean overlapping bbox intervals;
  `bbox_overlap` means nonempty bbox intersection; `bbox_contains` is directed A-contains-B;
  `same_palette` means equality of all visible values inside the two authored object masks,
  including values equal to the board's modal color. Each game supplies at least two relation
  types and at least one truth-changing case.

Source/replay identities may author the answer key and marker placement only; no handle, role,
source name, or answer-derived crop enters the prompt. A case is eligible only if the two masks
and all four identity candidates are uniquely distinguishable in the rendered pixels under the
answerability audit. There is no quota relaxation: fewer than six eligible cases in either
family for any game stops before model calls and returns the question generator to design.
First-pass schemas are `{"identity":"A|B|C|D"}` and
`{"transition":"became_true|became_false|stayed_true|stayed_false"}`. Both have chance 0.25.

Champion add-on, report-only:

- **palette permutation** (RESOLVED 48 calls = 2 seeded contrast-preserving permutations × 4
  cases × 6 games; per game per permutation: 2 VP1 boards + 2 VP2 pairs). Collapse under
  permutation ⇒ reading familiar imagery, not state.

## 7. Interfaces, champion rule (Freeze 1)

| Arm | Content | Role |
|---|---|---|
| I-4 | image packet only, native board panels 256² (upscale 4; GI-1/reference control) | champion candidate |
| I-8 | image packet only, native board panels 512² (upscale 8) | champion candidate |
| I-16 | image packet only, native board panels 1024² (upscale 16) | champion candidate |
| I-A | ASCII board only (GI-1 text presentation) | **control — never visual champion** |
| I-H | I-16 packet + ASCII board | reported (synergy probe) |
| I-C | clean board at 8 + keyed 32× crops for every marked region (margin 4 cells) | **oracle ceiling** — champion-ineligible, feeds nothing |

**Champion rule (RESOLVED):** among {I-4, I-8, I-16}, select the best **minimum normalized
margin**:

```text
min( marked_accuracy / 0.90,
     exact_patch_accuracy / 0.70,
     pixel_band_accuracy / 0.75,
     component_band_accuracy / 0.70 )
```

If arms are within one board-cluster standard error, choose fewer reported server input tokens,
then smaller encoded payload, then lower upscale. **If I-H passes
while every pure-image arm fails, compare I-H directly with I-A: that is evidence of
multimodal synergy, not proof that vision works independently** — routed as its own finding.

**No-iteration rule:** the arms above are the complete set; all-arms-fail is a *result*.
Renderer = value-space ops + vendored `frame_to_png_data_url` unmodified; ring/contact-sheet/
crop compositing is new deterministic utility code.

## 8. Scoring, decoding, execution (Freeze 1)

- **Count bands (RESOLVED**, replacing ±10%-or-±1; the model selects a band, isolating global
  perception from arithmetic**):**
  - pixels: 0 · 1–4 · 5–16 · 17–64 · 65–256 · 257–1024 · 1025–4096;
  - components: 0 · 1 · 2 · 3–4 · 5–8 · 9–16 · 17–32 · 33+.
- Region boxes per §6; strict JSON schema per family.
- **Decoding (RESOLVED):** greedy/deterministic primary. Substitute **only if the server
  rejects deterministic parameters** — never because accuracy or formatting is poor;
  predeclared fallback `temperature=0.01, top_p=1`. Deployment sampling is measured only in
  the exact score-stack calibration below; it does not alter the local primary.
- **Repair policy (RESOLVED):** first-pass validity is a primary reported metric. Primary
  scores use first-pass responses — a format failure scores wrong and is not erased. Repaired
  responses contribute to a secondary result track only; repair calls draw from the reserve.
- Models: dev = `Qwen3.6-35B-A3B-4bit` (bring-up on ≤1 game, discarded); measurement =
  `Qwen3.6-27B-8bit`. Question set frozen (sha over generator + corpus inputs + emitted
  questions) before the first measurement call; freeze artifact + `--verify`, A-R pattern.
- **Answerability audit before any model call**: unique derivable gold everywhere; marker and
  distractor distinctions survive the complete packet composition, contact-sheet composition,
  and the model processor's effective resize/tokenization for every arm. The audit validates
  marker-footprint nonintersection, clean/annotated question routing, semantic candidate
  uniqueness, response schemas, and all shortage relaxations. Operator eyeball option: 20
  rendered packets, including ≥2 VP2-S packets and ≥2 I-C packets.

### 8.1 Exact score-stack calibration and deployment envelope

Local VP1/VP2 passing establishes a perception result for MLX 8-bit only. The phrase
**deployable channel** additionally requires a **RESOLVED 48-call calibration** on the exact
submission artifact and engine (`vrfai/Qwen3.6-27B-FP8`, vLLM, score-run chat template/tool
schema, thinking enabled, `temperature=0.6`, `top_p=0.95`, `top_k=20`, 32,768-token analyzer
context, and 28 concurrent score jobs). The selected visual scale and temporal packaging are
used. The subset is frozen before local measurement: per game 2 VP1 packets + 4 VP2 packets
(3 changed, 1 no-op where available; tu93 4 changed) + 2 VP2-S packets (1 identity, 1 relation)
= 8/game.

The candidate deployment unit is a sidecar advisor read at level entry or after three consecutive
executed environment actions that leave the board unchanged, hard-capped at **8 advisor
calls/game**. It does not take an environment action. The calibration sends that request
envelope inside representative retained history and the full tool-bearing score-run prefix.
Tool schemas remain attached for behavior and context cost, but `tool_choice` is forced to
`none`; an emitted tool call is a first-pass format failure and is never executed. Context-load
strata are 16 fresh (≤8k input tokens), 16 mid-run (>8k–20k), and 16 late-run (>20k before the
advisor packet); per-game counts differ by at most one within each stratum, with surplus slots
rotated by the VP1 game-hash order. Report raw/rendered dimensions, processor
vision/input tokens, encoded bytes, output tokens, request latency, first-pass validity, request
errors, and context trimming/overflow for every call. Latency p95 is the nearest-rank p95 over
all 48 elapsed durations; failed/timed-out calls retain their elapsed duration rather than being
dropped.

Calibration answers are discarded and no advisor is integrated by Freeze 1. The calibration
licenses only the image/request channel and cadence envelope. VP2-S's source-authored markers
and answer-key identities are diagnostic-only and may never appear on hidden games. A later
VP3/VP4 integration freeze must define the non-oracle live readout, how it is inserted into the
ordinary analyzer prompt, and its incremental score value.

**Score-run viability passes iff all hold:**

- ≥47/48 requests succeed; zero image rejection and zero unrecovered context overflow;
- first-pass schema validity ≥0.90;
- marked-cell accuracy ≥0.80; VP2 changed-count accuracy ≥0.70 and region F1 ≥0.60;
  VP2-S identity and relation-transition accuracy each ≥0.60;
- every request leaves ≥512 output tokens inside the 32,768-token context after tools;
- `8 × p95(advisor latency) ≤ 270 s`, reserving at least 90% of a 45-minute game for the
  playing agent.

Failure does not erase the local channel result; it labels the champion **ceiling-only** and
forbids score-run integration. No MLX result, token table, or mere `image_url` acceptance may
substitute for this gate.

**Freeze-1 call budget (RESOLVED cap 1,100):**
VP1 288 + VP2 worst-case 480 + VP2-S 72 + palette 48 + target-stack calibration 48 =
**936 planned worst-case**, leaving a **164-call reserve** for repairs and operational
anomalies. If I-4 is champion, deduplication reduces VP2 by 144 calls. Tokens, bytes, and latency
per packet/arm are recorded; only §8.1 is the deployment cost gate.

## 9. Gates (Freeze 1; RESOLVED)

Statistics per §3.2 item 9: game-macro scores, absolute thresholds, per-game floors; 90%
hierarchical bootstrap intervals (games, then sessions within games, then boards/pairs within
sessions) reported; chance baselines reported; **no nominal per-question p<0.05 gate**.

**VP1 — visual-route pass iff one pure-image arm clears all of:**

- marked-cell game-macro accuracy ≥ **0.90**; ≥ **5/6** games ≥ 0.80; **no game < 0.60**;
- 3×3 patch per-cell accuracy ≥ **0.97**; completely-correct patches ≥ **0.70**;
- pixel-count band accuracy ≥ **0.75**; component-count band accuracy ≥ **0.70**.

I-A/I-H/I-C reported against the same thresholds (control/synergy/ceiling readings — §7).

**VP2 — pass iff the champion with its selected packaging clears:**

- changed-count band game-macro ≥ **0.80**;
- region-box F1 ≥ **0.70**;
- ≥ **5/6** games ≥ 0.60 on both;
- no-op balanced accuracy over eligible games ≥ **0.85**; ≥ **3/4** eligible games ≥ 0.70;
- change-kind report-only.

**VP2-S semantic bridge — part of the VP2 pass, not an add-on:**

- identity game-macro accuracy ≥ **0.75** and relation-transition game-macro ≥ **0.70**;
- ≥ **4/6** games score at least 4/6 on identity and at least 4/6 on relation transition;
- no game is below chance (fewer than 2/6 correct) on either family.

Passing VP1+VP2 says the visual channel can recover task-relevant observed state and change. It
still says nothing about predicting an unobserved effect or inferring a completion rule; those
claims remain reserved for VP3 and VP4b.

**VP3/VP4 (frozen later, after the causal question inventory exists):** four-choice tasks keep
an explicit chance-margin form — chance 0.25, practical minimum game-macro ≥ **0.50**; ≥ 4/6
games for VP3; ≥ 5/6 for VP4b plus lower 90% game-bootstrap bound above 0.25.

## 10. VP3 — effects and affordances (conditional)

Design-stage; numerics at its own freeze from the causal inventory.

- **Withheld-outcome MCQ (moved from VP2):** board at t + recorded action; 1 true settled
  result + (k−1) real settled frames from the same game+level, change-magnitude banded,
  deduplicated; reachable states only.
- **Causal affordance gold via re-execution:** candidate clicks/actions re-executed from
  recorded states with the replay driver (`gi2_replay` + fork machinery; vc33 under the
  settled-fidelity erratum; existing fork tables reused where states coincide). Mouse games:
  which of k candidate cells responds (truth by re-execution). Keyboard games: which component
  is controlled; which direction under ACTION*k*; truth from measured deltas.

## 11. VP4 — completion (conditional; only VP4b prices reopening)

- **VP4a — detection** (123 MCQs available): genuine solved terminal + (k−1) temporally-near
  settled near-misses, same level; no completion metadata, no completing action. HUD cues are
  legitimate perception — which is exactly why VP4a is never a reopening case.
- **VP4b — rule transfer** (105 cases): evidence = 1–2 completed earlier levels; at a
  pre-terminal state of a later level, select which of k candidate actions completes it.
  Positives = recorded completing action; negatives = **fork-confirmed non-completing
  actions**. No result frames shown; metadata stripped. Free-text follow-ups recorded, never
  gated. A pass creates the pricing case for reopening — operator dated decision required.

## 12. Routing

| Outcome | Routing |
|---|---|
| VP1: every pure-image arm fails AND I-A fails | channel-independent perception failure → local model unusable as advisor; action-semantics proceeds model-free |
| VP1: pure-image arms fail, I-A passes | vision adds nothing; GI-1's wall was binding/inference (consistent with GI-2) → no vision-based GI-3 case. **Frontier-arm reconsideration trigger (RESOLVED): this outcome at I-16** — a small external arm then answers model-vs-channel |
| VP1: only I-H passes | multimodal synergy finding (§7): I-H vs I-A comparison reported; visual route not independently validated |
| VP1 passes, selected-packaging VP2/VP2-S fails | static or pixel-only perception → advisor limited to single-frame facts; mechanics stay with the action-semantics artifact |
| VP2 passes locally, §8.1 fails | local channel ceiling only; do not integrate an advisor into score runs |
| VP2 and §8.1 pass, VP3 fails | score-stack channel reads objects/relations/change, but cannot predict effects/affordances → change-describer at most under a separate integration freeze; interaction knowledge from the agent's own probing |
| VP3 passes, VP4a fails | mechanics-aware perception, blind to completion → strengthens §3.4 stop |
| VP4a passes, VP4b fails | recognizes completion effects without the rule → strengthens §3.4 stop |
| VP4b passes | pricing case for reopening GI (operator dated decision) |

All results reported per game (ft09 abstract vs vc33 icon-like proxies the pretrained prior's
reach; public≠hidden applies to any positive). I-C reported alongside as the vision ceiling.
**Frontier-VLM arm: off for Freeze 1 (RESOLVED)**; reconsideration trigger above.
Ceiling vs deployable: I-16/I-C measure the interface ceiling; the submission stack (FP8 vLLM)
must pass §8.1 before any champion is called a deployable channel. Advisor cadence and wall-time
cost are therefore measured rather than inferred from `image_url` support or token counts.

## 13. Deliverables

1. `agent/harness/vp_inventory.py` + `logs/vp_inventory.json` v3 (delta regions) — **done**.
2. `agent/harness/vp_questions.py` — deterministic VP1–VP2 generator + answerability audit.
3. `agent/harness/vp_screen.py` — freeze / measure / verify CLI (A-R pattern).
4. `logs/vp_freeze.json`, `logs/vp_questions.json`, `logs/vp_results.json`, and conditional
   `logs/vp_score_stack_calibration.json` (only after the local gate passes).
5. Unit tests over generator, audit, scoring (incl. region matching), parser, marker/contact
   compositing, constrained sampling, packaging selection, arm deduplication, and deployment
   envelope arithmetic.
6. Results section appended here + the routing row that fired.

## 14. Freeze 1 declaration — FROZEN 2026-08-02

The operator froze Freeze 1 on 2026-08-02. The frozen scope comprises the values table, packet
layouts, session/level sampling, semantic bridge, packaging selection, gates, champion rule,
count and region formats, decoding fallback, repair policy, exact-stack deployment envelope,
frontier-off decision, naming, budget, and VP4b deferral.

Implementation bring-up may repair code to match this text but may not tune or reinterpret the
contract from model results. Before the first measurement call, `logs/vp_freeze.json` must pin
this governing commit plus the generator, renderer/compositor, parser, scorer, corpus inputs,
and emitted question set. Any contract change requires a dated erratum and a new freeze digest.

---

## 15. Dated addendum — 2026-08-03: ES cross-reference to the §2 reopening route

Appended cross-reference. No frozen text, gate, result, or routing above this line is modified;
Freeze 1 and its ongoing measurements remain governed by their original contract.

§2 records that goal-inference formulations stay stopped per GI-2 §3.4 and that **only VP4b
prices reopening**, via an explicit dated operator decision. The operator decision of 2026-08-03
(header of `notes/qwen-evidence-sufficiency-screen.md`; register entry `ES-GOV-2026-08-03` in
`docs/README.md`) takes that step **for the ES protocol only**, without a VP4b pricing case: the
completed VP1 measurement (288/288 rows; best pure-image marked-cell game-macro 0.438 against the
0.90 gate, global counting failed in every tested channel) means no pure-image arm can pass VP1,
so the conditional VP3/VP4 stages — frozen only if VP1–VP2 pass — and with them the VP4b pricing
case cannot arise from Freeze 1. ES does not amend Freeze 1, its results, or its routing; the VP1
result is an input to ES §0. VP3/VP4 remain design-stage and are not activated by ES.
