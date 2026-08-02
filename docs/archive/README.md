# `docs/archive/` — superseded and spent

Moved here 2026-07-28. **Nothing in this directory is authoritative.** It is kept because these
documents were the pre-registration context for decisions that are still live, not because their
content is still true. Do not cite them; do not resolve a disagreement in their favour.

> **⚠ These files predate the 2026-07-29 family rename and were deliberately not edited** — the
> standing rule is that frozen documents are superseded, not corrected in place. Read `F1` → **Alias**
> (history-required aliasing) and `F3` → **Delay** (sparse delayed causal memory) throughout.
>
> **Except where `F1` is the classification metric.** These documents use `F1` for *both* — see
> `arc-agi-3-execution-plan.md` "changed-cell precision, recall, and F1", which is the harmonic mean
> and has nothing to do with the family. **That collision is exactly why the numbering was retired.**
> Live documents now write `F1 score` for the metric and never use `F1` for a family.

| File | Why it is here |
|---|---|
| `arc-agi-3-execution-plan.md` | Frozen 2026-07-23 under the **old utility ordering**. Contains the 48-model confirmatory matrix that does not run as specified, the 33-day decision protocol that the 18.5-day screening sprint replaced, and "5 submissions/day" — which is factually wrong (the quota is 1/day + 2 final). Superseded by [`arc-agi-3-screening-experiments-and-results.md`](../arc-agi-3-screening-experiments-and-results.md) and [`arc-agi-3-implementation-spec.md`](../arc-agi-3-implementation-spec.md) |
| `arc-agi-3-executive-summary.md` | Frozen 2026-07-23. Contains "competitive placement is not an objective", which was **reversed on 2026-07-25** — leaderboard score is primary |
| `arc-agi-3-agent-architecture.md` | Track B candidate design, never committed. Superseded by [`arc-agi-3-implementation-spec.md`](../arc-agi-3-implementation-spec.md), which is binding. Its four derivations were folded into SPEC §§2, 4.4, 4.5 and 9; its evaluation-apparatus definitions into the screening document's §16 |
| `arc-agi-3-s0-s1-execution.md` | Day-by-day schedule for S0 and S1. **S0 complete** (2026-07-25); **S1 closed on the DEGRADED branch** (2026-07-28) after the blind re-rate passed κ 0.7207 over 30/30 rows and was promoted. Spent as a schedule, not wrong. Its verification register lives on in `gate_manifest.yaml → verification:` |

## What was extracted before archiving

These two frozen documents were the only definition sites for four terms that live documents still
use. All four are now reproduced in full in
[`arc-agi-3-screening-experiments-and-results.md` §16](../arc-agi-3-screening-experiments-and-results.md),
which is the definition site from 2026-07-28 onward. (They passed briefly through
`agent-architecture.md` §10 on the same day, before that file was itself archived.)

- **common-candidate audit** (= same-candidate oracle audit) — `execution-plan.md` §6.7
- **attribution ladder** (the four rungs) — `execution-plan.md` §6.7
- **diagnostic contract** — `execution-plan.md` §6.7
- **procedural boundary suite** — `executive-summary.md`, *Controlled mechanism study*

If anything else here turns out to be load-bearing, extract it into a live document rather than
promoting this directory back to authority.

## Also removed on 2026-07-28

`docs/sources/` — four earlier LLM drafts (1,692 lines), marked "not authoritative, do not cite" and
referenced by nothing. Deleted rather than archived; recoverable from git history if ever needed.
