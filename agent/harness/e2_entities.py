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
matcher, not an observation. So the matcher only makes the claim where the evidence is
EXACT: an identical cell set, or an identical normalized shape in the same colour (a rigid
translation, whose vector the lineage line reports). Everything else — a reshape, a split, a
merge, a recolour, an unrelated same-colour object drifting past — gets a FRESH id, and the
lineage line names the plausible partner while explicitly declining to assert it.

An earlier version scored area and proximity and kept an id across a change of shape. The
prompt meanwhile told the model that an id denotes the same entity, so that matcher could
hand the model invented continuity in the one place the record exists to be conservative.
Fresh ids are the safe direction: two ids may name one thing, but one id never silently
names two.

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
    # how this entity's id was obtained: `exact` (identical cells), `translated` (identical
    # shape, moved), `new` (no exact match — a fresh id, never a scored guess), or `first`
    # for the frame that started the tracker.
    match: str = "first"

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
        # what happened between the last two observed frames, in the model's own vocabulary
        self.lineage: list[str] = []

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
        lineage, gone = self._assign_ids(entities)
        _relate(entities)
        self._previous = entities
        self.lineage = lineage + gone
        return entities

    def _assign_ids(self, entities: list[Entity]) -> tuple[list[str], list[str]]:
        """Match against the previous frame, and KEEP AN ID ONLY WHEN THE EVIDENCE IS EXACT.

        An id is a claim that two components in two frames are the same thing. The earlier
        version of this matcher would keep an id across a CHANGE OF SHAPE on the strength of
        area and proximity, while the prompt told the model an id denotes the same entity —
        so a reshape, a split or an unrelated same-colour object drifting past could all be
        presented to the model as continuity. That is invented evidence, in the one place the
        record is supposed to be conservative.

        Two tiers keep an id, and both are exact:

          exact       identical cell set. It did not move; it is the same thing.
          translated  identical NORMALIZED SHAPE and the same colour, matched nearest-first.
                      A rigid translation of the same cell set is the strongest signal a grid
                      game offers, and the lineage line reports the vector.

        Anything else gets a FRESH id. Where a plausible partner exists — same colour, at
        least half the area, nearby — the lineage line SAYS SO and explicitly does not assert
        it. Returns `(lineage, unmatched)`: the events to print, and the ids that vanished.
        """
        available = list(self._previous)
        taken: set[int] = set()
        lineage: list[str] = []

        by_cells: dict[frozenset, Entity] = {}
        for entity in available:
            by_cells.setdefault(entity.cells, entity)
        pending: list[Entity] = []
        for entity in entities:
            match = by_cells.get(entity.cells)
            if match is not None and match.colour == entity.colour and id(match) not in taken:
                entity.eid = match.eid
                entity.match = "exact"
                taken.add(id(match))
            else:
                pending.append(entity)

        # tier 2: same colour AND same normalized shape, nearest first
        candidates: list[tuple[float, int, Entity, Entity]] = []
        for index, entity in enumerate(pending):
            for candidate in available:
                if (
                    candidate.colour != entity.colour
                    or candidate.shape_key != entity.shape_key
                    or id(candidate) in taken
                ):
                    continue
                distance = abs(entity.centre[0] - candidate.centre[0]) + abs(
                    entity.centre[1] - candidate.centre[1]
                )
                candidates.append((distance, index, entity, candidate))
        candidates.sort(key=lambda row: (row[0], row[1]))
        for distance, _, entity, candidate in candidates:
            if entity.eid != -1 or id(candidate) in taken:
                continue
            entity.eid = candidate.eid
            entity.match = "translated"
            taken.add(id(candidate))
            dr = entity.bbox[0] - candidate.bbox[0]
            dc = entity.bbox[1] - candidate.bbox[1]
            lineage.append(f"#{entity.eid} moved by ({dr:+d},{dc:+d}), same shape")

        leftovers = [entity for entity in available if id(entity) not in taken]
        for entity in entities:
            if entity.eid != -1:
                continue
            entity.eid = self._next_eid
            entity.match = "new"
            self._next_eid += 1
            partner = None
            for other in leftovers:
                if other.colour != entity.colour:
                    continue
                ratio = min(entity.area, other.area) / max(entity.area, other.area)
                distance = abs(entity.centre[0] - other.centre[0]) + abs(
                    entity.centre[1] - other.centre[1]
                )
                if ratio >= 0.5 and distance <= 8:
                    partner = other
                    break
            if partner is not None:
                lineage.append(
                    f"#{partner.eid} is gone and #{entity.eid} is new — same colour c"
                    f"{entity.colour}, {partner.area} cells then {entity.area} now, nearby. "
                    f"POSSIBLY the same thing changing shape; NOT asserted, which is why it "
                    f"has a new id"
                )
            else:
                lineage.append(f"#{entity.eid} is new — c{entity.colour}, {entity.area} cells")
        gone = [
            f"#{entity.eid} is gone (c{entity.colour}, {entity.area} cells)"
            for entity in leftovers
            if not any(
                line.startswith(f"#{entity.eid} is gone and ") for line in lineage
            )
        ]
        return lineage, gone


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
