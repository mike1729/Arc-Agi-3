# Queued after S1-e — refactor and hygiene

Queued 2026-07-26, deliberately **not** applied while the breadth run is in flight.

**Why nothing was changed.** `run_s1e_by_action_class.sh` is executing, and bash reads a script
incrementally by byte offset — editing a running script can make it execute garbage. `run_resumable.py`
is also re-invoked for phase 2 (ACTION6). Risking a ~16 h run for cosmetic deduplication is a bad trade,
so the analysis was completed and the changes were queued instead.

**Precondition: S1-e has concluded.** Verify before starting:

```
pgrep -f run_s1e_by_action_class     # must return nothing
```

---

## 1. `run_artifacts.py` — one loader, keyed by game  *(task #3)*

Four modules independently parse `benchmark.json` / `*_events.jsonl` / `*_requests.jsonl`:
`analyse_reference_run.py`, `make_run_tables.py`, `s1c_measure.py`, `s1d_label.py`. **That duplication is
why the `game_runs[0]` bug had to be fixed twice.** A shared loader that only ever returns a per-game
view makes the bug unrepresentable rather than merely fixed.

Checked 2026-07-26: `make_run_tables.py` and `analyse_reference_run.py` iterate all `game_runs`
correctly and do **not** carry the defect. `analyse_reference_run.py` being correct is exactly why
`per_game_analysis.json` could serve as the independent cross-check that validated the repair — so
migrate those two only if it does not put their output at risk.

## 2. Game lists from measured data, not four hardcoded copies  *(task #4)*

The 25-game set and the 6 keyboard games are typed out in `run_resumable.py`,
`run_s1e_by_action_class.sh`, `s1d_blind_rerate.py` and `gate_manifest.yaml`, in three different
formats, linked by nothing. The six define **both** the S1-E4 eligibility stratum **and** the
concurrency schedule; drift between those two uses would be silent.

Derive from `logs/s2_arc_conventions.json`. **Blocked on item 3** — that file is not in the repo.

## 3. Track the small measurement JSONs  *(task #5)*

`logs/` is gitignored, so every `logs/*.json` cited as evidence across `notes/` exists only on this
machine and is in no commit. **The raw evidence for all of S1 has no off-machine copy.**

Add exceptions for the small derived-measurement files; keep `logs/runs/` and `logs/quarantine/`
ignored. Per `PUBLISHING.md`, read each file before tracking it — anything carrying reference-derived
prompts or model output is bucket-3 and must not be committed.

Once `s2_arc_conventions.json` is tracked, `measure_arc_conventions.py` can be retired too; it is kept
today only because its output is untracked.

## 4. Dedupe `game_of()` and `COMPLETED`  *(task #6)*

`game_of()` is byte-identical in two modules. `{"gave_up", "won"}` is defined twice — and that one is
load-bearing: it encodes the S1-E8 inclusion criterion, so the supervisor's retry rule and the corpus
builder's exclusion rule must agree by construction, not coincidence.

---

## Not queued — decisions, not refactors

- **S1-E7**, the re-rate sample size. Better made once the concluded-game count is known.
- **`docs/sources/`** — 4 files, 88 K, "not authoritative, do not cite", referenced by nothing. Removal
  would want a matching edit to the precedence table in `CLAUDE.md`. Left alone because the instruction
  was to minimise *code*.
- **Back up `logs/` off-machine.** Independent of the repo question: a disk failure now costs the Kaggle
  reference run and everything S1-e is producing.
