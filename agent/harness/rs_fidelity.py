#!/usr/bin/env python3
"""E0 engine truth — do the frozen game sources reproduce the recordings byte-for-byte?

E0 reads its labels and its grids from the human recordings. That is only sound if the
recordings are what the game engine actually produces, so this replays every session of every
measured game through the frozen local source via ``ReplayDriver`` over ``arcengine`` and
compares EVERY returned frame.

GI-2 established this on 6 games / 18 selected sessions. E0 uses all sessions of those games,
so the gate is re-run over the full per-game corpus rather than inherited. A game whose
sessions do not reproduce exactly is reported and its E0 rows are not trustworthy — the
finding would be about a divergence between the source and the client, not about levels.

Run:
  .venv/bin/python agent/harness/rs_fidelity.py --jobs 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from gi2_replay import ReplayDriver, _plain_frames, iter_recorded_actions  # noqa: E402
from rs_transitions import CORPUS, ITERATION_GAMES, ROOT  # noqa: E402

OUTPUT = ROOT / "logs/e0_fidelity.json"
FORMAT_VERSION = 1


def _role_bearing(frames: list, *, state: str, increment: int) -> list:
    """The frames E0 actually reads: settled, solved_terminal, next_level_initial.

    Intermediate (animation) frames are never a transition endpoint, so they cannot affect an
    E0 result. Reporting them apart is what separates the ACCEPTED vc33 settled-frame erratum —
    a divergence confined to intermediates — from a divergence that would invalidate the
    measurement.
    """
    if not frames:
        return []
    if increment > 0 and state != "WIN":
        return frames[-2:]
    return frames[-1:]


def check_session(args: tuple[str, str]) -> dict[str, Any]:
    game, guid = args
    path = CORPUS / game / f"{guid}.recording.jsonl"
    driver = ReplayDriver(game)
    engine = driver.new_game()
    steps = matched = role_matched = 0
    previous = 0
    first_divergence: dict[str, Any] | None = None
    first_role_divergence: dict[str, Any] | None = None
    for recorded in iter_recorded_actions(path):
        replayed = driver.perform(engine, recorded)
        steps += 1
        got = _plain_frames(replayed.frame or [])
        increment = recorded.levels_completed - previous
        previous = recorded.levels_completed

        if got == recorded.frames:
            matched += 1
        elif first_divergence is None:
            first_divergence = {
                "step": recorded.step,
                "action_id": recorded.action_id,
                "recorded_frames": len(recorded.frames),
                "replayed_frames": len(got),
            }

        state = str(getattr(replayed.state, "value", replayed.state))
        want = _role_bearing(recorded.frames, state=recorded.state, increment=increment)
        have = _role_bearing(got, state=state, increment=increment)
        if want == have:
            role_matched += 1
        elif first_role_divergence is None:
            first_role_divergence = {
                "step": recorded.step,
                "action_id": recorded.action_id,
                "completion": increment > 0,
            }
    return {
        "game": game,
        "guid": guid,
        "steps": steps,
        "frames_matched": matched,
        "role_frames_matched": role_matched,
        "exact": matched == steps,
        "role_exact": role_matched == steps,
        "first_divergence": first_divergence,
        "first_role_divergence": first_role_divergence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    jobs = [
        (game, path.name.split(".")[0])
        for game in args.games
        for path in sorted((CORPUS / game).glob("*.recording.jsonl"))
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(check_session, jobs))

    per_game: dict[str, dict[str, Any]] = {}
    for row in rows:
        cell = per_game.setdefault(
            row["game"],
            {
                "sessions": 0, "exact": 0, "role_exact": 0, "steps": 0,
                "matched": 0, "role_matched": 0, "divergent": [], "role_divergent": [],
            },
        )
        cell["sessions"] += 1
        cell["exact"] += int(row["exact"])
        cell["role_exact"] += int(row["role_exact"])
        cell["steps"] += row["steps"]
        cell["matched"] += row["frames_matched"]
        cell["role_matched"] += row["role_frames_matched"]
        if not row["exact"]:
            cell["divergent"].append(
                {"guid": row["guid"], "first_divergence": row["first_divergence"]}
            )
        if not row["role_exact"]:
            cell["role_divergent"].append(
                {"guid": row["guid"], "first_role_divergence": row["first_role_divergence"]}
            )

    for game in args.games:
        cell = per_game[game]
        print(
            f"{game}  all-frame {cell['exact']}/{cell['sessions']} sessions "
            f"({cell['matched']}/{cell['steps']} actions)  |  "
            f"ROLE-BEARING {cell['role_exact']}/{cell['sessions']} sessions "
            f"({cell['role_matched']}/{cell['steps']} actions)"
            + ("" if not cell["role_divergent"] else "  <-- AFFECTS E0"),
            flush=True,
        )

    document = {"format_version": FORMAT_VERSION, "per_game": per_game, "sessions": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
