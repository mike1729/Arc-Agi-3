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

THE CENSORING HAZARD — the one that matters most
------------------------------------------------
The reference harness defines `COMPLETED_GAME_RUN_STATES = {"gave_up", "won"}` (`inference/tools/eval.py`).
A run in state `playing` was interrupted; `cancelled` was cancelled by the harness. Neither concluded.

The manifest defines a failure episode as "a level attempt that TERMINATED without level advancement,
or was ABANDONED". A killed run did neither — it is censored, not failed. Counting it injects failure
mass that measures the wall-clock budget and the operator's kill decisions rather than the agent's
competence, and it loads that mass disproportionately onto `latency_or_budget`, which would then rank
high in a `primary_share` ordering purely because runs were stopped.

Measured 2026-07-26: the 25 reference episodes are **all** `gave_up`. The 47 local episodes are
23 `playing`, 13 `cancelled`, 11 with no state — **zero completed runs.** So the entire local corpus,
as of that date, is censored and none of it is labelable as failure. Excluding censored episodes is
therefore the DEFAULT; keeping them requires passing `--allow-censored` deliberately.

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

Every exclusion is reported. A corpus that quietly dropped episodes would understate its own denominator.

Run:
  .venv/bin/python agent/harness/s1d_build_corpus.py --runs logs/runs/A logs/runs/B --out logs/s1d_corpus.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from s1d_label import extract_episodes, frequencies


# inference/tools/eval.py — a run that reached neither state did not conclude.
COMPLETED_GAME_RUN_STATES = {"gave_up", "won"}


def build(run_dirs: list[Path], require_evidence: bool, allow_censored: bool, out: Path) -> int:
    chosen: dict[tuple, dict] = {}
    dropped_dup, dropped_noev, dropped_censored = [], [], []
    per_run = collections.Counter()

    for rd in run_dirs:
        if not rd.exists():
            print(f"SKIP {rd} — does not exist")
            continue
        data = extract_episodes(rd)
        for ep in data["episodes"]:
            key = (ep["game"], ep["level"])
            ev = sum(len(v) for v in (ep["evidence"].get("reasoning_by_step") or {}).values())
            ep["evidence_steps_with_reasoning"] = ev
            ep["source_run"] = rd.name
            ep["run_completed"] = ep.get("terminal_state") in COMPLETED_GAME_RUN_STATES

            if not allow_censored and not ep["run_completed"]:
                dropped_censored.append((rd.name, ep["game"], ep["level"], ep["actions_taken"],
                                         ep.get("terminal_state")))
                continue
            if require_evidence and ev == 0:
                dropped_noev.append((rd.name, ep["game"], ep["level"], ep["actions_taken"]))
                continue
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
        "selection_rule": "first run in --runs order wins for a given (game, level)",
        "require_evidence": require_evidence,
        "allow_censored": allow_censored,
        "completed_states": sorted(COMPLETED_GAME_RUN_STATES),
        "n_episodes": len(episodes),
        "n_distinct_games": len({e["game"] for e in episodes}),
        "contributed_per_run": dict(per_run),
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
        print(f"\nexcluded {len(dropped_censored)} CENSORED episode(s) — run never reached "
              f"{sorted(COMPLETED_GAME_RUN_STATES)}: {dict(by_state)}")
        print("   These are interrupted runs, not failures. Counting them would rank the build order "
              "on the operator's kill decisions.")
        for r, g, l, a, s in dropped_censored[:10]:
            print(f"   {g} L{l} ({a} actions, state={s}) from {r}")
        if len(dropped_censored) > 10:
            print(f"   ... and {len(dropped_censored) - 10} more")
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
    ap.add_argument("--out", default="logs/s1d_corpus.json")
    args = ap.parse_args()
    return build([Path(r) for r in args.runs], args.require_evidence, args.allow_censored,
                 Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
