#!/usr/bin/env python3
"""E2 slice-2 control — the prior library: five stock goal shapes, instantiated mechanically.

`notes/e2-slice2.md` §A and `notes/e2-slice2-build.md` sub-task 2. Zero model calls.

WHAT THIS IS THE CONTROL FOR
----------------------------
Channel A asks Qwen for a falsifiable completion-condition predicate. The corrected S1
end-to-end read (`aca2d47`, `notes/s1-clear-vs-stall.md` §1) found that the reference's wins
are dominated by a small set of DEFAULT GOAL SHAPES it brings to every game — the prior
fires on 21 of 42 reference wins, 50%. So a correct predicate is worth nothing on its own:
the channel is alive only where the model is right AND this library is not. This file is the
"no capability" hypothesis, hardcoded.

The five shapes, verbatim from that read: avatar -> salient target · every X into/onto its Y ·
clear/collect all X · copy the displayed template · align the two matching objects.

BUILT BLIND — the methodological hard rule
------------------------------------------
Census and store only. No game source is opened here, by this module or by anything it
imports, and no adjudication of any candidate happens at build time. Source adjudication of
the library — and of channel A — happens at slice-2 SCORING time, against the same rubric,
by the same reader, in one pass. A control that had been tuned against the answers would make
the comparison meaningless in the direction that flatters us.

Bindings are enumerated MECHANICALLY: for each shape, every concrete instantiation its
census preconditions admit (each movable class × each salient static, each colour for
clear-all, each shape-matched pair, ...), written in the task-1 DSL so that scoring is
symmetric with channel A's. A shape with no admissible binding on a game yields NONE — that
is recorded, never padded with something almost-applicable.

THE CONSISTENCY FILTER, AND WHAT IT CANNOT DO HERE
--------------------------------------------------
Surviving candidates are those consistent with every store transition under row-C's own
three-valued rule (`unknown` neither eliminates nor confirms; definite-and-wrong kills).
The note also asks for the own-completion positive check "where one exists — sp80 and lf52
have one". MEASURED: both completions exist in the v2 store and neither is evaluable — the
explorer hashes the level-advance frame but never adds it to `states.json`, so the completion
row's POST frame is absent and `e2_dose.load_store` substitutes the pre frame as a
placeholder. Evaluating a positive against a fabricated post frame would manufacture the
library's only positive evidence out of nothing. So the check is implemented, applied where
a real post frame exists, and reports `positives_evaluable: 0` on every one of the 8 games
with the reason attached. Slice 2's channel A scoring inherits the same limitation and
should say so rather than quietly dropping clause 1 of its own rubric.

Run:
  .venv/bin/python agent/harness/e2_prior_library.py
  .venv/bin/python agent/harness/e2_prior_library.py --render ft09 m0r0 vc33
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
from e2_dose import load_store  # noqa: E402
from es_candidates import _Objects  # noqa: E402

from rs_transitions import ROOT, Transition  # noqa: E402

OUTPUT = ROOT / "logs/e2_prior_library.json"
FORMAT_VERSION = 1

# The slice-2 protocol set: the six iteration games plus the two E1-completed games.
SLICE2_GAMES = dsl.SLICE2_GAMES

SHAPES = (
    "avatar_to_salient_target",
    "every_x_into_its_y",
    "clear_all_x",
    "copy_the_template",
    "align_two_matching",
)


# ======================================================================================
# Census — the object catalogue, from the store alone
# ======================================================================================


def _normalized_shape(cells: frozenset) -> tuple:
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    top, left = min(rows), min(cols)
    return tuple(sorted((row - top, col - left) for row, col in cells))


def object_census(store: list[Transition]) -> dict[str, Any]:
    """Object catalogue over the whole store, plus the origin frame's own inventory.

    Two different things, deliberately kept apart:

      * the ORIGIN inventory (colours, per-colour object counts, shapes, positions) comes
        from the store's first pre-frame — the same single grid row C enumerates its term
        universe from, so the prior library and the row-C universe cannot end up quantifying
        over different terms;
      * MOBILITY comes from every effect signature in the store. A colour is inert when it
        appears in no effect event anywhere: never moved, never reshaped, never appeared,
        never disappeared. On the recolour convention (`rs_transitions`) a recolour is
        disappear+appear, so a recoloured object is not inert — which is the reading that
        makes "inert" mean "the game never touches it".

    `max_count` is over every pre-frame, not just the origin: a colour that is unique at the
    origin and duplicated later is not a unique-object term, and treating it as one is how a
    relational binding silently stops denoting anything.
    """
    if not store:
        return {"empty": True}

    origin = _Objects(store[0].pre)
    origin_objects: dict[int, list[dict[str, Any]]] = {}
    for colour, members in origin.by_colour.items():
        origin_objects[colour] = [
            {
                "cells": len(member["cells"]),
                "bbox": list(member["bbox"]),
                "shape": _normalized_shape(member["cells"]),
            }
            for member in sorted(members, key=lambda m: m["bbox"])
        ]

    counts_seen: dict[int, Counter] = {}
    frames_seen = 0
    seen_digests: set[int] = set()
    for transition in store:
        marker = id(transition.pre)
        if marker in seen_digests:
            continue
        seen_digests.add(marker)
        frames_seen += 1
        objects = _Objects(transition.pre)
        for colour, members in objects.by_colour.items():
            counts_seen.setdefault(colour, Counter())[len(members)] += 1

    touched: dict[int, Counter] = {}
    for transition in store:
        for event in transition.effect:
            colour = int(event[1])
            touched.setdefault(colour, Counter())[event[0]] += 1

    colours: dict[str, Any] = {}
    for colour in sorted(set(counts_seen) | set(origin.by_colour) | set(touched)):
        seen = counts_seen.get(colour, Counter())
        events = touched.get(colour, Counter())
        colours[str(colour)] = {
            "at_origin": len(origin_objects.get(colour, [])),
            "max_count": max(seen) if seen else 0,
            "min_count": min(seen) if seen else 0,
            "frames_present": sum(seen.values()),
            "unique_everywhere": bool(seen) and set(seen) == {1},
            "events": dict(events),
            "moved": bool(events.get("move")),
            "reshaped": bool(events.get("reshape")),
            "appeared": bool(events.get("appear")),
            "disappeared": bool(events.get("disappear")),
            "inert": not events,
        }

    return {
        "empty": False,
        "background_at_origin": origin.background,
        "origin_step": store[0].step,
        "pre_frames_scanned": frames_seen,
        "store_transitions": len(store),
        "colours": colours,
        "origin_objects": {
            str(colour): [
                {"cells": o["cells"], "bbox": o["bbox"]} for o in members
            ]
            for colour, members in sorted(origin_objects.items())
        },
        "_origin_shapes": {
            colour: [o["shape"] for o in members]
            for colour, members in origin_objects.items()
        },
    }


def inert_inventory(census: dict[str, Any]) -> list[dict[str, Any]]:
    """Objects that appear in NO effect signature anywhere in the store.

    Channel A's primary seed, and the thing the digest structurally hides: every other
    section of the digest is organized by what CHANGED, so an object that never changes is
    invisible in it — while both reference discoveries read a static object as a
    specification (sb26 from layout alone at analysis step 1; ft09's encoding hypothesis at
    step 5). Position and shape come from the origin frame; an inert object has none other.
    """
    if census.get("empty"):
        return []
    out: list[dict[str, Any]] = []
    for colour, row in sorted(census["colours"].items(), key=lambda item: int(item[0])):
        if not row["inert"] or not row["at_origin"]:
            continue
        for member in census["origin_objects"][colour]:
            top, left, bottom, right = member["bbox"]
            out.append(
                {
                    "colour": int(colour),
                    "cells": member["cells"],
                    "bbox": [top, left, bottom, right],
                    "height": bottom - top + 1,
                    "width": right - left + 1,
                    "objects_of_this_colour": row["at_origin"],
                }
            )
    return out


# ======================================================================================
# The five shapes -> concrete bindings, in the task-1 DSL
# ======================================================================================


def _colours(census: dict[str, Any]) -> list[int]:
    """Terms available at the origin — row C's own term inventory rule."""
    return sorted(
        int(colour)
        for colour, row in census["colours"].items()
        if row["at_origin"] > 0
    )


def _bindings(census: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Every shape's admissible instantiations. Preconditions are census facts only."""
    rows = census["colours"]
    shapes_at_origin = census["_origin_shapes"]
    present = _colours(census)

    def row(colour: int) -> dict[str, Any]:
        return rows[str(colour)]

    # An "avatar" is, to the census, a UNIQUE object that the game changes: exactly one
    # component in every frame it appears in, and present in at least one effect signature.
    #
    # Not `moved`. MEASURED on the two largest stores: no colour in m0r0 or dc22 records a
    # single `move` event, because `rs_transitions`' lineage rule matches a pre-component to a
    # post-component only when their CELL SETS INTERSECT. An object that steps far enough not
    # to overlap itself is recorded as disappear+appear, so `moved` selects only objects that
    # shuffle within their own footprint — the opposite of an avatar. Requiring it emptied
    # this shape on both games, which would have handed channel A a free win on the one prior
    # shape the S1 read found firing most often.
    movable_unique = [
        c for c in present if not row(c)["inert"] and row(c)["max_count"] == 1
    ]
    inert = [c for c in present if row(c)["inert"]]
    consumable = [c for c in present if row(c)["disappeared"]]
    # a "salient target" the avatar can reach: something that never moves on its own, i.e.
    # either wholly inert or only ever consumed
    targets = sorted(set(inert) | set(consumable))
    multi_at_origin = [c for c in present if row(c)["at_origin"] >= 2]

    shape_matched: list[tuple[int, int]] = []
    for i, first in enumerate(present):
        for second in present[i + 1 :]:
            if set(shapes_at_origin.get(first, [])) & set(shapes_at_origin.get(second, [])):
                shape_matched.append((first, second))

    out: dict[str, list[dict[str, Any]]] = {shape: [] for shape in SHAPES}

    # 1. avatar -> salient target. Two readings of "reaches", because a composited grid
    #    renders standing-on either as adjacency or as an overlapping bounding box and the
    #    census cannot say which this game uses. Both are enumerated; neither is chosen.
    for avatar in movable_unique:
        for target in targets:
            if target == avatar:
                continue
            for relation in ("adjacent", "bbox_overlap"):
                out["avatar_to_salient_target"].append(
                    {
                        "dsl": f"exists x in c{avatar}: exists y in c{target}: "
                        f"{relation}(x, y)",
                        "binding": {"avatar": avatar, "target": target, "relation": relation},
                    }
                )

    # 2. every X into/onto its Y. Enumerated over ORDERED colour pairs: "every X" fixes the
    #    quantified set, and X-into-Y is not Y-into-X.
    for x_colour in present:
        for y_colour in present:
            if x_colour == y_colour:
                continue
            out["every_x_into_its_y"].extend(
                [
                    {
                        "dsl": f"all x in c{x_colour}: exists y in c{y_colour}: "
                        f"bbox_overlap(x, y)",
                        "binding": {"x": x_colour, "y": y_colour, "relation": "bbox_overlap"},
                    },
                    {
                        "dsl": f"all x in c{x_colour}: exists y in c{y_colour}: "
                        f"adjacent(x, y)",
                        "binding": {"x": x_colour, "y": y_colour, "relation": "adjacent"},
                    },
                    {
                        "dsl": f"all x in c{x_colour}: exists y in c{y_colour}: "
                        f"bbox_contains(y, x)",
                        "binding": {"x": x_colour, "y": y_colour, "relation": "contained_in"},
                    },
                ]
            )

    # 3. clear / collect all X.
    for colour in present:
        out["clear_all_x"].append(
            {"dsl": f"empty(c{colour})", "binding": {"cleared": colour}}
        )

    # 4. copy the displayed template. The template is a static object — that is what makes it
    #    "displayed" rather than played — and the copy is any other colour class.
    for template in inert:
        for edited in present:
            if edited == template:
                continue
            out["copy_the_template"].extend(
                [
                    {
                        "dsl": f"all x in c{edited}: exists y in c{template}: same_shape(x, y)",
                        "binding": {"edited": edited, "template": template, "reading": "all"},
                    },
                    {
                        "dsl": f"exists x in c{edited}: exists y in c{template}: "
                        f"same_shape(x, y)",
                        "binding": {"edited": edited, "template": template, "reading": "exists"},
                    },
                    {
                        "dsl": f"count(c{edited}) = count(c{template})",
                        "binding": {"edited": edited, "template": template, "reading": "count"},
                    },
                ]
            )

    # 5. align the two matching objects. Two matching objects of DIFFERENT colours align in
    #    the row/column sense; two of the SAME colour cannot be distinguished by any relation
    #    over one term (`R(x, x)` is satisfied reflexively), so the census reading of "they
    #    are now aligned" for a same-colour pair is that they became one 4-connected
    #    component — which is what `exactly_one` says, and it is a real observable.
    for first, second in shape_matched:
        for relation in ("row_aligned", "col_aligned", "bbox_overlap"):
            out["align_two_matching"].append(
                {
                    "dsl": f"exists x in c{first}: exists y in c{second}: {relation}(x, y)",
                    "binding": {"a": first, "b": second, "relation": relation},
                }
            )
    for colour in multi_at_origin:
        out["align_two_matching"].append(
            {
                "dsl": f"exactly_one(c{colour})",
                "binding": {"merged": colour, "objects_at_origin": rows[str(colour)]["at_origin"]},
            }
        )
    return out


# ======================================================================================
# The consistency filter
# ======================================================================================


def filter_candidates(
    candidates: list[dict[str, Any]],
    store: list[Transition],
    post_missing: set[int],
    contexts: list | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Row-C survivorship over the store, with the positives handled honestly.

    Negative evidence is every store transition with a REAL post frame. A completion row's
    post frame is a placeholder (`e2_dose.load_store`), so it is excluded from the negative
    stream — it is neither a negative nor an evaluable positive, and using the placeholder
    would evaluate the candidate on the pre-state while labelling it a completion.
    """
    usable = [t for t in store if t.step not in post_missing]
    positives = [t for t in usable if t.completed]
    if contexts is None:
        contexts = dsl.transition_contexts(usable)

    kept: list[dict[str, Any]] = []
    outcomes = Counter()
    for candidate in candidates:
        node = dsl.parse_predicate(candidate["dsl"])
        verdict = dsl.consistent_with(node, usable, contexts=contexts)
        outcomes[verdict["outcome"]] += 1
        candidate = {
            **candidate,
            "outcome": verdict["outcome"],
            "definite_correct": verdict["definite_correct"],
            "positives_matched": verdict["positives_matched"],
        }
        if verdict["outcome"] == "falsified":
            continue
        if positives and verdict["positives_matched"] == 0:
            candidate["outcome"] = "misses_own_completion"
            outcomes["misses_own_completion"] += 1
            continue
        kept.append(candidate)
    report = {
        "negative_transitions": len(usable),
        "positives_evaluable": len(positives),
        "positives_in_store_without_post_frame": sum(
            1 for t in store if t.completed and t.step in post_missing
        ),
        "outcomes": dict(outcomes),
    }
    return kept, report


# ======================================================================================
# Per game
# ======================================================================================


def run_game(game: str) -> dict[str, Any]:
    store, post_missing = load_store(game)
    census = object_census(store)
    if census.get("empty"):
        return {"game": game, "skipped": "empty store"}

    proposed = _bindings(census)
    per_shape: dict[str, Any] = {}
    seen_canonical: dict[str, str] = {}
    total_before = total_after = 0
    # one componentization pass over the store, shared by every shape and every binding
    usable = [t for t in store if t.step not in post_missing]
    contexts = dsl.transition_contexts(usable)
    for shape in SHAPES:
        candidates = []
        for candidate in proposed[shape]:
            key = dsl.canonical(candidate["dsl"])
            candidates.append({**candidate, "canonical": key})
        kept, report = filter_candidates(candidates, store, post_missing, contexts)
        for candidate in kept:
            seen_canonical.setdefault(candidate["canonical"], shape)
        per_shape[shape] = {
            "bindings_before_filter": len(candidates),
            "bindings_after_filter": len(kept),
            "filter": report,
            "surviving": [
                {
                    "dsl": candidate["dsl"],
                    "binding": candidate["binding"],
                    "definite_correct": candidate["definite_correct"],
                    "positives_matched": candidate["positives_matched"],
                    "outcome": candidate["outcome"],
                }
                for candidate in sorted(kept, key=lambda c: c["canonical"])
            ],
            "falsified_examples": [
                candidate["dsl"]
                for candidate in candidates
                if candidate.get("dsl") not in {k["dsl"] for k in kept}
            ][:5],
        }
        total_before += len(candidates)
        total_after += len(kept)

    return {
        "game": game,
        "store_transitions": len(store),
        "store_completions": sum(1 for t in store if t.completed),
        "census": {
            key: value for key, value in census.items() if not key.startswith("_")
        },
        "inert_inventory": inert_inventory(census),
        "shapes": per_shape,
        "totals": {
            "bindings_before_filter": total_before,
            "bindings_after_filter": total_after,
            "distinct_surviving_predicates": len(seen_canonical),
            # Row C's split, kept rather than collapsed: a `vacuous` candidate is one the
            # store never evaluated definitely anywhere. It is consistent with the evidence
            # and so passes the note's filter, but it is not a claim the evidence supports,
            # and folding it into `survived` would report the grammar's silence as the
            # control's strength.
            "surviving_by_outcome": {
                outcome: sum(
                    1
                    for shape in SHAPES
                    for candidate in per_shape[shape]["surviving"]
                    if candidate["outcome"] == outcome
                )
                for outcome in ("survived", "vacuous")
            },
            "shapes_with_no_binding": [
                shape
                for shape in SHAPES
                if per_shape[shape]["bindings_before_filter"] == 0
            ],
            "shapes_with_no_survivor": [
                shape
                for shape in SHAPES
                if per_shape[shape]["bindings_after_filter"] == 0
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(SLICE2_GAMES))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument(
        "--render", nargs="*", default=None, help="print surviving candidates for these games"
    )
    args = parser.parse_args()

    rows = []
    for game in args.games:
        row = run_game(game)
        rows.append(row)
        if "skipped" in row:
            print(f"{game:5s} skipped: {row['skipped']}", flush=True)
            continue
        totals = row["totals"]
        print(
            f"{game:5s} store={row['store_transitions']:5d} "
            f"bindings {totals['bindings_before_filter']:4d} -> "
            f"{totals['bindings_after_filter']:4d} "
            f"({totals['distinct_surviving_predicates']} distinct; "
            f"{totals['surviving_by_outcome']['survived']} definite, "
            f"{totals['surviving_by_outcome']['vacuous']} vacuous) "
            f"inert_objects={len(row['inert_inventory']):3d} "
            f"no_binding={len(totals['shapes_with_no_binding'])} "
            f"no_survivor={len(totals['shapes_with_no_survivor'])}",
            flush=True,
        )
        for shape in SHAPES:
            cell = row["shapes"][shape]
            print(
                f"        {shape:26s} {cell['bindings_before_filter']:4d} -> "
                f"{cell['bindings_after_filter']:4d}",
                flush=True,
            )

    document = {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/e2_prior_library.py",
        "store": "logs/e1_store_v2",
        "shapes": list(SHAPES),
        "shape_source": (
            "notes/s1-clear-vs-stall.md §1 (corrected S1 end-to-end read, aca2d47): the five "
            "default goal shapes the reference brings, firing on 21 of 42 of its wins"
        ),
        "built_blind": "census + store only; no game source read at build time",
        "games": {row["game"]: row for row in rows},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")

    for game in args.render or []:
        row = document["games"].get(game)
        if row is None or "skipped" in row:
            print(f"\n=== {game}: nothing to render ===")
            continue
        print(f"\n=== {game}: surviving prior-library candidates ===")
        for shape in SHAPES:
            cell = row["shapes"][shape]
            print(f"  {shape} ({cell['bindings_after_filter']} of "
                  f"{cell['bindings_before_filter']}):")
            if not cell["surviving"]:
                print("    none")
            for candidate in cell["surviving"]:
                print(
                    f"    {candidate['dsl']}   "
                    f"[definite-correct on {candidate['definite_correct']} transitions]"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
