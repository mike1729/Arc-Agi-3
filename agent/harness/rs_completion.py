#!/usr/bin/env python3
"""E0 row C — completion-condition rule survival, L1 -> L2.

Row M asks whether the DYNAMICS transfer. This row asks whether the GOAL does: take every
hypothesis about what completes a level that is consistent with all of L1's evidence, and
see how many are still consistent with L2's.

The hypothesis space is the frozen ES visual candidate grammar, resurrected unmodified from
``archive/screening-line-2026-08-04`` and asserted by hash at run time. Visual terms only —
source-semantic constructs never enter, so no candidate can smuggle in knowledge of the game
that an agent looking at the screen would not have. Evaluation is three-valued; ``unknown``
neither eliminates nor confirms.

THREE OUTCOMES, NOT TWO
-----------------------
    falsified   some L2 transition where the candidate predicts definitely and wrongly
    survived    never contradicted at L2, and definite-and-correct at least once
    vacuous     never definite anywhere in L2 — its terms do not bind to the L2 board

`vacuous` is the category that makes this honest. A candidate whose colour terms name objects
L2 does not contain is never contradicted, and folding that into `survived` would report the
grammar's silence as the goal's stability — a rule that cannot be evaluated has not
transferred.

THE COVERAGE CONFOUND, MEASURED
-------------------------------
The ES screen closed coverage-blocked with six of six games unproven, and that failure lands
directly on this row: where the visual grammar cannot express a game's completion condition
at all, its L1 survivor set is empty, the survival rate is 0/0, and the cell is UNDEFINED.
It is never reported as 0%. How many games are expressible at all is itself a result here,
and it bounds what row C can say.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import es_candidates as ec  # noqa: E402
from rs_transitions import (  # noqa: E402
    ITERATION_GAMES,
    ROOT,
    Transition,
    grid_digest,
    load_game,
    split_half,
)

OUTPUT = ROOT / "logs/e0_row_c.json"
FORMAT_VERSION = 1

# Asserted, not assumed: the grammar this row is defined against is the frozen one.
EXPECTED_GRAMMAR_HASH = "49c0cc3e4abc74186edbc65665f65fd68e1faa7e9e3678d58ce53346cb0b2a6b"

TRUE, FALSE, UNKNOWN = "true", "false", "unknown"


class ObjectCache:
    """One ``_Objects`` per distinct grid.

    The evaluator rebuilds components from the raw grid on every call, so a naive scoring
    loop pays componentization once per (candidate, transition) rather than once per grid —
    on the larger games that is the difference between minutes and hours, and it changes no
    result. The evaluator itself is untouched.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def get(self, grid: list) -> Any:
        digest = grid_digest(grid)
        cached = self._cache.get(digest)
        if cached is None:
            cached = ec._Objects(grid)
            self._cache[digest] = cached
        return cached

    def context(self, pre: list, post: list) -> dict[str, Any]:
        return {"objects": self.get(post), "pre_objects": self.get(pre)}


def predict(candidate: dict, transition: Transition, cache: ObjectCache) -> str:
    return ec.evaluate(candidate, cache.context(transition.pre, transition.post))


def survivors(
    universe: list[dict], transitions: list[Transition], cache: ObjectCache
) -> list[dict]:
    """Candidates not definitely contradicted by any labelled transition."""
    alive = []
    for candidate in universe:
        for transition in transitions:
            value = predict(candidate, transition, cache)
            if value == UNKNOWN:
                continue
            truth = TRUE if transition.completed else FALSE
            if value != truth:
                break
        else:
            alive.append(candidate)
    return alive


def score(
    candidates: list[dict], transitions: list[Transition], cache: ObjectCache
) -> dict[str, Any]:
    outcomes = Counter()
    for candidate in candidates:
        definite_correct = 0
        contradicted = False
        for transition in transitions:
            value = predict(candidate, transition, cache)
            if value == UNKNOWN:
                continue
            truth = TRUE if transition.completed else FALSE
            if value != truth:
                contradicted = True
                break
            definite_correct += 1
        if contradicted:
            outcomes["falsified"] += 1
        elif definite_correct:
            outcomes["survived"] += 1
        else:
            outcomes["vacuous"] += 1
    total = sum(outcomes.values())
    return {
        "scored": total,
        "falsified": outcomes["falsified"],
        "survived": outcomes["survived"],
        "vacuous": outcomes["vacuous"],
        # 0/0 stays None. An empty survivor set means the grammar could not express this
        # game's goal, which is not the same as the goal failing to transfer.
        "survival_rate": round(outcomes["survived"] / total, 4) if total else None,
    }


def run_game(game: str) -> dict[str, Any]:
    transitions = load_game(game, max_level=2)
    l1 = [t for t in transitions if t.level == 1]
    l2 = [t for t in transitions if t.level == 2]
    a, b = split_half(l1)
    cache = ObjectCache()

    universe_doc = ec.enumerate_universe(l1[0].pre)
    universe = universe_doc["universe"]

    row: dict[str, Any] = {
        "game": game,
        "l1_transitions": len(l1),
        "l2_transitions": len(l2),
        "l1_completions": sum(t.completed for t in l1),
        "l2_completions": sum(t.completed for t in l2),
        "universe_size": universe_doc["universe_size"],
        "universe_tractable": universe_doc["tractable"],
        "universe_hash": universe_doc["universe_hash"],
    }
    if not universe_doc["tractable"]:
        row["expressible"] = None
        row["note"] = "universe exceeded the frozen tractability limit; not enumerated"
        return row

    l1_survivors = survivors(universe, l1, cache)
    row["l1_survivors"] = len(l1_survivors)
    row["expressible"] = bool(l1_survivors)
    if not l1_survivors:
        row["l1_to_l2"] = None
        row["within_l1"] = None
        row["note"] = (
            "no candidate survives this game's own L1 evidence: the visual grammar cannot "
            "express its completion condition. L1 -> L2 is 0/0 and reported UNDEFINED."
        )
        return row

    row["l1_to_l2"] = score(l1_survivors, l2, cache)
    a_survivors = survivors(universe, a, cache)
    row["within_l1"] = (
        score(a_survivors, b, cache) if a_survivors else None
    )
    row["split_a_survivors"] = len(a_survivors)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if ec.GRAMMAR_SPEC_HASH != EXPECTED_GRAMMAR_HASH:
        raise SystemExit(
            f"grammar hash mismatch: {ec.GRAMMAR_SPEC_HASH} != {EXPECTED_GRAMMAR_HASH}"
        )

    results = []
    for game in args.games:
        row = run_game(game)
        results.append(row)
        if not row.get("expressible"):
            print(
                f"{row['game']}  U={row['universe_size']:4d}  "
                f"L1 survivors={row.get('l1_survivors', 0):4d}  -> UNDEFINED "
                f"(grammar cannot express this game's completion condition)",
                flush=True,
            )
            continue
        across = row["l1_to_l2"]
        within = row["within_l1"]
        print(
            f"{row['game']}  U={row['universe_size']:4d}  "
            f"L1 survivors={row['l1_survivors']:4d} | "
            f"L1->L2 survived={across['survived']:4d} falsified={across['falsified']:4d} "
            f"vacuous={across['vacuous']:4d} rate={across['survival_rate']} | "
            f"withinL1 rate={within['survival_rate'] if within else None}",
            flush=True,
        )

    document = {
        "format_version": FORMAT_VERSION,
        "row": "C",
        "grammar_spec_hash": ec.GRAMMAR_SPEC_HASH,
        "games": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
