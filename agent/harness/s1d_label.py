"""S1-d — failure-episode labelling pipeline.

Builds the labelling substrate the Day-7 build order is ranked from. Per `gate_manifest.yaml →
s1.failure_taxonomy`:

  failure episode  a level attempt that terminated without level advancement, or was abandoned.
                   Successful levels produce NO episode. This is the denominator for every frequency.
  labels           multi-label, confidence in {low, med, high}, evidence stored PER LABEL
  primary_label    exactly one per episode, rater-designated as CAUSALLY EARLIEST; ties broken by
                   highest confidence, then the fixed category order in the manifest
  frequencies      primary_share (ranks the build order) and episode_share (reported beside it)

This module EXTRACTS episodes and attaches machine-derivable evidence. It does NOT assign labels:
labelling is a rater judgement, and a script that guessed labels would manufacture the very frequencies
the build order is ranked on. It emits a template with `labels: []` for a human to complete.

Two categories are excluded up front (manifest `results.categories_unobservable`):
`coordinate_unreachable` (no coordinate candidate set exists) and `planning_depth` (the solver does not
search). They are never recorded as zero-frequency.

Run:  .venv/bin/python agent/harness/s1d_label.py <run_dir> [--out logs/s1d_episodes_<name>.json]
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from run_artifacts import game_of, load_run

# Fixed category order — the manifest's tie-break for primary_label depends on it being stable.
CATEGORIES = [
    "goal_unknown", "action_semantics_unknown", "perception_parsing",
    "hidden_state_aliasing_or_memory", "coordinate_unreachable", "planning_depth",
    "exploration_or_probe_selection", "progress_signal_misinterpretation",
    "irreversible_mistake", "invalid_output_interface", "retrieval_or_context",
    "reasoning_inconsistency", "latency_or_budget",
]
UNOBSERVABLE = {"coordinate_unreachable", "planning_depth"}
LABELABLE = [c for c in CATEGORIES if c not in UNOBSERVABLE]


def _counts(acts):
    """Action-display frequencies. Was an O(n^2) nested comprehension; a 742-action episode made that
    ~27k string comparisons per episode."""
    return collections.Counter(str(r.get("action_display")) for r in acts)


def extract_episodes(run_dir: Path):
    """One episode per level ATTEMPT that did not advance. A level the agent cleared yields no episode.

    All artifact access goes through `run_artifacts.RunArtifacts`, which is keyed by game id and has no
    accessor for "the run's game" — the `game_runs[0]` mis-attribution it replaced is unrepresentable.
    """
    run = load_run(run_dir)
    for w in run.warnings:
        print(f"  WARNING {w}")

    episodes = []
    games_seen = {}

    for pass_key in run.passes:
        rows = run.events(pass_key)
        game = game_of(pass_key)
        gr = run.game_run(pass_key)
        # Keyed by pass, not game: passes of one game have different states and action counts, and
        # keying by game would keep only the last (S1-E11 / run_artifacts docstring).
        games_seen[pass_key] = {
            "game": game,
            "state": gr.get("state"),
            "levels_completed": int(gr.get("levels_completed") or 0),
            "actions_per_level": run.actions_per_level(pass_key),
            "concluded": run.concluded(pass_key),
            "budget_terminated": run.budget_terminated(pass_key),
            "censored_at_seconds": run.budget_seconds if run.budget_terminated(pass_key) else None,
        }
        requests = run.requests(pass_key)

        # Segment the event stream by the level marker; a segment that never advances is an episode.
        segs, cur, cur_level = [], [], None
        for r in rows:
            lvl = r.get("level")
            if cur_level is None:
                cur_level = lvl
            if lvl != cur_level:
                segs.append((cur_level, cur))
                cur, cur_level = [], lvl
            cur.append(r)
        if cur:
            segs.append((cur_level, cur))

        # A level was CLEARED iff the next segment is at a HIGHER level. "A later segment exists" is
        # wrong: a RESET sends the marker backwards (2 -> 1), and treating that as advancement silently
        # drops the failed attempt — which is an episode, and this is the build-order denominator.
        levels_seq = [lv for lv, _ in segs]
        if any((b is not None and a is not None and b < a)
               for a, b in zip(levels_seq, levels_seq[1:])):
            print(f"  NOTE {pass_key}: level marker goes backwards {levels_seq} — reset detected; "
                  f"non-advancing segments are kept as episodes")

        for idx, (lvl, seg) in enumerate(segs):
            nxt = segs[idx + 1][0] if idx + 1 < len(segs) else None
            if nxt is not None and lvl is not None and nxt > lvl:
                continue                            # successful levels produce NO episode
            ana = [r for r in seg if r.get("type") == "analysis"]
            acts = [r for r in seg if r.get("type") == "action"]
            steps = sorted({r.get("analysis_step") for r in seg
                            if r.get("analysis_step") is not None})

            # Action count comes from benchmark.json, NOT from counting event rows by `level`.
            # The action that clears a level is stamped with the NEW level in the event stream while
            # benchmark.json counts it toward the level it completed (ar25: benchmark [30, 80] vs
            # events L1:29 L2:81). Counting rows makes a cleared level one low and the next one high.
            n_actions = run.actions_on_level(pass_key, lvl)
            n_events = len(acts)
            if n_actions is None:
                n_actions = n_events
            base = run.baseline_for(pass_key, lvl)

            episodes.append({
                "episode_id": f"{run.name}::{pass_key}::L{lvl}",
                "game": game, "level": lvl, "pass_key": pass_key,
                "terminal_state": gr.get("state"),
                "concluded": run.concluded(pass_key),
                "censored_at_seconds": run.budget_seconds if run.budget_terminated(pass_key) else None,
                "actions_taken": n_actions,
                "actions_in_event_stream": n_events,
                "human_baseline": base,
                "action_ratio_vs_baseline": (round(n_actions / base, 2) if base else None),
                "analysis_turns": len(ana),
                "distinct_actions": len(_counts(acts)),
                "top_action_share": (round(_counts(acts).most_common(1)[0][1] / len(acts), 3)
                                     if acts else None),
                # --- rater fields, deliberately empty ---
                "labels": [],
                "primary_label": None,
                "rater_notes": "",
                # --- evidence packet ---
                "evidence": {
                    "analysis_steps": steps,
                    "reasoning_by_step": {str(k): requests.get(k, []) for k in steps if k in requests},
                    "events_ref": f"artifacts/{pass_key}_events.jsonl",
                },
            })

    return {
        "run": run.name,
        "concurrency": run.concurrency,
        "model": run.model,
        "passes": games_seen,
        "n_passes": len(games_seen),
        "n_distinct_games": len({v["game"] for v in games_seen.values()}),
        "scheduled_but_not_run": run.scheduled_not_run,
        "categories_labelable": LABELABLE,
        "categories_unobservable": sorted(UNOBSERVABLE),
        "unobservable_rule": ("excluded from failure_frequency_ranking and build_order; NEVER recorded "
                              "as zero-frequency"),
        "episodes": episodes,
    }


def _level_band(level):
    """L1 vs L2+. The reference clears level 1 in 15/25 games and level 2 in only 3, so pooling the two
    lets easy-case episodes dominate a ranking that is supposed to order eight weeks of construction."""
    try:
        return "L1" if int(level or 1) <= 1 else "L2+"
    except Exception:  # noqa: BLE001
        return "L1"


def _shares(eps):
    n = len(eps)
    if not n:
        return {"total_failure_episodes": 0}
    prim, epis = {}, {}
    for e in eps:
        if e.get("primary_label"):
            prim[e["primary_label"]] = prim.get(e["primary_label"], 0) + 1
        for l in e.get("labels") or []:
            c = l.get("category")
            if c:
                epis[c] = epis.get(c, 0) + 1
    return {
        "total_failure_episodes": n,
        "labelled": sum(1 for e in eps if e.get("primary_label")),
        # primary_share RANKS THE BUILD ORDER; episode_share is reported beside it. A category often
        # present but rarely primary is a contributing factor, not a root cause.
        "primary_share": {k: round(v / n, 4) for k, v in sorted(prim.items(), key=lambda x: -x[1])},
        "episode_share": {k: round(v / n, 4) for k, v in sorted(epis.items(), key=lambda x: -x[1])},
    }


def frequencies(episodes):
    """Stratified by level band, and pooled.

    The pooled figure is reported but MUST NOT be the ranking on its own: if L1 episodes outnumber L2+
    ones, a pooled ranking optimises the case the reference already solves. Where the two disagree, the
    disagreement is itself a finding and is surfaced explicitly.
    """
    by_band = {}
    for band in ("L1", "L2+"):
        eps = [e for e in episodes if _level_band(e.get("level")) == band]
        if eps:
            by_band[band] = _shares(eps)
    pooled = _shares(episodes)

    # Does the top-ranked category differ between pooled and L2+? That is the case the warning exists for.
    def top(d):
        ps = (d or {}).get("primary_share") or {}
        return next(iter(ps), None)
    divergence = None
    if "L2+" in by_band and top(pooled) and top(by_band["L2+"]):
        if top(pooled) != top(by_band["L2+"]):
            divergence = {
                "pooled_top": top(pooled),
                "L2plus_top": top(by_band["L2+"]),
                "warning": ("the pooled ranking and the L2+ ranking disagree on the top category. "
                            "RANK ON L2+: the reference already clears level 1 in 15/25 games, so "
                            "level-1 episodes describe the solved case, not the bottleneck."),
            }

    return {
        "pooled": pooled,
        "by_level_band": by_band,
        "ranking_rule": ("rank the build order on the L2+ band. Report pooled beside it. Level 1 is "
                         "soft (reference: 15/25 cleared) and level 2 is the wall (3/25) — see "
                         "logs/kaggle-reference/per_game_analysis.json"),
        "band_divergence": divergence,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)

    data = extract_episodes(run_dir)
    data["frequencies"] = frequencies(data["episodes"])
    out = args.out or f"logs/s1d_episodes_{run_dir.name}.json"
    Path(out).write_text(json.dumps(data, indent=2) + "\n")

    print(f"run      : {data['run']}   {data['n_games']} game(s)")
    for g, meta in sorted(data["games"].items()):
        print(f"   {g:20s} state={meta['state']} levels={meta['levels_completed']} "
              f"apl={meta['actions_per_level']}")
    print(f"episodes : {len(data['episodes'])} failure episode(s)")
    for e in data["episodes"]:
        print(f"   {e['episode_id']}")
        print(f"      actions={e['actions_taken']} baseline={e['human_baseline']} "
              f"ratio={e['action_ratio_vs_baseline']}x  analysis_turns={e['analysis_turns']}")
        print(f"      distinct_actions={e['distinct_actions']} top_action_share={e['top_action_share']} "
              f"evidence_steps={len(e['evidence']['analysis_steps'])}")
    print(f"\nlabelable categories : {len(data['categories_labelable'])}")
    print(f"unobservable         : {data['categories_unobservable']} (excluded, never zero-frequency)")
    print(f"\nlabels are EMPTY by design — labelling is a rater judgement, not a script's.")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
