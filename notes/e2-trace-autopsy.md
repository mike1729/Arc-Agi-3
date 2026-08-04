# E2 trace autopsy — why the 82 proposals failed, by layer

**Task note 2026-08-04, lean mode. Zero model calls.** Self-contained; execute without
further context. Working numbers labelled (w).

## What this is

The E2 slice (`notes/e2-slice.md`, commit `faa40ee`) measured THAT Qwen's rule synthesis
fails (1 of 82 proposals survives full evidence); this task diagnoses WHY, from the 24
committed thinking traces — the first verified-thinking reasoning artifacts the line has
(every call passed the mechanical instrument check; July-era traces were void).

**Grounding example (measured, 2026-08-04):** `tu93_125.think.json` is 32,990 chars,
recaps the digest accurately, and contains **zero occurrences** of support/sample/
uncertainty language — it produced the 312-support/7-contradiction rule without ever
reasoning about evidence weight. Whether that signature generalizes across the 8 refuted
rules is this task's first question.

## Data

- `logs/e2_slice_traces/{game}_{dose}.think.json` — 24 files: `prompt` (the digest),
  `raw` (completion; think body before `</think>`), `verdict`.
- `logs/e2_slice_traces/{game}_{dose}.extract0.json` — the transcriptions.
- `logs/e2_slice.json` — per-cell verification reports (which rules survived/died and why).
- `notes/e2-slice.md` — the 8 refuted dose-125 rules with sup/contra at both doses.
- Game source for goal-truth: the competition environment files under `data/`
  (gitignored competition data — see the `.gitignore` note and `PUBLISHING.md`).

## Method — three failure layers, mechanical definitions

Label every one of the 82 proposed rules (refuted-8 first), plus each cell's
goal/hidden_state/next_probe. **Every label carries a verbatim trace quote**; a label
without a quote is not a finding. S1-d discipline.

1. **READING** — the trace asserts something about the digest that the digest contradicts
   (misquoted count, wrong effect, invented key/guard value). Checkable claims are checked
   against the digest text mechanically where possible (counts, key inventories); the
   reading-error *rate* over all checkable claims is a headline number, not just examples.
2. **REASONING** — reading was correct, inference was not. Typed:
   - `evidence-weight-blind`: rule proposed with no consideration of support size or of
     what a counterexample would look like (tu93 exemplar above).
   - `overgeneralization`: pattern correctly seen in shown rows, extended beyond them
     without hedge.
   - `alternative-dropped`: a correct (or later-surviving) candidate considered, then
     abandoned — quote both the consideration and the abandonment.
   - `guard-misread`: the guard semantics misunderstood (`adj:C:dir` is the first
     non-background colour stepping out from a SINGLE-object colour; subtle by design).
3. **EXPRESSIBILITY** — the trace correctly identifies that the vocabulary cannot express
   the separating condition (ft09 exemplar). These are diagnosis *successes*; count them
   separately, never as failures.

**Blinding:** label each trace BEFORE looking up its rules' verification/refutation
outcomes in `e2_slice.json`; join outcomes only afterwards. Record that the discipline was
followed. (One rater; label-before-join is the blinding available.)

**Goal sections vs source:** for each of the 6 games, read the game's actual completion
condition from source and label the trace's goal hypothesis {correct | partial | wrong |
unfalsifiable}. ⚠ Competition source is never quoted into committed artifacts — labels
and paraphrases only (PUBLISHING.md; git history counts as redistribution). Trace quotes
are our model's output and are committable.

## Outputs

- `logs/e2_trace_autopsy.json` — one row per proposed rule: cell, rule, layer label(s),
  trace quote(s), joined outcome; plus per-cell goal/hidden-state/next-probe labels; plus
  the reading-error rate with its denominator (claims checked).
- A short results section appended to this note: layer distribution over 82 · refuted-8
  signature · goal-correctness counts · the 2–4 prompt/digest changes the evidence
  supports (recommendations only — no prompt is edited in this task).

## Cautions

- Traces are evidence of what information was **used or misused**, not of mechanism —
  trace faithfulness is not guaranteed. Label what the text shows; no psychological
  narration ("it believed", "it panicked").
- No invented thresholds; report distributions and rates with denominators.
- The 24 traces are one sampled run (seed 20260804, temp 0.6) — findings are about these
  traces, not about Qwen-in-general; say so wherever a count could be read otherwise.

## Non-goals

New model calls · prompt redesign (recommend, don't do) · scoring goals beyond the
per-game label · any change to e2_slice.py.
