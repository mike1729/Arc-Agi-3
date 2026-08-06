#!/usr/bin/env python3
"""Is the answer we demanded even sayable in the language we demanded it in?

Slice-3 readout, `notes/e2-slice3.md` → RUN RESULTS. Zero model calls.

WHY THIS EXISTS
---------------
Slice 3 graded Qwen 0/16 on goal predicates and the readout then read all eight games'
completion conditions out of the source. Three of them cannot be written in the predicate
grammar at all — ft09's is a per-tile 8-neighbour constraint satisfaction, vc33's a
cross-class relational match, sp80's a containment property of a spreading region — and a
fourth, dc22, is only approximable, which is exactly why seed 2's structurally correct
answer was falsified on 3 of 2,939 transitions.

That adjudication was a human reading source under a rubric. This module makes it a
machine-checked result: enumerate the grammar and ask whether ANY predicate in it separates
the boards humans actually solved from the boards they did not. If none does, the game was
unwinnable by construction and a model scored zero on it was scored against nothing. If one
does, it is the grading target — and the distance from the model's answer to it is the real
measurement, in place of a binary against perfection.

WHAT A SEPARATOR IS
-------------------
A predicate that evaluates definite-TRUE at every captured completion board and
definite-FALSE at every non-completing transition of the same game and level, in the human
corpus (`e2_positives`). `unknown` is not a pass: a predicate whose colour is the state's
background is unevaluable there, and a candidate that is unknown at a completion has not
separated it. Both directions are required — the negative direction alone is what every
earlier slice measured, and it accepts any predicate that is nearly never true.

This is a claim about ONE LEVEL of ONE GAME against the human corpus. It is not a claim
that no goal language could express the condition, only that this one cannot, which is the
question that bears on the grading.

THE ENUMERATION, AND WHY IT IS TRACTABLE
----------------------------------------
Single clauses over the colours that actually occur: cardinalities, temporal events, count
comparisons, and the quantified forms over every relation and both argument orders. A few
thousand per game. Conjunctions are NOT enumerated blindly — a conjunct of a predicate true
at every positive must itself be true at every positive, so pairs are drawn only from the
clauses that survived the positive direction. That is a version-space bound, not a sample,
and it is exhaustive over the two-clause grammar.

v1 VERSUS v2
------------
Every game is run twice: once over the relation vocabulary as it stood when slices 2 and 3
were graded, and once over the vocabulary `e2_dsl` was extended to on 2026-08-06. The
difference is the measured value of the extension, per game, and it is reported rather than
claimed.

Run:
  .venv/bin/python agent/harness/e2_expressibility.py
  .venv/bin/python agent/harness/e2_expressibility.py --games dc22 --level 1 --vocab v2
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
import e2_positives as pos  # noqa: E402

ROOT = pos.ROOT
OUTPUT = ROOT / "logs/e2_expressibility.json"
FORMAT_VERSION = 1

# The relation vocabulary as slices 2 and 3 were graded, so the extension's value is
# measured against what was actually in force rather than against an idealization.
V1_RELATIONS = ("adjacent", "bbox_overlap", "bbox_contains", "row_aligned", "col_aligned", "same_shape")
V1_QUANTIFIERS = ("exists", "all")

# `count(cN) = k` is enumerated up to the largest component count any frame of the game
# actually shows, capped — beyond that the clause is unsatisfiable and enumerating it is
# pure cost.
MAX_COUNT = 40


def _colours(rows: list) -> list[int]:
    """Colours that appear as non-background components anywhere in these rows."""
    seen: set[int] = set()
    for row in rows:
        for grid in (row.pre, row.post):
            objects = dsl._Objects(grid)
            seen.update(objects.by_colour)
    return sorted(seen)


def _max_count(rows: list, colours: list[int]) -> int:
    top = 0
    for row in rows:
        objects = dsl._Objects(row.post)
        for colour in colours:
            members = objects.members(colour)
            if members:
                top = max(top, len(members))
    return min(top, MAX_COUNT)


def clauses(colours: list[int], top: int, *, vocab: str) -> list[dict[str, Any]]:
    """Every single clause of the grammar over these colours. Deduplicated by canonical form."""
    relations = V1_RELATIONS if vocab == "v1" else dsl.RELATIONS
    quantifiers = V1_QUANTIFIERS if vocab == "v1" else dsl.OUTER_QUANTIFIERS
    out: dict[str, dict[str, Any]] = {}

    def add(node: dict[str, Any]) -> None:
        out.setdefault(dsl.canonical(node), node)

    for colour in colours:
        term = {"op": "colour_components", "colour": colour}
        for form in dsl.CARDINALITY:
            add({"op": form, "set": dict(term)})
        for event in dsl.TEMPORAL:
            add({"op": "temporal", "event": event, "set": dict(term)})
        for k in range(top + 1):
            add({"op": "count_cmp", "cmp": "=", "left": dict(term), "right": k})
            if k:
                add({"op": "count_cmp", "cmp": ">=", "left": dict(term), "right": k})
    for left, right in itertools.combinations(colours, 2):
        add(
            {
                "op": "count_cmp",
                "cmp": "=",
                "left": {"op": "colour_components", "colour": left},
                "right": {"op": "colour_components", "colour": right},
            }
        )

    for outer in quantifiers:
        for a in colours:
            for b in colours:
                for relation in relations:
                    orders = (("x", "y"),) if relation in dsl.SYMMETRIC else (("x", "y"), ("y", "x"))
                    for args in orders:
                        add(
                            {
                                "op": outer,
                                "var": "x",
                                "in": {"op": "colour_components", "colour": a},
                                "satisfies": {
                                    "op": "exists",
                                    "var": "y",
                                    "in": {"op": "colour_components", "colour": b},
                                    "satisfies": {
                                        "op": "relation",
                                        "name": relation,
                                        "args": [{"op": "var", "name": n} for n in args],
                                    },
                                },
                            }
                        )
    return list(out.values())


def _values(node: dict[str, Any], contexts: list) -> list[str]:
    return [dsl.evaluate(node, context) for context in contexts]


def search(game: str, *, level: int = 1, vocab: str = "v2") -> dict[str, Any]:
    started = time.time()
    positives = pos.positives(game, level=level)
    negatives = pos.negatives(game, level=level)
    if not positives:
        return {
            "game": game,
            "level": level,
            "vocab": vocab,
            "searched": False,
            "reason": "no completion in the human corpus at this level",
        }

    pos_ctx = dsl.transition_contexts(positives)
    neg_ctx = dsl.transition_contexts(negatives)
    colours = _colours(positives + negatives)
    candidates = clauses(colours, _max_count(positives + negatives, colours), vocab=vocab)

    # Stage 1 — the positive direction. A separator, and every conjunct of one, must be
    # definite-TRUE at every completion. This is the cut that makes stage 2 affordable.
    survivors: list[tuple[str, dict[str, Any]]] = []
    for node in candidates:
        if all(value == dsl.TRUE for value in _values(node, pos_ctx)):
            survivors.append((dsl.canonical(node), node))

    # Stage 2 — the negative direction, on the survivors only.
    separators: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for text, node in survivors:
        values = _values(node, neg_ctx)
        wrong = sum(1 for value in values if value == dsl.TRUE)
        unknown = sum(1 for value in values if value == dsl.UNKNOWN)
        decidable = len(values) - unknown
        row = {
            "predicate": text,
            "skeleton": dsl.skeleton(node),
            "clauses": 1,
            "false_positives": wrong,
            "negatives_decidable": decidable,
            "negatives_unknown": unknown,
            "contradiction_rate": None if not decidable else round(wrong / decidable, 6),
        }
        if wrong == 0 and decidable:
            separators.append(row)
        elif best is None or (row["contradiction_rate"] or 1.0) < (best["contradiction_rate"] or 1.0):
            best = row

    # Stage 3 — two-clause conjunctions, drawn only from stage-1 survivors. Exhaustive over
    # the two-clause grammar because a conjunct of an all-positive predicate is all-positive.
    pair_separators: list[dict[str, Any]] = []
    if not separators and len(survivors) > 1:
        neg_true: dict[str, set[int]] = {}
        for text, node in survivors:
            values = _values(node, neg_ctx)
            neg_true[text] = {i for i, value in enumerate(values) if value == dsl.TRUE}
        for (left_text, left), (right_text, right) in itertools.combinations(survivors, 2):
            overlap = neg_true[left_text] & neg_true[right_text]
            node = {"op": "and", "args": [left, right]}
            row = {
                "predicate": dsl.canonical(node),
                "skeleton": dsl.skeleton(node),
                "clauses": 2,
                "false_positives": len(overlap),
                "negatives_decidable": len(negatives),
                "negatives_unknown": None,
                "contradiction_rate": round(len(overlap) / len(negatives), 6)
                if negatives
                else None,
            }
            if not overlap:
                pair_separators.append(row)
                if len(pair_separators) >= 200:
                    break
            # A two-clause near miss can beat every single clause, so the closest miss is
            # tracked across both tiers rather than reported from the single-clause tier
            # and quietly contradicted by the conjunctions.
            elif best is None or (row["contradiction_rate"] or 1.0) < (
                best["contradiction_rate"] or 1.0
            ):
                best = row

    found = separators + pair_separators
    found.sort(key=lambda row: (row["clauses"], len(row["predicate"])))
    return {
        "game": game,
        "level": level,
        "vocab": vocab,
        "searched": True,
        "positives": len(positives),
        "negatives": len(negatives),
        "colours": colours,
        "candidates": len(candidates),
        "true_at_every_completion": len(survivors),
        "separators": len(found),
        "expressible": bool(found),
        # The grading target: the simplest predicate that actually separates. When there is
        # none, the closest miss, so the readout can say how far the language got rather
        # than only that it did not arrive.
        "simplest": found[0] if found else None,
        "examples": found[:8],
        "closest_miss": None if found else best,
        "seconds": round(time.time() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(pos.GAMES))
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--vocab", nargs="*", default=["v1", "v2"], choices=["v1", "v2"])
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    rows = []
    for game in args.games:
        for vocab in args.vocab:
            row = search(game, level=args.level, vocab=vocab)
            rows.append(row)
            if not row["searched"]:
                print(f"{game:5s} {vocab}: not searched — {row['reason']}", flush=True)
                continue
            verdict = "EXPRESSIBLE" if row["expressible"] else "inexpressible"
            print(
                f"{game:5s} {vocab}: {verdict:14s} "
                f"{row['candidates']:5d} candidates, {row['true_at_every_completion']:4d} "
                f"true at every completion, {row['separators']:3d} separators "
                f"({row['positives']}+ / {row['negatives']}-, {row['seconds']}s)",
                flush=True,
            )
            if row["simplest"]:
                print(f"        simplest: {row['simplest']['predicate']}", flush=True)
            elif row["closest_miss"]:
                miss = row["closest_miss"]
                print(
                    f"        closest:  {miss['predicate']} "
                    f"({miss['false_positives']}/{miss['negatives_decidable']} false positives)",
                    flush=True,
                )

    args.out.write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "generated_by": "agent/harness/e2_expressibility.py",
                "note": "notes/e2-slice3.md RUN RESULTS — is the goal sayable in the goal grammar",
                "level": args.level,
                "results": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
