# Project index and decision register

Start here. Two primary documents plus this index; everything else is rationale or archive.

## The two primary documents

| | Document | Role | Amendment rule |
|---|---|---|---|
| **Normative** | [`arc-agi-3-implementation-spec.md`](arc-agi-3-implementation-spec.md) | What the deployed agent **is**: component definitions and interfaces · tier membership · runtime arbitration · build order and slack policy · gates and production retention · predeclared tolerances · fallback behaviour | Dated amendment, logged in the register below. **Never amended implicitly by a result** |
| **Evidentiary** | [`arc-agi-3-screening-experiments-and-results.md`](arc-agi-3-screening-experiments-and-results.md) | How uncertain choices are **tested** and what happened: S0–S5 protocols · hypotheses and arms · schedules and budgets · actual results · deviations · limitations · pre-registration records · the S5 audit | Updated freely as measurement proceeds |

**Where they conflict, the specification governs until explicitly amended.**

```
experiments produce evidence  →  decision register (below) evaluates it
                              →  implementation spec is amended  →  code implements the amendment
```

The mapping between them is a table in each: SPEC §1.1 lists *decision → evidence source*; the
screening document's §2.1 is its inverse, *sprint → decision informed*. An experiment that maps to no
row is either infrastructure or should not be run.

## Supporting documents

| Document | Role |
|---|---|
| [`arc-agi-3-ship-jepa-x-architecture.md`](arc-agi-3-ship-jepa-x-architecture.md) | **Track A.** The belief model's internals — SPEC §11 specifies it only to admission level and defers the rest here. Also what S3's arms instantiate, and what the paper describes |
| [`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md) | Can the design work? Source of the **F3 risk** — the central argument against reconstruction-free prediction |
| [`arc-agi-3-architecture-alternatives.md`](arc-agi-3-architecture-alternatives.md) | What would work better. Ordinal judgments, not measurements |
| [`archive/`](archive/) | Superseded or spent. **Not authoritative, do not cite** |

Pre-registration lives in [`../gate_manifest.yaml`](../gate_manifest.yaml) (append-only; changes need
a dated erratum). Session output and working analysis live in [`../notes/`](../notes/), never in a new
document here.

> **One document per decision horizon. New thinking amends an existing document or lands in
> `notes/`.** The doc count reached nine because each thinking session produced a file; that is the
> failure mode this rule exists to prevent.

---

## Decision register

One entry per binding change to the specification. A result becomes binding **only** by appearing
here and in a dated spec amendment — never by being written down in the screening document.

Entry format:

```yaml
decision_id: R0-2026-09-04
question: predictive objective for the belief model
evidence:
  - experiment: S3
  - artifact: results/s3-summary.json
decision: exact_sparse_delta
rejected:
  - reconstruction_free_latent
  - reconstructive_next_state
effective_spec_sections: ["§10.2", "§11"]
approved_at: 2026-09-04
```

### Entries

```yaml
decision_id: DOCS-2026-07-28
question: which document is authoritative now that a binding implementation spec exists
evidence:
  - artifact: docs/arc-agi-3-implementation-spec.md   # v1.2, self-declared binding
decision: split_authority_by_phase
detail: >
  Implementation spec is normative for the deployed agent and governs on conflict.
  The screening document is re-scoped to evidence and results; its component
  inventory (former §2) is withdrawn in favour of SPEC §3, and its claim to
  supersede architecture build orders is withdrawn. agent-architecture.md is
  archived; its four derivations are folded into SPEC §§2, 4.4, 4.5, 9, and its
  evaluation-apparatus definitions into the screening document's §16 appendix.
effective_spec_sections: ["§1.1"]
approved_at: 2026-07-28
```

```yaml
decision_id: G0-SCOPE-2026-07-28
question: >
  goal induction was ranked first among build targets on S1-d's single-run
  primary_share of 75%; the spec places G0 experiments in Tier 3 and production
  integration in Tier 4. Which ordering binds?
evidence:
  - experiment: S1-d, three runs of one byte-identical configuration
  - artifact: notes/s1d-cross-run-stability.md
  - finding: >
      goal_unknown primary_share (L2+) fell 75% -> 53% -> 27%; only 5 of 16
      (game, level) triples agree across all three runs. Real variation vs rating
      artifact is NOT yet established: the only re-rate is partial (17 of 25), not
      blind, primary labels only — consistent with real variation, cannot demonstrate
      it. goal_unknown remains the top POOLED category in all three runs (76/56/44%)
      with flat episode_share 76-92%.
decision: gate_not_build_order
detail: >
  The spec's ordering binds. A build order pinned to an unstable statistic is the
  failure mode; a gate with predeclared margins and a non-inferiority floor is the
  correct instrument, and this holds whichever explanation the blind re-rate supports.
  Goal inference remains the largest single lever — that is not in dispute — but it
  earns integration through G0 rather than inheriting priority.
revisit_if: the blind re-rate shows the instability is a rating artifact, not the agent.
effective_spec_sections: ["§3", "§9", "§9.7"]
approved_at: 2026-07-28
```

---

## Open items requiring a decision

| # | Item | Blocking |
|---|---|---|
| 1 | **Two pre-registrations coexist.** `gate_manifest.yaml` has `s2`–`s5` as `NOT_STARTED` while SPEC §13 predeclares ~30 constants under its own freeze rule (§13.6: loss-side frozen now, cost-side re-anchorable once). Either the spec's numbers migrate into the manifest, or the manifest yields build-phase authority to the spec — but both currently claim the role | anything that cites a pre-registered number |
| 2 | **Calendar tail.** SPEC §12 ends at "submission Oct 18" with W8 closing Oct 16; the project's other dates treat Oct 18 as *feature freeze* with ~3 weeks of tuning before the Nov 2 final submission. Either the spec's scope ends at freeze, or the tuning window has been absorbed | S5 audit, and the final-submission plan |
| 3 | **The DEGRADED submission branch.** No entrant-authored payload exists, so S5's B axis has no score to read. SPEC step 3 (W2) produces one; until then the branch stands | S5's B axis |
