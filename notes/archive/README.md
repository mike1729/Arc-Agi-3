# notes/archive — spent working notes

Moved here 2026-08-02. Same rule as `docs/archive/`: **superseded or spent — not
authoritative, do not cite from new work.** Content is preserved verbatim; `git log --follow`
reaches each file's full history at its original `notes/` path.

`gate_manifest.yaml` `evidence_ref` entries and older notes that cite these files by their
pre-move `notes/<name>.md` path resolve here — the manifest is append-only and its historical
pointers are not edited for a file move.

| File | Why archived |
|---|---|
| `s1-code-inspection.md` | S1 harness read-through; findings folded into the DEV deviation records |
| `s1-quantization-arm.md` | 4-bit vs 8-bit matched pair; consumed by the measurement-model choice (8-bit) |
| `s1-queued-refactor.md` | refactor queue for the S1-e run; S1-e concluded |
| `s1e-phase1-keyboard.md` | S1-e phase log; phase concluded, results in `s1-measurements.md` and the screening doc |
| `s1e-phase2-running.md` | S1-e live log; phase concluded, summary recorded elsewhere |
| `s2-sprint.md` | self-labelled "TEMPORARY. DERIVED. NOT AUTHORITATIVE."; superseded by `docs/arc-agi-3-execution-schedule.md` |

Kept live deliberately (checked 2026-08-02, citation map in the cleanup commit message):
`design-pivot.md`, `gi1-iteration-audit.md`, `gi2-grounded-binding.md` (frozen §3.4 is
re-sliced by `gi2_sprint_ar.py --verify`), `vp-perception-screen.md` (active),
`s1-reference-freeze.md` (cited line-anchored by the VP note; describes the live submission
stack), `s1d-failure-frequencies.md` (the build-order input), `s1-retired-scripts.md`
(provenance ledger for deleted code), `s1-measurements.md` + `s1-closeout.md` +
`s1-verification.md` + `s1-reference-variance.md` + `s1d-cross-run-stability.md` (cited by the
evidentiary screening doc, `docs/README.md`, `paper/`, or the manifest), and the pending
build-phase planning set (`build-difficulty.md`, `training-data-master.md`,
`screening-training-data.md`, `evaluator-training-data.md`,
`progress-head-and-goal-inference.md`, `local-compute-options.md`) — paused by the design
pivot, not spent.
