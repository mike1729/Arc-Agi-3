#!/usr/bin/env python3
"""Frozen VP2 connected-region box representation and mechanical matching.

Boxes use zero-based inclusive grid coordinates in the order
``[row_min, col_min, row_max, col_max]``.  Gold regions carry their true changed-cell
count because an irregular region's size cannot be recovered from its bounding box.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

GRID_SIZE = 64
MAX_REGIONS = 12
TINY_REGION_CELLS = 4
IOU_THRESHOLD = 0.50
MAX_TINY_EDGE_ERROR = 1

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class GoldRegion:
    box: Box
    cell_count: int


@dataclass(frozen=True)
class RegionScore:
    matched: int
    predicted: int
    gold: int
    precision: float
    recall: float
    f1: float
    pairs: tuple[tuple[int, int], ...]


def validate_box(value: object, *, grid_size: int = GRID_SIZE) -> Box:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("region box must contain four coordinates")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError("region box coordinates must be integers")
    row_min, col_min, row_max, col_max = value
    if not (0 <= row_min <= row_max < grid_size and 0 <= col_min <= col_max < grid_size):
        raise ValueError(f"region box must lie inside a {grid_size}x{grid_size} grid")
    return row_min, col_min, row_max, col_max


def canonicalize_boxes(values: Sequence[object], *, grid_size: int = GRID_SIZE) -> tuple[Box, ...]:
    if len(values) > MAX_REGIONS:
        raise ValueError(f"at most {MAX_REGIONS} region boxes are allowed")
    boxes = tuple(validate_box(value, grid_size=grid_size) for value in values)
    if len(set(boxes)) != len(boxes):
        raise ValueError("duplicate region boxes are not allowed")
    return tuple(sorted(boxes))


def box_iou(left: Box, right: Box) -> float:
    row_overlap = max(0, min(left[2], right[2]) - max(left[0], right[0]) + 1)
    col_overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]) + 1)
    intersection = row_overlap * col_overlap
    left_area = (left[2] - left[0] + 1) * (left[3] - left[1] + 1)
    right_area = (right[2] - right[0] + 1) * (right[3] - right[1] + 1)
    return intersection / (left_area + right_area - intersection)


def _edge_error(left: Box, right: Box) -> int:
    return max(abs(a - b) for a, b in zip(left, right))


def _eligible(predicted: Box, gold: GoldRegion) -> tuple[bool, float]:
    overlap = box_iou(predicted, gold.box)
    tiny_match = (
        gold.cell_count <= TINY_REGION_CELLS
        and _edge_error(predicted, gold.box) <= MAX_TINY_EDGE_ERROR
    )
    return overlap >= IOU_THRESHOLD or tiny_match, overlap


def score_region_boxes(
    predicted_values: Sequence[object],
    gold_regions: Sequence[GoldRegion],
    *,
    grid_size: int = GRID_SIZE,
) -> RegionScore:
    """Score the maximum-cardinality matching, then maximum summed IoU.

    The final lexicographic pair ordering is only a deterministic tie-break; precision,
    recall and F1 depend on matching cardinality and therefore cannot depend on input order.
    """
    predicted = canonicalize_boxes(predicted_values, grid_size=grid_size)
    if len(gold_regions) > MAX_REGIONS:
        raise ValueError(f"at most {MAX_REGIONS} gold regions are allowed")
    gold = tuple(
        GoldRegion(validate_box(region.box, grid_size=grid_size), region.cell_count)
        for region in gold_regions
    )
    if any(
        isinstance(region.cell_count, bool)
        or not isinstance(region.cell_count, int)
        or region.cell_count <= 0
        for region in gold
    ):
        raise ValueError("gold region cell_count must be a positive integer")

    edges = tuple(
        tuple(_eligible(box, region) for box in predicted)
        for region in gold
    )

    @lru_cache(maxsize=None)
    def solve(gold_index: int, used_mask: int) -> tuple[int, float, tuple[tuple[int, int], ...]]:
        if gold_index == len(gold):
            return 0, 0.0, ()
        best = solve(gold_index + 1, used_mask)
        for predicted_index, (eligible, overlap) in enumerate(edges[gold_index]):
            if not eligible or used_mask & (1 << predicted_index):
                continue
            matched, total_iou, pairs = solve(
                gold_index + 1, used_mask | (1 << predicted_index)
            )
            candidate = (
                matched + 1,
                total_iou + overlap,
                ((gold_index, predicted_index),) + pairs,
            )
            if candidate[:2] > best[:2]:
                best = candidate
            elif candidate[:2] == best[:2]:
                best = min(candidate, best, key=lambda result: result[2])
        return best

    matched, _total_iou, pairs = solve(0, 0)
    precision = matched / len(predicted) if predicted else (1.0 if not gold else 0.0)
    recall = matched / len(gold) if gold else (1.0 if not predicted else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return RegionScore(matched, len(predicted), len(gold), precision, recall, f1, pairs)
