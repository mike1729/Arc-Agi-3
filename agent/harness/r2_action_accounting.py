"""R2 — does the scored action count accumulate across RESET, or restart?

Pre-registered in `gate_manifest.yaml → s1.reset_experiment.r2_action_accounting`. Runs only because R1
returned `deterministic`.

Design, unchanged from the pre-registration:
  Arm A (clean)     scripted completion of level 1 in `a` actions. No reset. Close, read.
  Arm B (wasteful)  `w` deliberately wasted actions -> RESET -> the SAME scripted completion. Close, read.
  a = max(20, round(1.5*H)) = 28 for tu93 (H=19);  w = a
  3 repetitions per arm, independent scorecards, SAME GAME and SAME LEVEL (a cross-game comparison is
  not identifiable — H and the level weight would not cancel).
  estimator  r = sqrt(median(score_A) / median(score_B))     — a ratio of medians, not a median of ratios
  restarts    r in [0.85, 1.15]
  accumulates r in [1.85, 2.20]
  inconclusive otherwise, or if either arm's spread > 0.10, or if the waste-validity check fails

THE CONFOUND THAT WOULD INVERT THE ANSWER: if the `w` wasted actions are rejected, or are no-ops the
scorer does not count, arm B scores like arm A and R2 reads `restarts` when the truth is `accumulates` —
selecting the aggressive controller in a world where every probe costs score. So every wasted action is
validated as ACCEPTED and STATE-CHANGING from arm B's own log BEFORE any score is read.

Run:  .venv/bin/python agent/harness/r2_action_accounting.py --arm A --reps 1   (precondition check)
      .venv/bin/python agent/harness/r2_action_accounting.py --reps 3           (full run)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics

import arc_agi
import arcengine

ENV_DIR = "data/environment_files"
ACTION_BY_ID = {a.value: a for a in arcengine.GameAction if a.value != 0}


def obs_digest(frame) -> str:
    raw = getattr(frame, "frame", None)
    grids = [(l.tolist() if hasattr(l, "tolist") else l) for l in raw] if raw is not None else None
    return hashlib.sha256(json.dumps(
        {"g": grids, "lc": int(getattr(frame, "levels_completed", 0) or 0),
         "s": str(getattr(frame, "state", ""))}, sort_keys=True, default=str).encode()).hexdigest()[:16]


def env_score(card, game):
    """Pull the per-environment score row out of a closed scorecard."""
    if card is None:
        return None
    envs = getattr(card, "environments", None) or {}
    if isinstance(envs, dict):
        for k, v in envs.items():
            if game.split("-")[0] in str(k) or str(k) in game:
                return v
        return next(iter(envs.values()), None)
    return envs[0] if envs else None


def run_arm(arcade, game, solution, arm, w_actions, rng):
    """One repetition on its own scorecard. Arm B prepends `w` wasted actions and a RESET."""
    card_id = arcade.open_scorecard(tags=[f"r2-arm-{arm}"])
    env = arcade.make(game, seed=0, scorecard_id=card_id)
    assert env is not None

    waste_log = []
    frame = env.reset()
    if arm == "B":
        for a in w_actions:
            before = obs_digest(frame)
            frame = env.step(a)
            after = obs_digest(frame)
            waste_log.append({"action": a.value, "accepted": frame is not None, "changed": before != after})
        frame = env.reset()          # the RESET under test (a LEVEL reset, per V5)

    for a in solution:
        frame = env.step(a)

    levels = int(getattr(frame, "levels_completed", 0) or 0)
    card = arcade.close_scorecard(card_id)
    row = env_score(card, game)
    return {
        "arm": arm, "card_id": card_id, "levels_completed": levels,
        "score": getattr(row, "score", None) if row else None,
        "actions": getattr(row, "actions", None) if row else None,
        "resets": getattr(row, "resets", None) if row else None,
        "level_scores": list(getattr(row, "level_scores", []) or []) if row else None,
        "level_actions": list(getattr(row, "level_actions", []) or []) if row else None,
        "level_baselines": list(getattr(row, "level_baseline_actions", []) or []) if row else None,
        "waste_log": waste_log,
    }


def spread(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    m = statistics.median(vals)
    return (max(vals) - min(vals)) / m if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="tu93-0768757b")
    ap.add_argument("--solution", default="logs/r2_arm_a_tu93.json")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arm", default="", help="A or B to run a single arm (precondition checking)")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default="logs/r2_action_accounting.json")
    args = ap.parse_args()

    spec = json.load(open(args.solution))
    solution = [ACTION_BY_ID[i] for i in spec["action_ids"]]
    a_len = len(solution)
    assert a_len == spec["a"], "solution length must equal the pre-registered a"
    assert a_len >= 20, "min_a violated — c_reset would no longer be absorbed"

    rng = random.Random(args.seed)
    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=ENV_DIR)

    # w = a, and the wasted actions are drawn from the simple action set. Validity is checked from the
    # log after the fact, not assumed here.
    w_actions = [ACTION_BY_ID[rng.choice([1, 2, 3, 4])] for _ in range(a_len)]
    print(f"game={args.game}  a={a_len}  w={len(w_actions)}  reps={args.reps}")

    arms = [args.arm] if args.arm else ["A", "B"]
    results = {"A": [], "B": []}
    for arm in arms:
        for i in range(args.reps):
            r = run_arm(arcade, args.game, solution, arm, w_actions, rng)
            results[arm].append(r)
            print(f"  arm {arm} rep {i+1}: levels={r['levels_completed']} score={r['score']} "
                  f"actions={r['actions']} resets={r['resets']} level_scores={r['level_scores']}")

    # ---- waste validity, checked BEFORE any score is interpreted ----
    waste_ok = None
    if results["B"]:
        logs = [x for r in results["B"] for x in r["waste_log"]]
        acc = sum(1 for x in logs if x["accepted"])
        chg = sum(1 for x in logs if x["changed"])
        waste_ok = (acc == len(logs) and chg == len(logs))
        print(f"\nwaste validity: {acc}/{len(logs)} accepted, {chg}/{len(logs)} changed state "
              f"-> {'VALID' if waste_ok else 'VOID — arm B must be rebuilt and rerun'}")

    out = {"game": args.game, "a": a_len, "w": len(w_actions), "reps": args.reps,
           "waste_valid": waste_ok, "results": results}

    if results["A"] and results["B"]:
        sa = [r["score"] for r in results["A"]]
        sb = [r["score"] for r in results["B"]]
        spa, spb = spread(sa), spread(sb)
        ma, mb = statistics.median(sa), statistics.median(sb)
        r_stat = (ma / mb) ** 0.5 if mb else None
        print(f"\nmedian score A={ma} B={mb}   spread A={spa} B={spb}")
        print(f"r = sqrt(median_A/median_B) = {r_stat}")
        if not waste_ok or (spa or 0) > 0.10 or (spb or 0) > 0.10 or r_stat is None:
            verdict = "inconclusive"
        elif 0.85 <= r_stat <= 1.15:
            verdict = "restarts"
        elif 1.85 <= r_stat <= 2.20:
            verdict = "accumulates"
        else:
            verdict = "inconclusive"
        # Direct corroboration: the scorer exposes `actions` and `resets` outright.
        aa = [r["actions"] for r in results["A"]]
        ab = [r["actions"] for r in results["B"]]
        print(f"\nDIRECT observation (corroborating, not the pre-registered estimator):")
        print(f"  arm A actions={aa}  arm B actions={ab}  (a={a_len}, a+w={2*a_len})")
        out.update({"r": r_stat, "verdict": verdict, "spread_A": spa, "spread_B": spb})
        print(f"\nR2 VERDICT: {verdict}")

    json.dump(out, open(args.out, "w"), indent=2, default=str)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
