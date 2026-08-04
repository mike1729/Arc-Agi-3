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

VOCABULARY v2 AND CENSUS SCOPE (notes/miner-vocab-v2.md)
-------------------------------------------------------
Two independent changes, measured together and apart by ``miner_vocab_v2.py``, decided
separately:

  ``--vocab``   v2 (``clicked_adjacent_to:C``) ADOPTED 2026-08-04 and now the DEFAULT.
                ``--vocab v1`` reproduces logs/e0_row_m*.json exactly.
  ``--scope``   census-scoped firing REJECTED as specified — it trades 73% of coverage for
                +0.015 accuracy-over-covered. Default stays ``none``. The arms are kept
                because the rejection is a measured result that a later design will revisit,
                not a dead end to be deleted.
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
    set_vocab,
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
    scope: dict[str, Any] | None = None   # census scope; None = fires unconditionally

    def rid(self) -> str:
        head = f"{self.key[0]}:{self.key[1]}"
        return head if self.guard is None else f"{head}|{self.guard}={self.guard_value}"


# ======================================================================================
# Mining
# ======================================================================================


def _hashable(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


# ======================================================================================
# Census scope (notes/miner-vocab-v2.md, mechanism 2)
# ======================================================================================
#
# A rule mined at L1 carries an unstated assumption: the census of the board it was mined
# on. "The blue block moves left" was observed with one blue block and four walls, and E0's
# largest transfer-failure bucket — `separable_by_census`, ~10 games — is exactly the case
# where a `count:`/`present:` feature is constant across every supporter and differs on the
# failing transition. The separator is already in the vocabulary; nothing selected it,
# because tier 1 only searches for a feature that partitions the TRAINING evidence, and a
# feature constant across all of it partitions nothing.
#
# So instead of mining the scope, attach it: every census feature constant across a rule's
# supporters becomes an applicability condition, and a rule whose scope does not match
# ABSTAINS rather than firing. The trade is explicit and is the point of the measurement —
# census-separable WRONG predictions become ABSTENTIONS (uncovered), which cost a probe
# instead of a misprediction-repair cycle. No utility number for that trade is invented
# here; the deltas are reported and the X-phase design consumes them.
#
#   none            v1 behaviour — no scope, rules always fire
#   effect_local    scope restricted to colours the rule's effect mentions, plus the clicked
#                   colour for A6 keys. The (w) design choice.
#   present_only    POST HOC, added after the first run and labelled as such: effect-local,
#                   but `present:C` only. The three pre-specified arms collapsed coverage to
#                   0.24 (effect_local) and 0.00 (full), and the abstention causes said why —
#                   `count:` alone accounts for the large majority of them, because it demands
#                   the exact same NUMBER of objects of a colour where `present:` only demands
#                   the colour exist. This arm isolates that. It is a diagnosis of the first
#                   three arms, not a fourth pre-registered hypothesis, and is reported as such
#   full            every census feature constant across supporters, all 16 colours. Present
#                   to SHOW THE COLLAPSE, not to win: inside one level's evidence nearly
#                   every census feature is constant, so an L1 rule scoped this way abstains
#                   on almost any L2 state. A result here that is not a collapse would mean
#                   effect-locality is doing nothing.
#
# `full` scopes on census features only, not on `adj:`/`clicked_adjacent_to:` — those are
# mechanical preconditions that tier 1 is already entitled to select, and scoping on them
# would conflate the two mechanisms.

SCOPES = ("none", "effect_local", "present_only", "full")
# Guard families that count as a MECHANICAL precondition rather than a census difference.
MECHANICAL = ("adj:", "clicked_adjacent_to:")
COLOURS = range(16)
_MISSING = "\x00missing"


def _effect_colours(effect: tuple, key: tuple) -> set[int]:
    """Colours a rule's effect mentions, plus the clicked colour for an A6 key.

    Every effect event is `(kind, colour, ...)` except `changed` mode's single `(bool,)`,
    which mentions no colour at all — a `changed`-mode rule therefore scopes on the click
    colour alone, which is correct: the bit carries no colour information to be local to.
    """
    colours = {
        event[1]
        for event in effect
        if len(event) >= 2 and isinstance(event[1], int) and not isinstance(event[1], bool)
    }
    if key[0] == "A6" and isinstance(key[1], int):
        colours.add(key[1])
    return colours


def _census_scope(
    train: list[Transition], supporters: list[int], effect: tuple, key: tuple, scope: str
) -> dict[str, Any] | None:
    """The census features constant across `supporters`, restricted per `scope`.

    Absence is a value: a colour with no components emits no `present:`/`count:` feature at
    all, and a rule every one of whose supporters lacked colour 7 is scoped on "no 7" just
    as meaningfully as one scoped on "exactly two 7s". Treating the missing feature as a
    sentinel keeps that case in the scope instead of silently dropping it.
    """
    if scope == "none":
        return None
    colours = COLOURS if scope == "full" else sorted(_effect_colours(effect, key))
    features = (
        ("present:{}",) if scope == "present_only" else ("present:{}", "count:{}")
    )
    out: dict[str, Any] = {}
    for colour in colours:
        for feature in (template.format(colour) for template in features):
            values = {
                _hashable(train[i].guards.get(feature, _MISSING)) for i in supporters
            }
            if len(values) == 1:
                out[feature] = next(iter(values))
    return out


def _in_scope(rule: Rule, transition: Transition) -> bool:
    if not rule.scope:
        return True
    return all(
        _hashable(transition.guards.get(feature, _MISSING)) == value
        for feature, value in rule.scope.items()
    )


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


def mine(
    train: list[Transition], mode: str, scope: str = "none"
) -> tuple[dict[str, Rule], dict[str, Any]]:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope: {scope}")
    by_key: dict[tuple, list[int]] = defaultdict(list)
    for index, transition in enumerate(train):
        by_key[transition.key()].append(index)

    rules: dict[str, Rule] = {}
    unresolved: list[dict[str, Any]] = []

    for key, indices in sorted(by_key.items(), key=lambda item: str(item[0])):
        effects = {abstract(train[i].effect, mode) for i in indices}
        if len(effects) == 1:
            effect = next(iter(effects))
            rule = Rule(
                key=key,
                guard=None,
                guard_value=None,
                effect=effect,
                support=len(indices),
                supporters=indices,
                tier="tier0",
                scope=_census_scope(train, indices, effect, key, scope),
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
                effect = abstract(train[cell[0]].effect, mode)
                rule = Rule(
                    key=key,
                    guard=feature,
                    guard_value=value,
                    effect=effect,
                    support=len(cell),
                    supporters=cell,
                    tier="tier1",
                    scope=_census_scope(train, cell, effect, key, scope),
                )
                rules[rule.rid()] = rule
            continue

        counts = Counter(abstract(train[i].effect, mode) for i in indices)
        effect, support = counts.most_common(1)[0]
        supporters = [i for i in indices if abstract(train[i].effect, mode) == effect]
        rule = Rule(
            key=key,
            guard=None,
            guard_value=None,
            effect=effect,
            support=support,
            supporters=supporters,
            tier="majority",
            scope=_census_scope(train, supporters, effect, key, scope),
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
    """The rule that predicts this transition, or None (uncovered).

    A scoped rule out of its census scope ABSTAINS — it is skipped here exactly as if it did
    not exist, so an out-of-scope guarded rule does not fall through to an out-of-scope
    unguarded one, and a key all of whose rules abstain leaves the transition uncovered.
    Under `scope="none"` every rule is in scope and this is v1 behaviour unchanged.
    """
    key = transition.key()
    guarded = [
        rule
        for rule in rules.values()
        if rule.key == key
        and rule.guard is not None
        and _hashable(transition.guards.get(rule.guard)) == rule.guard_value
        and _in_scope(rule, transition)
    ]
    if guarded:
        return max(guarded, key=lambda rule: rule.support)
    for rule in rules.values():
        if rule.key == key and rule.guard is None and _in_scope(rule, transition):
            return rule
    return None


def _abstain_cause(rules: dict[str, Rule], transition: Transition) -> set[str]:
    """Which scope families made every rule for this key abstain.

    Reported because `present:` and `count:` are not equally brittle: `present:C` asks
    whether a colour exists at all, `count:C` asks for the exact same number of objects, and
    an abstention caused ONLY by `count:` is one an inequality-tolerant scope would not have
    made. Without this split a total coverage collapse is uninterpretable.
    """
    families: set[str] = set()
    for rule in rules.values():
        if rule.key != transition.key() or not rule.scope:
            continue
        for feature, value in rule.scope.items():
            if _hashable(transition.guards.get(feature, _MISSING)) != value:
                families.add(feature.split(":")[0])
    return families


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
    # Mechanical preconditions first: `adj:` (something is in the way) and, under vocabulary
    # v2, `clicked_adjacent_to:` (the clicked object touches something) are real repairs.
    # A `count`/`present` separator only says L2 has a different census of objects, which
    # distinguishes the transition without explaining it — reported apart, never as a repair.
    # Under v1 no `clicked_adjacent_to:` feature exists, so this ordering is v1's unchanged.
    ordered = sorted(
        transition.guards.items(),
        key=lambda item: (not item[0].startswith(MECHANICAL), item[0]),
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
    abstain_causes = Counter()
    per_rule: dict[str, Counter] = defaultdict(Counter)
    for transition in test:
        rule = _fire(rules, transition)
        if rule is None:
            counts["uncovered"] += 1
            # An uncovered transition has two very different causes and the census-scope
            # measurement is about exactly one of them: the key was never seen at all, or it
            # was and every rule for it abstained. Separated here so a coverage drop can be
            # attributed rather than guessed at.
            if any(rule.key == transition.key() for rule in rules.values()):
                counts["abstained"] += 1
                cause = _abstain_cause(rules, transition)
                abstain_causes["count_only" if cause == {"count"} else "|".join(sorted(cause))] += 1
            continue
        if rule.effect == abstract(transition.effect, mode):
            counts["correct"] += 1
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
        "abstain_causes": dict(abstain_causes),
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


def guard_families(rules: dict[str, Rule]) -> dict[str, int]:
    """Which guard family tier 1 actually SELECTED, per mined rule.

    A feature that never partitions anything is dead weight and is reported as such rather
    than silently kept — the adoption check `notes/miner-vocab-v2.md` §4 asks for.
    """
    counter: Counter = Counter()
    for rule in rules.values():
        if rule.tier == "tier1" and rule.guard:
            counter[rule.guard.split(":")[0]] += 1
    return dict(counter)


def key_purity(train: list[Transition], mode: str) -> list[dict[str, Any]]:
    """For every UNRESOLVED key, the best single guard feature by partition purity.

    Tier 1 is all-or-nothing: a feature is selected only if every cell of its partition holds
    exactly one effect, so a feature that explains most of a key and not all of it is
    discarded and leaves no trace in the rule count. That makes `rules mined` a bad instrument
    for asking whether a NEW feature carries signal — it can be the single most informative
    guard in the vocabulary and still change nothing.

    Purity is the fraction of a key's transitions landing in a single-effect cell. It is
    reported, never mined on: lowering the tier-1 bar is a rule-model change, out of scope
    for this measurement, and adopting one on the strength of a number produced by the same
    pass that motivated it is how a measurement becomes a story.
    """
    by_key: dict[tuple, list[int]] = defaultdict(list)
    for index, transition in enumerate(train):
        by_key[transition.key()].append(index)

    out: list[dict[str, Any]] = []
    for key, indices in sorted(by_key.items(), key=lambda item: str(item[0])):
        if len({abstract(train[i].effect, mode) for i in indices}) == 1:
            continue
        shared = set(train[indices[0]].guards)
        for i in indices[1:]:
            shared &= set(train[i].guards)
        ranked: list[tuple[float, str]] = []
        for feature in sorted(shared):
            partition: dict[Any, list[int]] = defaultdict(list)
            for i in indices:
                partition[_hashable(train[i].guards[feature])].append(i)
            pure = sum(
                len(cell)
                for cell in partition.values()
                if len({abstract(train[i].effect, mode) for i in cell}) == 1
            )
            ranked.append((pure / len(indices), feature))
        if not ranked:
            continue
        ranked.sort(key=lambda item: (-item[0], item[1]))
        best = ranked[0]
        new = [item for item in ranked if item[1].startswith("clicked_adjacent_to:")]
        out.append(
            {
                "key": str(key),
                "transitions": len(indices),
                "distinct_effects": len({abstract(train[i].effect, mode) for i in indices}),
                "best_feature": best[1],
                "best_purity": round(best[0], 4),
                "best_family": best[1].split(":")[0],
                "best_new_feature": new[0][1] if new else None,
                "best_new_purity": round(new[0][0], 4) if new else None,
            }
        )
    return out


def run_game(game: str, *, scope: str = "none") -> dict[str, Any]:
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
        rules_a, _ = mine(a, mode, scope)
        rules_l1, mining_l1 = mine(l1, mode, scope)
        row["by_effect_mode"][mode] = {
            "rules_mined_l1": len(rules_l1),
            "rule_tiers": dict(Counter(rule.tier for rule in rules_l1.values())),
            "tier1_guard_families": guard_families(rules_l1),
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
    # `--vocab v1` reproduces logs/e0_row_m*.json, which predate the v2 adoption. The full
    # arm matrix lives in `miner_vocab_v2.py`; these flags are for spot-checking by hand.
    parser.add_argument("--vocab", choices=("v1", "v2"), default="v2")
    parser.add_argument("--scope", choices=SCOPES, default="none")
    args = parser.parse_args()

    set_vocab(args.vocab)
    results = []
    for game in args.games:
        row = run_game(game, scope=args.scope)
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
