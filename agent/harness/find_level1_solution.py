"""Search offline for a SCRIPTED action sequence that completes level 1.

R2 (`gate_manifest.yaml → s1.reset_experiment.r2_action_accounting`) requires a scripted completion of
level 1, not an agent's: "Use a scripted sequence, not the agent. A stochastic policy makes the two arms
incomparable and the result uninterpretable." We have no published solution for any game, so we search
for one.

This is only tractable because R1 established that these offline environments replay deterministically —
a sequence found here reproduces exactly when replayed, which is precisely what arms A and B require.

Restricted to games whose level 1 opens with SIMPLE actions (no ACTION6), since a coordinate policy would
add a second search dimension over a 64x64 grid.

Run:  .venv/bin/python agent/harness/find_level1_solution.py --game tu93-0768757b
"""

from __future__ import annotations

import argparse
import json
import random
import time

import arc_agi
import arcengine

ENV_DIR = "data/environment_files"
# GameAction is not an IntEnum — use .value, not int().
ACTION_BY_ID = {a.value: a for a in arcengine.GameAction if a.value != 0}


def rollout(env, actions):
    """Replay a sequence from a fresh RESET. Returns (levels_completed, step_index_of_first_completion)."""
    frame = env.reset()
    start = int(getattr(frame, "levels_completed", 0) or 0)
    for i, a in enumerate(actions):
        frame = env.step(a)
        lc = int(getattr(frame, "levels_completed", 0) or 0)
        if lc > start:
            return lc, i + 1
    return int(getattr(frame, "levels_completed", 0) or 0), None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="tu93-0768757b")
    ap.add_argument("--max-len", type=int, default=60)
    ap.add_argument("--trials", type=int, default=20000)
    ap.add_argument("--budget-s", type=float, default=600.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=ENV_DIR)
    env = arcade.make(args.game, seed=0)
    assert env is not None, f"make() failed for {args.game}"

    frame = env.reset()
    avail = [ACTION_BY_ID[int(a)] for a in (frame.available_actions or []) if int(a) in ACTION_BY_ID]
    assert avail, "no simple actions available"
    assert all(a.value != 6 for a in avail), "ACTION6 present — this searcher handles simple actions only"
    print(f"game={args.game}  actions={[a.value for a in avail]}  max_len={args.max_len}")

    rng = random.Random(args.seed)
    best = None
    t0 = time.monotonic()
    tried = 0

    for _ in range(args.trials):
        if time.monotonic() - t0 > args.budget_s:
            print(f"  (time budget {args.budget_s}s reached)")
            break
        seq = [rng.choice(avail) for _ in range(args.max_len)]
        tried += 1
        lc, at = rollout(env, seq)
        if at is not None and (best is None or at < best[1]):
            best = (seq[:at], at)
            print(f"  trial {tried}: level 1 completed in {at} actions")
            if at <= 8:
                break

    elapsed = time.monotonic() - t0
    print(f"\ntried {tried} rollouts in {elapsed:.1f}s")
    if best is None:
        print("NO level-1 completion found. Options: raise --max-len/--trials, or try another game.")
        return 2

    seq, n = best
    ids = [a.value for a in seq]
    print(f"SHORTEST FOUND: {n} actions -> {ids}")

    # Verify it reproduces — R1 says it must, and R2 depends on that being true for THIS sequence.
    ok = all(rollout(env, seq)[1] == n for _ in range(3))
    print(f"reproduces on 3 replays: {ok}")

    if args.out:
        json.dump({"game": args.game, "n_actions": n, "action_ids": ids, "reproduces": ok},
                  open(args.out, "w"), indent=2)
        print(f"wrote {args.out}")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
