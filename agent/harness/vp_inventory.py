#!/usr/bin/env python3
"""VP screen — pre-freeze sample inventory (notes/vp-perception-screen.md §"inventory").

Counts, per iteration game, the raw material the VP question generator can draw from:
settled boards, within-level before/after pairs (changed vs no-op), click effectiveness,
color statistics (chance levels for marked-target questions), change magnitudes (distractor
banding), and completion/transfer cases. Pure corpus arithmetic: no RNG, no model calls,
iteration games only (`selected_sessions` rejects reserved games by construction).

Baseline rule: a VP2 pair is (previous settled board -> this step's settled board) within a
level. RESET rows and full resets re-baseline without forming a pair; a completion forms a
`completion_pair` (baseline -> solved_terminal) and re-baselines to next_level_initial.

Run:
  .venv/bin/python agent/harness/vp_inventory.py            # write logs/vp_inventory.json
  .venv/bin/python agent/harness/vp_inventory.py --verify   # recompute and compare
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gi2_traces import (  # noqa: E402
    CORPUS,
    DRAW,
    ROLE_NEXT_LEVEL_INITIAL,
    ROLE_SETTLED,
    ROLE_SOLVED_TERMINAL,
    SESSIONS,
    _sha256,
    iter_trace,
    selected_sessions,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "logs/vp_inventory.json"
FORMAT_VERSION = 3  # v3 separates eligible 9-12-region pairs from excluded >12 pairs.
RESET_ACTION_ID = 0
MOUSE_ACTION_ID = 6
TINY_REGION_CELLS = 4
REGION_QUESTION_MAX = 12
REGION_HIST_BANDS = ("1", "2", "3", "4-8", "9-12", ">12")


def _percentiles(values: list[int]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {
        "n": len(ordered),
        "p25": pick(0.25),
        "p50": pick(0.50),
        "p75": pick(0.75),
        "max": ordered[-1],
    }


def _diff_set(before: list, after: list) -> set[tuple[int, int]]:
    return {
        (row_index, col_index)
        for row_index, (row_before, row_after) in enumerate(zip(before, after))
        for col_index, (cell_before, cell_after) in enumerate(zip(row_before, row_after))
        if cell_before != cell_after
    }


def _region_band(count: int) -> str:
    if count <= 3:
        return str(count)
    if count <= 8:
        return "4-8"
    if count <= REGION_QUESTION_MAX:
        return "9-12"
    return ">12"


def _delta_regions(cells: set[tuple[int, int]]) -> list[int]:
    """Sizes of 4-connected components over the changed-cell set."""
    remaining = set(cells)
    sizes = []
    while remaining:
        frontier = [remaining.pop()]
        size = 0
        while frontier:
            row, col = frontier.pop()
            size += 1
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    frontier.append(neighbor)
        sizes.append(size)
    return sizes


def _mouse_cell(action_data: dict) -> tuple[int, int]:
    """Canonical display-grid coordinate for a recorded MOUSE action.

    Recordings store engine coordinates as ``x=column`` and ``y=row``; every VP question and
    observation-layer coordinate is ``(row, col)``.
    """
    return int(action_data.get("y", -1)), int(action_data.get("x", -1))


def _settled_frame(step) -> list | None:
    for role in (ROLE_SETTLED, ROLE_SOLVED_TERMINAL):
        for frame in step.frames:
            if frame.role == role:
                return frame.grid
    return None


def _next_level_frame(step) -> list | None:
    for frame in step.frames:
        if frame.role == ROLE_NEXT_LEVEL_INITIAL:
            return frame.grid
    return None


def _session_inventory(path: Path) -> dict:
    counts = {
        "actions": 0,
        "resets": 0,
        "settled_boards": 0,
        "pairs_changed": 0,
        "pairs_noop": 0,
        "pairs_region_eligible": 0,
        "pairs_region_excluded": 0,
        "completion_pairs": 0,
        "completions": 0,
        "clicks_effective": 0,
        "clicks_noop": 0,
    }
    magnitudes: list[int] = []
    region_counts: list[int] = []
    region_hist = {band: 0 for band in REGION_HIST_BANDS}
    tiny_regions = 0
    total_regions = 0
    color_counts: list[int] = []
    available_sizes: list[int] = []
    click_cells_effective: set[tuple[int, int]] = set()
    click_cells_noop: set[tuple[int, int]] = set()
    baseline: list | None = None
    max_levels = 0

    for step in iter_trace(path):
        counts["actions"] += 1
        max_levels = max(max_levels, step.levels_completed)
        available_sizes.append(len(step.available_actions))
        settled = _settled_frame(step)
        if settled is not None:
            counts["settled_boards"] += 1
            color_counts.append(len({cell for row in settled for cell in row}))

        if step.action_id == RESET_ACTION_ID or step.full_reset:
            counts["resets"] += 1
            baseline = settled if settled is not None else baseline
            continue

        changed: bool | None = None
        if step.is_completion:
            counts["completions"] += step.completion_increment
            if baseline is not None and settled is not None:
                counts["completion_pairs"] += 1
                changed = True
            baseline = _next_level_frame(step)
        elif baseline is not None and settled is not None:
            diff = _diff_set(baseline, settled)
            changed = bool(diff)
            counts["pairs_changed" if changed else "pairs_noop"] += 1
            if changed:
                magnitudes.append(len(diff))
                sizes = _delta_regions(diff)
                region_counts.append(len(sizes))
                region_hist[_region_band(len(sizes))] += 1
                counts[
                    "pairs_region_eligible"
                    if len(sizes) <= REGION_QUESTION_MAX
                    else "pairs_region_excluded"
                ] += 1
                total_regions += len(sizes)
                tiny_regions += sum(1 for size in sizes if size <= TINY_REGION_CELLS)
            baseline = settled
        else:
            baseline = settled if settled is not None else baseline

        if step.action_id == MOUSE_ACTION_ID and changed is not None:
            cell = _mouse_cell(step.action_data)
            if changed:
                counts["clicks_effective"] += 1
                click_cells_effective.add(cell)
            else:
                counts["clicks_noop"] += 1
                click_cells_noop.add(cell)

    return {
        **counts,
        "max_levels": max_levels,
        "change_magnitude": _percentiles(magnitudes),
        "delta_regions": _percentiles(region_counts),
        "delta_regions_hist": region_hist,
        "tiny_region_share": round(tiny_regions / total_regions, 4) if total_regions else None,
        "colors_per_board": _percentiles(color_counts),
        "available_actions": _percentiles(available_sizes),
        "distinct_click_cells_effective": len(click_cells_effective),
        "distinct_click_cells_noop_only": len(click_cells_noop - click_cells_effective),
    }


def build() -> dict:
    sessions_doc = json.loads(SESSIONS.read_text(encoding="utf-8"))
    draw_doc = json.loads(DRAW.read_text(encoding="utf-8"))
    games = []
    for env in sorted(draw_doc["iteration"]):
        rows = selected_sessions(env, sessions_doc, draw_doc)
        per_session = []
        for row in rows:
            path = CORPUS / env / f"{row['guid']}.recording.jsonl"
            per_session.append({"guid": row["guid"], **_session_inventory(path)})
        aggregate = {
            key: sum(session[key] for session in per_session)
            for key in (
                "actions", "resets", "settled_boards", "pairs_changed", "pairs_noop",
                "pairs_region_eligible", "pairs_region_excluded",
                "completion_pairs", "completions", "clicks_effective", "clicks_noop",
            )
        }
        aggregate["transfer_cases"] = sum(
            max(0, session["completions"] - 1) for session in per_session
        )
        aggregate["delta_regions_hist"] = {
            band: sum(session["delta_regions_hist"][band] for session in per_session)
            for band in REGION_HIST_BANDS
        }
        games.append({"env": env, "sessions": per_session, "totals": aggregate})

    totals = {
        key: sum(game["totals"][key] for game in games)
        for key in games[0]["totals"]
        if key != "delta_regions_hist"
    }
    totals["delta_regions_hist"] = {
        band: sum(game["totals"]["delta_regions_hist"][band] for game in games)
        for band in REGION_HIST_BANDS
    }
    return {
        "format_version": FORMAT_VERSION,
        "region_question": {
            "connectivity": 4,
            "maximum_regions": REGION_QUESTION_MAX,
            "eligible_histogram_bands": ["1", "2", "3", "4-8", "9-12"],
            "excluded_histogram_band": ">12",
        },
        "inputs": {
            "sessions": str(SESSIONS.relative_to(ROOT)),
            "sessions_sha256": _sha256(SESSIONS),
            "draw": str(DRAW.relative_to(ROOT)),
            "draw_sha256": _sha256(DRAW),
        },
        "games": games,
        "totals": totals,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    document = build()
    if args.verify:
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if existing != document:
            print("vp_inventory: artifact differs from rebuild", file=sys.stderr)
            return 1
        print("vp_inventory: verified")
        return 0
    OUTPUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for game in document["games"]:
        totals = game["totals"]
        print(
            f"{game['env']}: actions={totals['actions']} boards={totals['settled_boards']} "
            f"pairs +{totals['pairs_changed']}/-{totals['pairs_noop']} "
            f"completions={totals['completions']} clicks +{totals['clicks_effective']}"
            f"/-{totals['clicks_noop']} transfer={totals['transfer_cases']} "
            f"regions={totals['delta_regions_hist']}"
        )
    print("totals:", json.dumps(document["totals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
