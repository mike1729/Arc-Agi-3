#!/usr/bin/env python3
"""Completion states for every game — the positive half of goal grading.

Slice-3 readout, `notes/e2-slice3.md` → RUN RESULTS. Zero model calls, zero engine calls.

THE HOLE THIS CLOSES
--------------------
Every goal predicate this project has scored was graded in one direction. `consistent_with`
asks "is this predicate ever definite-and-wrong on a transition the store recorded", and a
completion condition is definite-and-wrong on a NEGATIVE transition only by being TRUE while
nothing happened. Being FALSE at the actual completion — the other way to be wrong, and the
more common one — is invisible unless the corpus holds a completion.

The explorer's v2 store holds one completion on sp80 and one on lf52 and NONE on the other
six protocol games, and in both of those two the post frame was hashed and dropped. So slice
2 and slice 3 both graded 7 of every 9 survivors on the negative direction alone. Measured
on the slice-3 night: of the two cells that COULD be graded positively, both were false at
the real completion. Every cell that could be checked was wrong; every cell that "passed"
was unchecked.

WHERE THE POSITIVES COME FROM, AND WHY NOT THE ENGINE
-----------------------------------------------------
`e3_completion_capture.py` re-executes a store route and keeps the frames, but it can only
capture a completion the EXPLORER walked, and the explorer completed a level on two games.
Extending it to the other six would require solving them first.

The human-replay corpus already contains them. `rs_transitions.iter_session_transitions`
marks `completed` on the transition whose response incremented `levels_completed`, and keeps
the `solved_terminal` frame as its `post` — the board at the moment the level was solved.
Measured, all eight protocol games:

    dc22 20   ft09 15   ls20 20   m0r0 20   tu93 26   vc33 18   sp80 17   lf52 18

8–13 distinct completions per game at L1 alone, across 10–13 independent sessions. Nothing
had to be run to obtain them; they were in the corpus the miner already reads.

THE TWO CORPORA ARE NOT THE SAME DISTRIBUTION, AND THIS MODULE DOES NOT PRETEND OTHERWISE
------------------------------------------------------------------------------------------
The store is the explorer's own breadth-first flailing; the replays are humans playing to
win. A goal predicate is a claim about which BOARDS are terminal, so a completion is a
completion whoever produced it and the positives transfer. A contradiction RATE does not:
0.1% of the explorer's transitions is not 0.1% of a human's. So `grade` reports the two
directions against their own corpora and never divides one by the other, and it additionally
reports the same-corpus negative rate over human non-completing transitions at the same
level, which is the matched comparison.

DEDUPLICATION
-------------
Sessions of one game converge on the same terminal board, so raw completion counts
overstate the evidence. Rows are deduplicated by the digest of the post grid: distinct
BOARDS, not distinct sessions. `sessions` travels with every count so a game whose 20
completions are 3 boards cannot be read as 20 independent checks.

Grids stay local. The emitted JSON carries counts, digests, levels and session ids only —
`logs/e2_positives.json` is committed; the grids it describes are in `data/`.

Run:
  .venv/bin/python agent/harness/e2_positives.py
  .venv/bin/python agent/harness/e2_positives.py --games dc22 ft09 --max-level 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import rs_transitions as rs  # noqa: E402

ROOT = rs.ROOT
OUTPUT = ROOT / "logs/e2_positives.json"
FORMAT_VERSION = 1

# The slice protocol games. Order is the slice order, so tables line up by eye.
GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33", "sp80", "lf52")

_CACHE: dict[tuple[str, int], list] = {}


def _load(game: str, max_level: int) -> list:
    key = (game, max_level)
    if key not in _CACHE:
        _CACHE[key] = rs.load_game(game, max_level=max_level)
    return _CACHE[key]


def positives(game: str, *, level: int | None = 1, max_level: int = 2) -> list:
    """Completing transitions from the human corpus, deduplicated by post grid.

    `level=None` takes every level up to `max_level`; `level=1` is the slice default,
    because L1 is the level the evidence-first line is trying to clear and an L2 completion
    condition is a different predicate on most of these games.
    """
    rows = [t for t in _load(game, max_level) if t.completed]
    if level is not None:
        rows = [t for t in rows if t.level == level]
    seen: set[str] = set()
    unique = []
    for row in sorted(rows, key=lambda t: (t.guid, t.step)):
        digest = rs.grid_digest(row.post)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(row)
    return unique


def negatives(game: str, *, level: int | None = 1, max_level: int = 2) -> list:
    """Human non-completing transitions — the matched-corpus negative direction."""
    rows = [t for t in _load(game, max_level) if not t.completed]
    if level is not None:
        rows = [t for t in rows if t.level == level]
    return rows


def grade(node: dict[str, Any], game: str, *, level: int | None = 1) -> dict[str, Any]:
    """Evaluate a parsed predicate in BOTH directions against the human corpus.

    The positive direction is the one no earlier slice could ask: the predicate must be
    TRUE at a board a human actually solved. `unknown` is reported as its own count and
    never folded into either side — a predicate whose colour is this state's background is
    not wrong there, it is unevaluable there.
    """
    import e2_dsl as dsl  # noqa: PLC0415 — avoids a cycle; e2_dsl does not import this

    pos = positives(game, level=level)
    neg = negatives(game, level=level)

    def _tally(rows: list, want: str) -> dict[str, Any]:
        contexts = dsl.transition_contexts(rows)
        right = wrong = unknown = 0
        wrong_at: list[dict[str, Any]] = []
        for row, context in zip(rows, contexts, strict=True):
            value = dsl.evaluate(node, context)
            if value == dsl.UNKNOWN:
                unknown += 1
            elif value == want:
                right += 1
            else:
                wrong += 1
                if len(wrong_at) < 10:
                    wrong_at.append({"guid": row.guid[:8], "step": row.step})
        evaluable = right + wrong
        return {
            "rows": len(rows),
            "evaluable": evaluable,
            "correct": right,
            "wrong": wrong,
            "unknown": unknown,
            "wrong_at": wrong_at,
            # None, not 0.0, when nothing was evaluable: a rate over zero rows is not a rate.
            "error_rate": None if not evaluable else round(wrong / evaluable, 6),
        }

    positive = _tally(pos, dsl.TRUE)
    negative = _tally(neg, dsl.FALSE)
    return {
        "corpus": "human_replays",
        "level": level,
        "sessions": len({t.guid for t in pos}),
        "positive": positive,
        "negative": negative,
        # The verdict this module exists to produce. A predicate is `correct_here` only if
        # it fires on every completion AND on no non-completion. Anything less is reported
        # with its two rates rather than collapsed to a boolean.
        "holds_at_every_completion": positive["evaluable"] > 0 and positive["wrong"] == 0,
        "fires_only_at_completions": negative["evaluable"] > 0 and negative["wrong"] == 0,
        "measurable": positive["evaluable"] > 0,
    }


def census(games=GAMES, *, max_level: int = 2) -> dict[str, Any]:
    rows = []
    for game in games:
        try:
            all_rows = _load(game, max_level)
        except ValueError as error:  # excluded by fidelity
            rows.append({"game": game, "available": False, "reason": str(error)})
            continue
        by_level: dict[int, dict[str, Any]] = {}
        for level in sorted({t.level for t in all_rows if t.completed}):
            unique = positives(game, level=level, max_level=max_level)
            raw = [t for t in all_rows if t.completed and t.level == level]
            by_level[level] = {
                "completions": len(raw),
                "distinct_boards": len(unique),
                "sessions": len({t.guid for t in raw}),
                "post_digests": [rs.grid_digest(t.post)[:12] for t in unique],
                "non_completing": sum(
                    1 for t in all_rows if not t.completed and t.level == level
                ),
            }
        rows.append(
            {
                "game": game,
                "available": bool(by_level),
                "transitions": len(all_rows),
                "sessions": len({t.guid for t in all_rows}),
                "by_level": by_level,
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/e2_positives.py",
        "corpus": str(rs.CORPUS.relative_to(ROOT)),
        "note": (
            "Completion states for goal grading. Counts and digests only — the grids are "
            "competition data and stay in data/. See notes/e2-slice3.md RUN RESULTS."
        ),
        "max_level": max_level,
        "games": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(GAMES))
    parser.add_argument("--max-level", type=int, default=2)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    report = census(args.games, max_level=args.max_level)
    for row in report["games"]:
        if not row["available"]:
            print(f"{row['game']:5s} none available: {row.get('reason', '')}", flush=True)
            continue
        parts = [
            f"L{level}: {info['distinct_boards']} distinct of {info['completions']} "
            f"({info['sessions']} sessions, {info['non_completing']} negatives)"
            for level, info in sorted(row["by_level"].items())
        ]
        print(f"{row['game']:5s} {' | '.join(parts)}", flush=True)

    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(f"\nwrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
