"""Extract verified level solutions from a completed benchmark run.

WHAT THIS IS FOR
----------------
`benchmark.json` keeps a full `history` of every action a run took, with exact coordinates for
ACTION6. Combined with two facts already established, that turns a scored run into a solution library:

  * REPLAY-DET measured that the OFFLINE competition environments replay byte-identically — two games, two
    prefix lengths, three replays each. So a recorded prefix is reproducible, not merely a trace.
  * `actions_per_level` says exactly how many actions each level consumed, so the history splits at
    known boundaries.

A level the run CLEARED therefore yields a *verified* action sequence that solves it. RESET-ACCT needed one
such sequence and had to find it by breadth-first search (960 nodes expanded on `tu93`); the reference
run contains dozens for free.

USES
----
  * scripted experiments that need a deterministic solve (RESET-ACCT's arms, replay determinism on click games)
  * ground truth for "did the agent choose well", separate from "did the agent act"
  * a target for a world model: given the prefix, does it predict the observation that follows?

SCOPE LIMIT, AND IT MATTERS
---------------------------
REPLAY-DET's determinism result covers the OFFLINE environment files. Competition mode was never tested and
`ONLY_RESET_LEVELS` / gateway behaviour may differ. These sequences are verified reproducible OFFLINE;
treating them as competition-valid would exceed what was measured.

Sequences are recorded but NOT replayed by this script — replaying needs the environment bundle. Each
entry carries `verified: false` until `--replay` confirms it, so nothing here silently claims more than
it has checked.

Run:  .venv/bin/python agent/harness/extract_solutions.py <benchmark.json> [--out logs/solutions.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def action_repr(a: dict) -> str:
    """`{'id': 'ACTION6', 'data': {'x': 48, 'y': 46}}` -> `ACTION6(48,46)`; simple actions -> `ACTION3`."""
    if not isinstance(a, dict):
        return str(a)
    aid = a.get("id", "?")
    d = a.get("data") or {}
    if "x" in d and "y" in d:
        return f"{aid}({d['x']},{d['y']})"
    return str(aid)


def extract(bench_path: Path, out: Path) -> int:
    b = json.loads(bench_path.read_text())
    solutions, partial = [], []

    for gr in b.get("game_runs") or []:
        game = gr.get("game_id")
        hist = gr.get("history") or []
        apl = gr.get("actions_per_level") or []
        bal = gr.get("base_actions_per_level") or []
        completed = int(gr.get("levels_completed") or 0)
        if not hist or not apl:
            continue

        # Split the flat history at the per-level boundaries benchmark.json records.
        idx = 0
        for level0, n in enumerate(apl):
            if n <= 0:
                continue
            seg = hist[idx: idx + n]
            idx += n
            if len(seg) < n:                       # history shorter than claimed — do not guess
                break
            level = level0 + 1
            base = bal[level0] if level0 < len(bal) else None
            entry = {
                "game": game,
                "level": level,
                "n_actions": n,
                "human_baseline": base,
                "ratio_vs_baseline": round(n / base, 3) if base else None,
                "actions": [action_repr(r.get("action")) for r in seg],
                "action_ids": [(r.get("action") or {}).get("id") for r in seg],
                # Verified means REPLAYED. Recording is not verification.
                "verified": False,
                "scope": "offline environment files only; competition mode untested (REPLAY-DET scope limit)",
            }
            # A level is solved iff a later level was reached, i.e. it is below levels_completed.
            (solutions if level <= completed else partial).append(entry)

    payload = {
        "source": str(bench_path),
        "benchmark_label": b.get("label"),
        "n_solutions": len(solutions),
        "n_partial": len(partial),
        "definition": ("a SOLUTION is the action sequence for a level the run cleared; a PARTIAL is the "
                       "sequence for the level it stalled on, which is not a solution"),
        "replay_basis": ("REPLAY-DET: offline environments replay byte-identically (2 games x 2 prefix lengths "
                         "x 3 replays). Sequences here are RECORDED, not replayed — `verified` stays "
                         "false until independently confirmed."),
        "solutions": sorted(solutions, key=lambda s: (s["game"], s["level"])),
        "partial": sorted(partial, key=lambda s: (s["game"], s["level"])),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"solutions: {len(solutions)} cleared levels across "
          f"{len({s['game'] for s in solutions})} games")
    print(f"{'game':22s} {'lvl':>3} {'actions':>7} {'baseline':>8} {'ratio':>6}")
    for s in payload["solutions"]:
        print(f"{s['game']:22s} {s['level']:3d} {s['n_actions']:7d} "
              f"{str(s['human_baseline']):>8} {str(s['ratio_vs_baseline']):>6}")
    best = [s for s in payload["solutions"] if s["ratio_vs_baseline"] and s["ratio_vs_baseline"] < 1]
    if best:
        print(f"\nbetter than the human baseline: {len(best)}")
        for s in sorted(best, key=lambda x: x["ratio_vs_baseline"]):
            print(f"   {s['game']} L{s['level']}: {s['n_actions']} vs {s['human_baseline']} "
                  f"= {s['ratio_vs_baseline']}x")
    print(f"\npartial (stalled levels, NOT solutions): {len(partial)}")
    print(f"wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("benchmark")
    ap.add_argument("--out", default="logs/solutions.json")
    args = ap.parse_args()
    return extract(Path(args.benchmark), Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
