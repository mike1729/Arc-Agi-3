#!/usr/bin/env python3
"""E2 retro re-grade — the recorded rule proposals under REPAIR semantics, against a
mechanical tolerance control. Zero model calls (`notes/e2-regrade.md`).

THE CHARGE BEING TESTED
-----------------------
External review: zero-tolerance verification discards near-miss concepts — "right mechanic,
one edge case, whole concept dead". Slices 1 and 1.1 kept a proposal only when it was
contradicted ZERO times on the evidence it was shown, and the rule channel was dropped on
that basis. The charge's one true premise is that a tolerance-graded channel was never run.
Every proposal was recorded, so the question is answerable retroactively at zero model cost.

THE THREE ARMS (all scored the same way: union with the miner's rules, score on the SAME
held-out human L1/L2 targets, delta against the miner-only floor)

  A  TOLERANCE KEEP    the recorded proposal, kept when its contradiction rate
                       contradicted / (support + contradicted) is <= eps.
  B  RE-GUARD CREDIT   credit the CONCEPT, not the string: take the proposal's
                       (action key, guard feature) and let the miner re-fit the best value
                       and effect on the store. Kept when the re-fit beats the proposal's
                       own contradiction rate AND is <= eps. This is the conceptual-prior
                       standard the review asks for — "named the right feature" scores.
  C  THE CONTROL       no model anywhere: per key the miner left UNRESOLVED, mine the single
                       guard with the fewest contradictions and keep its cells at <= eps.
                       If C moves the floors as much as A or B, the value is the TOLERANCE
                       MECHANISM and the miner should simply grow a tolerance tier; the
                       model's proposals get no credit for it.

WHAT IS NOT INVENTED HERE
-------------------------
* The eps sweep is reported WHOLE — {0, 1%, 2%, 5%, 10%} for every arm, every game, both
  vocabularies. Nothing is selected. eps = 0 is not a new threshold: it is the committed
  zero-tolerance rule, carried as the anchor that must reproduce slice 1 exactly.
  The comparison is `<=`, so eps = 0 means "contradicted zero times", verbatim.
* No repair bar is set. If one is ever set it comes out of these measurements.
* v1 is the PRIMARY vocabulary: the proposals were elicited under v1 digests (slice 1
  predates the v2 adoption, commit f025154). v2 is recomputed and reported alongside.

REPRODUCTION IS A GATE, NOT A COURTESY
--------------------------------------
The recorded `verification` rows carry the rule id, support and contradiction count but NOT
the effect, so the proposals are re-bound from the extraction traces in
`logs/e2_slice_traces/`. Every re-bound cell is checked against its recorded verification
rows; a cell that does not reproduce is reported `reproduced: false` and its arms are still
computed but must not be read as a re-grade of the committed result. A proposal that cannot
be re-bound to (key, feature, value, effect) at all is counted `unbindable` and reported —
slice 1 predates the grammar statement, so odd parses are expected, not silently dropped.

Run:
  .venv/bin/python agent/harness/e2_regrade.py                    # both vocabularies
  .venv/bin/python agent/harness/e2_regrade.py --vocab v1         # primary only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from e2_dose import load_store  # noqa: E402
from rs_e0 import Rule, abstract, mine, score  # noqa: E402
from rs_transitions import ROOT, Transition, load_game, set_vocab, vocab  # noqa: E402

OUTPUT = ROOT / "logs/e2_regrade.json"
TRACES = ROOT / "logs/e2_slice_traces"
FORMAT_VERSION = 1

MODE = "full"  # the layer the slices were scored on
# (slice label, recorded results, the trace-name suffix that generation used)
SLICES = (
    ("slice1", ROOT / "logs/e2_slice.json", ""),
    ("seed1", ROOT / "logs/e2_slice_seed1.json", "_s1"),
    ("seed2", ROOT / "logs/e2_slice_seed2.json", "_s2"),
)
# eps = 0 is the committed rule, carried as the reproduction anchor. The rest is the sweep
# the note pre-committed; all five are reported and none is chosen.
EPSILONS = (0.0, 0.01, 0.02, 0.05, 0.10)
# The committed floor files, read only to CROSS-CHECK the floors recomputed here.
FLOORS = {"v1": ROOT / "logs/e2_dose.json", "v2": ROOT / "logs/e2_dose_vocab_v2.json"}

GUARD_PREFIXES = ("present:", "count:", "adj:", "clicked_adjacent_to:")
GUARD_EXACT = ("click_colour", "click_on_background")


def valid_guard(feature: str, vocabulary: set[str]) -> bool:
    return feature in vocabulary and (
        feature.startswith(GUARD_PREFIXES) or feature in GUARD_EXACT
    )


def _hv(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


# ======================================================================================
# Re-binding the recorded proposals
# ======================================================================================


def _event(event: Any) -> tuple:
    """Canonicalize one effect event, int-coercing numerics — slice 1's own coercion.

    JSON has no int/float distinction, so a transcribed `1.0` would never equal the miner's
    `1`; without this a rule scores zero support instead of being read.
    """
    out = []
    for field in tuple(event):
        if isinstance(field, bool):
            out.append(field)
        elif isinstance(field, float) and field.is_integer():
            out.append(int(field))
        else:
            out.append(field)
    return tuple(out)


def to_rules(payload: dict[str, Any], vocabulary: set[str]) -> tuple[dict[str, Rule], list[str]]:
    """Slice 1's `to_rules`, copied rather than imported.

    `e2_slice.py` is slice 2 now and no longer contains it, and this file must not touch
    that one. The copy is verbatim so that the reproduction gate below means something.
    """
    rules: dict[str, Rule] = {}
    rejected: list[str] = []
    for index, item in enumerate(payload.get("rules") or []):
        try:
            action_id = int(item["action_id"])
            colour = item.get("click_colour")
            key = (
                ("A6", None if colour is None else int(colour))
                if action_id == 6
                else ("A", action_id)
            )
            guard_spec = item.get("guard")
            guard = guard_value = None
            if isinstance(guard_spec, dict) and guard_spec.get("feature"):
                guard = str(guard_spec["feature"])
                if not valid_guard(guard, vocabulary):
                    rejected.append(f"rule {index}: guard '{guard}' is not in the vocabulary")
                    continue
                guard_value = guard_spec.get("value")
                if isinstance(guard_value, float) and guard_value.is_integer():
                    guard_value = int(guard_value)
            effect = tuple(sorted(_event(event) for event in (item.get("effect") or [])))
        except (KeyError, TypeError, ValueError) as error:
            rejected.append(f"rule {index}: {type(error).__name__} {error}")
            continue
        rule = Rule(
            key=key,
            guard=guard,
            guard_value=guard_value,
            effect=effect,
            support=0,
            supporters=[],
            tier="proposed",
        )
        rules[f"p{index}:{rule.rid()}"] = rule
    return rules, rejected


def parse_json(text: str) -> dict[str, Any] | None:
    import re

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if candidate is None:
        return None
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def trace_payload(game: str, dose: int | None, suffix: str) -> tuple[dict | None, str | None]:
    """The extraction payload for one recorded cell, from the last attempt that parses."""
    tag = f"{game}_{'full' if dose is None else dose}{suffix}"
    for attempt in (1, 0):
        path = TRACES / f"{tag}.extract{attempt}.json"
        if not path.is_file():
            continue
        payload = parse_json(json.loads(path.read_text()).get("answer", ""))
        if payload is not None:
            return payload, path.name
    return None, None


# ======================================================================================
# Verification, with a rate instead of a bit
# ======================================================================================


def counts(rule: Rule, store: list[Transition]) -> tuple[int, int, list[int]]:
    support = contradicted = 0
    supporters: list[int] = []
    for index, transition in enumerate(store):
        if transition.key() != rule.key:
            continue
        if rule.guard is not None:
            if _hv(transition.guards.get(rule.guard)) != rule.guard_value:
                continue
        if abstract(transition.effect, MODE) == rule.effect:
            support += 1
            supporters.append(index)
        else:
            contradicted += 1
    return support, contradicted, supporters


def rate(support: int, contradicted: int) -> float | None:
    total = support + contradicted
    return None if total == 0 else round(contradicted / total, 4)


# ======================================================================================
# The arms
# ======================================================================================


def best_refit(key: tuple, feature: str, store: list[Transition]) -> dict[str, Any] | None:
    """Arm B's re-fit: the best VALUE of this (key, feature), with the effect re-mined.

    "Best" is the value whose cell has the lowest contradiction rate, ties broken by the
    larger support and then by the value's repr — deterministic, no sampling. A value cell
    with no majority is still returned if it wins; the eps filter is what rejects it.
    """
    cells: dict[Any, list[Transition]] = defaultdict(list)
    for transition in store:
        if transition.key() != key or feature not in transition.guards:
            continue
        cells[_hv(transition.guards[feature])].append(transition)
    best = None
    for value, rows in cells.items():
        tally = Counter(abstract(row.effect, MODE) for row in rows)
        effect, support = tally.most_common(1)[0]
        contradicted = len(rows) - support
        rank = (contradicted / len(rows), -support, repr(value))
        if best is None or rank < best[0]:
            best = (rank, value, effect, support, contradicted)
    if best is None:
        return None
    _, value, effect, support, contradicted = best
    return {
        "feature": feature,
        "value": value,
        "effect": effect,
        "support": support,
        "contradicted": contradicted,
        "rate": rate(support, contradicted),
    }


def tolerance_tier(key: tuple, store: list[Transition]) -> dict[str, Any] | None:
    """Arm C: for one unresolved key, the single guard with the FEWEST contradictions.

    This is exactly tier 1 with the all-or-nothing requirement replaced by a count. The
    feature is chosen on the whole key (lowest total contradiction rate, then the coarsest
    partition, then the name); its cells are emitted with their own rates, and the eps
    filter — not this function — decides which survive.
    """
    rows = [t for t in store if t.key() == key]
    if not rows:
        return None
    shared = set(rows[0].guards)
    for row in rows[1:]:
        shared &= set(row.guards)
    best = None
    for feature in sorted(shared):
        cells: dict[Any, list[Transition]] = defaultdict(list)
        for row in rows:
            cells[_hv(row.guards[feature])].append(row)
        contradicted = 0
        emitted = []
        for value, cell in sorted(cells.items(), key=lambda item: repr(item[0])):
            tally = Counter(abstract(row.effect, MODE) for row in cell)
            effect, support = tally.most_common(1)[0]
            miss = len(cell) - support
            contradicted += miss
            emitted.append(
                {
                    "value": value,
                    "effect": effect,
                    "support": support,
                    "contradicted": miss,
                    "rate": rate(support, miss),
                }
            )
        rank = (contradicted / len(rows), len(cells), feature)
        if best is None or rank < best[0]:
            best = (rank, feature, emitted, contradicted)
    if best is None:
        return None
    (overall, _, _), feature, emitted, contradicted = best
    return {
        "key_tuple": key,
        "key": f"{key[0]}:{key[1]}",
        "feature": feature,
        "transitions": len(rows),
        "contradicted": contradicted,
        "rate": round(overall, 4),
        "cells": emitted,
    }


def as_rule(key: tuple, feature: str | None, value: Any, effect: tuple, support: int) -> Rule:
    return Rule(
        key=key,
        guard=feature,
        guard_value=value,
        effect=effect,
        support=support,
        supporters=[],
        tier="proposed",
    )


def union_score(
    kept: dict[str, Rule],
    baseline: dict[str, Rule],
    train: list[Transition],
    human: dict[str, list[Transition]],
    pending: list[tuple],
    floor: dict[str, Any],
) -> dict[str, Any]:
    """Kept rules FIRST, exactly as slice 1 unioned them.

    `_fire` prefers guarded rules by support and otherwise takes the first UNGUARDED rule in
    insertion order, so this ordering is what lets a kept rule beat the miner's majority
    guess on the key it addresses — deterministically, not by dict luck.
    """
    union = {**kept, **baseline}
    out: dict[str, Any] = {"rules_kept": len(kept)}
    for target in ("l1", "l2"):
        scored = score(union, train, human[target], MODE)
        base = floor[target]
        out[target] = {
            "accuracy_over_all": scored["accuracy_over_all"],
            "coverage": scored["coverage"],
            "floor_accuracy_over_all": base["accuracy_over_all"],
            "delta": (
                None
                if scored["accuracy_over_all"] is None or base["accuracy_over_all"] is None
                else round(scored["accuracy_over_all"] - base["accuracy_over_all"], 4)
            ),
        }
        # The subset the slice is actually about: transitions on keys the miner could not
        # resolve. The headline is diluted by every key the miner already got right.
        target_rows = [t for t in human[target] if t.key() in set(pending)]
        if target_rows:
            before = score(baseline, train, target_rows, MODE)["accuracy_over_all"]
            after = score(union, train, target_rows, MODE)["accuracy_over_all"]
            out[target]["unresolved_keys_only"] = {
                "transitions": len(target_rows),
                "floor": before,
                "union": after,
                "delta": (
                    None
                    if before is None or after is None
                    else round(after - before, 4)
                ),
            }
    return out


# ======================================================================================
# One recorded cell, all three arms, the whole eps sweep
# ======================================================================================


def regrade_cell(
    label: str,
    suffix: str,
    recorded: dict[str, Any],
    store: list[Transition],
    human: dict[str, list[Transition]],
) -> dict[str, Any]:
    game, dose = recorded["game"], recorded["dose"]
    used = store if dose is None else store[:dose]
    baseline, _ = mine(used, MODE)
    pending = [rule.key for rule in baseline.values() if rule.tier == "majority"]
    vocabulary = {name for t in used for name in t.guards}
    floor = {
        "l1": score(baseline, used, human["l1"], MODE),
        "l2": score(baseline, used, human["l2"], MODE),
    }

    row: dict[str, Any] = {
        "slice": label,
        "game": game,
        "dose": dose,
        "store_transitions": len(used),
        "miner_rules": len(baseline),
        "unresolved_keys": len(pending),
        "floor": {
            "l1": floor["l1"]["accuracy_over_all"],
            "l2": floor["l2"]["accuracy_over_all"],
        },
    }

    payload, trace = trace_payload(game, dose, suffix)
    row["trace"] = trace
    if payload is None:
        row["reproduced"] = False
        row["unbindable"] = None
        row["note"] = "no extraction trace parsed for this cell — no proposal is re-bindable"
        return row

    proposed, rejected = to_rules(payload, vocabulary)
    row["unbindable"] = len(rejected)
    row["unbindable_detail"] = rejected

    verified: list[dict[str, Any]] = []
    for name, rule in proposed.items():
        support, contradicted, _ = counts(rule, used)
        rule.support = support
        # For a dose-125 cell the recorded verification used the 125-transition prefix; the
        # full-store recheck is reported beside it so a proposal kept on thin evidence is
        # visible as such. Nothing downstream reads it — the arms use the recorded convention.
        full_support, full_contradicted, _ = counts(rule, store)
        verified.append(
            {
                "name": name,
                "rule": rule.rid(),
                "support_on_store": support,
                "contradicted_on_store": contradicted,
                "rate": rate(support, contradicted),
                "full_store": {
                    "support": full_support,
                    "contradicted": full_contradicted,
                    "rate": rate(full_support, full_contradicted),
                },
            }
        )
    row["proposals"] = verified

    # THE REPRODUCTION GATE — same rule ids, same supports, same contradiction counts as the
    # committed run. Order-insensitive: the recorded list is a list, but it is keyed by rid.
    recorded_rows = {
        (r["rule"], r["support_on_store"], r["contradicted_on_store"])
        for r in (recorded.get("verification") or [])
    }
    mine_rows = {
        (r["rule"], r["support_on_store"], r["contradicted_on_store"]) for r in verified
    }
    row["reproduced"] = recorded_rows == mine_rows
    if not row["reproduced"]:
        row["reproduction_diff"] = {
            "recorded_not_here": sorted(map(str, recorded_rows - mine_rows))[:10],
            "here_not_recorded": sorted(map(str, mine_rows - recorded_rows))[:10],
        }

    # ---- arm B's re-fits, computed once per (key, feature) and reused across eps
    refits: list[dict[str, Any]] = []
    for entry, (name, rule) in zip(verified, proposed.items()):
        if rule.guard is None:
            refits.append({"name": name, "skipped": "proposal names no guard feature"})
            continue
        refit = best_refit(rule.key, rule.guard, used)
        if refit is None:
            refits.append({"name": name, "skipped": "no store transition carries this key"})
            continue
        own = entry["rate"]
        refits.append(
            {
                "name": name,
                "key": rule.rid(),
                **{k: (v if k != "effect" else list(v)) for k, v in refit.items()},
                "proposal_rate": own,
                "beats_proposal": own is not None and refit["rate"] < own,
            }
        )
    row["refits"] = refits

    # ---- arm C's tolerance tier, one per unresolved key, also eps-independent
    tiers = [t for t in (tolerance_tier(key, used) for key in pending) if t is not None]
    row["tolerance_tier"] = [
        {
            **{k: v for k, v in t.items() if k != "key_tuple"},
            "cells": [{**c, "effect": list(c["effect"])} for c in t["cells"]],
        }
        for t in tiers
    ]

    arms: dict[str, Any] = {}
    for eps in EPSILONS:
        tag = f"{eps:.2f}"

        kept_a: dict[str, Rule] = {}
        for entry, (name, rule) in zip(verified, proposed.items()):
            if entry["support_on_store"] > 0 and (entry["rate"] or 0.0) <= eps:
                kept_a[name] = rule

        kept_b: dict[str, Rule] = {}
        for refit, (name, rule) in zip(refits, proposed.items()):
            if refit.get("skipped") or not refit["beats_proposal"]:
                continue
            if refit["support"] <= 0 or refit["rate"] > eps:
                continue
            kept_b[f"b:{name}"] = as_rule(
                rule.key, refit["feature"], refit["value"], tuple(refit["effect"]), refit["support"]
            )

        kept_c: dict[str, Rule] = {}
        for tier in tiers:
            key = tier["key_tuple"]
            for index, cell in enumerate(tier["cells"]):
                if cell["support"] <= 0 or cell["rate"] > eps:
                    continue
                kept_c[f"c:{tier['key']}:{tier['feature']}:{index}"] = as_rule(
                    key, tier["feature"], cell["value"], tuple(cell["effect"]), cell["support"]
                )

        arms[tag] = {
            "A": union_score(kept_a, baseline, used, human, pending, floor),
            "B": union_score(kept_b, baseline, used, human, pending, floor),
            "C": union_score(kept_c, baseline, used, human, pending, floor),
        }
        arms[tag]["A"]["kept_rules"] = sorted(r.rid() for r in kept_a.values())
        arms[tag]["B"]["kept_rules"] = sorted(r.rid() for r in kept_b.values())
        arms[tag]["C"]["kept_rules"] = sorted(r.rid() for r in kept_c.values())
    row["arms"] = arms
    return row


# ======================================================================================
# Runner
# ======================================================================================


def committed_floor(path: Path, game: str) -> dict[str, Any] | None:
    """The full-dose floor from the committed dose file, for cross-checking only."""
    if not path.is_file():
        return None
    row = json.loads(path.read_text()).get("games", {}).get(game)
    if row is None:
        return None
    doses = row.get("mechanics", {}).get(MODE, {}).get("doses", [])
    full = next((d for d in doses if d.get("full_store")), None)
    if full is None:
        return None
    return {
        "l1": full["on_human_l1"]["accuracy_over_all"],
        "l2": full["on_human_l2"]["accuracy_over_all"],
    }


def run_vocab(version: str, games: list[str] | None) -> dict[str, Any]:
    set_vocab(version)
    # Guards are computed at load time, so every store and every human replay must be
    # reloaded when the vocabulary changes. Caching across vocabularies would silently
    # score v1 proposals against v2 guards.
    stores: dict[str, list[Transition]] = {}
    humans: dict[str, dict[str, list[Transition]]] = {}
    rows: list[dict[str, Any]] = []

    for label, path, suffix in SLICES:
        document = json.loads(path.read_text())
        for recorded in document["cells"]:
            game = recorded["game"]
            if games and game not in games:
                continue
            if recorded.get("outcome") != "scored":
                rows.append(
                    {
                        "slice": label,
                        "game": game,
                        "dose": recorded["dose"],
                        "skipped": recorded.get("outcome", "not scored"),
                    }
                )
                continue
            if game not in stores:
                stores[game], _ = load_store(game)
                everything = load_game(game, max_level=2)
                humans[game] = {
                    "l1": [t for t in everything if t.level == 1],
                    "l2": [t for t in everything if t.level == 2],
                }
            row = regrade_cell(label, suffix, recorded, stores[game], humans[game])
            rows.append(row)
            print(
                f"  {label:7s} {game} dose={'full' if row['dose'] is None else row['dose']:>4} "
                f"proposals={len(row.get('proposals') or []):3d} "
                f"unbindable={row.get('unbindable')} "
                f"reproduced={row.get('reproduced')}",
                flush=True,
            )

    checks = []
    for game in sorted(stores):
        committed = committed_floor(FLOORS[version], game)
        here = next(
            (
                r["floor"]
                for r in rows
                if r.get("game") == game and r.get("dose") is None and "floor" in r
            ),
            None,
        )
        if committed is not None and here is not None:
            checks.append(
                {
                    "game": game,
                    "committed": committed,
                    "recomputed": here,
                    "matches": committed == here,
                }
            )
    return {"cells": rows, "floor_cross_check": checks}


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    """Per arm x eps: how many cells moved the floor, and by how much. Directions only."""
    out: dict[str, Any] = {}
    for version, block in document["vocabularies"].items():
        per_arm: dict[str, Any] = {}
        for eps in EPSILONS:
            tag = f"{eps:.2f}"
            for arm in ("A", "B", "C"):
                bucket = per_arm.setdefault(arm, {}).setdefault(tag, {})
                for target in ("l1", "l2"):
                    deltas = [
                        row["arms"][tag][arm][target]["delta"]
                        for row in block["cells"]
                        if "arms" in row and row["arms"][tag][arm][target]["delta"] is not None
                    ]
                    kept = [
                        row["arms"][tag][arm]["rules_kept"]
                        for row in block["cells"]
                        if "arms" in row
                    ]
                    bucket[target] = {
                        "cells": len(deltas),
                        "cells_improved": sum(1 for d in deltas if d > 0),
                        "cells_worsened": sum(1 for d in deltas if d < 0),
                        "sum_delta": round(sum(deltas), 4),
                        "max_delta": max(deltas) if deltas else None,
                        "min_delta": min(deltas) if deltas else None,
                    }
                    bucket["rules_kept_total"] = sum(kept)
        out[version] = per_arm
    return out


def anchor_check(document: dict[str, Any]) -> dict[str, Any]:
    """The second gate: at eps = 0 arm A IS the committed rule, so its union accuracy must
    equal the union accuracy recorded in the slice files, cell for cell.

    The first gate (per-cell `reproduced`) checks the proposals were re-bound identically.
    This one checks the whole scoring path — mining, union ordering, `_fire` preference,
    scoring — reproduces the committed result end to end. Computed from the recorded files
    and the result document only; it re-mines nothing.
    """
    recorded: dict[tuple, tuple] = {}
    for label, path, _ in SLICES:
        for cell in json.loads(path.read_text())["cells"]:
            if cell.get("outcome") == "scored":
                recorded[(label, cell["game"], cell["dose"])] = (
                    cell["union"]["human_l1"]["accuracy_over_all"],
                    cell["union"]["human_l2"]["accuracy_over_all"],
                )
    out: dict[str, Any] = {}
    for version, block in document["vocabularies"].items():
        matched, mismatched = 0, []
        for row in block["cells"]:
            if "arms" not in row:
                continue
            arm = row["arms"]["0.00"]["A"]
            here = (arm["l1"]["accuracy_over_all"], arm["l2"]["accuracy_over_all"])
            there = recorded.get((row["slice"], row["game"], row["dose"]))
            if there == here:
                matched += 1
            else:
                mismatched.append(
                    {
                        "slice": row["slice"],
                        "game": row["game"],
                        "dose": row["dose"],
                        "recorded": there,
                        "here": here,
                    }
                )
        out[version] = {"matched": matched, "mismatched": mismatched}
    return out


def headline(document: dict[str, Any]) -> None:
    """The comparable table: one row per (game, dose), A and B averaged over the slices.

    Summing raw cells would count arm C THREE TIMES. C is model-free, so its value on a
    (game, dose) is identical in all three recorded slices, while A and B differ — a raw sum
    over 36 cells inflates the control 3x against itself and makes the contrast unreadable.
    Collapsing to the 12 distinct (game, dose) cells, with A and B averaged across the slices
    that produced them, is the like-for-like comparison.
    """
    for version, block in document["vocabularies"].items():
        primary = " (PRIMARY)" if version == document["primary_vocabulary"] else ""
        print(f"\n=== vocabulary {version}{primary} — headline, 12 (game, dose) cells ===")
        rows = [r for r in block["cells"] if "arms" in r]
        for target in ("l1", "l2"):
            print(f"\n  human {target.upper()}: summed delta vs floor (cells improved/worsened)")
            for eps in EPSILONS:
                tag = f"{eps:.2f}"
                per_cell: dict[tuple, dict[str, list[float]]] = defaultdict(
                    lambda: defaultdict(list)
                )
                for row in rows:
                    cell = (row["game"], "full" if row["dose"] is None else row["dose"])
                    for arm in "ABC":
                        per_cell[cell][arm].append(row["arms"][tag][arm][target]["delta"] or 0.0)
                parts = []
                for arm in "ABC":
                    values = [sum(v[arm]) / len(v[arm]) for v in per_cell.values()]
                    parts.append(
                        f"{arm} {sum(values):+.4f} "
                        f"(+{sum(1 for x in values if x > 1e-9)}"
                        f"/-{sum(1 for x in values if x < -1e-9)})"
                    )
                print(f"    eps={tag}   " + "   ".join(parts))


def report(document: dict[str, Any]) -> None:
    """The note's readout: per game x arm x eps, union deltas vs floor and rules kept.

    Cells are summed over the three recorded slices and both doses, because a slice is one
    sample of the same channel on the same game; the per-cell rows stay in the JSON.
    """
    for version, block in document["vocabularies"].items():
        primary = " (PRIMARY)" if version == document["primary_vocabulary"] else ""
        print(f"\n=== vocabulary {version}{primary} — union accuracy delta vs the miner floor ===")
        games = sorted({row["game"] for row in block["cells"] if "arms" in row})
        for target in ("l1", "l2"):
            print(f"\n  human {target.upper()}      " + "".join(f"{arm:>26s}" for arm in "ABC"))
            print("  " + " " * 12 + "".join(f"{'sum d (cells+) kept':>26s}" for _ in "ABC"))
            for game in games:
                rows = [r for r in block["cells"] if r.get("game") == game and "arms" in r]
                for eps in EPSILONS:
                    tag = f"{eps:.2f}"
                    parts = []
                    for arm in "ABC":
                        deltas = [
                            r["arms"][tag][arm][target]["delta"]
                            for r in rows
                            if r["arms"][tag][arm][target]["delta"] is not None
                        ]
                        kept = sum(r["arms"][tag][arm]["rules_kept"] for r in rows)
                        parts.append(
                            f"{sum(deltas):+8.4f} ({sum(1 for d in deltas if d > 0)}/{len(deltas)})"
                            f" {kept:5d}".rjust(26)
                        )
                    print(f"  {game:5s} eps={tag}" + "".join(parts))
                print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=None)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="print the per-game readout from an existing result file and exit",
    )
    parser.add_argument(
        "--vocab",
        nargs="*",
        choices=("v1", "v2"),
        default=["v1", "v2"],
        help="v1 is PRIMARY — the proposals were elicited under v1 digests",
    )
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if args.report:
        existing = json.loads(args.report.read_text())
        print(json.dumps(anchor_check(existing), indent=2, sort_keys=True))
        headline(existing)
        report(existing)
        return 0

    document: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "note": "notes/e2-regrade.md",
        "mode": MODE,
        "epsilons": list(EPSILONS),
        "keep_rule": "support > 0 and contradicted / (support + contradicted) <= eps",
        "primary_vocabulary": "v1",
        "sources": {label: str(path.relative_to(ROOT)) for label, path, _ in SLICES},
        "vocabularies": {},
    }
    for version in args.vocab:
        print(f"=== vocabulary {version} ===", flush=True)
        document["vocabularies"][version] = run_vocab(version, args.games)
    document["summary"] = summarize(document)
    document["committed_union_anchor"] = anchor_check(document)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}  (vocab() = {vocab()})")

    for version, per_arm in document["summary"].items():
        print(f"\n--- {version} — union delta vs floor, summed over cells ---")
        print(f"{'eps':>6}  " + "  ".join(f"{arm}:L1     {arm}:L2    " for arm in "ABC"))
        for eps in EPSILONS:
            tag = f"{eps:.2f}"
            cells = "  ".join(
                f"{per_arm[arm][tag]['l1']['sum_delta']:+.4f}({per_arm[arm][tag]['l1']['cells_improved']:d})"
                f" {per_arm[arm][tag]['l2']['sum_delta']:+.4f}({per_arm[arm][tag]['l2']['cells_improved']:d})"
                for arm in "ABC"
            )
            print(f"{tag:>6}  {cells}")
    headline(document)
    report(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
