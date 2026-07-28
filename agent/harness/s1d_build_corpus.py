"""Assemble the S1-d labelling corpus from run directories — with the pooling hazard blocked.

WHY THIS IS NOT A CONCATENATION
-------------------------------
As of 2026-07-26 the local runs hold 47 failure episodes across only 13 distinct games. They are not 47
observations. They are the same games re-run under different configurations while the harness was being
debugged:

    wa30-ee6fef47    0 actions  |  201 actions  |  201 actions
    lp85-305b61c3    0 actions  |    1 action   |    3 actions  |  26 actions
    ft09-0d8bbf25    nine episodes, all zero-action, from five superseded configs

Concatenating episode files would enter the same game up to nine times into a distribution whose
`primary_share` ranks eight weeks of construction, weighting whichever game happened to be debugged
most. Worse, the duplicates are not random: they are biased toward the games that failed hardest,
because those are the ones that got re-run.

So this script REFUSES to emit a corpus containing two episodes for the same (game, level) unless one
is explicitly selected. Selection is by run directory — never automatic, because "the newest run" is
not a rule that survives a rerun done for an unrelated reason.

REPLICATES ARE NOT DUPLICATES — `--replicates` (S1-E11, as amended by S1-E14)
-----------------------------------------------------------------------------
The hazard above is pooling one game across DIFFERENT configurations. A replicate is the opposite
case: the same game replayed under an IDENTICAL configuration. Those are genuine independent
observations — they are what makes the pre-registered `sample_size: 30` reachable (25 games -> 75
episodes over three runs) and they supply the paired replicates S4 needs, given the run-to-run
disagreement measured on 2026-07-27 (36% of games change their cleared-level count between v1 and v2,
20% between v2 and v3). Collapsing them on (game, level) would discard exactly what the erratum was
filed to obtain.

S1-E11 originally specified replicates as `n_passes = 3` inside ONE kernel. **S1-E14 changed the
mechanism to repeated SINGLE-PASS RUNS**, because passes inside one kernel share a session, a vLLM
server and a GPU — so they bound within-run variance, while S4 compares advisor-on to advisor-off as
SEPARATE runs and needs the run-to-run floor.

That change has a consequence this script has to encode, because the obvious implementation is wrong
in both directions:

  * keying on the PASS alone collapses the replicates. Under S1-E14 every episode has pass_index 0,
    so (game, level, pass) makes three runs look like one. The key is (game, level, run, pass).
  * keying ownership on the RUN DIRECTORY refuses the replicates. The original guard said the first
    directory to supply a (game, level) owns it and no other directory may contribute — correct in
    intent, too strict in form, because it conflated "different directory" with "different
    configuration".

So ownership keys on a CONFIGURATION SIGNATURE (see `_config_signature`), and it is scoped to the RUN,
not to the (game, level). The first run to contribute fixes the corpus configuration; any run sharing
it may add replicates; a run that does not match is refused ENTIRELY, and both signatures are reported
so the refusal can be checked rather than trusted.

  * scoping it per (game, level) is not enough, and this was a real defect. A foreign-configuration run
    was refused only where it collided with a game-level someone already owned, so every game unique to
    it walked in — a different-model run contributed five levels no other run covered and the corpus
    silently held two configurations. "One configuration" is a property of the whole corpus, and a
    per-episode check cannot enforce it.

Off by default — a corpus that silently multiplied its own denominator would inflate every
`primary_share`.

THE CENSORING HAZARD — decided by wall-clock, not by the recorded state (S1-E9)
-------------------------------------------------------------------------------
The recorded state does NOT tell you whether the agent concluded. Measured 2026-07-26: 0 of 25
reference games finished early — all ran 7920.8-7921.3 s against a 7920 s budget — yet all recorded
`gave_up`, while our identically budget-terminated games recorded `cancelled`. The difference is
generation length: a long generation in flight at the deadline gets killed, and that path sets
`stop_event`. The label reflects the model's token rate, not the agent's behaviour.

So admissibility turns on WHY the run stopped, which only the wall-clock reveals:

  admissible    the agent finished (`won`/`gave_up` before the budget), OR the run consumed the full
                uniform pre-registered budget. The latter is a stated experimental condition, and the
                episode is RIGHT-CENSORED at a known bound recorded as `censored_at_seconds`.
  inadmissible  the run stopped EARLY — an operator kill or a crash. Non-uniform, and correlated with
                nothing but the operator's attention. It records `cancelled` too; only the wall-clock
                separates it from a budget expiry.

`latency_or_budget` frequency must be reported WITH the statement that it is partly a property of the
budget rather than of the agent — that caveat is what the censoring bound exists to support.

A run killed early enough may not even have its games recorded in `benchmark.json` — several runs here
have event files for games with no matching `game_run`. That is reported as a warning, not silently
absorbed, and such episodes carry no baseline or terminal state.

  --runs        run directories to draw from, in priority order (first match for a (game, level) wins)
  --require-evidence   drop episodes with no reasoning evidence. Three categories
                       (`reasoning_inconsistency`, `goal_unknown`, `retrieval_or_context`) are defined
                       on reasoning text; an episode without it cannot be rated on them, and silently
                       keeping it makes those categories look rarer than they are.
  --allow-censored     KEEP episodes from runs that never completed. Off by default. Use only for
                       inspecting partial runs, never to build a corpus that ranks the build order.
  --replicates         keep every (run, pass) replicate of a (game, level) whose configuration matches
                       the one that owns it, instead of one. For the S1-E11/S1-E14 corpus. See
                       "REPLICATES ARE NOT DUPLICATES" above.

Every exclusion is reported. A corpus that quietly dropped episodes would understate its own denominator.

Run:
  .venv/bin/python agent/harness/s1d_build_corpus.py --runs logs/runs/A logs/runs/B --out logs/s1d_corpus.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

from s1d_label import extract_episodes, frequencies


# S1-E9: the agent genuinely finishing is only ONE way to conclude; consuming the full uniform budget
# is the other, and the recorded state cannot tell them apart from an early kill.
AGENT_FINISHED = {"gave_up", "won"}
BUDGET_TOLERANCE = 0.98


def _budget_seconds(run_dir: Path):
    """The uniform per-game budget this run was launched with, from its own run_config.json."""
    rc = run_dir / "run_config.json"
    if not rc.exists():
        return None
    try:
        m = json.loads(rc.read_text()).get("max_runtime_minutes_per_game")
        return float(m) * 60.0 if m else None
    except Exception:  # noqa: BLE001
        return None


# Per-invocation fields that legitimately differ between two runs of the SAME configuration. They are
# stripped before comparison; everything else in the repr is treated as configuration.
_VOLATILE_SOLVER_FIELDS = ("job_dir=", "soft_end_time=", "runtime_environment=")
UNKNOWN_SIGNATURE = "UNKNOWN"
INCOMPLETE_PREFIX = "INCOMPLETE"

# Fields WITHOUT WHICH TWO RUNS CANNOT BE CALLED THE SAME CONFIGURATION. Absence must not read as
# agreement: `run_config.json` is the only place model and sampling are recorded, Kaggle does not emit
# it (ours are reconstructed by hand from each run's log and taaf_setup_env.json), and an earlier
# version simply omitted these parts of the signature when the file was missing. Two runs on DIFFERENT
# WEIGHTS then produced byte-identical signatures that did not look UNKNOWN, and pooled — the exact
# failure S1-E14's guard exists to prevent, reached by leaving the guard uninformed instead of wrong.
#
# All five are outcome-relevant, not bookkeeping. `provider` decides the inference stack and therefore
# tokenisation and stop behaviour; `context_window` decides when history is truncated, which is what
# `retrieval_or_context` is defined on; `max_runtime_minutes_per_game` is the censoring bound that
# `latency_or_budget` is defined on, so two runs on different budgets do not produce comparable
# episodes of that category at all. Requiring only model and sampling let a run missing any of the
# other three pass as a complete, poolable identity.
_REQUIRED_IDENTITY = ("model", "sampling", "provider", "context_window",
                      "max_runtime_minutes_per_game")

# `sampling` is a NESTED dict, and requiring the key only checked that the dict was non-empty. A run
# recording temperature alone therefore passed as a complete identity while top_p, top_k, the seed and
# the thinking flag were unknown — each of which changes the distribution the episodes were drawn from.
# A partially-recorded sampling config is an incomplete identity for the same reason a missing one is.
_REQUIRED_SAMPLING = ("LOCAL_ANALYZER_TEMPERATURE", "LOCAL_ANALYZER_TOP_P", "LOCAL_ANALYZER_TOP_K",
                      "LOCAL_ANALYZER_SEED", "LOCAL_ANALYZER_ENABLE_THINKING")


def _config_signature(run_dir: Path) -> str:
    """The configuration two runs must share before their episodes may be pooled (S1-E14).

    Built from the benchmark label plus the `HarnessSolver(...)` repr the harness prints at startup.
    The LABEL matters as much as the repr: `save_request_logs` is set after the repr is printed, so
    the unlogged 2026-07-26 run (`duck-harness-kaggle`) and the logged ones
    (`duck-harness-kaggle-logged`) have identical reprs and are separated only by their label.

    Returns UNKNOWN when it cannot be established. UNKNOWN never equals UNKNOWN — an unidentifiable
    run is refused rather than pooled on the assumption that it matches.
    """
    parts = []
    bj = run_dir / "benchmark.json"
    if bj.exists():
        try:
            b = json.loads(bj.read_text())
            parts.append(f"label={b.get('label')}")
            parts.append(f"n_passes={b.get('n_passes')}")
        except Exception:  # noqa: BLE001
            pass
    # WHAT THE MODEL WAS AND HOW IT SAMPLED. Neither appears in the benchmark or in the HarnessSolver
    # repr — the repr carries `model='local'`, which is a transport, not an identity. Without these two
    # runs on different weights, or at different temperature/top_p/top_k/seed, produce IDENTICAL
    # signatures and pool as one configuration. That is the exact failure the S1-E14 guard exists to
    # prevent, so the fields it needs most were the ones missing from it.
    rc = run_dir / "run_config.json"
    cfg = {}
    if rc.exists():
        try:
            cfg = json.loads(rc.read_text())
        except Exception:  # noqa: BLE001
            cfg = {}
    missing = [f for f in _REQUIRED_IDENTITY if not cfg.get(f)]
    # `SEED: null` is a RECORDED value (the reference samples unseeded), so test key presence, not
    # truthiness — otherwise the one field that says "this run is not reproducible" reads as absent.
    sampling_cfg = cfg.get("sampling")
    if isinstance(sampling_cfg, dict):
        missing += [f"sampling.{k}" for k in _REQUIRED_SAMPLING if k not in sampling_cfg]
    if not missing:
        parts.append(f"model={cfg.get('model')}")
        parts.append(f"provider={cfg.get('provider')}")
        parts.append(f"context_window={cfg.get('context_window')}")
        # Concurrency is not REQUIRED — a run that omits it is still identifiable — but where it is
        # recorded it must split the signature: contention changes how much wall clock each game gets
        # against a fixed budget, and the budget is what `latency_or_budget` turns on.
        parts.append(f"concurrency={cfg.get('effective_concurrent_jobs')}")
        s = cfg.get("sampling") or {}
        parts.append("sampling(" + ", ".join(f"{k}={s[k]}" for k in sorted(s)) + ")")
    for log in sorted(run_dir.glob("*.log")):
        found = None
        try:
            with log.open(errors="replace") as fh:
                for line in fh:
                    m = re.search(r"HarnessSolver\(([^)]*)\)", line)
                    if m:
                        found = m.group(1)
                        break
        except OSError:
            continue
        if found:
            fields = [f.strip() for f in found.split(", ")
                      if not f.strip().startswith(_VOLATILE_SOLVER_FIELDS)]
            parts.append("HarnessSolver(" + ", ".join(sorted(fields)) + ")")
            break
    budget = _budget_seconds(run_dir)
    if budget is not None:
        parts.append(f"budget_s={budget}")
    if not parts:
        return UNKNOWN_SIGNATURE
    # An identity missing `model` or `sampling` is not a weaker identity, it is no identity — the two
    # fields that distinguish "same configuration" from "same harness" are exactly the two that go
    # missing when run_config.json was not reconstructed. Marked so it can never compare equal.
    if missing:
        return f"{INCOMPLETE_PREFIX}(missing {'+'.join(missing)}) | " + " | ".join(parts)
    return " | ".join(parts)


def _same_config(a: str, b: str) -> bool:
    """UNKNOWN and INCOMPLETE match nothing, including themselves."""
    if a != b:
        return False
    return a != UNKNOWN_SIGNATURE and not a.startswith(INCOMPLETE_PREFIX)


def _pass_index(episode: dict) -> int:
    """Which pass an episode came from. `pass_key` is `<game>_p<N>`; older episode files predate the
    field, so fall back to the `<run>::<pass_key>::L<n>` episode_id."""
    pk = episode.get("pass_key")
    if not pk:
        parts = (episode.get("episode_id") or "").split("::")
        pk = parts[1] if len(parts) > 2 else ""
    m = re.search(r"_p(\d+)$", pk)
    return int(m.group(1)) if m else 0


def _wallclock(run_dir: Path, game: str, pass_idx: int = 0):
    """Wall clock for ONE pass. `game_runs` is passes-major and repeats the game id per pass, so
    returning the first id match served p0's clock for every pass (see run_artifacts.py)."""
    bj = run_dir / "benchmark.json"
    if not bj.exists():
        return None
    try:
        b = json.loads(bj.read_text())
    except Exception:  # noqa: BLE001
        return None
    seen = 0
    for gr in b.get("game_runs") or []:
        if gr.get("game_id") == game:
            if seen == pass_idx:
                return gr.get("final_wallclock_seconds")
            seen += 1
    return None


def build(run_dirs: list[Path], require_evidence: bool, allow_censored: bool, out: Path,
          replicates: bool = False) -> int:
    chosen: dict[tuple, dict] = {}
    # `--replicates` only: THE CORPUS HAS ONE CONFIGURATION, fixed by the first run that contributes.
    #
    # An earlier version scoped this per (game, level): a foreign-configuration run was refused only
    # where it collided with a game-level another run already owned, so its games that NOBODY had
    # supplied were admitted. A different-model run then contributed every level unique to it and the
    # corpus silently mixed two configurations — a per-episode guard cannot enforce a property of the
    # whole corpus. Configuration identity belongs to the RUN, so the whole run is admitted or refused.
    corpus_sig: str | None = None
    corpus_sig_run: str | None = None
    dropped_dup, dropped_noev, dropped_censored = [], [], []

    refused_runs = []
    per_run = collections.Counter()
    signatures: dict[str, str] = {}

    for rd in run_dirs:
        if not rd.exists():
            print(f"SKIP {rd} — does not exist")
            continue
        sig = _config_signature(rd)
        signatures[rd.name] = sig
        if sig == UNKNOWN_SIGNATURE:
            print(f"WARNING {rd.name} — configuration not identifiable; it may not be pooled with "
                  f"any other run (S1-E14)")
        elif sig.startswith(INCOMPLETE_PREFIX):
            print(f"WARNING {rd.name} — {sig.split(' | ')[0]}. run_config.json does not record the "
                  f"model and/or sampling parameters, so this run cannot be shown to share a "
                  f"configuration with any other and will not be pooled (S1-E14). Reconstruct it from "
                  f"the run's own log and taaf_setup_env.json, as was done for kaggle_v2/v3/v4.")

        # RUN-LEVEL GATE. Decided before a single episode is read, so a foreign configuration cannot
        # enter through games no other run happens to cover.
        if replicates:
            if corpus_sig is None:
                corpus_sig, corpus_sig_run = sig, rd.name
            elif not _same_config(corpus_sig, sig):
                why = ("its configuration is not identifiable" if sig == UNKNOWN_SIGNATURE
                       else "its configuration is incomplete" if sig.startswith(INCOMPLETE_PREFIX)
                       else "it is a different configuration")
                print(f"REFUSED RUN {rd.name} — {why}; the corpus configuration was fixed by "
                      f"{corpus_sig_run}. No episode from this run enters, including games no other "
                      f"run supplied (S1-E14).")
                refused_runs.append({"run": rd.name, "signature": sig, "why": why,
                                     "corpus_signature": corpus_sig,
                                     "corpus_signature_from": corpus_sig_run})
                continue

        data = extract_episodes(rd)
        for ep in data["episodes"]:
            gl = (ep["game"], ep["level"])
            pass_idx = _pass_index(ep)
            ep["pass_index"] = pass_idx
            # A replicate is identified by (run, pass), not by pass alone. Under S1-E14 the corpus is
            # built from repeated SINGLE-PASS runs, so every episode has pass_index 0 and keying on the
            # pass alone would collapse the replicates into one — silently discarding exactly what the
            # erratum was filed to obtain.
            ep["replicate_id"] = f"{rd.name}/p{pass_idx}"
            key = (*gl, rd.name, pass_idx) if replicates else gl
            ev = sum(len(v) for v in (ep["evidence"].get("reasoning_by_step") or {}).values())
            ep["evidence_steps_with_reasoning"] = ev
            ep["source_run"] = rd.name
            budget = _budget_seconds(rd)
            wall = _wallclock(rd, ep["game"], pass_idx)
            ran_full_budget = bool(budget and wall is not None and wall >= BUDGET_TOLERANCE * budget)
            ep["budget_terminated"] = ran_full_budget
            ep["censored_at_seconds"] = budget if ran_full_budget else None
            ep["final_wallclock_seconds"] = wall
            ep["run_completed"] = (ep.get("terminal_state") in AGENT_FINISHED) or ran_full_budget

            if not allow_censored and not ep["run_completed"]:
                dropped_censored.append((rd.name, ep["game"], ep["level"], ep["actions_taken"],
                                         ep.get("terminal_state")))
                continue
            if require_evidence and ev == 0:
                dropped_noev.append((rd.name, ep["game"], ep["level"], ep["actions_taken"]))
                continue
            # No per-episode configuration check here: the run-level gate above already decided it.
            # A single unidentifiable run is still admitted whole — one directory is one configuration
            # by construction, and S1-E14's "UNKNOWN matches nothing" governs pooling ACROSS runs.
            if key in chosen:
                dropped_dup.append((rd.name, ep["game"], ep["level"], ep["actions_taken"],
                                    chosen[key]["source_run"], chosen[key]["actions_taken"]))
                continue
            chosen[key] = ep
            per_run[rd.name] += 1

    episodes = [chosen[k] for k in sorted(chosen)]
    payload = {
        "built": "s1d_build_corpus.py",
        "source_runs": [r.name for r in run_dirs],
        "selection_rule": ("every (game, level, run, pass) enters once. Configuration ownership is "
                           "PER RUN, not per (game, level): the first run to contribute fixes the "
                           "corpus configuration, and a run whose signature does not match is refused "
                           "in full — including games no other run supplied"
                           if replicates else
                           "first run in --runs order wins for a given (game, level)"),
        "replicates": replicates,
        "replicate_rule": ("S1-E11 as amended by S1-E14: replicates of one game under an IDENTICAL "
                           "configuration are independent observations, not duplicates — whether they "
                           "are passes inside one kernel or separate single-pass runs. Ownership keys "
                           "on the configuration signature, so cross-configuration pooling is refused."
                           if replicates else
                           "OFF — one episode per (game, level); replicates collapse"),
        "config_signatures": signatures,
        "config_identity_note": ("S1-E14: pooling across runs is admissible ONLY while their signatures "
                                 "match. UNKNOWN matches nothing, including itself."),
        "require_evidence": require_evidence,
        "allow_censored": allow_censored,
        "admissibility_rule": ("S1-E9: agent-finished OR consumed the full uniform budget "
                               "(>= 0.98 x max_runtime_minutes_per_game). Early stops are "
                               "operator kills or crashes and are excluded."),
        "n_episodes": len(episodes),
        "n_distinct_games": len({e["game"] for e in episodes}),
        "n_distinct_game_levels": len({(e["game"], e["level"]) for e in episodes}),
        "n_passes_present": sorted({e.get("pass_index", 0) for e in episodes}),
        "n_replicates_present": sorted({e.get("replicate_id", "") for e in episodes}),
        "replicates_per_game_level": dict(collections.Counter(
            collections.Counter((e["game"], e["level"]) for e in episodes).values())),
        "contributed_per_run": dict(per_run),
        "corpus_configuration": corpus_sig,
        "corpus_configuration_fixed_by": corpus_sig_run,
        "refused_runs_different_configuration": refused_runs,
        "excluded_censored_run_never_completed": [
            {"run": r, "game": g, "level": l, "actions": a, "terminal_state": s}
            for r, g, l, a, s in dropped_censored],
        "excluded_duplicate_game_level": [
            {"run": r, "game": g, "level": l, "actions": a, "kept_from": kr, "kept_actions": ka}
            for r, g, l, a, kr, ka in dropped_dup],
        "excluded_no_reasoning_evidence": [
            {"run": r, "game": g, "level": l, "actions": a} for r, g, l, a in dropped_noev],
        "episodes": episodes,
    }
    payload["frequencies"] = frequencies(episodes)
    out.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"corpus: {len(episodes)} episodes across {payload['n_distinct_games']} distinct games")
    for r, n in per_run.most_common():
        print(f"   {n:>3} from {r}")
    if dropped_censored:
        by_state = collections.Counter(s for *_, s in dropped_censored)
        print(f"\nexcluded {len(dropped_censored)} episode(s) — run stopped EARLY, before its "
              f"budget: {dict(by_state)}")
        print("   Operator kills or crashes, not failures. Counting them would rank the build order "
              "on the operator's attention. Budget-terminated runs ARE admitted (S1-E9).")
        for r, g, l, a, s in dropped_censored[:10]:
            print(f"   {g} L{l} ({a} actions, state={s}) from {r}")
        if len(dropped_censored) > 10:
            print(f"   ... and {len(dropped_censored) - 10} more")
    if refused_runs:
        print(f"\nREFUSED {len(refused_runs)} whole run(s) — DIFFERENT CONFIGURATION (S1-E14). The "
              f"corpus is one configuration; a run that does not match contributes nothing, including "
              f"games no other run supplied:")
        for r in refused_runs:
            print(f"   {r['run']} — {r['why']}")
            print(f"      its signature    : {r['signature']}")
            print(f"      corpus signature : {r['corpus_signature']}  (from {r['corpus_signature_from']})")
    if dropped_dup:
        print(f"\nexcluded {len(dropped_dup)} duplicate (game, level) episode(s):")
        for r, g, l, a, kr, ka in dropped_dup:
            print(f"   {g} L{l}: dropped {a} actions from {r}  (kept {ka} from {kr})")
    if dropped_noev:
        print(f"\nexcluded {len(dropped_noev)} episode(s) with no reasoning evidence:")
        for r, g, l, a in dropped_noev:
            print(f"   {g} L{l} ({a} actions) from {r}")
    # The blind re-rate cannot exceed the corpus. Say so here rather than at draw time.
    print(f"\nblind re-rate ceiling: {len(episodes)} episodes. `blind_rerate.sample_size` cannot exceed "
          f"this (see S1-E7).")
    print(f"wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--require-evidence", action="store_true")
    ap.add_argument("--allow-censored", action="store_true",
                    help="keep episodes from runs that never completed (default: exclude)")
    ap.add_argument("--replicates", action="store_true",
                    help="keep every pass of a (game, level) from the run that owns it (S1-E11)")
    ap.add_argument("--out", default="logs/s1d_corpus.json")
    args = ap.parse_args()
    return build([Path(r) for r in args.runs], args.require_evidence, args.allow_censored,
                 Path(args.out), args.replicates)


if __name__ == "__main__":
    raise SystemExit(main())
