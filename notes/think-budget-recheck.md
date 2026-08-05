# THINK_BUDGET recheck against the lifted-cap digests

**2026-08-05. Task note for agent execution. Model task — Qwen3.6-27B-8bit, ~1 h GPU.**
Small and self-contained: an instrument check, not a slice.

## What and why

The slice-1.1 follow-up lifted `MAX_FEATURES_PER_GROUP` (commit `e116357`), growing
digests **+29–51%** (dc22/125: 11,760 → 17,741 chars). `THINK_BUDGET = 16384` in
`e2_slice.py` was calibrated before that and **never re-checked**: on 3.6-8bit a 5k
budget produced an unclosed think block and a voided call, so an under-budget run against
longer prompts would silently void cells in any future slice. This measures whether 16k
still closes, before anything model-side is scheduled on the repaired digest.

Secondary (free): first-ever model contact with the lifted-cap digest — a qualitative
read on whether the full feature lists get used. **n=3; no conclusions about
contribution from this task** — instrument verdicts and length distributions only.

## Instrument rules (unchanged, non-negotiable)

Qwen3.6-27B-8bit (`~/models/mlx/Qwen3.6-27B-8bit`) · direct `mlx_lm`, never a server ·
template rendered with `enable_thinking=True` · **never constrain the first decoded
token** · per-call trace logged · mechanical thinking verdict per call (open/closed/
substantive/no-prefill); an unclosed think block is itself a datum here, not just a void.

## Protocol

1. Render the current digests for all 12 slice cells (`e2_slice.py` machinery as on
   main; no code changes). Record char lengths; pick the **3 longest**.
2. For each of the 3: run the phase-1 think call exactly as the slice would (same
   prompt, same sampling, temp 0.6, seed 1), `max_tokens = THINK_BUDGET` (16384).
3. Record per call: think chars/tokens, closed or not, tokens remaining at close,
   answer present, wall time, prefill + generation tok/s (the +30–50% prompt growth
   also moves the slice feasibility arithmetic — re-derive minutes/call).
4. If any think block is unclosed at 16,384: rerun that digest once at 24k (w) to get
   the actual closing length. Report; do NOT silently change `THINK_BUDGET`.

## Deliverable

Append results here: per-call table (digest, chars, think length, closed?, headroom,
tok/s), the re-derived minutes-per-call, and one recommendation line: keep 16384 / raise
to a measured value (state the observed max + headroom arithmetic — measured, not
invented). The slice-2 design consumes the recommendation; this task changes no code.

## Cautions

- Two other agents are live in the tree: modify **nothing** — this task writes only
  `logs/think_budget_recheck.json`, traces under `logs/e2_slice_traces/` with a
  `_tbcheck` tag, and this note's results section. `git status` before commit; stage
  only those.
- If the m0r0 digest is among the 3 longest, remember its hidden-state lines are the
  live channel — do not read anything about channel quality from one call.
- Seeds: 1 (and 2 only if a rerun is needed) — **never 20260804**.

## Estimate

3 renders + 3 calls at ~15–25 min/call ≈ **1–1.5 h wall**, one GPU slot. Can run today;
does not conflict with the three zero-model tasks.

---

# RESULTS — 2026-08-05

Ran as specified. Qwen3.6-27B-8bit (`~/models/mlx/Qwen3.6-27B-8bit`), direct `mlx_lm`,
`enable_thinking=True`, first token unconstrained, temp 0.6 / top_p 0.95, seed 1,
`max_tokens = 16384`, prompt = `e2_slice.PROMPT` unchanged. Machine record:
`logs/think_budget_recheck.json`; traces `logs/e2_slice_traces/*_s1_b16384_tbcheck.think.json`.
No code on main was touched; the runner was a throwaway that imports `e2_slice` and calls
`build_digest`/`PROMPT` as-is.

## Step 1 — current digest lengths, all 12 cells

| game | dose 125 | dose full | unresolved (125 / full) |
|---|---:|---:|---|
| dc22 | 17,741 | **28,742** | 10 / 14 |
| m0r0 | 11,363 | **17,196** | 9 / 10 |
| ls20 | 7,769 | 9,759 | 4 / 4 |
| tu93 | 7,066 | 9,927 | 3 / 4 |
| vc33 | 5,255 | 9,558 | 3 / 7 |
| ft09 | 3,365 | 4,242 | 0 / 1 |

Three longest: **dc22/full 28,742 · dc22/125 17,741 · m0r0/full 17,196**.

Note the headline in "What and why" understates the growth: dc22/125 is the +51% cell
(11,760 → 17,741), but **dc22/full grew 16,972 → 28,742 (+69%)** and is the real worst
case. It was measured. m0r0/full is among the three — its hidden-state lines are the live
channel and **nothing about channel quality is read from this task**.

## Step 2–3 — per-call results at THINK_BUDGET = 16,384

| cell | digest chars | prompt tok | think chars | think tok | `</think>` at gen-token | total gen tok | headroom at close | answer chars | closed? | wall | prefill tok/s | gen tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|---:|---:|---:|
| dc22/full | 28,742 | 12,524 | 26,884 | 7,443 | 7,444 | 8,560 | **8,940** | 4,295 | ✅ | 996 s | 371.5 | 8.90 |
| dc22/125 | 17,741 | 7,140 | 25,422 | 8,009 | 8,010 | 9,676 | **8,374** | 5,149 | ✅ | 1,086 s | 334.3 | 9.09 |
| m0r0/full | 17,196 | 7,395 | 25,544 | 7,096 | 7,097 | 8,433 | **9,287** | 4,765 | ✅ | 945 s | 424.8 | 9.10 |

**All three closed, and all five mechanical verdict flags pass on all three**
(`no_prefilled_empty_think`, `think_opened`, `think_closed`, `think_substantive`,
`answer_nonempty`). No call ran to the cap, so **step 4 (the 24k rerun) did not trigger.**

Worst case observed on the *whole* generation (think + answer, which is what `max_tokens`
actually caps): **9,676 of 16,384 tokens — 59% used, 6,708 spare (41%).**

Think length did not track prompt length: the largest prompt produced the *second*-shortest
think block. Across the three, think length sits in a 7.1k–8.0k-token band regardless of a
1.75× spread in prompt size.

## Re-derived minutes per call

- Think call: 945–1,086 s (mean **16.8 min**). Prefill is 21–34 s of that (2–3%) — the
  +29–69% prompt growth costs ~30 s/call, not a proportional hit, because decode at
  ~9 tok/s dominates and the think block did not lengthen.
- Same three cells **before** the cap lift (slice 1, seed 1): 907.2 / 987.8 / 1028.4 s,
  mean 974.5 s → now 1008.7 s. **+3.5% wall.**
- Extraction phase measured from slice-1 seed 1 (`total − think`): 14–176 s, mean **76 s**.
- **≈ 18 min/cell → ≈ 3.6 h for a 12-cell seed** on one GPU slot. Slice-1 seed 1 was
  3.5 h; the lifted-cap digest does not move slice feasibility.

## Recommendation

**Keep `THINK_BUDGET = 16384`.** Measured basis, no invented numbers:

- max total generation observed here: 9,676 tok → 1.69× headroom;
- longest think block ever recorded in this line: 35,405 chars (tu93/full, slice-1 seed 1)
  — no closure token count was logged then, but at the 3.2–3.6 chars/token measured today
  that is ~9.8k–11.1k think tokens, still inside 16,384 with the answer. *(Estimate,
  labelled as such — not a measurement.)*
- every slice-1 and slice-1.0 cell (24 calls at 16,384) scored, which requires closure.

So 16,384 has never been hit, and the digest growth pushes prompt tokens, not output
tokens. Raise it only if a future call actually closes above ~13k generation tokens.

## Secondary — n=3, qualitative only, no contribution claims

The three think blocks name 22–39 distinct vocabulary features each, and none of them
contains "unlisted", "not shown", or the slice-1.1 failure phrase pattern
("unlisted ⇒ constant ⇒ cannot separate"). The no-separation witness is referenced 5–13
times per trace, and "vocabulary limit" 14–21 times per trace — i.e. all three took the
"name the limit instead of forcing a rule" branch of the prompt at least once. dc22/full
attributes the unresolved keys to needing *combinations* of adjacency features; m0r0/full
attributes them to a hidden phase/turn counter absent from the vocabulary. **n=3, one seed,
unscored — this is an instrument observation, not evidence about proposal quality.**
