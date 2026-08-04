# Restart record — 2026-08-04

This repository restarts here. Everything that existed before this commit is preserved unchanged
on the archive branch; `main` is deliberately close to empty while the new direction is written
down. This file is the link in the chain: the decision register it replaces
(`docs/README.md`) lives only on the archive branch from now on, so the register's continuity
depends on this record and on the register entry in `gate_manifest.yaml`.

## Where the previous version is

| | |
|---|---|
| Branch | `archive/screening-line-2026-08-04` (pushed to `origin`) |
| Tag | `v0-screening-line-2026-08-04` (annotated, pushed to `origin`) |
| Last commit | `85f3e2b` — *MU screen: implementation, frozen measurement, and a `stop` verdict* |

No history was rewritten. This commit **descends from** `85f3e2b`; the archive refs are pointers to
the pre-restart state, not a separate lineage. Anything from the old tree is retrievable directly:

```bash
git show archive/screening-line-2026-08-04:notes/mu-representation-screen-results.md
```

The rule for the reusable estate — the replay driver, `s2_replay_ingest` with its parsing traps, the
fork tables — is **resurrect on demand**, not pre-emptive keeping. They are one `git show` away and
carrying them forward would import assumptions the new architecture has not agreed to.

## What is not in git, and must not be treated as archived by it

The most expensive artifacts in this project are gitignored. No branch, tag, or push preserves them.
They live on one disk and are left in place, untouched:

- `data/` — 6.5 GB: human replay sessions, the 25 public game sources. Competition material; not
  redistributable, therefore never committed.
- `logs/` — 2 GB of raw measurement output (`*_raw.jsonl`, `es_source_gold_r.sealed`, the Kaggle run
  directories). Reference runs are stochastic and hours long; a lost run cannot be reproduced, only
  re-sampled into a different result.
- `agent/work/` — the throwaway build of the vendored reference.
- `CLAUDE.md` — local working context.

**`git clean -dfx` would destroy all of it.** Tracked-file cleanup and these assets are two separate
worlds; nothing in a normal git workflow touches them.

## What the screening line established

Four screens ran between 2026-07-30 and 2026-08-03 against the local `Qwen3.6-27B-8bit` (MLX) model.
All four terminated negatively. Full records are on the archive branch under `notes/`.

| Screen | Outcome |
|---|---|
| **VP** — perception | VP1 complete, 288/288 rows, zero errors. All six arms fail the gates; pure-image arms recover neither marked local state nor the 3×3 patch, and no channel rescues global counting. Terminal routed stop — VP2 never ran. |
| **GI-2** — grounded binding | Sprint A stopped at representability, 2026-07-30, after A0–A3. |
| **ES** — evidence sufficiency | Closed out coverage-blocked before its common freeze, 2026-08-03. Six of six games unproven; zero `ES-USE` calls spent; operator elected to record failure. |
| **MU** — representation | Complete: 492 calls, 3.55 h GPU, schema validity 1.000. Verdict **`stop`** — no funding cell among {T3, T4} is screen-positive on C. The representation menu is exhausted for Qwen mechanics use. |

**Thinking-mode invalidation.** A subsequent finding is that the local Qwen measurements were taken
under a thinking-mode configuration that does not represent the model's usable capability. This
**voids the Qwen-measured cells** across the screening line. The archived results remain accurate
records of what was run; they no longer stand as evidence about what the model can do. The full
statement of this finding belongs with the new direction and is not reproduced here — it is recorded
in this file so that nobody reads the archived verdicts as a live capability ceiling.

Together these are why the project restarts rather than continues: the screening line never
established that any usable local-model capability exists, and the evidence it did produce is now
partly void.

## The new direction

Exploration-first evidence collection; Qwen used as a **batch synthesizer over a verified store**
rather than as an online perceiver; **L1 as the evidence budget**. The architecture is being written
down in a separate working session and will land as its own document on this branch — until it does,
this section is a one-line placeholder, not a specification.

**First measurement, once the direction is written:** the offline L1→L2 rule-survival measurement.
It is zero-model, needs only `data/` plus a resurrected replay driver, and it prices the OOD
objection before any new architecture is built.

## What carried forward, and why

| Kept | Reason |
|---|---|
| `agent/reference/`, `agent/patches/` | The vendored taaf snapshot is the external substrate the new architecture still needs — game client, scorer, segmentation. Vendored unmodified; deviations stay as patch files. |
| `PUBLISHING.md` | **The policy is unchanged by the restart.** This repository is never made public; git history counts as redistribution, and deleting a directory later is not sufficient. The archive branch changes nothing about that. |
| `LICENSE`, `.gitignore` | Unchanged. |

## Open items

1. **`CLAUDE.md` must be rewritten by hand.** It is gitignored, so nothing above touched it. It
   currently asserts a document precedence table, a sprint state, and a hard-stop schedule that no
   longer exist on this branch. Until it is rewritten it is actively misleading.
2. The new architecture document, and the pre-registration blocks that go with it.
3. Stale side branches `s1-review-hardening` and `s2-goal-predicates-v2` are left as they are —
   they are already their own archive.
