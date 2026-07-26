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


def _wallclock(run_dir: Path, game: str):
    bj = run_dir / "benchmark.json"
    if not bj.exists():
        return None
    try:
        b = json.loads(bj.read_text())
    except Exception:  # noqa: BLE001
        return None
    for gr in b.get("game_runs") or []:
        if gr.get("game_id") == game:
            return gr.get("final_wallclock_seconds")
    return None


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
            budget = _budget_seconds(rd)
            wall = _wallclock(rd, ep["game"])
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
        "admissibility_rule": ("S1-E9: agent-finished OR consumed the full uniform budget "
                               "(>= 0.98 x max_runtime_minutes_per_game). Early stops are "
                               "operator kills or crashes and are excluded."),
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
        print(f"\nexcluded {len(dropped_censored)} episode(s) — run stopped EARLY, before its "
              f"budget: {dict(by_state)}")
        print("   Operator kills or crashes, not failures. Counting them would rank the build order "
              "on the operator's attention. Budget-terminated runs ARE admitted (S1-E9).")
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
