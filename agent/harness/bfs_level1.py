"""BFS for a scripted level-1 completion, exploiting the determinism R1 established.

Random rollouts fail here: 4^60 is not searchable and 5000 samples found nothing on tu93. But R1 showed
these offline environments replay exactly, which makes systematic search valid — a sequence found now
reproduces when replayed, which is exactly what R2's two arms require.

The environment exposes no save/restore, so a node is expanded by replaying its prefix from RESET. Cost
is therefore O(depth) per expansion, and the saving comes entirely from deduplicating states by
observation digest. Available actions are re-read at every node, since a game may unlock actions as it
progresses.

Run:  .venv/bin/python agent/harness/bfs_level1.py --game tu93-0768757b --max-depth 24
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import deque

import arc_agi
import arcengine

ENV_DIR = "data/environment_files"
ACTION_BY_ID = {a.value: a for a in arcengine.GameAction if a.value != 0}


def obs_digest(frame) -> str:
    """Same observation definition R1 settled on: the grids plus observable status, with per-call
    metadata (guid, full_reset, action_input) excluded. Dedup on anything less would merge genuinely
    different boards and could make a solution unreachable."""
    raw = getattr(frame, "frame", None)
    grids = [(l.tolist() if hasattr(l, "tolist") else l) for l in raw] if raw is not None else None
    obs = {
        "grids": grids,
        "available_actions": [int(a) for a in (getattr(frame, "available_actions", None) or [])],
        "state": str(getattr(frame, "state", "")),
        "levels_completed": int(getattr(frame, "levels_completed", 0) or 0),
    }
    return hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()[:20]


def replay(env, seq):
    frame = env.reset()
    for a in seq:
        frame = env.step(a)
    return frame


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="tu93-0768757b")
    ap.add_argument("--max-depth", type=int, default=24)
    ap.add_argument("--budget-s", type=float, default=900.0)
    ap.add_argument("--max-nodes", type=int, default=200000)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=ENV_DIR)
    env = arcade.make(args.game, seed=0)
    assert env is not None, f"make() failed for {args.game}"

    root = env.reset()
    start_levels = int(getattr(root, "levels_completed", 0) or 0)
    print(f"game={args.game}  start levels_completed={start_levels}  max_depth={args.max_depth}")

    seen = {obs_digest(root)}
    queue = deque([([], root)])
    t0 = time.monotonic()
    expanded = 0
    steps = 0

    while queue:
        if time.monotonic() - t0 > args.budget_s:
            print(f"  (time budget reached after {expanded} expansions)")
            break
        if expanded >= args.max_nodes:
            print("  (node budget reached)")
            break

        seq, frame = queue.popleft()
        if len(seq) >= args.max_depth:
            continue
        avail = [ACTION_BY_ID[int(a)] for a in (frame.available_actions or []) if int(a) in ACTION_BY_ID]
        avail = [a for a in avail if a.value != 6]  # coordinate actions are out of scope here
        expanded += 1

        for a in avail:
            child = replay(env, seq + [a])          # no save/restore: replay the prefix
            steps += len(seq) + 1
            lc = int(getattr(child, "levels_completed", 0) or 0)
            if lc > start_levels:
                ids = [x.value for x in (seq + [a])]
                print(f"\nSOLVED level 1 in {len(ids)} actions: {ids}")
                # Reproduce it — R2's arms depend on this exact sequence replaying.
                ok = True
                for _ in range(3):
                    f = replay(env, seq + [a])
                    ok &= int(getattr(f, "levels_completed", 0) or 0) > start_levels
                print(f"reproduces on 3 replays: {ok}")
                print(f"expanded {expanded} nodes, {steps} env steps, {time.monotonic()-t0:.1f}s")
                if args.out:
                    json.dump({"game": args.game, "n_actions": len(ids), "action_ids": ids,
                               "reproduces": bool(ok), "expanded_nodes": expanded},
                              open(args.out, "w"), indent=2)
                    print(f"wrote {args.out}")
                return 0 if ok else 3
            d = obs_digest(child)
            if d not in seen:
                seen.add(d)
                queue.append((seq + [a], child))

        if expanded % 500 == 0:
            print(f"  expanded={expanded} frontier={len(queue)} seen={len(seen)} "
                  f"depth={len(seq)+1} steps={steps} {time.monotonic()-t0:.0f}s")

    print(f"\nNO solution within depth {args.max_depth}. expanded={expanded} seen={len(seen)} "
          f"frontier={len(queue)} steps={steps}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
