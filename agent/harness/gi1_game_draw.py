#!/usr/bin/env python3
"""GI-1 game draw: iteration slice (6) / reserved (4) / one-shot read (15).

Stratified by primary goal-predicate class from logs/s2_goal_predicates_labelled.json,
proportional to the measured distribution (quant 9 / state 6 / symmetry 5 / other 5 of 25):

    stratum                          iter  reserved  one-shot
    quantified_object_conditions       2       1        6
    state_relations                    2       1        3
    symmetry_and_template_match        1       1        3
    other (all remaining classes)      1       1        3

Constraints:
  - lp85 is in neither iteration nor reserved (preview-build recordings; one-shot only);
  - iteration contains >=1 simple-action-only game and >=1 ACTION6 game, so treatments are
    developed against both action regimes (simple-only list per erratum S1-E4).

Deterministic: seeded RNG over sorted inputs; on constraint violation the attempt counter
increments and reseeds (seed+attempt), bounded. The FIRST seed tried is adopted; if the
operator re-draws, the note must record the reason — a re-draw without one is cherry-picking.

Writes logs/gi1_game_draw.json.  --verify re-derives and exits non-zero on any drift.
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "logs" / "s2_goal_predicates_labelled.json"
OUT = ROOT / "logs" / "gi1_game_draw.json"

SEED = 20260729
SIMPLE_ONLY = {"g50t", "ls20", "re86", "tr87", "tu93", "wa30"}  # S1-E4
NEVER_ITER_OR_RESERVED = {"lp85"}

TOP = ["quantified_object_conditions", "state_relations", "symmetry_and_template_match"]
QUOTA = {  # stratum -> (iteration, reserved); one-shot is the remainder
    "quantified_object_conditions": (2, 1),
    "state_relations": (2, 1),
    "symmetry_and_template_match": (1, 1),
    "other": (1, 1),
}
MAX_ATTEMPTS = 1000


def draw(labels_path: Path) -> dict:
    data = json.loads(labels_path.read_text())
    by_stratum: dict[str, list[str]] = {k: [] for k in QUOTA}
    primary: dict[str, str] = {}
    for rec in data["records"]:
        env, cls = rec["env"], rec["label"]["primary"]
        primary[env] = cls
        by_stratum[cls if cls in TOP else "other"].append(env)
    for games in by_stratum.values():
        games.sort()

    for attempt in range(MAX_ATTEMPTS):
        rng = random.Random(SEED + attempt)
        iteration, reserved = [], []
        for stratum, (n_iter, n_res) in QUOTA.items():
            pool = [g for g in by_stratum[stratum] if g not in NEVER_ITER_OR_RESERVED]
            picked = rng.sample(pool, n_iter + n_res)
            iteration += picked[:n_iter]
            reserved += picked[n_iter:]
        it = set(iteration)
        if it & SIMPLE_ONLY and it - SIMPLE_ONLY:
            one_shot = sorted(set(primary) - it - set(reserved))
            return {
                "seed": SEED,
                "attempt": attempt,
                "labels_file": str(labels_path.relative_to(ROOT)),
                "n_games": len(primary),
                "iteration": sorted(iteration),
                "reserved": sorted(reserved),
                "one_shot": one_shot,
                "primary_class": primary,
                "constraint_audit": {
                    "iteration_simple_only": sorted(it & SIMPLE_ONLY),
                    "iteration_action6": sorted(it - SIMPLE_ONLY),
                    "lp85_bucket": "one_shot" if "lp85" in one_shot else "VIOLATION",
                },
            }
    sys.exit("no draw satisfied constraints")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    result = draw(LABELS)
    if args.verify:
        on_disk = json.loads(OUT.read_text())
        if on_disk != result:
            sys.exit("gi1_game_draw.json does not match a fresh derivation — DRIFT")
        print("verify OK")
        return
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    for bucket in ("iteration", "reserved", "one_shot"):
        games = result[bucket]
        print(f"{bucket:>9} ({len(games)}): " + " ".join(f"{g}[{result['primary_class'][g][:5]}]" for g in games))


if __name__ == "__main__":
    main()
