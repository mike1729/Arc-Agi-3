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

---

# Results — 2026-08-04, zero model calls

Code `agent/harness/e2_autopsy.py` (mechanical claim ledger) + `agent/harness/e2_autopsy_labels.py`
(rater labels, every quote checked to occur in its trace or the build fails).
Outputs `logs/e2_autopsy_claims.json` · `logs/e2_autopsy_adjudication.json` ·
`logs/e2_trace_autopsy.json`. 84 transcribed proposals = the 82 scored + ft09/125's 2
vocabulary rejections.

## Headline: the traces do not misread the evidence — they misread the display

**7 reading errors in 3,468 checkable claims (0.20%).** Every claim of a vocabulary key
(2,091), a count (354) and a guard value pair (1,023) was checked against the digest text;
62 came back not-ok and were adjudicated one by one from their recorded context. 52 were
hedged hypotheses or named probe targets, 2 were features named in order to *reject* them,
1 was a stated range ("each ~600-660 transitions" against a true 621–661). Only 7 asserted
something the digest contradicts, all of them `adj:10:*` on a two-component colour in m0r0.

Point-fact fidelity is therefore essentially perfect, and the failure of 82 proposals is
not explained at the reading layer as the note defined it. It is explained one level up:
**by a systematic misreading of what one line of the digest means.**

## The mechanism: one example row read as a group constant

`build_digest` prints, for each effect group of an unresolved key, the guards of a **single
example transition** under the header `varying guards {...}`. The traces read that row as
the value the feature takes *throughout* the group — which converts a feature the miner has
already reported as non-separating into an apparently perfect separator. tu93/125 states
the inference in one sentence:

> But it only shows one value per feature. This implies the feature was constant across
> those transitions.

and then, on the strength of it:

> This is a perfect split!

**59 of 84 proposals (70%) rest on that reading**, across 7 of the 12 cells. It is not a
lapse of attention: tu93/125 derives a physical impossibility from it — colour 4 having
colour 9 on both its left and its right when the census says there is one colour-9 object —
notices it ("That's impossible"), and rescues the reading by inventing a multi-cell object
rather than dropping it. dc22/full contains **both** readings, the correct one first:

> within each group, the guards vary

and then, forty paragraphs later, the one it builds on: "Within a group, they are fixed."
ft09/full is the only trace that states the correct semantics and holds them — "It doesn't
mean they are constant. It just lists the values seen." — and it is one of the two cells
whose rules were not built on example rows.

This also explains the dose asymmetry that `notes/e2-slice.md` attributed to the
verification bar. Both explanations are the same fact: a rule read off one example row is
consistent with the store only where the store is too thin to contain a differing row.

## The digest's refutation is read, contradicted, and explained away

The digest asserts of every unresolved key that no single guard in the vocabulary separates
it. **55 of 84 proposals (65%) come from a trace that derives a single separating guard,
notices the contradiction with that assertion, and resolves it by inventing a defect in the
miner.** The blame is always unevidenced and always different: dc22/125 —

> That *should* separate them! Why does the miner say it can't?

m0r0/125 — "So `adj:12:left == 11` perfectly separates them! Why did the miner fail?";
ft09/full — "The miner failed because it likely" didn't evaluate exact thresholds. m0r0/full
is the sharpest, stating the discipline and breaking it in the same paragraph:

> I should not claim `count:10` separates it if the miner says it doesn't

The digest gives an assertion with no evidence attached, so the model treats it as a claim
to be beaten rather than a constraint to be respected. Nothing in the prompt tells it which
authority wins.

## Evidence weight is absent, uniformly

The note's grounding fact holds literally: tu93/125's 32,990-char trace contains **0**
occurrences of "support", "sample" or "uncertain" while producing the 312-support /
7-contradiction rule. Under a broader pre-declared lexicon (12 weight terms, 8 refutation
terms — `LEXICON` in `e2_autopsy.py`) it has 5 hits in 33k chars, and **the whole corpus is
in that regime: 0.35–3.21 weight tokens per 10k chars, 0.00–1.05 refutation tokens.** No
trace asks how many rows back a rule, and none asks what a counterexample would look like.
The signature generalises. Density does not track survival either — the two highest-weight
cells (m0r0/full 3.21, ls20/full 3.14) verified zero rules.

## Layer distribution over the 84 proposals

| layer | label | proposals |
|---|---|---:|
| READING | example-row-as-group-constant | 59 |
| REASONING | digest-assertion-overridden | 55 |
| REASONING | evidence-weight-blind | 12 |
| REASONING | guard-misread | 10 |
| REASONING | overgeneralization | 5 |
| EXPRESSIBILITY | vocabulary-limit-named | 10 |
| EXPRESSIBILITY | guard-outside-vocabulary | 2 |

Labels are assigned per cell-mechanism and inherited by the rules that mechanism produced —
the traces contain one line of reasoning per cell, not 84. Each carries its quote and the
scope is recorded in every row. Two labels are declared additions to the note's four types:
`example-row-as-group-constant` (READING) and `digest-assertion-overridden` (REASONING).

**The expressibility successes are 10 proposals in 3 cells**, and they are the run's real
output: ft09/125 names `clicked_adjacent_to:C` (already banked as `notes/miner-vocab-v2.md`),
ls20 declines to guard at all across both doses and names distance, parity and action
direction as the missing features. Scored zero, all of them.

**A second expressibility gap is operator-shaped, not feature-shaped.** 10 of 84 proposals
carry a guard value the vocabulary cannot test at all — `not 11`, `!= 0`, `greater than 1`,
`True`/`False`. The model writes the else-branch as a negation because nothing tells it the
only admissible test is equality against a literal. All 10 died.

## Goals, hidden state, probes

Labelled against each game's actual completion condition, read from source and paraphrased
only (PUBLISHING.md — no source is quoted here or in the JSON).

- **Goal: 2 correct, 1 partial, 8 wrong, 1 unfalsifiable.** Both correct are tu93, which
  reasons from inertness — colour 14 is present, unique and never appears in any effect,
  "almost always the goal marker" — and lands on the real condition (movers onto exit
  tiles). That is the only goal-inference method in the corpus that worked, and it used the
  census, not the rules. The partial is m0r0/125 (repositioning the right objects, no notion
  of the pairing-to-zero condition). The 8 wrong are dominated by one prior: *clear the
  board* — dc22, ft09, ls20, vc33 all get a reach-target, edge-match, collect-all or
  assignment condition and answer with removal or counting.
- **Hidden state: 3 correct, 3 wrong, 6 licensed-none.** m0r0 is the only game whose digest
  recorded alias conflicts, and it is the only cell asked a real question — it answered
  "binary phase flag or turn parity" at both doses, and the game's declared hidden state is
  an action count whose parity drives a mode switch. **Correct, at both doses, from three
  alias lines.** The 6 "licensed-none" answered None where the digest showed no conflicts,
  which the evidence supports even though every one of these games does carry a hidden
  counter.
- **Next probe: 8 discriminating, 2 non-discriminating, 2 out-of-band.** The two out-of-band
  are ls20 asking for exact coordinates and a global step count — instrumentation, not an
  action. vc33/125 is the best probe in the run: it asks for the state that breaks the
  correlation between its two candidate guards.

The probe channel is the strongest unscored channel in the slice, and `e2_slice.py` does not
score it.

## Recommendations (not applied — this task recommends, it does not edit)

1. **Print the value SET per feature per group, not one example row.** One line of
   `build_digest`. It removes the reading that 70% of the proposals rest on, and where the
   set is genuinely a singleton the model gets a licensed constant instead of a guessed one.
   Zero model cost, zero store regeneration.
2. **Attach the miner's counterexample to its own assertion.** "No single guard separates
   them" should be followed by, for the best-scoring feature, the two transitions that share
   its value and disagree about the effect. 65% of proposals came from overriding an
   assertion the model was given no evidence for; a refutation it can read is a constraint,
   a bare assertion is a challenge.
3. **State the guard grammar, including the operator.** One sentence — a guard is
   `feature = literal`, equality only, no negation, no threshold, no boolean predicate —
   removes 10 dead-on-arrival proposals and redirects that intent into the expressibility
   channel where it is useful.
4. **Ask for support and expected counterexample per rule.** No trace volunteers either.
   Making them fields costs nothing and makes the rule set self-scoring before verification
   runs.

Ordering is by evidence weight; 1 and 2 are the two that address the 59/84 and 55/84.

## Also found

**The `full`-dose cells were shown strictly less than the 125-dose cells.** `build_digest`
suppresses majority-tier rules from the resolved-rules section, and at full dose every mined
rule is majority-tier — so all six full-dose digests read "RULES THE MECHANICAL MINER
RESOLVED (N total, top 40 by support) — none" while reporting a nonzero N. The full-dose
prompt shows more unresolved evidence and no worked examples at all. Any dose comparison in
`notes/e2-slice.md` is confounded by this, independently of the counterexample story.

## Limits

- **One rater, one sampled run** (seed 20260804, temp 0.6). Every count here is about these
  24 traces, not about Qwen.
- **Blinding was partial and the deviation is recorded in the output JSON.** Label-before-join
  held for 10 of 12 cells; `dc22_125`'s verification array was read during schema discovery,
  and the 8 refuted dose-125 rules are published in `notes/e2-slice.md`, so no blinding was
  ever available for them.
- Trace faithfulness is not guaranteed. The labels describe what the text does with the
  digest, not what the model did.
- The layer counts are per cell-mechanism inherited by rule, so they are not 84 independent
  judgments; the ratio of mechanisms to rules is 12:84.
