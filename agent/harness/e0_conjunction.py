#!/usr/bin/env python3
"""Miner tier 1.5 — the conjunction tier, measured (notes/miner-conjunction-tier.md).

Zero model calls. A WRAPPER over `rs_e0`: this file never edits the shared miner, it mines
on top of its primitives and re-implements only the two functions the new rule shape
touches (`_fire`, `score`). Folding in happens on acceptance, later, coordinated.

THE MECHANISM
-------------
`rs_e0`'s rule model is `action key [+ ONE guard] -> effect`. A key no single guard can
separate is declared UNRESOLVED and falls back to its majority effect — and by construction
the exhaustive tier-1 search already saw every single guard, so what remains guard-shaped is
conjunction-shaped or worse. The measured failure splits put the mass there: `guard_fixable`
is the largest bucket on most games.

Tier 1.5, for unresolved keys only:

    for every pair of guard features (f1, f2) and every value combination (v1, v2) observed
    for that key, if EVERY training transition with `f1=v1 AND f2=v2` shares one effect,
    emit `key + (f1=v1) ^ (f2=v2) -> effect` with support = that cell's size.

Per-CELL zero-contradiction, not per-key: unlike tier 1 this is not all-or-nothing, so a key
that stays unresolvable as a whole can still be predicted on the part of its evidence that is
crisp, with the majority rule left as the fallback for everything else. Support >= 1, no
invented minimum; the support distribution is reported instead.

Two deliberate restrictions:

  * only features that are SHARED by all of the key's transitions (tier 1's own restriction)
    and NON-CONSTANT across them. A constant f1 makes `(f1=v1) ^ (f2=v2)` numerically
    identical to the single-guard cell `f2=v2` — a different mechanism (call it tier 1.25),
    which would be smuggled in under this one's name. It is counted and reported as a
    diagnostic (`pure_single_cells`) and NOT mined.
  * unresolved keys only. Keys tier 0 or tier 1 already resolved are untouched, so with the
    tier off this file reproduces `rs_e0` exactly — asserted, not assumed (`--regress`, and
    the `off` arm of every run re-checks it).

ARBITRATION
-----------
tier 1.5 (both guards match, highest support) -> tier 1 (one guard) -> unguarded/majority.
Specific before general, which is `rs_e0`'s existing order with one more rung at the top.
When no tier-1.5 rule matches, firing is delegated to `rs_e0._fire` unchanged.

OVERFIT IS CONTROLLED BY THE PROTOCOL, NOT BY A THRESHOLD
---------------------------------------------------------
Support-1 conjunctions can fit explorer noise. They are not filtered; acceptance is scored on
HELD-OUT HUMAN REPLAYS, an external test set, where a rule that fits noise lowers accuracy and
rejects itself. Rule-count inflation and per-tier firing shares are reported alongside, so a
win that is really a thicket is visible as one.

Run:
  .venv/bin/python agent/harness/e0_conjunction.py --regress
  .venv/bin/python agent/harness/e0_conjunction.py --jobs 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_e0 import (  # noqa: E402
    SCOPES,
    Rule,
    _census_scope,
    _classify_failure,
    _fire,
    _hashable,
    _in_scope,
    abstract,
    mine,
)
from rs_e0 import score as rs_score  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ROOT,
    Transition,
    load_game,
    set_vocab,
    split_half,
    vocab,
)

OUTPUT = ROOT / "logs/e0_conjunction.json"
FORMAT_VERSION = 1

MODES = ("full", "moveset")  # `changed` is degenerate, as in e2_dose / miner_vocab_v2
DOSE_ENDPOINTS = (125, None)  # (w) the e2_dose endpoints; None = the full store

# Caps. Both are (w) working values chosen to bound the combinatorics, not tuned: the
# measured shapes (<= 10 non-constant shared features, <= 24 value groups per unresolved key)
# leave both far from binding. `caps_bound` reports every key where one DID bind, so a capped
# search can never be mistaken for an exhaustive one.
MAX_FEATURE_PAIRS = 250_000   # (w) pairs examined per key
MAX_RULES_PER_KEY = 5_000     # (w) tier-1.5 rules emitted per key


@dataclass
class PairRule(Rule):
    """`rs_e0.Rule` with a second guard. Everything downstream that reads `.supporters`,
    `.effect`, `.support` or `.tier` works unchanged; only matching and `rid` differ."""

    guard2: str | None = None
    guard2_value: Any = None

    def rid(self) -> str:
        head = f"{self.key[0]}:{self.key[1]}"
        return f"{head}|{self.guard}={self.guard_value}&{self.guard2}={self.guard2_value}"


# ======================================================================================
# Mining — tier 1.5
# ======================================================================================


def mine_conjunction(
    train: list[Transition], mode: str, scope: str = "none"
) -> tuple[dict[str, Rule], dict[str, Rule], dict[str, Any]]:
    """Returns (base rules from `rs_e0.mine`, tier-1.5 rules, diagnostics).

    The two rule sets are kept apart rather than merged into one dict because the arbitration
    order is defined over them and because every report wants the tier-1.5 count on its own.
    """
    base, report = mine(train, mode, scope)
    unresolved = {item["key"] for item in report["unresolved_keys"]}

    by_key: dict[tuple, list[int]] = defaultdict(list)
    for index, transition in enumerate(train):
        by_key[transition.key()].append(index)

    conj: dict[str, Rule] = {}
    diag: dict[str, Any] = {
        "unresolved_keys": len(unresolved),
        "keys_with_tier15_rules": 0,
        "feature_pairs_examined": 0,
        "supports": [],
        "caps_bound": [],
        "pure_single_cells": 0,
        "per_key": [],
    }

    for key, indices in sorted(by_key.items(), key=lambda item: str(item[0])):
        if str(key) not in unresolved:
            continue
        effects = [abstract(train[i].effect, mode) for i in indices]

        shared = set(train[indices[0]].guards)
        for i in indices[1:]:
            shared &= set(train[i].guards)
        values = {
            feature: [_hashable(train[i].guards[feature]) for i in indices]
            for feature in sorted(shared)
        }
        features = [feature for feature, column in values.items() if len(set(column)) > 1]

        # Diagnostic only (see the docstring): pure SINGLE-guard cells inside an unresolved
        # key. A different mechanism, counted so its size is on the record, never mined here.
        for feature in features:
            cells: dict[Any, set] = defaultdict(set)
            for position, value in enumerate(values[feature]):
                cells[value].add(effects[position])
            diag["pure_single_cells"] += sum(1 for e in cells.values() if len(e) == 1)

        capped = False
        if len(features) * (len(features) - 1) // 2 > MAX_FEATURE_PAIRS:
            # Deterministic truncation, by feature name, with the bind recorded.
            limit = 2
            while limit * (limit - 1) // 2 <= MAX_FEATURE_PAIRS:
                limit += 1
            features = features[: limit - 1]
            capped = True
            diag["caps_bound"].append({"key": str(key), "cap": "feature_pairs"})

        found: list[PairRule] = []
        pairs = 0
        for f1, f2 in combinations(features, 2):
            pairs += 1
            column1, column2 = values[f1], values[f2]
            cells: dict[tuple, list[int]] = defaultdict(list)
            for position in range(len(indices)):
                cells[(column1[position], column2[position])].append(position)
            for (v1, v2), positions in cells.items():
                cell_effects = {effects[p] for p in positions}
                if len(cell_effects) != 1:
                    continue
                supporters = [indices[p] for p in positions]
                found.append(
                    PairRule(
                        key=key,
                        guard=f1,
                        guard_value=v1,
                        effect=next(iter(cell_effects)),
                        support=len(supporters),
                        supporters=supporters,
                        tier="tier1_5",
                        scope=_census_scope(
                            train, supporters, next(iter(cell_effects)), key, scope
                        ),
                        guard2=f2,
                        guard2_value=v2,
                    )
                )
        diag["feature_pairs_examined"] += pairs

        if len(found) > MAX_RULES_PER_KEY:
            found.sort(key=lambda rule: (-rule.support, rule.rid()))
            found = found[:MAX_RULES_PER_KEY]
            capped = True
            diag["caps_bound"].append({"key": str(key), "cap": "rules_per_key"})

        for rule in found:
            conj[rule.rid()] = rule
        if found:
            diag["keys_with_tier15_rules"] += 1
        diag["supports"].extend(rule.support for rule in found)
        diag["per_key"].append(
            {
                "key": str(key),
                "transitions": len(indices),
                "distinct_effects": len(set(effects)),
                "candidate_features": len(features),
                "feature_pairs": pairs,
                "tier15_rules": len(found),
                "capped": capped,
            }
        )

    supports = diag.pop("supports")
    diag["tier15_rules"] = len(conj)
    diag["support_distribution"] = _support_distribution(supports)
    return base, conj, diag


def _support_distribution(supports: list[int]) -> dict[str, Any]:
    if not supports:
        return {"n": 0}
    ordered = sorted(supports)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
        "support_1": sum(1 for s in ordered if s == 1),
        "support_2": sum(1 for s in ordered if s == 2),
        "support_ge_5": sum(1 for s in ordered if s >= 5),
        "histogram": dict(Counter(min(s, 10) for s in ordered)),  # 10 = "10 or more"
    }


# ======================================================================================
# Firing and scoring — `rs_e0.score` with one more rung above `_fire`
# ======================================================================================


def fire(
    base: dict[str, Rule], conj: dict[str, Rule], transition: Transition
) -> Rule | None:
    key = transition.key()
    matched = [
        rule
        for rule in conj.values()
        if rule.key == key
        and _hashable(transition.guards.get(rule.guard)) == rule.guard_value
        and _hashable(transition.guards.get(rule.guard2)) == rule.guard2_value
        and _in_scope(rule, transition)
    ]
    if matched:
        # Deterministic: highest support, then rule id. Overlapping conjunctions are the
        # normal case here, so the tie-break cannot be left to dict order.
        return max(matched, key=lambda rule: (rule.support, rule.rid()))
    return _fire(base, transition)


def score(
    base: dict[str, Rule],
    conj: dict[str, Rule],
    train: list[Transition],
    test: list[Transition],
    mode: str,
) -> dict[str, Any]:
    """`rs_e0.score`, verbatim except for the firing function and the per-tier shares.

    With `conj` empty this must reproduce `rs_e0.score` field for field; every run asserts it
    on its own `off` arm, and `--regress` asserts it across all 24 games.
    """
    counts: Counter = Counter()
    separators: Counter = Counter()
    per_rule: dict[str, Counter] = defaultdict(Counter)
    by_tier: Counter = Counter()
    correct_by_tier: Counter = Counter()
    for transition in test:
        rule = fire(base, conj, transition)
        if rule is None:
            counts["uncovered"] += 1
            if any(r.key == transition.key() for r in base.values()):
                counts["abstained"] += 1
            continue
        by_tier[rule.tier] += 1
        if rule.effect == abstract(transition.effect, mode):
            counts["correct"] += 1
            correct_by_tier[rule.tier] += 1
            per_rule[rule.rid()]["correct"] += 1
        else:
            _, family = _classify_failure(rule, transition, train)
            kind = {
                "adj": "guard_fixable",
                "clicked_adjacent_to": "guard_fixable",
                "count": "separable_by_census",
                "present": "separable_by_census",
            }.get(family or "", "unpredicted")
            counts[kind] += 1
            if family is not None:
                separators[family] += 1
            per_rule[rule.rid()][kind] += 1

    fired = sum(
        counts[k]
        for k in ("correct", "guard_fixable", "separable_by_census", "unpredicted")
    )
    survived = sum(
        1
        for c in per_rule.values()
        if not (c["guard_fixable"] + c["separable_by_census"] + c["unpredicted"])
    )
    return {
        "test_transitions": len(test),
        "covered": fired,
        "coverage": round(fired / len(test), 4) if test else None,
        "uncovered": counts["uncovered"],
        "abstained": counts["abstained"],
        "correct": counts["correct"],
        "accuracy_over_covered": round(counts["correct"] / fired, 4) if fired else None,
        "accuracy_over_all": round(counts["correct"] / len(test), 4) if test else None,
        "failure_split": {
            "guard_fixable": counts["guard_fixable"],
            "separable_by_census": counts["separable_by_census"],
            "unpredicted": counts["unpredicted"],
        },
        "separating_guard_family": dict(separators),
        "rules_fired": len(per_rule),
        "rules_survived": survived,
        "rule_survival_rate": round(survived / len(per_rule), 4) if per_rule else None,
        "firing_share_by_tier": {
            tier: round(by_tier[tier] / fired, 4) for tier in sorted(by_tier)
        }
        if fired
        else {},
        "accuracy_by_tier": {
            tier: round(correct_by_tier[tier] / by_tier[tier], 4) for tier in sorted(by_tier)
        },
    }


# The fields `rs_e0.score` and this one must agree on when the tier is off. `abstain_causes`
# is excluded: it is a census-scope diagnostic and this measurement runs unscoped.
_REGRESSION_FIELDS = (
    "test_transitions",
    "covered",
    "coverage",
    "uncovered",
    "abstained",
    "correct",
    "accuracy_over_covered",
    "accuracy_over_all",
    "failure_split",
    "separating_guard_family",
    "rules_fired",
    "rules_survived",
    "rule_survival_rate",
)


def _assert_reproduces(
    base: dict[str, Rule], train: list[Transition], test: list[Transition], mode: str
) -> None:
    got = score(base, {}, train, test, mode)
    want = rs_score(base, train, test, mode)
    for field in _REGRESSION_FIELDS:
        if got[field] != want[field]:
            raise AssertionError(f"tier-1.5 OFF diverges from rs_e0 on {field}: {got[field]} != {want[field]}")


# ======================================================================================
# Runner A — E0-style scoring on human replays
# ======================================================================================


def e0_game(game: str) -> dict[str, Any]:
    transitions = load_game(game, max_level=2)
    l1 = [t for t in transitions if t.level == 1]
    l2 = [t for t in transitions if t.level == 2]
    a, b = split_half(l1)

    row: dict[str, Any] = {
        "game": game,
        "l1_transitions": len(l1),
        "l2_transitions": len(l2),
        "modes": {},
    }
    for mode in MODES:
        started = time.time()
        base_a, conj_a, diag_a = mine_conjunction(a, mode)
        base_l1, conj_l1, diag_l1 = mine_conjunction(l1, mode)
        mining_seconds = time.time() - started

        _assert_reproduces(base_a, a, b, mode)
        _assert_reproduces(base_l1, l1, l2, mode)

        row["modes"][mode] = {
            "mining_seconds": round(mining_seconds, 3),
            "rules_base": len(base_l1),
            "rules_tier15": len(conj_l1),
            "tier15_diagnostics": diag_l1,
            "off": {
                "within_l1": score(base_a, {}, a, b, mode),
                "l1_to_l2": score(base_l1, {}, l1, l2, mode),
            },
            "on": {
                "within_l1": score(base_a, conj_a, a, b, mode),
                "l1_to_l2": score(base_l1, conj_l1, l1, l2, mode),
            },
        }
    return row


# ======================================================================================
# Runner B — the e2_dose grid (explorer store -> human replays) + X-phase confidence
# ======================================================================================


def dose_game(game: str) -> dict[str, Any]:
    from e2_dose import load_store  # local: keeps the E0 runner free of the store dependency

    explorer, _post_missing = load_store(game)
    human = load_game(game, max_level=2)
    human_l1 = [t for t in human if t.level == 1]
    human_l2 = [t for t in human if t.level == 2]

    row: dict[str, Any] = {
        "game": game,
        "store_transitions": len(explorer),
        "human_l1": len(human_l1),
        "human_l2": len(human_l2),
        "modes": {},
    }
    for mode in MODES:
        doses: list[dict[str, Any]] = []
        for dose in DOSE_ENDPOINTS:
            prefix = explorer if dose is None else explorer[:dose]
            if dose is not None and len(explorer) < dose:
                doses.append({"dose": dose, "skipped": "store smaller than dose"})
                continue
            started = time.time()
            base, conj, diag = mine_conjunction(prefix, mode)
            mining_seconds = time.time() - started
            _assert_reproduces(base, prefix, human_l1, mode)
            doses.append(
                {
                    "dose": dose if dose is not None else len(explorer),
                    "full_store": dose is None,
                    "mining_seconds": round(mining_seconds, 3),
                    "rules_base": len(base),
                    "rules_tier15": len(conj),
                    "tier15_diagnostics": diag,
                    "off": {
                        "on_human_l1": score(base, {}, prefix, human_l1, mode),
                        "on_human_l2": score(base, {}, prefix, human_l2, mode),
                    },
                    "on": {
                        "on_human_l1": score(base, conj, prefix, human_l1, mode),
                        "on_human_l2": score(base, conj, prefix, human_l2, mode),
                    },
                }
            )
        row["modes"][mode] = {"doses": doses}

    # X-phase confidence classes (e3_executor.confidence): a `majority` rule is `weak`, any
    # other fired rule is `confident`, no rule is `uncovered`. Tier 1.5 is not a majority
    # rule, so every store edge it takes off the majority rule moves weak -> confident. Full
    # store, mode `full` — the configuration the planner runs on.
    if explorer:
        base, conj, _ = mine_conjunction(explorer, "full")
        classes = {"off": Counter(), "on": Counter()}
        for transition in explorer:
            for arm, rules in (("off", {}), ("on", conj)):
                rule = fire(base, rules, transition)
                cls = (
                    "uncovered"
                    if rule is None
                    else ("weak" if rule.tier == "majority" else "confident")
                )
                classes[arm][cls] += 1
        row["confidence"] = {
            arm: {
                cls: round(classes[arm][cls] / len(explorer), 4)
                for cls in ("confident", "weak", "uncovered")
            }
            for arm in ("off", "on")
        }
    return row


# ======================================================================================
# Reporting
# ======================================================================================


def _paired(rows: list[dict], extract) -> dict[str, Any]:
    """Paired per-game delta on -> off. Paired and per-game for the reason
    `miner_vocab_v2._delta` gives: the games differ by orders of magnitude in accuracy and a
    pooled mean would be a report about two of them."""
    pairs = []
    for row in rows:
        if "error" in row:
            continue
        got = extract(row)
        if got is None or got[0] is None or got[1] is None:
            continue
        pairs.append((row["game"], got[0], got[1]))
    deltas = [on - off for _, off, on in pairs]
    return {
        "n": len(pairs),
        "median_off": round(statistics.median([p[1] for p in pairs]), 4) if pairs else None,
        "median_on": round(statistics.median([p[2] for p in pairs]), 4) if pairs else None,
        "median_delta": round(statistics.median(deltas), 4) if deltas else None,
        "wins": sum(1 for d in deltas if d > 1e-9),
        "ties": sum(1 for d in deltas if abs(d) <= 1e-9),
        "losses": sum(1 for d in deltas if d < -1e-9),
        "largest_gain": max(pairs, key=lambda p: p[2] - p[1], default=None),
        "largest_loss": min(pairs, key=lambda p: p[2] - p[1], default=None),
    }


def _dose_cell(row: dict, mode: str, index: int) -> dict | None:
    doses = row["modes"][mode]["doses"]
    if index >= len(doses) or "skipped" in doses[index]:
        return None
    return doses[index]


def summarize(e0_rows: list[dict], dose_rows: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in MODES:
        for split in ("within_l1", "l1_to_l2"):
            for field in ("accuracy_over_all", "accuracy_over_covered", "coverage"):
                out[f"e0_{split}_{mode}_{field}"] = _paired(
                    e0_rows,
                    lambda row, m=mode, s=split, f=field: (
                        row["modes"][m]["off"][s][f],
                        row["modes"][m]["on"][s][f],
                    ),
                )
        for position, label in enumerate(("125", "full")):
            for target in ("on_human_l1", "on_human_l2"):
                for field in ("accuracy_over_all", "accuracy_over_covered"):
                    out[f"dose_{label}_{target}_{mode}_{field}"] = _paired(
                        dose_rows,
                        lambda row, m=mode, p=position, t=target, f=field: (
                            (cell := _dose_cell(row, m, p))
                            and (cell["off"][t][f], cell["on"][t][f])
                        ),
                    )
    out["confidence_confident_coverage"] = _paired(
        dose_rows,
        lambda row: (
            (c := row.get("confidence"))
            and (c["off"]["confident"], c["on"]["confident"])
        ),
    )
    out["rule_count_inflation"] = {
        "e0_l1_full": _paired(
            e0_rows,
            lambda row: (
                row["modes"]["full"]["rules_base"],
                row["modes"]["full"]["rules_base"] + row["modes"]["full"]["rules_tier15"],
            ),
        ),
        "dose_full_store_full": _paired(
            dose_rows,
            lambda row: (
                (cell := _dose_cell(row, "full", 1))
                and (cell["rules_base"], cell["rules_base"] + cell["rules_tier15"])
            ),
        ),
    }
    supports = []
    for row in dose_rows:
        cell = _dose_cell(row, "full", 1) if "error" not in row else None
        if cell:
            histogram = cell["tier15_diagnostics"]["support_distribution"].get("histogram", {})
            for value, count in histogram.items():
                supports.extend([int(value)] * count)
    out["dose_full_support_distribution"] = _support_distribution(supports)
    out["caps_bound"] = [
        {"game": row["game"], "where": "dose", "keys": cell["tier15_diagnostics"]["caps_bound"]}
        for row in dose_rows
        if "error" not in row
        for cell in [_dose_cell(row, "full", 1)]
        if cell and cell["tier15_diagnostics"]["caps_bound"]
    ]
    out["mining_seconds_max"] = max(
        (
            cell["mining_seconds"]
            for row in dose_rows
            if "error" not in row
            for mode in MODES
            for cell in row["modes"][mode]["doses"]
            if "skipped" not in cell
        ),
        default=None,
    )
    return out


# ======================================================================================
# Regression and main
# ======================================================================================


def regress(games: list[str]) -> int:
    """With the tier OFF, this file's scorer must be `rs_e0`'s. Asserted over every game and
    both scored splits — the deltas below only mean something if the baseline is unmoved."""
    checked = 0
    for game in games:
        transitions = load_game(game, max_level=2)
        l1 = [t for t in transitions if t.level == 1]
        l2 = [t for t in transitions if t.level == 2]
        a, b = split_half(l1)
        for mode in MODES:
            base_a, _ = mine(a, mode)
            base_l1, _ = mine(l1, mode)
            _assert_reproduces(base_a, a, b, mode)
            _assert_reproduces(base_l1, l1, l2, mode)
            checked += 2
        print(f"  {game} ok", flush=True)
    print(f"\ntier-1.5 OFF reproduces rs_e0 exactly ({checked} scored splits)")
    return 0


def _job(kind: str, game: str) -> dict[str, Any]:
    try:
        return e0_game(game) if kind == "e0" else dose_game(game)
    except Exception as error:  # a game that cannot load is reported, never skipped silently
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--games",
        nargs="*",
        default=[game for game in ALL_GAMES if game not in EXCLUDED_GAMES],
    )
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--vocab", choices=("v1", "v2"), default="v2")
    parser.add_argument("--regress", action="store_true")
    args = parser.parse_args()

    set_vocab(args.vocab)  # before the pool: workers spawn on macOS and inherit the env
    if args.regress:
        return regress(args.games)

    results: dict[str, list[dict]] = {"e0": [], "dose": []}
    started = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(_job, kind, game): (kind, game)
            for kind in ("e0", "dose")
            for game in args.games
        }
        for future in concurrent.futures.as_completed(futures):
            kind, game = futures[future]
            row = future.result()
            results[kind].append(row)
            if "error" in row:
                print(f"{kind:4s} {row['game']:5s} ERROR {row['error']}", flush=True)
                continue
            if kind == "e0":
                cell = row["modes"]["full"]
                print(
                    f"e0   {row['game']:5s} rules={cell['rules_base']:3d}+{cell['rules_tier15']:5d} "
                    f"L1->L2 off={cell['off']['l1_to_l2']['accuracy_over_all']:.4f} "
                    f"on={cell['on']['l1_to_l2']['accuracy_over_all']:.4f} "
                    f"({cell['mining_seconds']:.1f}s)",
                    flush=True,
                )
            else:
                cell = _dose_cell(row, "full", 1)
                if cell is None:
                    print(f"dose {row['game']:5s} no full-store cell", flush=True)
                    continue
                conf = row.get("confidence", {})
                print(
                    f"dose {row['game']:5s} rules={cell['rules_base']:3d}+{cell['rules_tier15']:5d} "
                    f"L1 off={cell['off']['on_human_l1']['accuracy_over_all']:.4f} "
                    f"on={cell['on']['on_human_l1']['accuracy_over_all']:.4f} | "
                    f"L2 off={cell['off']['on_human_l2']['accuracy_over_all']:.4f} "
                    f"on={cell['on']['on_human_l2']['accuracy_over_all']:.4f} | "
                    f"conf {conf.get('off', {}).get('confident')} -> "
                    f"{conf.get('on', {}).get('confident')} "
                    f"({cell['mining_seconds']:.1f}s)",
                    flush=True,
                )

    for kind in results:
        results[kind].sort(key=lambda row: args.games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "note": "notes/miner-conjunction-tier.md",
        "guard_vocabulary": vocab(),
        "modes": list(MODES),
        "dose_endpoints": list(DOSE_ENDPOINTS),
        "caps": {
            "max_feature_pairs_per_key": MAX_FEATURE_PAIRS,
            "max_rules_per_key": MAX_RULES_PER_KEY,
        },
        "wall_clock_seconds": round(time.time() - started, 1),
        "summary": summarize(results["e0"], results["dose"]),
        "e0_human_replays": {row["game"]: row for row in results["e0"]},
        "dose_explorer_store": {row["game"]: row for row in results["dose"]},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")
    print(json.dumps(document["summary"], indent=2, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
