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
import glob
import json
from pathlib import Path

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


def load_events(run_dir: Path):
    out = {}
    for f in sorted(glob.glob(str(run_dir / "artifacts" / "*_events.jsonl"))):
        key = Path(f).name.split("_events")[0]
        out[key] = [json.loads(l) for l in open(f)]
    return out


def load_requests(run_dir: Path):
    """analysis_step -> the model's reasoning and tool calls, from D6/D6b response rows."""
    by_step = {}
    for f in glob.glob(str(run_dir / "*requests.jsonl")):
        for line in open(f):
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get("event") != "response":
                continue
            msg = r.get("response_message") or {}
            codes = []
            for tc in (msg.get("tool_calls") or []):
                try:
                    codes.append(json.loads(tc.get("function", {}).get("arguments", "")).get("code", ""))
                except Exception:  # noqa: BLE001
                    pass
            by_step.setdefault(r.get("analysis_step"), []).append({
                "finish_reason": r.get("finish_reason"),
                "reasoning": (msg.get("reasoning") or "")[:4000],
                "content": (msg.get("content") or "")[:4000],
                "tool_code": codes,
                "usage": r.get("usage"),
            })
    return by_step


def extract_episodes(run_dir: Path):
    """One episode per level ATTEMPT that did not advance. A level the agent cleared yields no episode."""
    bj = run_dir / "benchmark.json"
    b = json.loads(bj.read_text()) if bj.exists() else {}
    gr = (b.get("game_runs") or [{}])[0]
    game = gr.get("game_id", run_dir.name)
    apl = gr.get("actions_per_level") or []
    bal = gr.get("base_actions_per_level") or []
    completed = int(gr.get("levels_completed") or 0)
    state = gr.get("state")

    events_by_pass = load_events(run_dir)
    requests = load_requests(run_dir)
    episodes = []

    for pass_key, rows in events_by_pass.items():
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

        for idx, (lvl, seg) in enumerate(segs):
            advanced = idx < len(segs) - 1          # a later segment exists => this level was cleared
            if advanced:
                continue                            # successful levels produce NO episode
            acts = [r for r in seg if r.get("type") == "action"]
            ana = [r for r in seg if r.get("type") == "analysis"]
            lvl_i = (lvl or 1) - 1
            steps = sorted({r.get("analysis_step") for r in seg if r.get("analysis_step") is not None})
            episodes.append({
                "episode_id": f"{run_dir.name}::{pass_key}::L{lvl}",
                "game": game, "level": lvl, "terminal_step": len(seg) - 1,
                "terminal_state": state,
                "actions_taken": len(acts),
                "human_baseline": bal[lvl_i] if 0 <= lvl_i < len(bal) else None,
                "action_ratio_vs_baseline": (
                    round(len(acts) / bal[lvl_i], 2) if 0 <= lvl_i < len(bal) and bal[lvl_i] else None),
                "analysis_turns": len(ana),
                "distinct_actions": len({str(r.get("action_display")) for r in acts}),
                "top_action_share": (
                    round(max([sum(1 for r in acts if str(r.get("action_display")) == a)
                               for a in {str(x.get("action_display")) for x in acts}]) / len(acts), 3)
                    if acts else None),
                # --- rater fields, deliberately empty ---
                "labels": [],            # [{category, confidence, evidence_ref}]
                "primary_label": None,   # REQUIRED before the ranking is computed
                "rater_notes": "",
                # --- evidence packet ---
                "evidence": {
                    "analysis_steps": steps,
                    "reasoning_by_step": {str(k): requests.get(k, []) for k in steps if k in requests},
                    "events_ref": f"artifacts/{pass_key}_events.jsonl",
                },
            })
    return {
        "run": run_dir.name, "game": game, "state": state,
        "levels_completed": completed, "actions_per_level": apl,
        "categories_labelable": LABELABLE,
        "categories_unobservable": sorted(UNOBSERVABLE),
        "unobservable_rule": ("excluded from failure_frequency_ranking and build_order; NEVER recorded "
                              "as zero-frequency"),
        "episodes": episodes,
    }


def frequencies(episodes):
    """primary_share ranks the build order; episode_share is reported beside it."""
    n = len(episodes)
    if not n:
        return {}
    prim, epis = {}, {}
    for e in episodes:
        if e.get("primary_label"):
            prim[e["primary_label"]] = prim.get(e["primary_label"], 0) + 1
        for l in e.get("labels") or []:
            c = l.get("category")
            if c:
                epis[c] = epis.get(c, 0) + 1
    return {
        "total_failure_episodes": n,
        "labelled": sum(1 for e in episodes if e.get("primary_label")),
        "primary_share": {k: round(v / n, 4) for k, v in sorted(prim.items(), key=lambda x: -x[1])},
        "episode_share": {k: round(v / n, 4) for k, v in sorted(epis.items(), key=lambda x: -x[1])},
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

    print(f"run      : {data['run']}  game={data['game']}  state={data['state']}")
    print(f"levels   : {data['levels_completed']} completed, actions_per_level={data['actions_per_level']}")
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
