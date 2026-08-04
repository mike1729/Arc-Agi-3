#!/usr/bin/env python3
"""E0 row M — mechanics rule mining and L1 -> L2 survival.

Mines precondition -> effect rules from one set of transitions and scores them on another,
with three evaluations per game:

    within-L1     train L1-A, test L1-B (sessions split by sha256(guid) parity)
    L1 -> L2      train all of L1, test all of L2
    memorizer     the same two splits under an exact-state lookup, reported as the floor

The within-L1 number is the whole point of the design. Rules die from thin evidence as well
as from the level changing underneath them, and a bare L1 -> L2 accuracy cannot separate the
two. Within-L1 is the ceiling this game's evidence supports; the GAP between it and L1 -> L2
is the part attributable to the level change. Reporting L1 -> L2 alone would let ordinary
estimation noise masquerade as an out-of-distribution finding.

THE RULE MODEL
--------------
A rule is `key [+ one guard] -> effect`, where `key` is the action (for ACTION6, the action
plus the colour under the click) and `effect` is the position-free object-event signature
from ``rs_transitions``. Mining is deterministic and complexity-bounded, in two tiers:

  tier 0   the key's transitions all share one effect            -> unguarded rule
  tier 1   one guard feature partitions them so that every       -> guarded rules
           partition shares one effect
  unresolved  no single guard separates them; the key falls back to its majority effect and
              is reported as unresolved rather than quietly predicting

One guard, not a conjunction: the cost of a search over guard conjunctions is not the compute,
it is that a rich enough hypothesis space fits any training split and the survival number
stops meaning anything. Tier 1 is the smallest refinement that can express "the mover moves
unless something is in the way", which is the mechanic the repair policy has to handle.

THE FAILURE SPLIT
-----------------
A misprediction is classified by whether a repair was AVAILABLE, not by whether one is
convenient:

  guard_fixable   an `adj` guard — a genuine mechanical precondition, "something is in the
                  way" — is constant across every train transition supporting the fired rule
                  and takes a different value here; a local guard repair addresses it
  separable_by
    _census       only a `count`/`present` guard separates: L2 holds a different number of
                  objects of some colour. Technically a distinguishing precondition, but it
                  does not explain the failure and a repair built on it would not generalize.
                  Measured to carry almost the entire separable mass, which is why it is
                  reported apart rather than folded into guard_fixable
  unpredicted     the transition is indistinguishable from the rule's supporters in the
                  entire guard vocabulary, and still behaves differently — no repair inside
                  this vocabulary can fix it; the rule has to be invalidated and re-synthesized

Guards are computed from the pre-state and the action only (``rs_transitions.guard_features``),
never from the outcome. A guard vocabulary allowed to see the effect would make every
misprediction look repairable, which is the number this measurement exists to establish.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_transitions import (  # noqa: E402
    ANOMALIES,
    ITERATION_GAMES,
    ROOT,
    Transition,
    grid_digest,
    load_game,
    split_half,
)

OUTPUT = ROOT / "logs/e0_row_m.json"
FORMAT_VERSION = 1


@dataclass
class Rule:
    key: tuple
    guard: str | None
    guard_value: Any
    effect: tuple
    support: int
    supporters: list[int]          # indices into the train list
    tier: str                      # "tier0" | "tier1" | "majority"

    def rid(self) -> str:
        head = f"{self.key[0]}:{self.key[1]}"
        return head if self.guard is None else f"{head}|{self.guard}={self.guard_value}"


# ======================================================================================
# Mining
# ======================================================================================


def _hashable(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


# ======================================================================================
# Effect granularity
# ======================================================================================
#
# The whole-grid signature is a strict forward model: every co-moving object has to be
# predicted correctly or the transition counts as wrong. On a busy board that is brittle in
# a way that has nothing to do with level transfer, and a survival number measured only at
# that granularity could be an artifact of the model class. So the same measurement runs at
# three granularities, coarsest last:
#
#   full      the exact position-free signature — every event, with movement vectors
#   moveset   event types and colours, vectors dropped — "the red thing moved", not how far
#   changed   a single bit: did the action change the board at all
#
# `changed` is the weakest mechanics claim that is still a mechanics claim, and it is immune
# to multi-object brittleness. If transfer collapses even there, the collapse is the game's
# and not the representation's.

EFFECT_MODES = ("full", "moveset", "changed")


def abstract(effect: tuple, mode: str) -> tuple:
    if mode == "full":
        return effect
    if mode == "moveset":
        return tuple(sorted({(event[0], event[1]) for event in effect}))
    if mode == "changed":
        return (bool(effect),)
    raise ValueError(f"unknown effect mode: {mode}")


def mine(train: list[Transition], mode: str) -> tuple[dict[str, Rule], dict[str, Any]]:
    by_key: dict[tuple, list[int]] = defaultdict(list)
    for index, transition in enumerate(train):
        by_key[transition.key()].append(index)

    rules: dict[str, Rule] = {}
    unresolved: list[dict[str, Any]] = []

    for key, indices in sorted(by_key.items(), key=lambda item: str(item[0])):
        effects = {abstract(train[i].effect, mode) for i in indices}
        if len(effects) == 1:
            rule = Rule(
                key=key,
                guard=None,
                guard_value=None,
                effect=next(iter(effects)),
                support=len(indices),
                supporters=indices,
                tier="tier0",
            )
            rules[rule.rid()] = rule
            continue

        # tier 1: the smallest single-feature partition that resolves every cell
        shared = set(train[indices[0]].guards)
        for i in indices[1:]:
            shared &= set(train[i].guards)
        best: tuple[int, str, dict] | None = None
        for feature in sorted(shared):
            partition: dict[Any, list[int]] = defaultdict(list)
            for i in indices:
                partition[_hashable(train[i].guards[feature])].append(i)
            if all(
                len({abstract(train[i].effect, mode) for i in cell}) == 1
                for cell in partition.values()
            ):
                if best is None or len(partition) < best[0]:
                    best = (len(partition), feature, dict(partition))
        if best is not None:
            _, feature, partition = best
            for value, cell in partition.items():
                rule = Rule(
                    key=key,
                    guard=feature,
                    guard_value=value,
                    effect=abstract(train[cell[0]].effect, mode),
                    support=len(cell),
                    supporters=cell,
                    tier="tier1",
                )
                rules[rule.rid()] = rule
            continue

        counts = Counter(abstract(train[i].effect, mode) for i in indices)
        effect, support = counts.most_common(1)[0]
        rule = Rule(
            key=key,
            guard=None,
            guard_value=None,
            effect=effect,
            support=support,
            supporters=[i for i in indices if abstract(train[i].effect, mode) == effect],
            tier="majority",
        )
        rules[rule.rid()] = rule
        unresolved.append(
            {
                "key": str(key),
                "transitions": len(indices),
                "distinct_effects": len(counts),
                "majority_share": round(support / len(indices), 4),
            }
        )

    return rules, {"unresolved_keys": unresolved}


# ======================================================================================
# Prediction and scoring
# ======================================================================================


def _fire(rules: dict[str, Rule], transition: Transition) -> Rule | None:
    key = transition.key()
    guarded = [
        rule
        for rule in rules.values()
        if rule.key == key
        and rule.guard is not None
        and _hashable(transition.guards.get(rule.guard)) == rule.guard_value
    ]
    if guarded:
        return max(guarded, key=lambda rule: rule.support)
    for rule in rules.values():
        if rule.key == key and rule.guard is None:
            return rule
    return None


def _classify_failure(
    rule: Rule, transition: Transition, train: list[Transition]
) -> tuple[str, str | None]:
    """Was a repair available inside the guard vocabulary?

    A separating feature must be CONSTANT across the rule's supporters and take a different
    value here. The constancy requirement is what makes this test mean anything. Every
    supporter of a rule shares that rule's effect by construction, so "some feature differs"
    is satisfied by almost any unseen state once the vocabulary includes per-colour counts
    and neighbour colours — measured at 100% guard-fixable on four of six games, which is a
    property of the vocabulary's width, not of the games. Requiring the feature to be
    constant among supporters asks the question the repair policy actually needs answered:
    is there a crisp, learnable precondition that the supporters satisfy and this transition
    violates?
    """
    # `adj` first: a mechanical precondition (something is in the way) is a real repair.
    # A `count`/`present` separator only says L2 has a different census of objects, which
    # distinguishes the transition without explaining it — reported apart, never as a repair.
    ordered = sorted(
        transition.guards.items(), key=lambda item: (not item[0].startswith("adj:"), item[0])
    )
    for feature, value in ordered:
        seen = set()
        usable = True
        for index in rule.supporters:
            supporter = train[index].guards
            if feature not in supporter:
                usable = False
                break
            seen.add(_hashable(supporter[feature]))
            if len(seen) > 1:
                usable = False
                break
        if usable and seen and _hashable(value) not in seen:
            return "guard_fixable", feature.split(":")[0]
    return "unpredicted", None


def score(
    rules: dict[str, Rule], train: list[Transition], test: list[Transition], mode: str
) -> dict[str, Any]:
    counts = Counter()
    separators = Counter()
    per_rule: dict[str, Counter] = defaultdict(Counter)
    for transition in test:
        rule = _fire(rules, transition)
        if rule is None:
            counts["uncovered"] += 1
            continue
        if rule.effect == abstract(transition.effect, mode):
            counts["correct"] += 1
            per_rule[rule.rid()]["correct"] += 1
        else:
            _, family = _classify_failure(rule, transition, train)
            kind = {
                "adj": "guard_fixable",
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
        "correct": counts["correct"],
        "accuracy_over_covered": round(counts["correct"] / fired, 4) if fired else None,
        "accuracy_over_all": round(counts["correct"] / len(test), 4) if test else None,
        "failure_split": {
            "guard_fixable": counts["guard_fixable"],
            "separable_by_census": counts["separable_by_census"],
            "unpredicted": counts["unpredicted"],
        },
        # Which guard family supplied the repair. `adj` is a real mechanical precondition
        # (something is in the way). `present`/`count` usually mean only that L2 introduced
        # a colour L1 never showed — technically separating, but not a precondition that
        # explains the failure. A guard_fixable mass dominated by present/count is a weaker
        # claim than the headline count suggests and must be read as such.
        "separating_guard_family": dict(separators),
        "rules_fired": len(per_rule),
        "rules_survived": survived,
        "rule_survival_rate": round(survived / len(per_rule), 4) if per_rule else None,
        "rules_never_fired": len(rules) - len(per_rule),
    }


def memorizer(train: list[Transition], test: list[Transition], mode: str) -> dict[str, Any]:
    """Exact-state lookup: the floor a generalizing rule model has to beat."""
    table: dict[tuple, tuple] = {}
    for transition in train:
        key = (
            grid_digest(transition.pre),
            transition.action_id,
            json.dumps(transition.action_data, sort_keys=True),
        )
        table.setdefault(key, abstract(transition.effect, mode))
    correct = covered = 0
    for transition in test:
        key = (
            grid_digest(transition.pre),
            transition.action_id,
            json.dumps(transition.action_data, sort_keys=True),
        )
        if key in table:
            covered += 1
            correct += int(table[key] == abstract(transition.effect, mode))
    return {
        "covered": covered,
        "coverage": round(covered / len(test), 4) if test else None,
        "correct": correct,
        "accuracy_over_all": round(correct / len(test), 4) if test else None,
    }


# ======================================================================================
# Runner
# ======================================================================================


def run_game(game: str) -> dict[str, Any]:
    transitions = load_game(game, max_level=2)
    l1 = [t for t in transitions if t.level == 1]
    l2 = [t for t in transitions if t.level == 2]
    a, b = split_half(l1)

    row: dict[str, Any] = {
        "game": game,
        "l1_transitions": len(l1),
        "l2_transitions": len(l2),
        "split_half_sizes": [len(a), len(b)],
        "distinct_effects": {
            "l1": len({t.effect for t in l1}),
            "l2": len({t.effect for t in l2}),
        },
        "by_effect_mode": {},
    }
    for mode in EFFECT_MODES:
        rules_a, _ = mine(a, mode)
        rules_l1, mining_l1 = mine(l1, mode)
        row["by_effect_mode"][mode] = {
            "rules_mined_l1": len(rules_l1),
            "rule_tiers": dict(Counter(rule.tier for rule in rules_l1.values())),
            "unresolved_l1": mining_l1["unresolved_keys"],
            "within_l1": score(rules_a, a, b, mode),
            "l1_to_l2": score(rules_l1, l1, l2, mode),
            "memorizer_within_l1": memorizer(a, b, mode),
            "memorizer_l1_to_l2": memorizer(l1, l2, mode),
        }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    results = []
    for game in args.games:
        row = run_game(game)
        results.append(row)
        for mode in EFFECT_MODES:
            cell = row["by_effect_mode"][mode]
            within = cell["within_l1"]
            across = cell["l1_to_l2"]
            print(
                f"{row['game']} {mode:8s} rules={cell['rules_mined_l1']:3d}  "
                f"withinL1 acc={within['accuracy_over_all']:.3f} "
                f"surv={within['rule_survival_rate']} | "
                f"L1->L2 acc={across['accuracy_over_all']:.3f} "
                f"cov={across['coverage']:.3f} "
                f"surv={across['rule_survival_rate']} "
                f"fix={across['failure_split']['guard_fixable']:4d} "
                f"census={across['failure_split']['separable_by_census']:5d} "
                f"unpred={across['failure_split']['unpredicted']:5d} | "
                f"memo={cell['memorizer_l1_to_l2']['accuracy_over_all']:.3f}",
                flush=True,
            )
        print(flush=True)

    document = {
        "format_version": FORMAT_VERSION,
        "row": "M",
        "games": results,
        "extraction_anomalies": ANOMALIES,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
