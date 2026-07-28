# `tests/` — the S1-d gate regressions, and how they are kept honest

Two things live here, and the second exists because the first kept lying.

| file | what it is |
|---|---|
| `test_s1d_gates.py` | 121 regressions over the corpus builder and the blind re-rate. Every test names the defect it pins |
| `run_mutation_harness.py` | breaks the source on purpose and checks a test notices |
| `mutation_allowlist.txt` | survivors that are provably not bugs, each with a reason |

```bash
.venv/bin/python -m pytest tests/ -q                    # the suite
.venv/bin/python tests/run_mutation_harness.py          # is the suite worth anything?
```

## Why a mutation harness

Across four review rounds the guards in `agent/harness/s1d_*` mostly held, and the **tests** were what
kept failing — silently, while green:

- `test_undefined_kappa_is_refused` went vacuous when `score` started requiring a manifest. It passed
  none, so it was refused for the missing manifest and never reached the branch it named. It would
  have passed with that branch deleted.
- `test_partial_run_config_is_incomplete` dropped `model` **and** `sampling`, so it could not tell
  whether `provider`, `context_window` and the budget were required. Reverting that requirement broke
  nothing.
- `test_forged_packet_digests_over_correct_ids_are_refused` passed through a *neighbouring* check.
  The guard it was written for could be disabled and the assertion still held.

Every one was found by deleting a line and noticing nothing failed. None was found by reading the
tests. A passing suite says "no test fails"; a surviving mutant says "this line could be deleted and
nothing would notice", which is the question worth asking of a pre-registration gate.

The recurring cause is **assertions on exit codes**. When several guards reject the same bad input,
`== 1` cannot say which one fired, so a test keeps passing after its subject is gone. This has now
accounted for nine survivors across five rounds, so treat it as a rule rather than a special case:
**where two checks can reject the same input, assert on the message.**

`score` catching broad exceptions makes this worse, deliberately. Turning a crash into a refusal is
right — a crash must leave the same trace a refusal does — but it also means *removing* a guard often
still produces exit 1, via the exception its absence causes. Message assertions are what separate
"the guard fired" from "something fired".

## Reading the output

```
killed      the suite failed  -> a test pins that line
SURVIVED    the suite passed  -> nothing tests it
```

Exit status is 0 only when every survivor is allowlisted, so this is usable as a pre-commit gate.

**The baseline runs in the sandbox, not the repository.** Measuring it at the repo root while every
mutant ran in a temp copy compared two different environments: a test reading `gate_manifest.yaml` —
which the sandbox does not contain — passed the baseline and then failed for *every* mutant, reporting
a flawless **155 killed / 0 survived** that meant only "one test errors out there". The run now prints
the sandbox baseline including its skip count, because a suite that mostly skips there kills mutants it
never exercised.
Current state: **126 killed, 30 survived, all 30 allowlisted**.

Self-test — adding a guard no test covers turns the run red even though `pytest` reports green:

```
121 passed
harness EXIT=1  ·  3 UNTESTED line(s)
```

**Keep these numbers current.** They were stale for one review cycle, which is exactly the failure this
directory exists to catch — a document asserting a verification state it no longer has.

## Operators

| operator | change | why this one |
|---|---|---|
| `guard-off` | an `if` whose body returns/continues/breaks/raises becomes `if False:` | every real defect found in review was a guard missing, scoped wrongly, or checking the wrong object |
| `compare` | `>=`↔`>`, `<=`↔`<`, `==`↔`!=`, `is`↔`is not` | boundaries are the blind spot: tests written with clearly-passing values never touch the edge. This is how the agreement-floor boundary turned out to be untested |
| `return-ok` | `return 1` → `return 0` | the guard detects the problem and reports success anyway — several defects here had exactly that shape |

## The allowlist is not a mute button

Three categories only — `equivalent`, `message-only`, `defensive` — and each entry carries its reason.
**A guard that decides whether a category drives the build order never belongs there.** If one appears,
the fix is a test.

Keys are `file::function::operator::fragment`, not line numbers, so they survive edits above them. A
stale key stops matching and its mutant reappears as unexplained — the right direction to fail in.

## Scope

Only `s1d_blind_rerate.py` and `s1d_build_corpus.py` are mutated by default. `s1d_apply_labels.py`,
`s1d_cross_run.py`, `s1d_label.py` and `s1d_worksheet.py` have **no direct tests**: mutating them
would report every line as untested, which is true and unhelpful. The harness prints that fact on
every run rather than hiding it. Run `--target <module>` once those have tests.

**The canonical gate result is write-protected.** `logs/s1d_rerate_result.json` is what the manifest
roll-ups are filled from. Every run writes to its own `--result-out` (mandatory, no default), and the
refusal is enforced in `_write_result` — the single choke point every write passes through — rather
than in `main()`, because the tests and the other harness modules call `score()` directly and an
invariant that only holds via argparse is not one.

`promote` is the only way in, and it does not trust what it is given: the submitted file is treated as
a POINTER TO THREE INPUTS, those inputs are re-scored at the pre-registered floor, and the
**recomputed** artifact is what gets written. Verifying the payload's own claims cannot work — a
hand-written result with `gate_valid: true` and an empty `inputs` map passed, because a loop over zero
inputs verifies zero inputs, and even requiring all three fails against a forgery that quotes correct
hashes beside an altered verdict. `invalidate` is the counterpart for withdrawing a verdict.

`select()` is pre-registration surface. `score` re-derives the drawn sample from `(corpus, n, seed)`
to verify it, so changing the selection logic invalidates every manifest issued before the change.
That is the right failure direction, but it means editing `select()` needs an erratum, not a commit.
