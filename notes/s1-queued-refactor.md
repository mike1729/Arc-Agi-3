# Queued after S1-e — refactor and hygiene

Queued 2026-07-26 while the breadth run was in flight. **S1-e has concluded** (`pgrep -f
run_s1e_by_action_class` returns nothing), so the precondition this file was gated on is discharged
and the remaining items are simply open work.

**Updated 2026-07-28.** Two of the four are done; the note previously still said "not applied while
the breadth run is in flight", which stopped being true two days ago and made a finished task look
pending.

| # | item | state |
|---:|---|---|
| 1 | `run_artifacts.py` — one loader for a run directory | **done** |
| 2 | game lists from measured data, not hardcoded copies | **open** — now unblocked |
| 3 | track the small measurement JSONs | **done** |
| 4 | dedupe `game_of()` and the finished-state set | **half done** |

---

## Done

**1. `run_artifacts.py`.** Four modules independently parsed `benchmark.json` / `*_events.jsonl` /
`*_requests.jsonl`, which is why the `game_runs[0]` bug had to be fixed twice. The shared loader
exists and every accessor is per **pass** (`<game>_p<N>`), not per game — the pass axis turned out to
carry the same defect: `game_runs` is passes-major and repeats the game id, so a game-keyed mapping
silently served the last pass's data for every pass. `make_run_tables.py` and
`analyse_reference_run.py` were verified free of the original defect and deliberately left alone, so
`per_game_analysis.json` remains an independent cross-check.

**3. Track the small measurement JSONs.** `.gitignore` now admits the derived-measurement files while
keeping `logs/runs/`, `logs/quarantine/` and the raw `logs/kaggle_v*/` directories out. Each tracked
file was read before being added, per `PUBLISHING.md`; the corpus JSONs carry reference reasoning
verbatim and are listed as **never publish** in `PUBLISHING.md` and `logs/README.md`.

---

## Open

**2. Game lists from measured data.** The 25-game set and the 6 keyboard games are still typed out in
`run_resumable.py`, `run_s1e_by_action_class.sh`, `run_s1e_v2.sh`, `s1d_blind_rerate.py` and
`gate_manifest.yaml`, in three formats, linked by nothing. The six define **both** the S1-E4
eligibility stratum **and** the concurrency schedule, so drift between those two uses would be silent.

**No longer blocked:** `logs/s2_arc_conventions.json` is tracked as of 2026-07-28, which was the
dependency. Deriving from it also retires `measure_arc_conventions.py`, kept only because its output
was untracked.

**4. Dedupe the finished-state set.** `game_of()` is no longer duplicated — item 1 absorbed it. But
`{"gave_up", "won"}` is still defined three times, in `run_artifacts.py`, `run_resumable.py` and
`s1d_build_corpus.py`. That one is load-bearing: it encodes the S1-E8/S1-E9 inclusion criterion, so
the supervisor's retry rule and the corpus builder's exclusion rule must agree by construction rather
than by coincidence.

---

## Not refactors — still live

- **Back up `logs/` off-machine.** Independent of the repo question and now the largest exposure:
  `kaggle_v2/`, `v3/` and `v4/` are ~1.6 GB of irreproducible stochastic evidence (the agent samples at
  temperature 0.6 with no seed), deliberately gitignored, and the three of them jointly constitute the
  75-episode pooled corpus. Losing one turns it into a 50-episode corpus. See `logs/README.md`.
- **S1-E7** (re-rate sample size) was resolved by S1-E11 and re-scoped by S1-E14; no longer queued.
- ~~`docs/sources/`~~ **done 2026-07-28** in the docs consolidation: `sources/` deleted (recoverable
  from history), three superseded documents moved to `docs/archive/`.
