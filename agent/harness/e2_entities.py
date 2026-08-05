#!/usr/bin/env python3
"""E2 slice 3, build item 1 — the entity layer. Stable identity, which nothing else has.

`notes/e2-slice3.md`. Zero model calls.

WHY THIS IS A NEW FILE AND NOT A HELPER
---------------------------------------
The review's fifth point, verified before adopting: `es_candidates._Objects` is a per-grid
colour -> components cache holding `cells` and `bbox` and nothing else. It has no persistent
identity across frames, no shape hash, no containment, and no tracking. Every "the object
moved" statement anywhere in this project is really a statement about effect SIGNATURES —
`rs_transitions` matches a pre-component to a post-component only when their cell sets
intersect, which is why an object that steps clear of its own footprint is recorded as
disappear+appear rather than as a move.

So an entity table with stable IDs cannot be assembled out of `_Objects` by formatting. It
needs a tracking layer, and this is it.

WHAT AN ID MEANS HERE, AND WHAT IT DOES NOT
-------------------------------------------
An entity id is a CLAIM that two components in two frames are the same thing, made by a
matcher, not an observation. The matcher is deliberately conservative and its rule is stated
in the prompt: same colour, then best score over (identical normalized shape, bounding-box
proximity, area ratio), and an unmatched component becomes a NEW id rather than being forced
onto an old one. Where it is unsure it invents an id — which is the direction that cannot
manufacture a false "this object moved across the board".

Objects are `_Objects`' objects: 4-connected same-colour components over the state-local
background. That convention is inherited so an entity id and a `cN` term in the predicate
grammar cannot disagree about what an object is.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_candidates import _Objects  # noqa: E402

MAX_CHILDREN = 6  # (w) listed per entity; the rest are counted
MAX_ADJACENT = 8  # (w) same


@dataclass
class Entity:
    eid: int
    colour: int
    cells: frozenset
    bbox: tuple[int, int, int, int]
    shape_key: str
    area: int
    children: list[int] = field(default_factory=list)
    adjacent: list[int] = field(default_factory=list)
    status: str = "unknown"

    @property
    def height(self) -> int:
        return self.bbox[2] - self.bbox[0] + 1

    @property
    def width(self) -> int:
        return self.bbox[3] - self.bbox[1] + 1

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)


def normalized_shape(cells: Iterable[tuple[int, int]]) -> tuple:
    """The cell set up to translation — exactly what the grammar's `same_shape` compares."""
    cells = list(cells)
    top = min(row for row, _ in cells)
    left = min(col for _, col in cells)
    return tuple(sorted((row - top, col - left) for row, col in cells))


class Tracker:
    """Assigns stable entity ids across a sequence of frames from one episode.

    Shape keys are global to the tracker, so `s3` means the same shape in every frame it
    appears in — which is what makes "the same shape as entity 7, elsewhere" a readable
    statement rather than a per-frame coincidence.
    """

    def __init__(self) -> None:
        self._shapes: dict[tuple, str] = {}
        self._next_eid = 1
        self._previous: list[Entity] = []

    def shape_key(self, cells: Iterable[tuple[int, int]]) -> str:
        shape = normalized_shape(cells)
        if shape not in self._shapes:
            self._shapes[shape] = f"s{len(self._shapes) + 1}"
        return self._shapes[shape]

    def observe(self, grid: Sequence[Sequence[int]]) -> list[Entity]:
        objects = _Objects(grid)
        raw: list[dict[str, Any]] = []
        for colour, members in objects.by_colour.items():
            for member in members:
                raw.append({"colour": int(colour), "cells": member["cells"], "bbox": member["bbox"]})
        raw.sort(key=lambda item: (item["bbox"][0], item["bbox"][1], item["colour"]))

        entities = [
            Entity(
                eid=-1,
                colour=item["colour"],
                cells=item["cells"],
                bbox=tuple(item["bbox"]),
                shape_key=self.shape_key(item["cells"]),
                area=len(item["cells"]),
            )
            for item in raw
        ]
        self._assign_ids(entities)
        _relate(entities)
        self._previous = entities
        return entities

    def _assign_ids(self, entities: list[Entity]) -> None:
        """Greedy best-first matching against the previous frame. Same colour, always.

        Exact cell-set equality is taken first and unconditionally: an object that did not
        move is the same object, and letting a scored match outrank that could swap two
        identical shapes for each other across a frame in which neither did anything.
        """
        available = list(self._previous)
        taken: set[int] = set()
        by_cells = {entity.cells: entity for entity in available}
        pending: list[Entity] = []
        for entity in entities:
            match = by_cells.get(entity.cells)
            if match is not None and match.colour == entity.colour and id(match) not in taken:
                entity.eid = match.eid
                taken.add(id(match))
            else:
                pending.append(entity)

        scored: list[tuple[float, int, Entity, Entity]] = []
        for index, entity in enumerate(pending):
            for candidate in available:
                if candidate.colour != entity.colour or id(candidate) in taken:
                    continue
                distance = abs(entity.centre[0] - candidate.centre[0]) + abs(
                    entity.centre[1] - candidate.centre[1]
                )
                area_ratio = min(entity.area, candidate.area) / max(entity.area, candidate.area)
                # Identical shape dominates: a translated copy of the same cell set is the
                # single most reliable signal a grid game offers. Then area, then distance.
                score = (
                    (0.0 if entity.shape_key == candidate.shape_key else 1.0)
                    + (1.0 - area_ratio)
                    + distance / 128.0
                )
                scored.append((score, index, entity, candidate))
        scored.sort(key=lambda row: (row[0], row[1]))
        for score, _, entity, candidate in scored:
            if entity.eid != -1 or id(candidate) in taken:
                continue
            # A match worse than "different shape and half the area" is not a match. An id
            # forced onto an unrelated component is worse than a new id: it would assert a
            # movement or a reshape that nothing observed.
            if score >= 2.0:
                continue
            entity.eid = candidate.eid
            taken.add(id(candidate))
        for entity in entities:
            if entity.eid == -1:
                entity.eid = self._next_eid
                self._next_eid += 1


def _relate(entities: list[Entity]) -> None:
    """Containment and adjacency, in the grammar's own terms.

    Containment is BOUNDING-BOX containment, not cell enclosure, because `bbox_contains` is
    what the predicate grammar has. A containment relation the model can see but cannot write
    would be worse than none.
    """
    owner: dict[tuple[int, int], int] = {}
    for index, entity in enumerate(entities):
        for cell in entity.cells:
            owner[cell] = index
    for index, entity in enumerate(entities):
        neighbours: set[int] = set()
        for row, col in entity.cells:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                other = owner.get((row + dr, col + dc))
                if other is not None and other != index:
                    neighbours.add(entities[other].eid)
        entity.adjacent = sorted(neighbours)
        top, left, bottom, right = entity.bbox
        children = []
        for other_index, other in enumerate(entities):
            if other_index == index:
                continue
            otop, oleft, obottom, oright = other.bbox
            if top <= otop and left <= oleft and obottom <= bottom and oright <= right:
                if (obottom - otop, oright - oleft) != (bottom - top, right - left):
                    children.append(other.eid)
        entity.children = sorted(children)


def annotate(entities: list[Entity], changed: set[tuple[int, int]]) -> dict[str, Any]:
    """Set each entity's status from the cells the whole store ever changed.

      inert    not one of its cells ever changed anywhere in this run. This is the column
               that replaces slice 3's dropped second full board render — and the thing both
               reference discoveries read as a specification.
      touched  at least one of its cells changed at some point.
      hud?     touched, and lying entirely outside the play field — the bounding box of the
               largest never-changing structure on the board. A HEURISTIC, labelled as one
               wherever it is printed: it is how a status bar or a counter usually sits
               relative to the board, not a measurement of what the thing is.

    "Inert" is a fact about THIS run, not about the game. The prompt says so where it counts:
    one autonomous exploration never tried most of what there is to try.
    """
    for entity in entities:
        entity.status = "inert" if not (entity.cells & changed) else "touched"
    static = [entity for entity in entities if entity.status == "inert"]
    field_box = None
    if static:
        largest = max(static, key=lambda entity: entity.area)
        field_box = largest.bbox
        top, left, bottom, right = field_box
        for entity in entities:
            if entity.status != "touched":
                continue
            etop, eleft, ebottom, eright = entity.bbox
            outside = ebottom < top or etop > bottom or eright < left or eleft > right
            if outside:
                entity.status = "hud?"
    return {
        "entities": len(entities),
        "inert": sum(1 for entity in entities if entity.status == "inert"),
        "touched": sum(1 for entity in entities if entity.status == "touched"),
        "hud_suspected": sum(1 for entity in entities if entity.status == "hud?"),
        "play_field_bbox": list(field_box) if field_box else None,
    }


def entity_of(entities: list[Entity], row: int, col: int) -> Entity | None:
    for entity in entities:
        if (row, col) in entity.cells:
            return entity
    return None


def entities_touching(entities: list[Entity], cells: Iterable[tuple[int, int]]) -> list[int]:
    wanted = set(cells)
    return sorted(
        {entity.eid for entity in entities if entity.cells & wanted}
    )
