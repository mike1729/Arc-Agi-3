# Night 2 — slice-4 chain (2026-08-17 → 08-18)

Operator order (verbatim, 23:00): gold + final preregistration/ceiling → six test suites +
renderer self-test + probe smokes → commit clean tree → rebuild recaptures and packets →
gate-night calibration → final fresh v2.2 probe PASS → `--freeze` → 16 Qwen pilot cells →
prepare four transcript-matched P comparator cells → run comparator → grade. Calibration is
folded into recertification per the same message; if it changes any budget/code/config the
loop repeats tests → commit → rebuild → recertify. Ceiling: `kind="model"`, same pinned
Qwen3.8-27B-8bit checkpoint, P arm only, seed 2, descriptive-only (no closure).

Running log; timestamps are start-of-stage, local (CEST).

## 23:05 — pre-registration validated

`notes/qwen-3.8-slice4-pilot-preregistration.json` (operator-written) validates against
`s4_grade.normalize_preregistration` with the live blind map: 20 expected cells
(16 Qwen T/V/O/P × {ls20, ft09, m0r0, sp80} + 4 ceiling P, all seed 2), budgets fill to the
runner constants exactly, `missing_reruns=1`, `game_pass_min_seeds=1`, plan budgets
mechanical (ft09 34 = 2×17, sp80 22 = 2×11, ls20/m0r0 150 fallback), Stage-B closure
thresholds auto-filled (inert in Stage A). Blind IDs are salt-deterministic
(`BLIND_SALT` in s4_packet.py), so rebuilds cannot invalidate the frozen matrix.

## 23:05 — tests green

86 passed + 22 subtests across the six suites; `s4_render.py --selftest` PASS.

## 23:10 — stale abort marker: resolved, no action

`logs/s4_observation_log/kaggle_v4/ABORTED.txt` survives from the first export attempt
(free-text `RIGHT` rejection, later fixed by the censused label set). Both s4_packet and
s4_grade already handle exactly this: the marker is admitted iff it *predates* the cutoff
manifest (mtime check) and is then recorded as `present_but_superseded` with its sha256.
Verified: marker 1786980157 < manifest 1786980213. Nothing to clean.

## 23:15–23:55 — sealed gold written and mechanically verified

`logs/s4_sealed/gold/{ls20,ft09,m0r0,sp80}.json` — paraphrase, constraints, counterfactual
boards, operator-familiarity record. Method, per game:

1. **Source read** (`data/environment_files/<g>/<ver>/<g>.py`) for the L1 mechanism and win
   condition — mechanism only, per the standing rule that source reads don't give
   signatures.
2. **Enumeration**: L1 completion boards from the human corpus via the established
   `e2_positives` machinery (dedup by post grid), L1 negatives likewise; initial boards
   from the normalized Kaggle export.
3. **Bidirectional mechanical verification**: each game's constraint set implemented as a
   board predicate and evaluated over the full corpus —

   | game | completions (true) | negatives (false) |
   |---|---|---|
   | ls20 | 9/9 | 469/469 |
   | ft09 | 4/4 | 456/456 |
   | m0r0 | 11/11 | 332/332 |
   | sp80 | 8/8 | 301/301 |

   Zero misfires in either direction.
4. **Counterfactuals are observed boards only** (no hand construction): the completion post
   (true), the same session's pre-board one action earlier (false, near-miss), the initial
   export board (false, vacuity killer), and for m0r0 additionally the observed
   touching-but-not-fused negative `0e1adaaf/23` (false — two adjacent pieces form one
   50-cell connected region; fusion leaves 25 — kills "single connected blob" readings and
   the night-1 always-true attractor class). Every `objective_holds` label asserted equal
   to the verified predicate at write time.

Win conditions as read + verified (the one-line versions):
- **ls20 L1**: avatar upright (rotation 0: colour-12 cap on top) standing exactly in the
  walled pocket (rows 10–14, cols 34–38); shape/colour already match from start; preview
  glyph absorbed. Start rotation 270; one rotator-tile touch suffices.
- **ft09 L1**: ring of 8 cells around the printed tile: unmarked sides (NW,W,E,SW) toggled
  to 8 (= tile centre), marked sides (N,NE,S,SE) left 9. All start 9; 32-click budget.
- **m0r0 L1**: two mirror-moving pieces brought onto the same cell → fuse (25 colour-10
  cells vs 50 whenever separate, even touching). 150-action budget.
- **sp80 L1**: pour settles with both targets water-captured (11→13) and zero water on the
  ground bar (no 14 in rows 60–63). 30 placement steps, 4 pour attempts.

Verification artifacts: scratchpad `gold_verify.py` + `write_gold.py`,
`gold_verify_summary.json`, `gold_write_report.json`. Gold sha256s (grader's
`snapshot_gold`): ft09 b761aec92ba6…, ls20 8b9418834405…, m0r0 5b4beb49f748…,
sp80 734c7c6375a3…. The familiarity fields are factual development-exposure records
written by the night agent (flagged in the morning summary — they seal at freeze without
operator review, per the overnight order; Stage A model ceiling makes them
non-closure-bearing).

## 00:00 — committed 5a09167; rebuilds green

Overhaul + prereg + night log committed (clean tree). Recaptures rebuilt v2, all four
games 100% verified (ls20 3000/3000, ft09 1699/1699, m0r0 3250/3250, sp80 1106/1106).
Packets rebuilt, 10 pages × 3 carriers each, initial visual tokens raw 3,991–5,197 /
overlay 4,376–6,128 — inside the 6,448 cap. Blind map regenerated byte-identical
(salt-deterministic).

## 00:05 — fresh probe certification launched

`e2_probe_vlm.py --out logs/e2_probe_vlm_38_8bit.json --force --max-tokens 12000
--packet-max-tokens 16000` on the committed tree. Budget calibration is folded into
this run per the operator order (packet-scale + production-sampler stability panels).

## 00:10–00:50 — ceiling executor written: `agent/harness/s4_ceiling.py`

The runner accepts only `--role qwen`; ceiling cells enter through the grader's
transcript-matched pathway (`--prepare-ceiling` → ceiling_input artifact →
executor → execution trace + answers document). The executor had to exist **before**
the freeze: the grader requires the ceiling document's git state to be the frozen
commit with a clean tree, so nothing new can be added after `--freeze`. Contract
implemented from `validate_run_document` / `validate_model_ceiling_execution_trace` /
`enforce_ceiling_matches`:

- delivers each cell's `evidence.user_messages` **verbatim** through the runner's own
  `ask_chat` (identical template invariants, production sampler, xhigh, budget 20,000)
  with image-byte SHA verification before send;
- seeds: `seed_for(2, "<blind>_r0")`, asserted equal to the grader's
  `generation_seed` derivation; round tag `<blind>_P_s2_r0` so
  `validate_cell_provenance` passes;
- writes 0o444 raw execution artifacts + trace bound to `ceiling_spec_sha256` and the
  ceiling_input sha; answers document mirrors the runner format (role=ceiling,
  budgets, frozen manifest + certificate identity checks via the runner's own
  `verify_certificate`);
- self-verifies through `grade.validate_run_document` + `collect_attempts` before
  reporting success — a document the grader would refuse never reports PASS.

Serving-config honesty gate: the frozen ceiling_spec's serving_config (xhigh, temp 1.0
/ top-p 0.95 / top-k 20, 20,000 out, mlx-vlm runtime) is checked against the actual
runtime constants at startup — the spec must describe reality, not merely name it.

## 01:00 — dry-run: all 16 cells assemble

T cells 22,955–27,502 chars text, 0 images; V/O/P cells 8,466–11,891 chars + 10 images.
No wiring errors. (Runner permits `--dry-run` pre-freeze by design.)

## 01:30 — probe verdict: gate 3 SEMANTIC_FAIL — diagnosed, one gate defect found

Gates 1 (palette production), 2 (grey fill, counterbalanced), 4 (spatial grounding,
16px), 5 (production-sampler stability 3/3) all PASS. Gate 3 (16-page permuted packet
binding): **all ten page bindings correct across both counter-permutations, frame
index 23 correct in both** — only the yellow event's cell coordinates wrong, and
**identically wrong in both runs: (row 55, col 12) vs truth (row 37, col 11)**.

Mechanical verification of the gate (pixel-level, scratchpad): exactly one yellow
[255,220,0] 4×4-px cell on the whole 1,856×1,152 canvas; tile geometry gives frame
top y=848, left x=536 → truth (37, 11) 0-based exact; target unique; frame labels
0-based and correctly read by the model. The gate's truth is sound.

The think trace is the smoking gun (call A, `call_06`): the model could not read the
4px cell's coordinates from pixels; it found a **printed annotation "(12,55)" on a
different marker page**, inferred the format, and transplanted those coordinates to
the animation answer — then confabulated visual confirmation ("row 55/64 = 0.859 of
height … Yes, matches!"; the actual cell sits at 58% of height, not 86%). Determinism
(temp-0 wiring sampler) makes both permutations produce the same anchored answer.

**Gate defect found (third of its kind after the round-2 gate-2/gate-3 fixes): the
request never pinned the coordinate convention.** Truth is 0-based; a perfect 1-based
reader would fail both checks — and the model's col 12 is exactly the correct 1-based
column. Per the standing adjudication rule ("do not treat a run under a defective
gate definition as negative evidence"), tonight's SEMANTIC_FAIL is **not yet** a
certified capability negative.

**Fix applied under the operator's calibration loop** ("if gate-night calibration
changes any budget, code, runtime, or configuration, repeat tests → commit →
rebuild → recertify"): the request now pins "Rows and columns are 0-indexed from the
top-left of the 64x64 board, so each runs 0-63; the frame index is the frame's
printed label." Regression assertion added inside the fake-VLM gate-3 branch (delivery
refused if the pin is absent). All 86 tests + 22 subtests green. Rebuild not required:
packets bind checkpoint serving files, not the probe script (verified s4_packet:894,
s4_grade:701–717). The anchoring-distractor marker page **stays** — annotations are
part of the packet contract, and anchoring-instead-of-reading is exactly what the
gate must detect if it recurs under a pinned convention.

If the rerun still fails on coordinates with the convention pinned, that is a clean
4px-readout negative — and it lands on the design, not just the gate: raw-carrier
causal pairs and probe storyboards lean on 4px/cell. An 8px floor quadruples
per-board visual tokens (64→256; the 28-frame storyboard 1,792→7,168 tokens vs the
2,112 probe-result reserve) — a structural redesign only the operator can order.
Throughput note for morning planning: xhigh generation measured at 7.2 tok/s
(packet-scale prompt, 39.3 GB peak) — a full 20k-token cell answer is ~46 min of
generation; the 16-cell estimate revises upward accordingly.

## 03:00 — rerun verdict: clean 4px-readout negative. Chain stops before freeze.

Convention-pinned rerun (`logs/e2_probe_vlm_runs/20260817T225229.462092Z`): gates
1/2/4/5 PASS again; gate 3 SEMANTIC_FAIL again — but the failure shape changed
exactly as the defect theory predicted. No more anchor-copying: the two
counter-permutations now give **scattered** estimates — A (47,12), B (22,10) vs
truth (37,11). Page bindings 10/10 and frame index 2/2 remain perfect.

Think-trace mechanism (call A): the model now does honest proportional arithmetic on
a **mis-estimated frame box** — it places the frame at y 1250–1645 and the label at
"y 1665" on a canvas that is only 1,152px tall (its internal pixel space runs ~1.45×
off), then computes 0.742·64 = row 47. The distractor marker page ("ACTION2(12,55)",
a deliberately overlapping trap — nice construction) was correctly ignored this time.

**Certified tonight:** the serving path, palette naming, counterbalanced fill
discrimination, 16px spatial grounding, production-sampler stability 3/3, packet-scale
delivery accounting (12.3k visual tokens exact), and page/frame *binding* at 4px.
**Refuted tonight:** cell-precise coordinate *readout* at 4px/cell under the packet
regime — scattered ±1 col, ±10–15 rows, with a systematically wrong internal pixel
scale. No PASS certificate → the freeze is structurally refused → the 16 Qwen cells,
ceiling, and grading do not run. This is the gate doing its job.

Resolution-floor diagnostic dispatched (3 calls, labelled `diag_resolution_floor`,
run dir under `logs/e2_probe_vlm_runs/` — NOT a certificate): the same 28-frame
storyboard at **8px/cell**, plus the event frame **alone** at 4px and at 8px. It
answers the two questions the redesign hinges on: is 8px above the floor in dense
tiling, and is 4px dead everywhere or only when tiled.

## 04:00 — resolution ladder measured (diagnostic, not a certificate)

Same fixture, same pinned convention, wiring sampler, truth (frame 23, row 37, col 11):

| condition | visual tokens | answer | verdict |
|---|---:|---|---|
| 8px, 28-frame storyboard | 7,752 | frame ✓, row **37 ✓**, col 12 | row exact, col ±1 |
| 4px, event frame alone | 81 | row 38, col **11 ✓** | ±1 both axes |
| 8px, event frame alone | 289 | **row 37 ✓, col 11 ✓** | **exact** |
| 16px boards (gate 4, certified) | — | — | exact |
| 4px, 28-frame storyboard (gate 3) | 7,364 | (47,12)/(22,10) | refuted |

Cell size and tiling density degrade readout **multiplicatively**: 8px isolated is
exact; 8px tiled and 4px isolated are ±1; 4px tiled is unusable. Wall-clock at xhigh:
the 8px-storyboard call thought for 27 min; even 81-visual-token calls ran ~12 min —
generation time is dominated by thinking, not input size.

## Morning brief — where the night ended and the decision menu

**Delivered:** sealed gold (verified 32/32 completions, 1,558/1,558 negatives) ·
overhaul + prereg committed (`5a09167`) · recaptures v2 + three-carrier packets
rebuilt · ceiling executor `s4_ceiling.py` built, self-verifying, committed
(`ede73c9`) · 16-cell dry-run clean · one real gate defect found, fixed,
regression-tested (`e3a6ec0`) · certification run twice; final verdict
SEMANTIC_FAIL on 4px coordinate readout under a sound gate (`53c4e6b`) · resolution
ladder measured. **Not run (structurally blocked without PASS):** freeze, 16 Qwen
cells, ceiling comparator, grading. Everything built tonight is reusable unchanged
except the rendering floors and the gate bar.

**Decision menu (with the measured ladder):**

- **(a) Raise the raw-carrier floor to 8px** and keep coordinate-precision claims on
  isolated exhibits. Costs: full board 64→256 visual tokens; the current packets'
  initial visual (3,991–6,128) likely exceeds the 6,448 cap after ×4 on causal
  pages → page trims; probe-result storyboards fit ≤7 frames per 2,112-token
  reserve (7×256=1,792) or go multi-page/subsampled with the budget-indeterminate
  rule intact.
- **(b) Re-scope the certification to what the carriers actually claim** (minimal
  change): 4px pages remain for structure/binding — which the gate PASSED at packet
  scale both runs — while every cell-precise claim rides on crops (≥16px, certified),
  overlay labels, and the text carrier's exact RLE. The gate's animation bar then
  tests frame binding + coarse localization, or precision via a follow-up crop.
  Requires your semantic sign-off on the re-scoped claim and gate text.
- **(c) Read tonight as the raw-channel null** — premature on the evidence: binding
  at 4px is solid; the pilot's question (goal inference) was never reached.

(a) and (b) compose. Throughput reality for any revised plan: at xhigh the model
thinks 12–27 min per call regardless of input size, so a P cell (4 generations,
20k-token budget) is plausibly 1.5–3 h — the 16-cell pilot is a ~24–40 h GPU affair
at current budgets, not one night. Worth deciding alongside the floor: whether the
pilot's effort tier stays xhigh (capability upper bound) or the budget shrinks.

Nothing in tonight's negatives touches the actor-regime signal (Kaggle LB jump on
3.8 actor swaps); mini-S1 remains pinned behind slice-4 readout per your decision.
