#!/usr/bin/env python3
"""E2 slice-2 channel B — the latent verifier, driven from a spec file.

`notes/e2-slice2.md` §B and `notes/e2-slice2-build.md` sub-task 3. Zero model calls.

WHAT IT DOES
------------
`e2_hidden_state.py` answered one question about one hardcoded hypothesis: does m0r0's
action-counter parity separate anything, and does mining with it beat the v2 floor. Slice 2
asks the same question of whatever the model proposes, on eight games. This file is that
generalization: a spec file of task-1 COUNTER EXPRESSIONS in, the same two halves out.

    half A   aliasing separation — does the latent separate genuinely aliased outcomes?
    half B   load-bearing — does mining with it as a guard feature beat the v2 floor on
             held-out HUMAN replays, at both dose endpoints, both effect modes, plus the
             ceiling arm (mine human L1, score human L2)?

against 5 seeded random controls per game (seeds 1-5, never 20260804 — the reserved draw
seed). A latent is accepted only if it beats EVERY control on the same metric: the
hidden-state task measured a random bit outperforming real-but-irrelevant latents, so this
floor has teeth and a latent that merely does something is not a latent that does this.

HALF A IS USUALLY UNMEASURABLE, AND SAYS SO
-------------------------------------------
Half A needs repeated `(pre, action)` observations whose outcomes disagree. The explorer's
`test()` pops each candidate exactly once, so its transitions log cannot hold them by
construction; the instrumented rerun's `performs.jsonl` adds the routing actions, and across
the 24 rerun games that yields 43 aliased groups on g50t, 4 on cn04, 3 each on m0r0 and sc25,
and ZERO on the rest — including 6 of the 8 slice-2 games. Where the volume is zero the
half is reported `measurable: false` with its census, and no separation rate is computed.
A separation fraction over zero groups is not 0% and must never be printed as one.

WHY IT IMPORTS `e2_hidden_state` AND NEVER EDITS IT
--------------------------------------------------
That file's author is still landing follow-ups (cn04, sc25) and a silent edit under a
concurrent agent is how a night gets burned. Everything reachable by import is imported —
`_rand_bit` (so the controls are the SAME controls, not a re-derivation), `human_counters`
(the authority the human-side counters are gated against), `feature_purity`, `_slim`,
`_floor`, `RERUN_DIR`. What is not importable is `mine_arms`' nested `run()`, which is
hardcoded to the `parity:` arm names; that loop is ~20 lines and is restated here rather
than refactored into the shared file. The restatement is checked, not asserted:

    .venv/bin/python agent/harness/e2_latent_verify.py --spec <file> --verify

reruns the committed `c2_episode` arm on m0r0 through this driver and diffs every number
against `logs/e2_hidden_state.json`. Any divergence is a failure of THIS file.

SPEC FILE
---------
    {"specs": [{"game": "m0r0", "name": "c2_episode",
                "definition": "actions_since_reset[reset_excluded] mod 2",
                "source": "e2_hidden_state arm, for the reproduction check"}]}

A definition that does not parse in the task-1 counter grammar is recorded
`prose_rejected` and is not run. Nothing is repaired.

Run:
  .venv/bin/python agent/harness/e2_latent_verify.py --verify
  .venv/bin/python agent/harness/e2_latent_verify.py --spec logs/e2_slice2_latents.json
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

import e2_dsl as dsl  # noqa: E402
from e2_dose import load_store  # noqa: E402
from e2_hidden_state import (  # noqa: E402  — imported, never edited
    CONTROL_SEEDS,
    DOSES,
    MODES,
    RERUN_DIR,
    _floor,
    _rand_bit,
    _slim,
    feature_purity,
    human_counters,
)
from gi2_traces import normalize_action_id  # noqa: E402
from rs_e0 import memorizer, mine, score  # noqa: E402
from rs_transitions import (  # noqa: E402
    CORPUS,
    EXCLUDED_SESSIONS,
    ROOT,
    Transition,
    load_game,
    set_vocab,
    vocab,
)

OUTPUT = ROOT / "logs/e2_latent_verify.json"
REFERENCE = ROOT / "logs/e2_hidden_state.json"
FORMAT_VERSION = 1

# The reproduction spec: the committed arm, restated in the task-1 grammar.
REPRODUCTION_SPEC = {
    "specs": [
        {
            "game": "m0r0",
            "name": "c2_episode",
            "definition": "actions_since_reset[reset_excluded] mod 2",
            "source": "e2_hidden_state.py ARMS — the acceptance check of sub-task 3",
        }
    ]
}

FEATURE_PREFIX = "latent:"


# ======================================================================================
# Counters — both sides, gated against the authorities
# ======================================================================================


def human_counter_table(game: str) -> tuple[dict[tuple[str, int], dict], dict[str, Any]]:
    """`(guid, step) -> counters at the pre-state`, per-action-id counts included.

    Gated against `e2_hidden_state.human_counters`, which is the authority for the three
    aggregate counters: if the streamed totals disagree with the committed table anywhere,
    that is reported as a failed gate and the run says so rather than proceeding on numbers
    that no longer mean what the note says they mean.
    """
    table: dict[tuple[str, int], dict] = {}
    for path in sorted((CORPUS / game).glob("*.recording.jsonl")):
        guid = path.name.split(".")[0]
        if (game, guid[:8]) in EXCLUDED_SESSIONS:
            continue
        stream = dsl.CounterStream()
        step = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                data = json.loads(line).get("data")
                if not isinstance(data, dict) or "frame" not in data:
                    continue
                step += 1
                action = data.get("action_input") or {}
                try:
                    action_id = normalize_action_id(action.get("id"))
                except ValueError:
                    action_id = -1
                table[(guid, step)] = stream.counters()
                stream.observe(action_id)

    committed = human_counters(game)
    mismatches = 0
    example = None
    for key, row in committed.items():
        ours = table.get(key)
        if ours is None or (
            ours["total"] != row["global"]
            or ours["since_reset_excluded"] != row["episode"]
            or ours["since_reset_included"] != row["episode_incl"]
        ):
            mismatches += 1
            if example is None:
                example = {"key": list(key), "ours": ours, "committed": row}
    gate = {
        "rows_committed": len(committed),
        "rows_streamed": len(table),
        "mismatches": mismatches,
        "example": example,
        "passed": mismatches == 0 and len(table) >= len(committed),
    }
    return table, gate


def store_counter_rows(
    game: str, transitions: list[Transition]
) -> tuple[list[dict[str, Any] | None], dict[str, Any]]:
    """Counters for the store rows, joined by step index to the instrumented rerun.

    The store's own `step` is a GLOBAL action index and its log holds no RESET rows, so the
    in-episode and per-action-id counts are not recoverable from it — that is what
    `logs/e2_hidden_state_rerun/<game>.performs.jsonl` is for. The rerun's own recorded
    `counters` are the authority for the three aggregates and are used verbatim; the per-id
    counts are streamed over the same rows and the streamed aggregates are checked against
    the recorded ones, so a join that silently slipped by one row cannot pass.
    """
    performs = RERUN_DIR / f"{game}.performs.jsonl"
    if not performs.exists():
        return [None] * len(transitions), {
            "source": "missing_rerun",
            "passed": False,
            "note": f"{performs} absent; no counter is computable for this game",
        }
    stream = dsl.CounterStream()
    by_index: dict[int, dict[str, Any]] = {}
    mismatches = 0
    example = None
    rows = 0
    with performs.open() as handle:
        for line in handle:
            row = json.loads(line)
            rows += 1
            streamed = stream.counters()
            recorded = row["counters"]
            if (
                streamed["total"] != recorded["global"]
                or streamed["since_reset_excluded"] != recorded["episode"]
                or streamed["since_reset_included"] != recorded["episode_incl"]
            ):
                mismatches += 1
                if example is None:
                    example = {
                        "index": row["index"],
                        "streamed": {
                            k: v for k, v in streamed.items() if not k.startswith("per_id")
                        },
                        "recorded": recorded,
                    }
            by_index[row["index"]] = {
                # the recorded aggregates are the authority; the streamed per-id counts are
                # the only thing this pass adds
                "total": recorded["global"],
                "since_reset_excluded": recorded["episode"],
                "since_reset_included": recorded["episode_incl"],
                "per_id_total": streamed["per_id_total"],
                "per_id_since_reset_excluded": streamed["per_id_since_reset_excluded"],
                "per_id_since_reset_included": streamed["per_id_since_reset_included"],
            }
            stream.observe(int(row["action"][0]))

    missing = sum(1 for t in transitions if t.step not in by_index)
    gate = {
        "source": "rerun_join",
        "perform_rows": rows,
        "store_rows": len(transitions),
        "store_rows_without_a_perform": missing,
        "aggregate_mismatches": mismatches,
        "example": example,
        "passed": mismatches == 0 and missing == 0,
    }
    return [by_index.get(t.step) for t in transitions], gate


# ======================================================================================
# Injection
# ======================================================================================


def inject(
    transitions: list[Transition],
    counters: list[dict[str, Any] | None],
    node: dict[str, Any],
    name: str,
) -> int:
    """Write one latent's value into `guards` in place; count the rows where it computed.

    A row whose counter is not computable gets NO key rather than a default — `rs_e0.mine`
    intersects the feature sets across a key's transitions, so an absent key removes the
    feature from consideration for that key, while a defaulted one would fabricate evidence.
    """
    feature = FEATURE_PREFIX + name
    present = 0
    for transition, counter in zip(transitions, counters, strict=True):
        transition.guards.pop(feature, None)
        if counter is None:
            continue
        value = dsl.counter_value(node, counter)
        if value is None:
            continue
        transition.guards[feature] = value
        present += 1
    return present


def clear(transitions: list[Transition]) -> None:
    for transition in transitions:
        for key in [k for k in transition.guards if k.startswith(FEATURE_PREFIX)]:
            transition.guards.pop(key)


# ======================================================================================
# Half A — aliasing separation over the instrumented rerun
# ======================================================================================


def half_a(game: str, definitions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Does the latent separate the aliased `(pre, action)` groups the rerun recorded?

    Same census and same separation criterion as `e2_hidden_state.rerun`, recomputed from
    the committed performs file rather than by re-running the explorer: a group is aliased
    when one `(pre, action)` produced two different post digests, and a feature separates it
    perfectly when every cell of its partition holds exactly one post and there is more than
    one cell. `distinct_feature_values` is reported per latent for the same reason the
    hidden-state task reported it — a feature with more cells separates more by arithmetic
    alone, so a mod-4 latent beating a binary control on this metric is not yet a win.
    """
    performs = RERUN_DIR / f"{game}.performs.jsonl"
    if not performs.exists():
        return {"measurable": False, "reason": f"{performs.name} absent"}
    stream = dsl.CounterStream()
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for line in performs.read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        counters = stream.counters()
        counters["total"] = row["counters"]["global"]
        counters["since_reset_excluded"] = row["counters"]["episode"]
        counters["since_reset_included"] = row["counters"]["episode_incl"]
        stream.observe(int(row["action"][0]))
        if row["pre"] is None or row["post"] is None:
            continue
        groups[(row["pre"], tuple(row["action"]))].append(
            {"index": row["index"], "post": row["post"], "counters": counters}
        )
    repeated = {k: v for k, v in groups.items() if len(v) > 1}
    aliased = {k: v for k, v in repeated.items() if len({r["post"] for r in v}) > 1}

    census = {
        "perform_rows_with_both_digests": sum(len(v) for v in groups.values()),
        "distinct_pre_action_groups": len(groups),
        "repeated_groups": len(repeated),
        "aliased_groups": len(aliased),
    }
    if not aliased:
        return {
            "measurable": False,
            "reason": (
                "the instrumented rerun recorded no aliased (pre, action) group on this "
                "game, so there is nothing for a latent to separate. This is an absence of "
                "instrument, NOT a separation rate of zero"
            ),
            "census": census,
        }

    per_latent: dict[str, Any] = {}
    for name, node in definitions.items():
        separated = computable = 0
        values_used: set = set()
        for observations in aliased.values():
            values = [
                _feature_value(name, node, row["counters"], row["index"])
                for row in observations
            ]
            if any(value is None for value in values):
                continue
            computable += 1
            cells: dict[Any, set[str]] = defaultdict(set)
            for value, row in zip(values, observations, strict=True):
                cells[value].add(row["post"])
            values_used.update(cells)
            if len(cells) > 1 and all(len(posts) == 1 for posts in cells.values()):
                separated += 1
        per_latent[name] = {
            "aliased_groups_computable": computable,
            "separated_perfectly": separated,
            "fraction": round(separated / computable, 4) if computable else None,
            "distinct_feature_values": len(values_used),
        }
    return {"measurable": True, "census": census, "by_latent": per_latent}


def half_a_prefix(game: str, definitions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The optional navigational column (`notes/e2-slice2.md` §B, added after review).

    Half B asks whether a latent helps PREDICT. This asks whether it explains why the
    store's own routes do not replay — m0r0's counter is exactly the case half B would
    miss, being mining-inert and navigationally load-bearing. Reported as its own column
    and NEVER pooled with half A: the two measure different things on different evidence.

    The instrument, and its limit. Each stored state carries one recorded prefix; replaying
    it either lands on the grid the store claims (VERIFIED) or somewhere else (DIVERGED).
    The latent's value at ARRIVAL is computed over that prefix — the driver issues a RESET
    and then the prefix actions, so at the arrival state the total count is `1 + len(prefix)`
    and the in-episode count is `len(prefix)`. What is reported is the CONTINGENCY TABLE of
    latent value against verified/diverged, with counts. No rate, no threshold, no test: one
    prefix per state means this can show an association and cannot show a mechanism, and a
    single number here would be read as more than the design supports.

    Imports `e1_prefix_audit.Replayer` and drives the engine, so it is off by default —
    `--half-a-prefix`. That file is under concurrent edit by the prefix-repair task; only
    `Replayer` and `_load` are used, and nothing here writes to its outputs.
    """
    from e1_prefix_audit import Replayer, _load  # noqa: PLC0415

    graph, states = _load(game)
    prefixes = graph["prefix"]
    replayer = Replayer(game)

    tables: dict[str, dict[str, Counter]] = {
        name: {"verified": Counter(), "diverged": Counter()} for name in definitions
    }
    verified = diverged = 0
    for digest in sorted(prefixes, key=lambda d: (len(prefixes[d]), d)):
        prefix = prefixes[digest]
        grid = replayer.run(prefix)
        outcome = "verified" if grid is not None and grid == states.get(digest) else "diverged"
        if outcome == "verified":
            verified += 1
        else:
            diverged += 1
        stream = dsl.CounterStream()
        stream.observe(0)  # the driver's own RESET, before the prefix
        for action_id, _row, _col in prefix:
            stream.observe(int(action_id))
        counters = stream.counters()
        for name, node in definitions.items():
            value = _feature_value(name, node, counters, len(prefix) + 1)
            if value is not None:
                tables[name][outcome][str(value)] += 1
    return {
        "states_with_a_prefix": len(prefixes),
        "verified": verified,
        "diverged": diverged,
        "by_latent": {
            name: {outcome: dict(counts) for outcome, counts in table.items()}
            for name, table in tables.items()
        },
        "reading": (
            "contingency counts only. One recorded prefix per state means an association "
            "here is not a mechanism, and this column is never pooled with half A"
        ),
    }


def _feature_value(name: str, node: dict[str, Any] | None, counters: dict, index: int):
    """A latent's value, or a control's. Controls are `e2_hidden_state._rand_bit`, imported."""
    if node is None:
        return _rand_bit(int(name.removeprefix("rand")), index)
    return dsl.counter_value(node, counters)


# ======================================================================================
# Half B — mining against the v2 floor
# ======================================================================================


def _arm(
    name: str | None,
    explorer: list[Transition],
    human_l1: list[Transition],
    human_l2: list[Transition],
) -> dict[str, Any]:
    """One arm's numbers. `name=None` is the baseline — no injected feature present.

    This is the restatement of `e2_hidden_state.mine_arms`' nested `run()`. It must produce
    the same numbers under the same inputs, and `--verify` is what says whether it does.
    """
    feature = None if name is None else FEATURE_PREFIX + name
    cell: dict[str, Any] = {}
    for mode in MODES:
        per_dose: dict[str, Any] = {}
        for dose in DOSES:
            prefix = explorer if dose is None else explorer[:dose]
            rules, _ = mine(prefix, mode, "none")
            per_dose["full" if dose is None else str(dose)] = {
                "rules": len(rules),
                "guard_selected": sum(
                    1 for rule in rules.values() if rule.guard == feature
                )
                if feature
                else 0,
                "on_human_l1": _slim(score(rules, prefix, human_l1, mode)),
                "on_human_l2": _slim(score(rules, prefix, human_l2, mode)),
            }
        ceiling_rules, _ = mine(human_l1, mode, "none")
        cell[mode] = {
            "doses": per_dose,
            "purity_on_store": feature_purity(explorer, mode, feature) if feature else None,
            "purity_on_human_l1": feature_purity(human_l1, mode, feature) if feature else None,
            "ceiling_rules": len(ceiling_rules),
            "ceiling_guard_selected": sum(
                1 for rule in ceiling_rules.values() if rule.guard == feature
            )
            if feature
            else 0,
            "human_ceiling_on_l2": _slim(score(ceiling_rules, human_l1, human_l2, mode)),
        }
    return cell


def _beats_controls(arms: dict[str, Any], name: str) -> dict[str, Any]:
    """Acceptance: the latent beats EVERY random control on the same metric.

    The metric is half B's own — accuracy over ALL held-out transitions, at the full dose,
    in both effect modes, against human L1 and human L2. Reported per comparison rather than
    as one boolean, because "wins on one of eight" is a different result from "wins on all
    eight" and a single flag would hide which.
    """
    controls = [f"rand{seed}" for seed in CONTROL_SEEDS if f"rand{seed}" in arms]
    comparisons: dict[str, Any] = {}
    for mode in MODES:
        for target in ("on_human_l1", "on_human_l2"):
            ours = arms[name][mode]["doses"]["full"][target]["accuracy_over_all"]
            control_values = {
                control: arms[control][mode]["doses"]["full"][target]["accuracy_over_all"]
                for control in controls
            }
            best = max((v for v in control_values.values() if v is not None), default=None)
            comparisons[f"{mode}/{target}"] = {
                "latent": ours,
                "best_control": best,
                "beats_every_control": (
                    ours is not None and best is not None and ours > best
                ),
                "controls": control_values,
            }
    return {
        "controls_run": controls,
        "comparisons": comparisons,
        "accepted": bool(comparisons)
        and all(row["beats_every_control"] for row in comparisons.values()),
    }


# ======================================================================================
# Driver
# ======================================================================================


def run_game(
    game: str, specs: list[dict[str, Any]], *, prefix_column: bool = False
) -> dict[str, Any]:
    parsed: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for spec in specs:
        outcome = dsl.classify_counter(spec.get("definition"))
        if outcome["status"] != "parsed":
            rejected.append({**spec, "prose_rejected": outcome["reason"]})
            continue
        name = str(spec.get("name") or f"latent{len(parsed) + 1}")
        parsed[name] = outcome["ast"]

    row: dict[str, Any] = {
        "game": game,
        "specs": len(specs),
        "prose_rejected": rejected,
        "latents": {name: dsl.unparse_counter(node) for name, node in parsed.items()},
    }
    if not parsed:
        row["skipped"] = "no spec parsed"
        return row

    explorer, _post_missing = load_store(game)
    human = load_game(game, max_level=2)
    human_l1 = [t for t in human if t.level == 1]
    human_l2 = [t for t in human if t.level == 2]
    if not explorer or not human_l1:
        row["skipped"] = "empty store or no human L1"
        return row

    store_rows, store_gate = store_counter_rows(game, explorer)
    human_table, human_gate = human_counter_table(game)
    l1_rows = [human_table.get((t.guid, t.step)) for t in human_l1]
    l2_rows = [human_table.get((t.guid, t.step)) for t in human_l2]

    row.update(
        {
            "store_transitions": len(explorer),
            "human_l1": len(human_l1),
            "human_l2": len(human_l2),
            "store_counter_gate": store_gate,
            "human_counter_gate": human_gate,
            "floor_of_record": _floor(game),
            "half_a": half_a(
                game,
                {
                    **parsed,
                    **{f"rand{seed}": None for seed in CONTROL_SEEDS},
                },
            ),
        }
    )
    if prefix_column:
        row["half_a_prefix"] = half_a_prefix(
            game, {**parsed, **{f"rand{seed}": None for seed in CONTROL_SEEDS}}
        )

    # --- half B -----------------------------------------------------------------------
    clear(explorer)
    clear(human_l1)
    clear(human_l2)
    arms: dict[str, Any] = {"baseline": _arm(None, explorer, human_l1, human_l2)}
    availability: dict[str, Any] = {}

    def _run(name: str, node: dict[str, Any] | None) -> None:
        clear(explorer)
        clear(human_l1)
        clear(human_l2)
        if node is None:  # a seeded control, in the same FORM as a real latent
            feature = FEATURE_PREFIX + name
            seed = int(name.removeprefix("rand"))
            for transitions in (explorer, human_l1, human_l2):
                for transition in transitions:
                    transition.guards[feature] = _rand_bit(seed, transition.step)
            availability[name] = {
                "store": len(explorer),
                "human_l1": len(human_l1),
                "human_l2": len(human_l2),
            }
        else:
            availability[name] = {
                "store": inject(explorer, store_rows, node, name),
                "human_l1": inject(human_l1, l1_rows, node, name),
                "human_l2": inject(human_l2, l2_rows, node, name),
            }
        if availability[name]["store"] == 0 or availability[name]["human_l1"] == 0:
            arms[name] = {"skipped": "latent not computable on both sides"}
            return
        arms[name] = _arm(name, explorer, human_l1, human_l2)

    for name, node in parsed.items():
        _run(name, node)
    for seed in CONTROL_SEEDS:
        _run(f"rand{seed}", None)
    clear(explorer)
    clear(human_l1)
    clear(human_l2)

    row["arms_available"] = availability
    row["by_arm"] = arms
    row["memorizer_on_human_l1"] = {
        mode: memorizer(explorer, human_l1, mode) for mode in MODES
    }
    row["acceptance"] = {
        name: _beats_controls(arms, name)
        for name in parsed
        if "skipped" not in arms.get(name, {})
    }
    return row


# ======================================================================================
# The acceptance check — reproduce the committed c2_episode numbers exactly
# ======================================================================================


def _diff(ours: Any, theirs: Any, path: str, out: list[str]) -> None:
    if isinstance(theirs, dict):
        if not isinstance(ours, dict):
            out.append(f"{path}: type {type(ours).__name__} != dict")
            return
        for key in theirs:
            if key not in ours:
                out.append(f"{path}.{key}: missing from this run")
                continue
            _diff(ours[key], theirs[key], f"{path}.{key}", out)
        return
    if ours != theirs:
        out.append(f"{path}: {ours!r} != committed {theirs!r}")


def verify(document: dict[str, Any]) -> dict[str, Any]:
    """Diff this driver's m0r0/c2_episode arm against `logs/e2_hidden_state.json`.

    Compares the BASELINE arm too: an arm that matches while the baseline does not would
    mean the two runs disagree about the floor the arm is measured against, which is a
    failure even though the headline row agrees.
    """
    if not REFERENCE.exists():
        return {"passed": False, "reason": f"{REFERENCE} absent"}
    committed = json.loads(REFERENCE.read_text())["mine"]["by_arm"]
    row = document["games"].get("m0r0", {})
    ours = row.get("by_arm", {})
    differences: list[str] = []
    for arm in ("baseline", "c2_episode"):
        if arm not in ours:
            differences.append(f"{arm}: not run")
            continue
        _diff(ours[arm], committed[arm], arm, differences)
    return {
        "passed": not differences,
        "reference": str(REFERENCE.relative_to(ROOT)),
        "arms_compared": ["baseline", "c2_episode"],
        "differences": differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None, help="spec file of latents")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="run the built-in m0r0/c2_episode spec and diff against the committed numbers",
    )
    parser.add_argument(
        "--half-a-prefix",
        action="store_true",
        dest="prefix_column",
        help=(
            "add the navigational column: replay every stored prefix and cross-tabulate "
            "each latent's arrival value against verified/diverged. Drives the engine, so "
            "it is off by default"
        ),
    )
    parser.add_argument("--vocab", choices=("v1", "v2"), default="v2")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if not args.spec and not args.verify:
        parser.error("nothing to do; pass --spec <file> or --verify")

    set_vocab(args.vocab)
    document_spec = (
        REPRODUCTION_SPEC if args.verify else json.loads(args.spec.read_text())
    )
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in document_spec["specs"]:
        by_game[spec["game"]].append(spec)

    rows = []
    for game, specs in sorted(by_game.items()):
        row = run_game(game, specs, prefix_column=args.prefix_column)
        rows.append(row)
        if "skipped" in row:
            print(f"{game:5s} skipped: {row['skipped']}", flush=True)
            continue
        half = row["half_a"]
        print(
            f"{game:5s} store={row['store_transitions']:5d} latents={len(row['latents'])} "
            f"rejected={len(row['prose_rejected'])} | half A "
            f"{'measurable' if half['measurable'] else 'UNMEASURABLE'}"
            + (
                f" ({half['census']['aliased_groups']} aliased groups)"
                if "census" in half
                else ""
            ),
            flush=True,
        )
        prefix_row = row.get("half_a_prefix")
        if prefix_row:
            print(
                f"       prefix column: {prefix_row['verified']} verified / "
                f"{prefix_row['diverged']} diverged over "
                f"{prefix_row['states_with_a_prefix']} stored prefixes",
                flush=True,
            )
        for name in row["latents"]:
            arm = row["by_arm"].get(name, {})
            if "skipped" in arm:
                print(f"  {name:20s} skipped: {arm['skipped']}", flush=True)
                continue
            full = arm["full"]["doses"]["full"]
            accepted = row["acceptance"][name]["accepted"]
            print(
                f"  {name:20s} L1={full['on_human_l1']['accuracy_over_all']:.4f} "
                f"L2={full['on_human_l2']['accuracy_over_all']:.4f} "
                f"selected={full['guard_selected']} "
                f"-> {'ACCEPTED' if accepted else 'rejected (loses to a control)'}",
                flush=True,
            )

    document = {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/e2_latent_verify.py",
        "guard_vocabulary": vocab(),
        "control_seeds": list(CONTROL_SEEDS),
        "doses": [d if d is not None else "full" for d in DOSES],
        "modes": list(MODES),
        "spec": document_spec,
        "games": {row["game"]: row for row in rows},
    }
    if args.verify:
        document["verification"] = verify(document)
        result = document["verification"]
        print(
            f"\nreproduction of the committed m0r0 c2_episode arm: "
            f"{'PASS' if result['passed'] else 'FAIL'}",
            flush=True,
        )
        for difference in result.get("differences", [])[:20]:
            print(f"  {difference}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")
    if args.verify and not document["verification"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
