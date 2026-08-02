"""Focused tests for the Sprint A-R primitives (note §3.4, frozen 2026-07-30)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))
import gi2_sprint_ar as AR  # noqa: E402

GRID = 64


def _grid(fill: int = 4) -> list[list[int]]:
    return [[fill] * GRID for _ in range(GRID)]


def _obj(obj_id: str, cells: set[tuple[int, int]], color: int) -> dict:
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    return {
        "id": obj_id,
        "kind": "atomic",
        "members": [obj_id],
        "colors": [color],
        "shapes": ["s"],
        "pixels": len(cells),
        "bbox": [min(rows), min(cols), max(rows), max(cols)],
        "centroid": [rows[0], cols[0]],
        "cells": sorted(cells),
        "role": "static",
        "occluded": False,
    }


# ------------------------------------------------------------------------------- R-2


def test_ring_decompose_splits_frame_and_interior():
    ring = {
        (row, col)
        for row in range(10, 17)
        for col in range(20, 27)
        if row in (10, 16) or col in (20, 26)
    }
    interior = {(row, col) for row in range(12, 15) for col in range(22, 25)}
    parts = AR._ring_decompose(_obj("p", ring | interior, 5))
    assert len(parts) == 2
    ring_part = next(part for part in parts if part["id"].endswith(":ring"))
    interior_part = next(part for part in parts if ":int" in part["id"])
    assert ring_part["pixels"] == len(ring) == 24
    assert {tuple(cell) for cell in interior_part["cells"]} == interior
    assert ring_part["derived_from"] == "p"


def test_ring_decompose_ignores_incomplete_perimeter_and_small():
    partial = {(0, col) for col in range(5)} | {(1, 0), (1, 4)}
    assert AR._ring_decompose(_obj("q", partial, 3)) == []
    tiny = {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert AR._ring_decompose(_obj("r", tiny, 3)) == []


# ------------------------------------------------------------------------------- R-1


def test_composites_pairs_and_clusters():
    a = _obj("a", {(0, 0), (0, 1)}, 1)
    b = _obj("b", {(0, 2), (0, 3)}, 2)
    c = _obj("c", {(0, 4), (0, 5)}, 3)
    background = _obj("z", {(9, 9)}, 4)
    groups = AR._composites([a, b, c, background], background=4)
    ids = {group["id"] for group in groups}
    assert "g:a+b" in ids and "g:b+c" in ids
    assert "g:a+b+c" in ids
    assert not any("z" in group_id for group_id in ids)
    cluster = next(group for group in groups if group["id"] == "g:a+b+c")
    assert cluster["pixels"] == 6 and cluster["colors"] == [1, 2, 3]


# ------------------------------------------------------------------------------- R-3


def _annotated(states_objects, gold_ids):
    annotated = []
    for objects, gold in zip(states_objects, gold_ids):
        annotated.append(
            {
                "registry": {
                    "objects_base": objects,
                    "background": 4,
                    "groups": [],
                },
                "gold_extensions": {"target": gold},
            }
        )
    return annotated


def test_gold_descriptor_single_conjunction():
    states = [
        [_obj("a", {(0, 0)}, 1), _obj("b", {(1, 1)}, 2)],
        [_obj("c", {(0, 0)}, 1), _obj("d", {(1, 1)}, 2)],
    ]
    annotated = _annotated(states, [["a"], ["c"]])
    conjunctions = AR.enumerate_conjunctions(annotated)
    chosen = AR.select_gold_descriptor(conjunctions, annotated, "target")
    assert chosen is not None
    assert len(chosen["union"]) == 1


def test_gold_descriptor_union_of_variants():
    states = [
        [
            _obj("a", {(0, 0)}, 1),
            _obj("b", {(1, 1)}, 2),
            _obj("x", {(2, 2)}, 3),
        ],
        [
            _obj("c", {(0, 0)}, 1),
            _obj("d", {(1, 1)}, 2),
            _obj("y", {(2, 2)}, 3),
        ],
    ]
    annotated = _annotated(states, [["a", "b"], ["c", "d"]])
    conjunctions = AR.enumerate_conjunctions(annotated)
    chosen = AR.select_gold_descriptor(conjunctions, annotated, "target")
    assert chosen is not None
    assert 2 <= len(chosen["union"]) <= AR.U_UNION
    for state in annotated:
        assert AR._extension(chosen, state["registry"]) == sorted(
            state["gold_extensions"]["target"]
        )


def test_gold_descriptor_unmatchable_returns_none():
    states = [
        [_obj("a", {(0, 0)}, 1), _obj("b", {(1, 1)}, 1)],
        [_obj("c", {(0, 0)}, 1), _obj("d", {(1, 1)}, 1)],
    ]
    annotated = _annotated(states, [["a"], ["c", "d"]])
    conjunctions = AR.enumerate_conjunctions(annotated)
    assert AR.select_gold_descriptor(conjunctions, annotated, "target") is None


# ------------------------------------------------------------------------------- R-4


def _paint(grid, cells, color):
    for row, col in cells:
        grid[row][col] = color


def _step_mover_onto_exit(tracker):
    """Adjacent one-cell step of a 3-cell mover onto a 1-cell exit.

    The mover's self-overlap (jaccard 2/4) beats the exit's (1/3), so the mover keeps its
    track identity and the exit disappears fully covered — the tu93 geometry.
    """
    first = _grid()
    _paint(first, {(10, 10)}, 9)                          # exit
    _paint(first, {(11, 10), (12, 10), (13, 10)}, 8)      # mover below it
    tracker.update(first, previous_grid=None, action_id=0, action_data={})
    second = _grid()
    _paint(second, {(10, 10), (11, 10), (12, 10)}, 8)     # stepped up, covering the exit
    tracker.update(second, previous_grid=first, action_id=1, action_data={})
    return first, second


def test_permanence_carries_covered_track_and_drops_destroyed():
    tracker = AR.PermanenceTracker()
    _, second = _step_mover_onto_exit(tracker)
    occluded = list(tracker.occluded.values())
    assert len(occluded) == 1
    assert occluded[0]["colors"] == [9] and occluded[0]["occluded"] is True
    registry = tracker.registry(second)
    ids = {obj["id"] for obj in registry["objects_base"]}
    assert occluded[0]["id"] in ids
    # Destruction: everything vanishes to background -> nothing new carried.
    third = _grid()
    tracker.update(third, previous_grid=second, action_id=1, action_data={})
    assert not any(
        record["colors"] == [8] for record in tracker.occluded.values()
    )


def test_permanence_cleared_on_level_reset():
    tracker = AR.PermanenceTracker()
    _step_mover_onto_exit(tracker)
    assert tracker.occluded
    tracker.reset_level()
    assert not tracker.occluded


# ------------------------------------------------------------------------- erratum


def test_role_frame_fidelity_tolerates_intermediate_divergence():
    settled = _grid(1)
    diverged = _grid(2)
    recorded = [settled, settled]
    roles = ("intermediate", "settled")
    assert AR._role_frame_fidelity([diverged, settled], recorded, roles)
    assert not AR._role_frame_fidelity([settled, diverged], recorded, roles)
    assert not AR._role_frame_fidelity([settled], recorded, roles)
