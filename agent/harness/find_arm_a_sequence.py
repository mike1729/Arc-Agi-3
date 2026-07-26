"""Find a scripted level-1 completion of EXACTLY the pre-registered length `a`.

R2 fixes `a = max(20, round(1.5 * H))` — for tu93 (H=19) that is 28. The length is not cosmetic:

  * `a >= 20` is what absorbs `c_reset` (whether RESET is itself a scored action) into the tolerance
    band, since 1/a <= 0.05.
  * `a ~= 1.5H` is what keeps arm A clear of the per-level cap. The BFS-shortest solution for tu93 is
    18 actions — SHORTER than the human baseline of 19 — which would score (19/18)^2 * 100 = 111.4
    against a cap of 115. That fails the `cap_not_saturated` precondition outright, and a saturated arm
    collapses the ratio the whole experiment rests on.

There are no no-op actions and no inverse pairs at tu93's start state, so the sequence cannot simply be
padded. Instead: take a random walk of k steps, BFS the shortest completion from there, and accept when
k + shortest == a exactly.

Run:  .venv/bin/python agent/harness/find_arm_a_sequence.py --game tu93-0768757b --target 28
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import deque

import arc_agi
import arcengine

ENV_DIR = "data/environment_files"
ACTION_BY_ID = {a.value: a for a in arcengine.GameAction if a.value != 0}


def obs_digest(frame) -> str:
    raw = getattr(frame, "frame", None)
    grids = [(l.tolist() if hasattr(l, "tolist") else l) for l in raw] if raw is not None else None
    obs = {"g": grids, "lc": int(getattr(frame, "levels_completed", 0) or 0),
           "s": str(getattr(frame, "state", "")),
           "a": [int(a) for a in (getattr(frame, "available_actions", None) or [])]}
    return hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()[:20]


def replay(env, seq):
    f = env.reset()
    for a in seq:
        f = env.step(a)
    return f


def shortest_from(env, prefix, start_levels, max_extra, budget_s):
    """BFS for the shortest completion reachable after `prefix`. Returns the full sequence or None."""
    root = replay(env, prefix)
    if int(getattr(root, "levels_completed", 0) or 0) > start_levels:
        return prefix
    seen = {obs_digest(root)}
    q = deque([([], root)])
    t0 = time.monotonic()
    while q:
        if time.monotonic() - t0 > budget_s:
            return None
        suffix, frame = q.popleft()
        if len(suffix) >= max_extra:
            continue
        avail = [ACTION_BY_ID[int(a)] for a in (frame.available_actions or []) if int(a) in ACTION_BY_ID]
        avail = [a for a in avail if a.value != 6]
        for a in avail:
            child = replay(env, prefix + suffix + [a])
            if int(getattr(child, "levels_completed", 0) or 0) > start_levels:
                return prefix + suffix + [a]
            d = obs_digest(child)
            if d not in seen:
                seen.add(d)
                q.append((suffix + [a], child))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="tu93-0768757b")
    ap.add_argument("--target", type=int, default=28, help="the pre-registered `a`")
    ap.add_argument("--attempts", type=int, default=200)
    ap.add_argument("--budget-s", type=float, default=900.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="logs/r2_arm_a_tu93.json")
    args = ap.parse_args()

    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=ENV_DIR)
    env = arcade.make(args.game, seed=0)
    assert env is not None
    root = env.reset()
    start_levels = int(getattr(root, "levels_completed", 0) or 0)
    rng = random.Random(args.seed)
    t0 = time.monotonic()

    print(f"game={args.game} target a={args.target}")
    for attempt in range(args.attempts):
        if time.monotonic() - t0 > args.budget_s:
            print("  (budget reached)")
            break
        k = rng.randint(2, args.target - 12)
        # random walk of k steps, re-reading available actions each step
        walk, f = [], env.reset()
        ok = True
        for _ in range(k):
            avail = [ACTION_BY_ID[int(a)] for a in (f.available_actions or []) if int(a) in ACTION_BY_ID]
            avail = [a for a in avail if a.value != 6]
            if not avail:
                ok = False
                break
            a = rng.choice(avail)
            walk.append(a)
            f = env.step(a)
            if int(getattr(f, "levels_completed", 0) or 0) > start_levels:
                ok = False  # walked into a completion; wrong length, discard
                break
        if not ok:
            continue

        sol = shortest_from(env, walk, start_levels, max_extra=args.target - k, budget_s=60.0)
        if sol is None:
            continue
        if len(sol) == args.target:
            ids = [x.value for x in sol]
            print(f"\nFOUND a={len(ids)}-action completion (walk k={k}): {ids}")
            reps = []
            for _ in range(3):
                f = replay(env, sol)
                reps.append(int(getattr(f, "levels_completed", 0) or 0) > start_levels)
            print(f"reproduces on 3 replays: {all(reps)}")
            h = 19
            print(f"projected arm-A level score: min(115, ({h}/{len(ids)})^2*100) = "
                  f"{min(115.0,(h/len(ids))**2*100):.1f}  (cap 115 — clear)")
            json.dump({"game": args.game, "a": len(ids), "action_ids": ids,
                       "walk_len": k, "reproduces": all(reps)}, open(args.out, "w"), indent=2)
            print(f"wrote {args.out}")
            return 0
        if attempt % 20 == 0:
            print(f"  attempt {attempt}: k={k} -> total {len(sol)} (want {args.target})")

    print("no sequence of the exact target length found")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
