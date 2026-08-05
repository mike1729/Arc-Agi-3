#!/usr/bin/env python3
"""E2 — the Qwen synthesis slice. The first model-bearing measurement of the line.

DIGEST v3 / SLICE 2 (2026-08-05, `notes/e2-slice2.md`; build order in
`notes/e2-slice2-build.md` sub-task 4). Slices 1 and 1.1 asked the model to repair the
miner's unresolved keys and it did not: 1/82 substantive proposals, then a repaired display
and the same nothing. That channel is DEAD BY MEASUREMENT and is gone from this file — the
rule request, `support_claim`, the per-rule `refuter` and `next_probe` are removed, not
disabled. The probe/directive channel is gone for the same reason (26/31 arms already
answered, 0/4 predictions realized).

What remains are the three channels still standing, each posed executably and each against a
mechanical control that hardcodes the "no capability" hypothesis:

  A  GOAL AS A FALSIFIABLE PREDICATE   a completion-condition predicate in the task-1 DSL,
     its refuter, and one test action. Control: the prior library
     (`e2_prior_library.py`) — the five default goal shapes the reference brings,
     instantiated mechanically from the census. The prior fires on 50% of reference wins,
     so matching the library is worth nothing.
  B  LATENTS AS EXECUTABLE DEFINITIONS up to 3 counter expressions in the task-1 counter
     grammar. Control: 5 seeded random features, verified by `e2_latent_verify.py`.
  C  VOCABULARY CRITIC                 up to 2 proposals naming a missing feature. Control:
     the measured failure typing. The one channel with a realized payoff (slice 1's ft09
     output became `clicked_adjacent_to` and moved the floor 0.2522 -> 0.3017).

Prose scores zero in A and B: a proposal that does not parse is recorded `prose_rejected`,
counted, and never repaired — the same category slice 1's parse-rejected rules were kept in.

INSTRUMENT RULES (the screens died on these; CLAUDE.md 2026-08-04)
------------------------------------------------------------------
* Qwen3.6-27B-8bit only. The FP8-class model is the deploy reference and the one S1's
  `goal_unknown` bottleneck was measured on; the 4-bit probe thought 2.7x shorter on an
  identical prompt, so precision is not a free axis and the slice must not mix it.
* Direct `mlx_lm`. NO server layer — the July `mlx_vlm` server is the voided lineage.
* Two-phase decode. Phase 1 thinks freely and NEVER has its first token constrained.
  Phase 2 is a separate mechanical extraction call over phase 1's own answer text, with
  thinking off by design; it re-reads, it does not reason. Recorded, not implied.
* Per-call mechanical thinking check identical to `e2_probe.py`. An unclosed think block
  VOIDS the call — the result is discarded, not repaired.
* Every call's raw trace is written to logs/e2_slice_traces/ before scoring.

WHAT THIS FILE SCORES, AND WHAT IT LEAVES TO SCORING TIME
---------------------------------------------------------
Mechanical and in-cell, because all of it is deterministic and zero-model:

  A  parse -> store consistency (row-C's own three-valued survivorship over every store
     transition) · refuter validity (a refuter already satisfied by the store SELF-REFUTES
     the proposal — the S1 finding was that unapplied falsifiers are this channel's failure
     mode) · novelty against the prior library, by canonical predicate string · test-action
     WELL-FORMEDNESS in the guard vocabulary
  B  parse -> a spec file for `e2_latent_verify.py`, which runs the arms and the 5 controls
  C  parse-free by design; each proposal's targeted keys are matched against the keys the
     miner actually left unresolved. The note's targeting rate against the measured failure
     TYPING is not computed here and not faked: the committed floors carry `failure_split`
     per game and target, not per key, so that join happens at readout time

Deferred, and named rather than quietly skipped: source adjudication of A (labels only, the
autopsy rubric, one pass over channel and control together), EXECUTION of the test action
through the probe executor, and C's post-slice implementation queue. An unscored proposal is
reported as unscored, never as a pass.

Run:
  .venv/bin/python agent/harness/e2_slice.py --dry-run          # digests only, no model
  .venv/bin/python agent/harness/e2_slice.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
import e2_frames as frames  # noqa: E402
import es_candidates as ec  # noqa: E402
from e2_dose import load_store  # noqa: E402
from e2_prior_library import inert_inventory, object_census  # noqa: E402
from rs_e0 import Rule, abstract, mine, score  # noqa: E402
from rs_transitions import ROOT, load_game  # noqa: E402

MODEL = Path.home() / "models/mlx/Qwen3.6-27B-8bit"  # PINNED — see notes/e2-dose.md
OUTPUT = ROOT / "logs/e2_slice.json"
TRACES = ROOT / "logs/e2_slice_traces"
PRIOR_LIBRARY = ROOT / "logs/e2_prior_library.json"
FLOOR = ROOT / "logs/e2_dose_vocab_v2.json"
# 2 = slice 2's digest v3, text-only. 3 = slice 3's digest v4, the same digest plus rendered
# boards (`--frames`) and optionally the contradiction-feedback turn (`--feedback`). The
# version travels with the FILE so a reader never has to infer which prompt produced a cell.
FORMAT_VERSION = 2
FRAMES_FORMAT_VERSION = 3

# The slice-2 protocol set: the six iteration games plus the two E1-completed games, whose
# stores hold channel A's only own-completion examples.
SLICE2_GAMES = dsl.SLICE2_GAMES

# Slice 2 runs the FULL store only. The dose axis was flat for rules across two slices and
# none of the three channels has a dose hypothesis, so it buys nothing and costs half a night.
DOSES = (None,)
MODE = "full"  # the layer the miner is weakest on, and the one Qwen is being asked for
THINK_BUDGET = 16384  # (w) >=16k; a 5k budget produced an unclosed block in bring-up
EXTRACT_BUDGET = 4096
TEMP = 0.6  # (w) Qwen thinking defaults
TOP_P = 0.95

# Slice 3's prompt ceilings. REV 2.1: TWO caps, with the reserve stated before F is rendered
# rather than discovered after. A 45k F prompt cannot also yield a <=45k FB chat, because the
# FB turn appends the model's own answer and a rendered counterexample to the SAME chat.
# Neither is a hardware limit — the window is 262,144 tokens. They bound prefill wall and how
# thinly attention is asked to spread.
TOKEN_BUDGET = 40_000  # the F prompt
FB_TOKEN_BUDGET = 45_000  # the full FB chat: F + the answer + the counterexample

# The answer half of the 5k reserve. MEASURED rather than assumed: every one of slice 2's
# sixteen phase-1 answers was 151-289 tokens (the think block is not resent — the chat carries
# the ANSWER), and v4 asks for two more short fields. 1,000 is ~3.5x the largest observed. The
# counterexample half is not allowanced at all: it is rendered per game and counted exactly.
FB_ANSWER_ALLOWANCE = 1_000  # (w)

MAX_RULES_SHOWN = 40
MAX_UNRESOLVED_SHOWN = 12
MAX_EVIDENCE_PER_KEY = 6
# slice 1.1 measured the cost of capping features silently: the digest asserted complete
# value sets while showing only the first 6 varying features, and 21 of 24 traces inferred
# "unlisted => constant => cannot separate". In 14 unresolved-key blocks the witness named a
# feature the display never showed. The cap is lifted so that inference is SOUND: every
# feature that varies is shown, so absence now really does mean constant across the key.
MAX_FEATURES_PER_GROUP = None  # no cap — see notes/e2-variance-arm.md §2
MAX_VALUES_PER_FEATURE = 4  # (w) truncation is marked "+N more" and declared in the prompt
MAX_ALIAS_SHOWN = 8
# digest v3 caps — every one of them is declared in the prompt where it can change a reading
MAX_INERT_SHOWN = 24  # (w)
MAX_REFUTED_GOALS_SHOWN = 10  # (w)
MAX_STRATUM_VALUES = 4  # (w) a feature with more values than this has no useful stratum table
MAX_INVARIANTS_SHOWN = 20  # (w)
SEED = 20260804  # phase 1 is sampled; seeded and recorded so a cell is reproducible

# The miner's actual guard vocabulary (rs_transitions.guard_features). A proposal naming a
# feature outside it is REJECTED, not silently unguarded: `guards.get(unknown)` is None for
# every transition, which equals a null guard_value, so an invented guard would vanish and
# the rule would be scored as unguarded — strictly more permissive than proposed.
GUARD_PREFIXES = ("present:", "count:", "adj:", "clicked_adjacent_to:")
GUARD_EXACT = ("click_colour", "click_on_background")


def valid_guard(feature: str, vocabulary: set[str]) -> bool:
    return feature in vocabulary and (
        feature.startswith(GUARD_PREFIXES) or feature in GUARD_EXACT
    )


_STORE_CACHE: dict[str, tuple[list, set[int]]] = {}
_MINE_CACHE: dict[tuple[str, Any], tuple] = {}


def store_for(game: str) -> list:
    return store_with_gaps(game)[0]


def store_with_gaps(game: str) -> tuple[list, set[int]]:
    """The store plus the steps whose POST frame it does not retain (completion rows).

    Any consumer that reads `.post` directly — the goal grammar, and so the whole negative
    evidence section below — must skip those rows: `e2_dose.load_store` substitutes the pre
    frame as a placeholder there, and evaluating a completion against its own pre-state
    would fabricate the store's only positive example.
    """
    if game not in _STORE_CACHE:
        _STORE_CACHE[game] = load_store(game)
    return _STORE_CACHE[game]


def mined(game: str, dose: int | None) -> tuple:
    key = (game, dose)
    if key not in _MINE_CACHE:
        store = store_for(game)
        used = store if dose is None else store[:dose]
        _MINE_CACHE[key] = (used, *mine(used, MODE))
    return _MINE_CACHE[key]


# ======================================================================================
# Digest — the whole prompt payload, built with zero model calls
# ======================================================================================


def _effect_text(effect: tuple) -> str:
    if not effect:
        return "no-change"
    return " + ".join(
        f"{event[0]}({event[1]}" + (f",{event[2]},{event[3]})" if len(event) > 3 else ")")
        for event in effect
    )


def _key_text(key: tuple) -> str:
    return f"ACTION6 on colour {key[1]}" if key[0] == "A6" else f"ACTION{key[1]}"


def _hv(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


def _no_separation_witness(rows: list, varying: list[str]) -> tuple | None:
    """The best single feature shown failing: fewest mixed value-classes, then the
    largest one — two transition sets sharing the feature's value with different effects.

    A varying feature with NO mixed class separates only under the None-for-absent
    convention the miner does not use; it is skipped, not presented as a witness.
    """
    best = None
    for name in varying:
        classes: dict[Any, Counter] = {}
        for row in rows:
            classes.setdefault(_hv(row.guards.get(name)), Counter())[
                abstract(row.effect, MODE)
            ] += 1
        mixed = {v: c for v, c in classes.items() if len(c) > 1}
        if not mixed:
            continue
        value, counts = max(
            mixed.items(), key=lambda item: (sum(item[1].values()), repr(item[0]))
        )
        rank = (len(mixed), -sum(counts.values()), name)
        if best is None or rank < best[0]:
            top = counts.most_common(2)
            best = (rank, name, value, (top[0][0], top[0][1]), (top[1][0], top[1][1]))
    if best is None:
        return None
    _, name, value, first, second = best
    return name, value, first, second


def unresolved_keys(rules: dict[str, Rule]) -> list[tuple]:
    """The keys the miner could not resolve.

    Derived from the rules themselves — the miner emits exactly one `tier == "majority"`
    rule per unresolved key. NOT parsed from mine()'s report: that report keys the list
    under "unresolved_keys" and stores `str(key)`, so reading it by the wrong name yields
    an empty section and reading it by the right one yields strings that never match a real
    transition key. Both failures are silent, and both empty the one section this slice
    exists to show.
    """
    return [rule.key for rule in rules.values() if rule.tier == "majority"]


def state_identity(game: str) -> list[str]:
    """The STATE IDENTITY block — replaces the old ALIAS CONFLICTS block.

    The old block listed `graph.conflicted` and printed "none recorded" when it was empty.
    That reads as "no aliasing here", and it is not: E1 flags a (state, action) pair only
    when its routing happens to re-test the pair, and the v2 policy re-tests almost
    nothing. `notes/e1-prefix-audit.md` measured what the list is worth — ka59, dc22, wa30
    and sk48 all record ZERO conflicted edges while under 6% of their stored states are
    reachable by their own recorded prefix. dc22's digest printed "none recorded" for a
    store whose settled frames do not identify its states at all, and 21 of 24 slice
    traces then reasoned from a clean state graph they were never given evidence for.

    So the section now leads with the MEASURED quantity — the fraction of stored states
    whose recorded prefix replays to the grid the store claims, over a deterministic engine
    — and demotes the conflict list to the lower bound it always was. Absence of evidence
    is stated as absence of evidence, in the prompt, in words.

    Reads `logs/e1_prefix_audit.json` (`agent/harness/e1_prefix_audit.py`). If that file is
    missing the block says the check has not been run rather than implying a clean store.
    """
    lines: list[str] = []
    audit_path = ROOT / "logs/e1_prefix_audit.json"
    audit = None
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text()).get("games", {}).get(game)

    if audit is None:
        lines.append(
            "  NOT MEASURED for this game. Whether the settled frame identifies the state "
            "is unknown here, and unknown is not the same as clean — treat every rule "
            "below as possibly conditioned on something these frames do not show."
        )
    else:
        rate = audit["verified_rate"]
        lines.append(
            f"  Measured: {audit['verified']} of {audit['states']} stored states "
            f"({rate:.1%}) are reached by replaying their own recorded action prefix from "
            f"reset. The engine is deterministic, so where a replay lands elsewhere, two "
            f"different histories produced the same settled frame."
        )
        if rate >= 0.999:
            lines.append(
                "  Every stored state replays. For this game the settled frame does "
                "identify the state, and a rule conditioned only on what you see below "
                "is not missing a hidden variable."
            )
        else:
            lines.append(
                f"  {1 - rate:.1%} of states do NOT replay to themselves. The settled "
                f"frame does NOT fully identify this game's state: there is at least one "
                f"hidden variable that no feature in the guard vocabulary can express. A "
                f"key you cannot separate may be unseparable for that reason, and no "
                f"guard over these frames would fix it."
            )

    graph_path = ROOT / "logs/e1_store_v2" / f"{game}.graph.json"
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text())
        conflicted = graph.get("conflicted", [])
        lines.append(
            f"  ({len(conflicted)} (state, action) pairs are flagged in the store as having "
            f"contradicted themselves. That count is NOT usable as evidence in either "
            f"direction and no pairs are listed: the explorer re-tested only a small "
            f"unrecorded fraction of pairs, so absence means nothing, and its routing "
            f"replayed paths that were never walked and flagged the divergences as "
            f"contradictions, so presence is often an artifact. Use the measurement above.)"
        )
    return lines


def coverage_ledger(used: list, by_key: dict[tuple, list]) -> list[str]:
    """What has been TRIED on each object, with the never-tried marks spelled out.

    Two independent readouts demand exactly this section. The probe task found 26 of 31
    proposed probe arms asking for evidence the store already held. The S1 end-to-end read
    found what finally unblocked ft09: the model printed its own action history and read the
    gap off it — "I have NOT tried clicking the blue cells". Neither is a reasoning failure
    that more thinking fixes; both are a digest that never states what is absent.

    ACTION6 is the only object-directed action in the vocabulary, so the per-object ledger is
    a ledger of clicks: how many landed ON each colour, and how many landed on something
    4-adjacent to it (`clicked_adjacent_to:C`, the v2 feature). The simple actions 1-5 are
    global and are counted once, not per object — claiming ACTION3 was "tried on the red
    block" would be an invented relation.
    """
    lines: list[str] = []
    clicks_on: Counter = Counter()
    adjacent_clicks: Counter = Counter()
    click_rows = 0
    for transition in used:
        if transition.action_id != 6:
            continue
        click_rows += 1
        colour = transition.guards.get("click_colour")
        if colour is not None:
            clicks_on[int(colour)] += 1
        for name, value in transition.guards.items():
            if name.startswith("clicked_adjacent_to:") and value:
                adjacent_clicks[int(name.split(":")[1])] += 1

    colours: set[int] = set()
    for transition in used:
        for name in transition.guards:
            if name.startswith("count:"):
                colours.add(int(name.split(":")[1]))
    colours |= set(clicks_on) | set(adjacent_clicks)

    simple = sorted(
        {t.action_id for t in used if t.action_id != 6}
    )
    lines.append(
        f"  Simple actions present in this evidence: "
        f"{', '.join(f'ACTION{i}' for i in simple) if simple else 'none'}"
        f"   (they are not aimed at an object, so they are counted once, not per colour)"
    )
    lines.append(f"  ACTION6 clicks in this evidence: {click_rows}")
    for colour in sorted(colours):
        on = clicks_on.get(colour, 0)
        near = adjacent_clicks.get(colour, 0)
        if on == 0 and near == 0:
            mark = "NEVER CLICKED, and never clicked next to"
        elif on == 0:
            mark = f"NEVER CLICKED (but {near} clicks landed 4-adjacent to it)"
        else:
            mark = f"clicked {on}x; {near} clicks landed 4-adjacent to it"
        lines.append(f"    colour {colour:<3d} {mark}")
    return lines


def stratum_lines(rows: list, varying: list[str]) -> list[str]:
    """Per unresolved key: how many stored transitions sit in each value stratum.

    The value SETS above say which values occur; this says how many transitions carry each,
    which is what tells "already tested to death" apart from "one observation". Features with
    more than MAX_STRATUM_VALUES distinct values are omitted with a count rather than
    truncated: a stratum table over a high-cardinality feature is not a stratum table.
    """
    shown: list[str] = []
    omitted = 0
    for name in varying:
        strata = Counter(_hv(row.guards.get(name)) for row in rows)
        if len(strata) > MAX_STRATUM_VALUES:
            omitted += 1
            continue
        cells = ", ".join(
            f"{value}: {count}" for value, count in sorted(strata.items(), key=repr)
        )
        shown.append(f"            {name} strata — {cells}")
    if omitted:
        shown.append(
            f"            ({omitted} further varying features take more than "
            f"{MAX_STRATUM_VALUES} distinct values here; no stratum table is shown for them)"
        )
    return shown


def inert_lines(census: dict[str, Any]) -> list[str]:
    """Objects that appear in NO effect signature anywhere in the store.

    Channel A's primary seed, and the one thing every other section of this digest
    structurally hides: the rest of the digest is organized by what CHANGED, so an object
    that never changes is invisible in it. Both reference discoveries read a STATIC object as
    a specification — sb26 stated the correct goal from layout alone at analysis step 1,
    before any action, and ft09's encoding hypothesis appears at step 5.
    """
    inventory = inert_inventory(census)
    if not inventory:
        return [
            "  none — every colour present in this game's opening frame takes part in at "
            "least one recorded effect. There is no static object to read as a specification."
        ]
    lines = []
    for entry in inventory[:MAX_INERT_SHOWN]:
        top, left, bottom, right = entry["bbox"]
        lines.append(
            f"    colour {entry['colour']:<3d} {entry['cells']:4d} cells, "
            f"{entry['height']}x{entry['width']} box at rows {top}-{bottom}, "
            f"cols {left}-{right}"
            + (
                f"   (one of {entry['objects_of_this_colour']} objects of this colour)"
                if entry["objects_of_this_colour"] > 1
                else ""
            )
        )
    if len(inventory) > MAX_INERT_SHOWN:
        lines.append(
            f"    (+{len(inventory) - MAX_INERT_SHOWN} further inert objects not shown)"
        )
    return lines


def observed_invariants(used: list) -> tuple[list[str], dict[str, Any]]:
    """Joint constraints among the count features that hold in EVERY stored state.

    `notes/e2-slice2.md` digest item 5, added after external review. Every other section
    shows per-feature MARGINALS, and the probe task's impossible requests were reasonable
    inferences from marginals alone — ft09's asked to move one of two counts whose sum is
    fixed by the game. A marginal cannot show that; a joint constraint can, and it costs a
    pass over the stored count vectors.

    An absent `count:C` means the colour has no component in that state, so it enters as 0
    — the miner omits the key rather than writing a zero, and reading the omission as
    "unknown" would drop exactly the states an invariant has to hold in.

    A pair whose two counts are BOTH individually constant is suppressed: its sum and
    difference are constant trivially, and printing them would bury the informative
    invariants under arithmetic.
    """
    colours = sorted(
        {int(name.split(":")[1]) for t in used for name in t.guards if name.startswith("count:")}
    )
    if not colours:
        return ["  none — this evidence has no count features"], {"invariants": 0}
    vectors: list[tuple] = []
    seen: set[tuple] = set()
    for transition in used:
        vector = tuple(int(transition.guards.get(f"count:{c}", 0)) for c in colours)
        if vector not in seen:
            seen.add(vector)
            vectors.append(vector)

    constant = {
        index: vectors[0][index]
        for index in range(len(colours))
        if len({vector[index] for vector in vectors}) == 1
    }
    found: list[str] = []
    for index, value in sorted(constant.items()):
        found.append(f"count:{colours[index]} = {value} in every one of the {len(vectors)} "
                     f"distinct count-states seen")
    for i in range(len(colours)):
        for j in range(i + 1, len(colours)):
            if i in constant and j in constant:
                continue
            sums = {vector[i] + vector[j] for vector in vectors}
            if len(sums) == 1:
                found.append(
                    f"count:{colours[i]} + count:{colours[j]} = {next(iter(sums))} always — "
                    f"these two counts are complements; NOTHING can change one alone"
                )
                continue
            differences = {vector[i] - vector[j] for vector in vectors}
            if len(differences) == 1:
                found.append(
                    f"count:{colours[i]} - count:{colours[j]} = {next(iter(differences))} "
                    f"always — these two counts move together, one for one"
                )
    lines = [f"    {text}" for text in found[:MAX_INVARIANTS_SHOWN]]
    if len(found) > MAX_INVARIANTS_SHOWN:
        lines.append(
            f"    (+{len(found) - MAX_INVARIANTS_SHOWN} further invariants not shown)"
        )
    if not found:
        lines = [
            "    none — no count is constant and no pair of counts has a constant sum or "
            "difference across the stored states"
        ]
    return lines, {
        "invariants": len(found),
        "distinct_count_states": len(vectors),
        "constant_counts": {str(colours[i]): v for i, v in sorted(constant.items())},
        "all": found,
    }


def null_effect_runs(used: list) -> dict[str, Any]:
    """Consecutive stored actions that changed nothing at all. Counts only, no claim."""
    runs: list[int] = []
    current = 0
    for transition in used:
        if transition.effect:
            if current:
                runs.append(current)
            current = 0
        else:
            current += 1
    if current:
        runs.append(current)
    return {
        "null_effect_transitions": sum(runs),
        "runs": len(runs),
        "longest_run": max(runs) if runs else 0,
        "runs_of_5_or_more": sum(1 for run in runs if run >= 5),
    }


def refuted_goals(used: list, post_missing: set[int]) -> dict[str, Any]:
    """Row-C candidates the store itself has already refuted, with the step that did it.

    The `e2_dose.goal_curve` pattern, run for a different purpose. A candidate is refuted the
    first time it is DEFINITELY TRUE at a transition that did not advance the level: the
    board satisfied it and nothing happened, so it is not the completion condition. Those are
    the re-specification events — ft09's L2 recoveries went through exactly this
    contradiction ("matches my decoded pattern, but the level is not complete, so my decoding
    is wrong") while sb26's L2 passes never re-specified and burned their whole budget
    enumerating inside a stale schema.

    SURVIVORS carry no such event by construction (a survivor is one nothing contradicted),
    which is why the section renders the REFUTED candidates: they are where the store's
    negative evidence about the goal actually lives.
    """
    usable = [t for t in used if t.step not in post_missing]
    if not usable:
        return {"skipped": "no transition with a real post frame"}
    universe = ec.enumerate_universe(usable[0].pre)
    if not universe["tractable"]:
        return {"skipped": "row-C universe exceeded the frozen tractability limit"}
    contexts = dsl.transition_contexts(usable)
    alive = [(index, candidate) for index, candidate in enumerate(universe["universe"])]
    events: list[dict[str, Any]] = []
    for transition, context in zip(usable, contexts, strict=True):
        if not alive:
            break
        still: list[tuple[int, dict]] = []
        for index, candidate in alive:
            value = ec.evaluate(candidate, context)
            if value == "unknown":
                still.append((index, candidate))
                continue
            truth = "true" if transition.completed else "false"
            if value == truth:
                still.append((index, candidate))
                continue
            events.append(
                {
                    "step": transition.step,
                    "predicate": dsl.unparse(candidate),
                    "completed": transition.completed,
                }
            )
        alive = still
    return {
        "universe_size": universe["universe_size"],
        "survivors": len(alive),
        "refuted": len(events),
        "satisfied_but_not_advanced": [e for e in events if not e["completed"]],
        "surviving_predicates": sorted(dsl.unparse(c) for _, c in alive),
    }


def negative_evidence_lines(used: list, post_missing: set[int]) -> tuple[list[str], dict]:
    nulls = null_effect_runs(used)
    goals = refuted_goals(used, post_missing)
    lines = [
        f"  Null-effect actions: {nulls['null_effect_transitions']} of {len(used)} stored "
        f"actions changed nothing at all, in {nulls['runs']} consecutive runs "
        f"(longest {nulls['longest_run']}, {nulls['runs_of_5_or_more']} runs of 5 or more). "
        f"This is data about where the evidence is thin, and nothing more is claimed from it.",
    ]
    if "skipped" in goals:
        lines.append(f"  Refuted goal candidates: not computed ({goals['skipped']}).")
        return lines, {"nulls": nulls, "goals": goals}
    # Shown LATEST-refuted first, not earliest. The earliest refutations are the candidates
    # that were trivially true on frame one — on m0r0 all ten of them are refuted at step 2
    # and carry no information. The candidate that survived 800 steps before the board
    # satisfied it and nothing happened is the re-specification event this section exists to
    # supply, and it is the last one refuted, not the first.
    satisfied = sorted(
        goals["satisfied_but_not_advanced"],
        key=lambda event: (-event["step"], event["predicate"]),
    )
    lines.append(
        f"  Goal candidates this evidence has already REFUTED: {len(satisfied)} of "
        f"{goals['universe_size']} mechanically enumerated candidates were SATISFIED by the "
        f"board at some step at which the level did NOT advance. A predicate that is true "
        f"while nothing happens is not this level's completion condition. "
        f"{goals['survivors']} candidates are still standing."
    )
    for event in satisfied[:MAX_REFUTED_GOALS_SHOWN]:
        lines.append(
            f"    `{event['predicate']}` was satisfied at step {event['step']} — "
            f"the level did not advance"
        )
    if len(satisfied) > MAX_REFUTED_GOALS_SHOWN:
        lines.append(
            f"    (+{len(satisfied) - MAX_REFUTED_GOALS_SHOWN} further refuted candidates "
            f"not shown; the ones above are those that survived the most evidence before "
            f"being refuted)"
        )
    return lines, {"nulls": nulls, "goals": goals}


def resolved_rules(rules: dict[str, Rule]) -> dict[tuple, str]:
    """Per action key, the miner's own resolved rules as one printable line.

    Feeds the action gallery (`notes/e2-slice3.md` item 6): a mechanic the miner has already
    solved is shown SOLVED, so the window is spent on what is unsolved rather than on
    re-deriving what is known. `majority`-tier rules are excluded — that tier IS the miner's
    "I could not resolve this key", and printing a guess as a rule is the one thing the
    gallery must not do.
    """
    out: dict[tuple, list[str]] = {}
    for rule in sorted(rules.values(), key=lambda r: -r.support):
        if rule.tier == "majority":
            continue
        guard = "" if rule.guard is None else f" WHEN {rule.guard}={rule.guard_value}"
        out.setdefault(rule.key, []).append(
            f"[{rule.tier}]{guard} -> {_effect_text(rule.effect)} (support {rule.support})"
        )
    return {key: "; ".join(texts) for key, texts in out.items()}


_DIGEST_CACHE: dict[tuple[str, Any], dict[str, Any]] = {}

# Rev 2: the v3 digest's EVIDENCE CONTENT is unchanged in v4 — only its section headers gain
# a provenance tag. Slice 2 blurred the distinction and a mined majority-tier rule was read
# as ground truth. Applied as a post-pass over the v3 text so the v3 builder stays untouched
# and an unframed run still reproduces slice 2's prompt character for character.
PROVENANCE_TAGS = {
    "ACTION INVENTORY": "OBSERVED",
    "OBJECT CENSUS": "OBSERVED",
    "RULES THE MECHANICAL MINER RESOLVED": "MINER-INFERRED",
    "KEYS THE MINER COULD NOT RESOLVE": "MINER-INFERRED",
    "STATE IDENTITY": "REPLAY-VERIFIED",
    "COVERAGE LEDGER": "OBSERVED",
    "INERT OBJECTS": "OBSERVED",
    "OBSERVED INVARIANTS": "OBSERVED",
    "NEGATIVE EVIDENCE": "OBSERVED",
    "LEVEL COMPLETION": "OBSERVED",
}


def tag_provenance(text: str) -> str:
    lines = text.split("\n")
    for index, line in enumerate(lines):
        for header, tag in PROVENANCE_TAGS.items():
            if line.startswith(header):
                lines[index] = f"{line}   [{tag}]"
                break
    return "\n".join(lines)


def build_digest(
    game: str, dose: int | None, *, with_frames: bool = False, caps: Any = None
) -> dict[str, Any]:
    """Digest v3, plus digest v4's rendered block when asked for it.

    The v3 half is cached per (game, dose) because it is deterministic and expensive — the
    row-C refuted-goal stream alone is ~45 s on the 3,000-transition stores — and slice 3's
    trim ladder rebuilds the digest once per trial. Without the cache, fitting one dense game
    to the token budget would cost seven minutes of pure recomputation of a block that cannot
    change.
    """
    key = (game, dose)
    if key not in _DIGEST_CACHE:
        _DIGEST_CACHE[key] = _build_digest_v3(game, dose)
    digest = dict(_DIGEST_CACHE[key])
    if not with_frames:
        digest["frames"] = {"rendered": False}
        return digest

    # DIGEST v4. Everything above is v3, unchanged and in the same order — the frames are
    # APPENDED, so a v4 prompt contains a v3 prompt as a prefix and the two slices differ by
    # exactly one block. Without `--frames` this does not run and the digest is slice 2's,
    # character for character (asserted against last night's committed traces).
    used, rules, _ = mined(game, dose)
    _, post_missing = store_with_gaps(game)
    block, frames_meta = frames.frames_section(
        game,
        used,
        post_missing,
        unresolved_keys(rules),
        key_text=_key_text,
        effect_text=_effect_text,
        effect_mode=lambda effect: abstract(effect, MODE),
        resolved=resolved_rules(rules),
        refuted_events=digest["negative_evidence"]["satisfied_but_not_advanced_events"],
        completion=load_completion(game),
        alias_probe=load_alias_probe(game),
        caps=caps,
    )
    frames_meta["rendered"] = True
    frames_meta["chars"] = len(block)
    digest["frames"] = frames_meta
    digest["text"] = f"{tag_provenance(digest['text'])}\n{block}\n"
    digest["chars"] = len(digest["text"])
    return digest


def _build_digest_v3(game: str, dose: int | None) -> dict[str, Any]:
    used, rules, _ = mined(game, dose)

    census = Counter()
    sampled = used[: min(len(used), 200)]
    for transition in sampled:
        for guard, value in transition.guards.items():
            if guard.startswith("count:"):
                census[guard.split(":")[1]] = max(census[guard.split(":")[1]], value)

    by_key: dict[tuple, list] = {}
    for transition in used:
        by_key.setdefault(transition.key(), []).append(transition)

    rule_lines = []
    for rule in sorted(rules.values(), key=lambda r: -r.support)[:MAX_RULES_SHOWN]:
        if rule.tier == "majority":
            continue  # unresolved keys get their own section, with their evidence
        guard = "" if rule.guard is None else f"  WHEN {rule.guard}={rule.guard_value}"
        rule_lines.append(
            f"  [{rule.tier}] {_key_text(rule.key)}{guard}  ->  {_effect_text(rule.effect)}"
            f"   (support {rule.support})"
        )

    pending = unresolved_keys(rules)
    unresolved_lines = []
    for key in pending[:MAX_UNRESOLVED_SHOWN]:
        rows = by_key.get(key, [])
        effects = Counter(abstract(row.effect, MODE) for row in rows)

        # Only guards that VARY across this key's transitions can possibly separate them.
        values: dict[str, set] = {}
        for row in rows:
            for name, value in row.guards.items():
                values.setdefault(name, set()).add(_hv(value))
        varying = [name for name, seen in sorted(values.items()) if len(seen) > 1]
        constant_note = "" if varying else "  (NO guard in the vocabulary varies here at all)"
        unresolved_lines.append(
            f"  {_key_text(key)} — {len(rows)} transitions, {len(effects)} distinct effects, "
            f"no single guard separates them:{constant_note}"
        )
        # Autopsy rec 1: the COMPLETE value set per feature within each effect group —
        # slice 1's one-example row was read as a group constant by 59 of 84 proposals.
        for effect, count in effects.most_common(MAX_EVIDENCE_PER_KEY):
            group = [row for row in rows if abstract(row.effect, MODE) == effect]
            parts = []
            for name in (varying if MAX_FEATURES_PER_GROUP is None
                         else varying[:MAX_FEATURES_PER_GROUP]):
                seen = sorted({_hv(row.guards.get(name)) for row in group}, key=repr)
                vals = ", ".join(str(v) for v in seen[:MAX_VALUES_PER_FEATURE])
                if len(seen) > MAX_VALUES_PER_FEATURE:
                    vals += f", +{len(seen) - MAX_VALUES_PER_FEATURE} more"
                parts.append(f"{name} in {{{vals}}}")
            unresolved_lines.append(f"      x{count:<4d} {_effect_text(effect)}")
            if parts:
                unresolved_lines.append(f"            {'; '.join(parts)}")
        # v3: the stratum counts. The value sets say WHICH values occur; these say how many
        # transitions carry each, which is what separates "already tested to death" from
        # "one observation" — the distinction 26 of 31 probe arms failed to make.
        unresolved_lines.extend(stratum_lines(rows, varying))
        # Autopsy rec 2: the miner's assertion carries its own evidence — the best single
        # feature shown FAILING. 55 of 84 slice-1 proposals overrode the bare assertion.
        witness = _no_separation_witness(rows, varying)
        if witness is not None:
            name, value, (effect_a, n_a), (effect_b, n_b) = witness
            unresolved_lines.append(
                f"      NO-SEPARATION WITNESS — the best single feature `{name}` still "
                f"fails: at {name}={value}, x{n_a} gave {_effect_text(effect_a)} while "
                f"x{n_b} gave {_effect_text(effect_b)}"
            )

    identity_lines = state_identity(game)
    _, post_missing = store_with_gaps(game)
    ledger_lines = coverage_ledger(used, by_key)
    catalogue = object_census(used)
    inert = inert_lines(catalogue)
    negative_lines, negative_data = negative_evidence_lines(used, post_missing)
    invariant_lines, invariant_data = observed_invariants(used)

    completion = next((t for t in used if t.completed), None)
    completion_line = (
        f"  {_key_text(completion.key())} completed the level at step {completion.step}"
        if completion is not None
        else "  none — this run never completed level 1"
    )

    text = f"""GAME {game}, evidence dose {"full store" if dose is None else dose} transitions.

Every fact below was derived mechanically from one autonomous exploration run of level 1.

ACTION INVENTORY (keys the evidence contains)
{chr(10).join(f"  {_key_text(k)}: {len(v)} transitions" for k, v in sorted(by_key.items(), key=lambda i: -len(i[1]))[:20])}

OBJECT CENSUS (max simultaneous components per colour, over the first {len(sampled)} transitions)
  {dict(sorted(census.items()))}

RULES THE MECHANICAL MINER RESOLVED ({len(rules)} total, top {MAX_RULES_SHOWN} by support)
{chr(10).join(rule_lines) if rule_lines else (
    "  none — every mined rule at this dose is a majority-tier guess for a key listed below"
    if rules else "  none")}

KEYS THE MINER COULD NOT RESOLVE — the actual problem
  A key is unresolved when its transitions disagree about the effect and NO SINGLE guard
  feature in the miner's vocabulary separates them. The vocabulary is: present:C, count:C,
  adj:C:direction (the first non-background colour met stepping one cell out from colour C's
  single object, or "edge"), clicked_adjacent_to:C (ACTION6 only — does the 4-connected
  same-colour component under the click touch any cell of colour C), click_colour,
  click_on_background. A guard tests exactly
  `feature = one literal value`; negation, inequalities, thresholds and combined conditions
  do not exist and cannot be tested.
  READ THE VALUE SETS LITERALLY. For each effect group, every feature that VARIES anywhere
  in this key is listed, with the set of values it takes within that group. A one-element
  set means constant within that group; a multi-element set means the feature took ALL of
  those values while producing the same effect. A set ending "+N more" is truncated at
  {MAX_VALUES_PER_FEATURE} values and N further values are not shown; an unmarked set is complete.
  A feature ABSENT from these lines is constant across every transition of this key, so it
  cannot separate anything — that inference is sound here, but it is the ONLY thing absence
  licenses. Only the {MAX_EVIDENCE_PER_KEY} largest effect groups are shown; if the header
  reports more distinct effects than there are groups below, the remainder are omitted.
  Each key ends with a NO-SEPARATION WITNESS: the single feature that comes CLOSEST to
  separating the key, shown failing on concrete counts. It is the best available, not a
  good one — a feature that splits two groups cleanly can still fail the key, because
  separating the key means telling ALL of its effects apart.
{chr(10).join(unresolved_lines) if unresolved_lines else "  none"}

STATE IDENTITY — does the settled frame below fully identify the game's state?
{chr(10).join(identity_lines)}

COVERAGE LEDGER — what has and has NOT been tried
  Read the never-tried marks as literally as the value sets. This evidence is one autonomous
  run; an object nothing was ever aimed at is not an object shown to be inert, and the two
  are told apart only by this section and the next one.
{chr(10).join(ledger_lines)}

INERT OBJECTS — present in the opening frame, never once changed
  These objects appear in NO effect signature anywhere in the evidence: they never moved,
  never changed shape, never appeared and never disappeared. Every other section of this
  digest is organized by what CHANGED, so this is the only place they are visible. Positions
  are from the opening frame; an inert object has no other.
{chr(10).join(inert)}

OBSERVED INVARIANTS — joint constraints the counts obey in EVERY stored state
  The census above gives each count on its own. These are constraints BETWEEN counts that
  held in every state this run visited. They bound what an action can possibly do: if two
  counts always sum to a fixed number, no action changes one of them alone, and asking for
  one is asking for something this game does not offer. A colour with no object in a state
  counts as 0 there.
{chr(10).join(invariant_lines)}

NEGATIVE EVIDENCE — what this run has already ruled out
{chr(10).join(negative_lines)}

LEVEL COMPLETION
{completion_line}
"""
    return {
        "game": game,
        "dose": dose,
        "text": text,
        "store_transitions": len(used),
        "miner_rules": len(rules),
        "unresolved_keys": len(pending),
        "unresolved_shown": min(len(pending), MAX_UNRESOLVED_SHOWN),
        "inert_objects": len(inert_inventory(catalogue)),
        "observed_invariants": invariant_data,
        "negative_evidence": {
            "null_effect_runs": negative_data["nulls"],
            "row_c": {
                key: value
                for key, value in negative_data["goals"].items()
                if key != "satisfied_but_not_advanced"
            },
            "satisfied_but_not_advanced": len(
                negative_data["goals"].get("satisfied_but_not_advanced", [])
            ),
            # The events themselves, for slice 3's block 3b — the boards that satisfied a
            # candidate while the level did not advance. v3 renders them as predicate names;
            # v4 renders the boards. Not written to the result file (`run_cell` drops it).
            "satisfied_but_not_advanced_events": negative_data["goals"].get(
                "satisfied_but_not_advanced", []
            ),
        },
        "chars": len(text),
    }


PROMPT = """You are analysing an unfamiliar grid-puzzle game from mechanically extracted evidence.

{digest}

An object is a 4-connected same-colour component, measured against the state's background
(its most common colour). An effect is position-free: move(colour,dr,dc), reshape(colour),
appear(colour), disappear(colour), or no-change. A recolour appears as disappear+appear.

Do NOT propose transition rules. The mechanical miner's unresolved keys were asked for twice
and answered twice with nothing; that channel is closed and anything you write about it is
discarded unread. Reason about the evidence as much as you like, then answer exactly three
questions, A, B and C.

{predicate_grammar}

{counter_grammar}

{frames_preamble}A. GOAL — one falsifiable predicate, its refuter, and one test action.
   * PREDICATE: what must be true of the board for this level to be complete, written in the
     predicate grammar above. The NEGATIVE EVIDENCE section lists predicates this run has
     already refuted: a predicate that was satisfied while the level did not advance is not
     the completion condition, and re-proposing one of them is a wasted answer.
   * REFUTER: a second predicate, in the same grammar — the single observation that would
     falsify your predicate if it were seen. Check it against the evidence before you write
     it: a refuter that the stored evidence already satisfies refutes your own proposal.
   * TEST ACTION: one concrete action whose outcome bears on the predicate, as
     (precondition, action id, click target). The precondition is one guard `feature=value`
     from the vocabulary above, or `none`. The click target is a colour for ACTION6 and
     `n/a` otherwise. A goal with no action attached to it is not yet usable: read the
     COVERAGE LEDGER and prefer an action that has NOT been tried.

B. LATENTS — at most 3 candidate hidden variables, each as `name: <counter expression>` in
   the counter grammar above. Propose one only if the STATE IDENTITY section reports states
   that do not replay to themselves; if every state replays, say so and propose none rather
   than inventing one. Never infer "no hidden state" from a short conflict list.

C. VOCABULARY — at most 2 proposals for a feature the guard vocabulary is MISSING. Each as:
   a name, a definition sketch computable from the pre-action board and the action alone,
   the unresolved keys above it should resolve, and the direction you expect it to move
   them. This is the one channel that has already paid out: a previous slice named a missing
   word that became `clicked_adjacent_to:C` and moved the mechanical floor by 0.05.
"""

# ======================================================================================
# SLICE 3's prompt — the same three channels, with the frozen interface defects fixed
# ======================================================================================
#
# `notes/e2-slice3.md` rev 2. Slice 2's PROMPT above is NOT edited: an unframed run has to
# reproduce a slice-2 cell character for character, and that equivalence is asserted against
# last night's committed traces. Slice 3 gets its own template.
#
# Three defects are fixed here, deliberately, at the cost of single-variable attribution:
#
#   * THE REFUTER FIELD IS GONE. It asked for "the single observation that would falsify
#     your predicate", and the scorer counted a refuter the store already satisfied as
#     self-refutation. That is not what refutes a completion condition: for a condition G the
#     discriminating observations are `G true AND the level did not advance` or `completion
#     AND G false`, and a bare predicate being true somewhere refutes nothing. Slice 2's
#     "self-refuting 10/16" measured a broken instrument and is withdrawn. What replaces it
#     is COMPUTED from the record rather than claimed by the model.
#   * `evidence_ids` REPLACES FREE-TEXT CITATION. Grounding is a schema field, checkable
#     against the record's own step numbers and entity ids — counting citations out of prose
#     would be a text-matching exercise.
#   * ONE OUT-OF-DSL SLOT. The grammar cannot express ft09-class per-clue match/differ
#     constraints, so a model can read the board correctly and still be forced into a wrong
#     aggregate predicate. The free-form condition is adjudicated separately and is NEVER a
#     win against the prior library — that control has no free-form output, so the comparison
#     would be unmatched. It measures understanding, not channel-A victory.
#
# CONTAMINATION HARD RULE: this text must never name the five stock goal shapes. They are
# channel A's control, and naming them would turn `in_prior_library` from convergence into
# compliance. The anchor is gone too — slice 2 was told `clicked_adjacent_to:C` was the
# previous channel-C win and duly re-proposed it.
PROMPT_V4 = """You are analysing an unfamiliar grid-puzzle game from a record of one autonomous run.

{digest}

An object is a 4-connected same-colour component, measured against the state's background
(its most common colour). An effect is position-free: move(colour,dr,dc), reshape(colour),
appear(colour), disappear(colour), or no-change. A recolour appears as disappear+appear.

Do NOT propose transition rules. The mechanical miner's unresolved keys were asked for twice
and answered twice with nothing; that channel is closed and anything you write about it is
discarded unread.

{predicate_grammar}

{counter_grammar}

HOW TO THINK BEFORE YOU ANSWER
Work through these headings, in this order, in your own reasoning:
  World model      what this level contains and how its parts relate
  Goal candidates  several different conditions that would explain a completed level
  Action model     what each action does, and what is still unknown about it
  Hidden state     whether anything not visible on the board is deciding outcomes
  Contradictions   which of your candidates the record above already rules out, and where
  Open questions   what this record cannot decide, and what observation would decide it
Generate several goal candidates. Eliminate the ones the record contradicts. Emit the one
that survives. A candidate you did not try to contradict is not a candidate you tested.

Then answer A, B and C.

A. GOAL — what must be true of the board for this level to be complete.
   * PREDICATE: one predicate in the grammar above. The record lists conditions this run has
     already refuted — a condition satisfied by the board at a step where the level did NOT
     advance is not the completion condition, and re-proposing one is a wasted answer.
   * EVIDENCE: the specific things in the record that support it, as a short list of ids.
     An id is `step <n>` for a stored action, `entity #<n>` for a row of the entity map, or
     one of `initial board`, `solved board`, `next level board`. Cite what you actually
     used; these are checked against the record.
   * TEST ACTION: one concrete action whose outcome bears on the predicate, as
     (precondition, action id, click target). The precondition is one guard `feature=value`
     from the vocabulary above, or `none`. The click target is a colour for ACTION6 and
     `n/a` otherwise. A goal with no action attached to it is not yet usable: read the
     COVERAGE LEDGER and prefer an action that has NOT been tried.
   * IF THE GRAMMAR CANNOT SAY IT: the grammar is small and this level's real condition may
     not be expressible in it. If so, still give your best predicate above, and ALSO state
     the real condition in one plain sentence. Say it plainly and concretely — name the
     colours, the entities and the relation. This is read separately and costs you nothing.

{latents_request}
C. VOCABULARY — at most 2 proposals for a feature the guard vocabulary is MISSING. Each as:
   a name, a definition sketch computable from the pre-action board and the action alone,
   the unresolved keys above it should resolve, and the direction you expect it to move
   them.
"""

# Channel B is SUPPRESSED where the record holds no alias exhibit. Rev 2: on seven of the
# eight games nothing in the record is evidence of hidden state, and asking anyway is asking
# for invention — slice 2's twelve latents were all unselected by the miner and all tied
# their random controls to four decimals.
LATENTS_REQUEST = """B. LATENTS — at most 3 candidate hidden variables, each as `name: <counter expression>` in
   the counter grammar above. The record shows the SAME board reached by two different
   histories and then diverging under the same action, so something not visible on the board
   is deciding the outcome. Propose what it counts.

"""

LATENTS_SUPPRESSED = """B. LATENTS — none are asked for on this game. Nothing in this record shows one board
   producing two different outcomes for the same action, so there is no observation here for
   a hidden variable to explain. Anything you write about latents is discarded unread.

"""

EXTRACT = """Below is an analysis of a grid game. Re-read it and transcribe its conclusions into JSON.
Do not add, judge, or correct anything — transcribe only what is stated. Copy the predicate
and counter expressions CHARACTER FOR CHARACTER; do not tidy, complete or reformat them.

{answer}

Emit ONLY a JSON object, no commentary:
{{"goal": {{"predicate": "<expression, exactly as written>",
           "refuter": "<expression, exactly as written, or empty>",
           "test_action": {{"precondition": null or {{"feature": "<e.g. adj:3:up>", "value": <int, string or bool>}},
                           "action_id": <int 1-7>, "click_colour": <int or null>}}}},
 "latents": [{{"name": "<short name>", "definition": "<counter expression, exactly as written>"}}],
 "vocabulary": [{{"name": "<short name>", "definition_sketch": "<one sentence>",
                 "targeted_keys": ["<e.g. ACTION6 on colour 3>"],
                 "expected_direction": "<one sentence>"}}]}}
If the analysis states nothing for a section, return an empty list or null for it. Never
invent an expression that the analysis does not contain."""

EXTRACT_V4 = """Below is an analysis of a grid game. Re-read it and transcribe its conclusions into JSON.
Do not add, judge, or correct anything — transcribe only what is stated. Copy the predicate
and counter expressions CHARACTER FOR CHARACTER; do not tidy, complete or reformat them.

{answer}

Emit ONLY a JSON object, no commentary:
{{"goal": {{"predicate": "<expression, exactly as written>",
           "evidence_ids": ["<e.g. step 412>", "<e.g. entity #7>", "<e.g. solved board>"],
           "free_form": "<the plain-sentence condition, if the analysis gives one, else empty>",
           "test_action": {{"precondition": null or {{"feature": "<e.g. adj:3:up>", "value": <int, string or bool>}},
                           "action_id": <int 1-7>, "click_colour": <int or null>}}}},
 "latents": [{{"name": "<short name>", "definition": "<counter expression, exactly as written>"}}],
 "vocabulary": [{{"name": "<short name>", "definition_sketch": "<one sentence>",
                 "targeted_keys": ["<e.g. ACTION6 on colour 3>"],
                 "expected_direction": "<one sentence>"}}]}}
If the analysis states nothing for a section, return an empty list or null for it. Never
invent an expression, an id, or a sentence that the analysis does not contain."""


# ======================================================================================
# Model
# ======================================================================================


class Qwen:
    def __init__(self, path: Path):
        from mlx_lm import load

        self.path = path
        self.model, self.tokenizer = load(str(path))

    def generate(
        self,
        messages: list,
        *,
        max_tokens: int,
        thinking: bool,
        temp: float = TEMP,
        seed: int | None = None,
    ) -> dict[str, Any]:
        import mlx.core as mx
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        if seed is not None:
            mx.random.seed(seed)
        prompt = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=thinking, tokenize=False
        )
        opens_think = prompt.rstrip().endswith("<think>")
        prefilled = "<think>\n\n</think>" in prompt
        # Phase 2 is transcription, so it decodes GREEDILY (temp=0): a sampled transcription
        # can lose a rule the analysis actually stated, and a parse failure costs the whole
        # ~20-minute cell.
        sampler = make_sampler(temp=temp, top_p=TOP_P if temp > 0 else 1.0)
        pieces: list[str] = []
        gen_tps = prompt_tps = None
        start = time.monotonic()
        for response in stream_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
        ):
            pieces.append(response.text)
            gen_tps = getattr(response, "generation_tps", None)
            prompt_tps = getattr(response, "prompt_tps", None)
        completion = "".join(pieces)
        full = ("<think>" + completion) if opens_think else completion
        closed = "</think>" in full
        body = full.split("<think>", 1)[-1].split("</think>", 1)[0] if "<think>" in full else ""
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        return {
            "prompt_chars": len(prompt),
            "prefilled_empty_think": prefilled,
            "prompt_opens_think": opens_think,
            "think_opened": "<think>" in full,
            "think_closed": closed,
            "think_chars": len(body.strip()),
            "answer": answer if thinking else completion.strip(),
            "raw": completion,
            "wall_seconds": round(time.monotonic() - start, 1),
            "prompt_tps": prompt_tps,
            "generation_tps": gen_tps,
            "temp": temp,
            "seed": seed,
        }


def thinking_verdict(call: dict[str, Any]) -> dict[str, bool]:
    return {
        "no_prefilled_empty_think": not call["prefilled_empty_think"],
        "think_opened": call["think_opened"],
        "think_closed": call["think_closed"],
        "think_substantive": call["think_chars"] >= 200,
        "answer_nonempty": bool(call["answer"]),
    }


# ======================================================================================
# Proposal parsing, verification, scoring
# ======================================================================================


_TOKENIZER = None


def token_count(text: str, model: Path = MODEL) -> int:
    """Real tokens, from the model's own tokenizer. Never characters, never an estimate.

    Slice 2's pre-flight measured why: digest v3 grew 59% in characters and the think block
    did not move, because the growth was all prefill. A character budget would have been a
    budget on the wrong quantity in both directions.
    """
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import AutoTokenizer

        _TOKENIZER = AutoTokenizer.from_pretrained(str(model))
    return len(_TOKENIZER.encode(text))


# The trim ladder, in the order rev 2 fixes: the episode's diff span first, then the matched
# contrasts (down to one per outcome class), then the entity table's columns. Blocks 3 and 5 —
# the completion exhibit and the alias exhibit — are NEVER on it. Block 3 is the priority
# exhibit and the only solved board this project holds; block 5 is two exhibits on one game,
# so trimming it means deleting it.
TRIM_LADDER = (
    {},
    {"episode_steps": 45},
    {"episode_steps": 30},
    {"episode_steps": 20, "diff_cells": 6},
    {"episode_steps": 12, "diff_cells": 6},
    {"episode_steps": 12, "diff_cells": 6, "gallery_examples": 1},
    {"episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1},
    {
        "episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1,
        "entity_columns": "compact",
    },
    {
        "episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1,
        "entity_columns": "compact", "gallery_keys": 5,
    },
    # Below here the record is genuinely thinner, and a run that reaches these steps says so
    # in its output. The order still respects rev 2: the episode's own snapshots and the
    # matched contrasts go before anything else, and blocks 3 and 5 are never touched.
    {
        "episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1,
        "entity_columns": "compact", "gallery_keys": 5, "snapshots": 1, "global_examples": 1,
    },
    {
        "episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1,
        "entity_columns": "compact", "gallery_keys": 5, "snapshots": 0, "global_examples": 1,
        "unresolved_keys": 6,
    },
    {
        "episode_steps": 12, "diff_cells": 6, "gallery_examples": 1, "key_examples": 1,
        "entity_columns": "compact", "gallery_keys": 4, "snapshots": 0, "global_examples": 1,
        "unresolved_keys": 3,
    },
)


def fit_caps(
    game: str,
    dose: int | None,
    budget: int,
    model: Path = MODEL,
    fb_budget: int = FB_TOKEN_BUDGET,
) -> tuple[frames.FrameCaps, dict[str, Any]]:
    """The loosest caps satisfying BOTH ceilings, and what it cost.

    Every trial is reported, and a game that fits none of them is reported OVER BUDGET with
    its measured count rather than trimmed further in silence. A cap that quietly drops
    evidence is the failure mode slice 1.1 paid for: the digest asserted complete value sets
    while showing six features, and 21 of 24 traces then reasoned from the omission.
    """
    trials: list[dict[str, Any]] = []
    chosen = None
    for step, overrides in enumerate(TRIM_LADDER):
        caps = frames.FrameCaps(**overrides)
        digest = build_digest(game, dose, with_frames=True, caps=caps)
        prompt = build_prompt(digest)
        f_tokens = token_count(prompt, model)
        # The FB chat is the binding one. Measured, not assumed: the counterexample renders a
        # full board of THIS game, and the chat template's own turn scaffolding is applied by
        # counting the assembled three-message conversation rather than summing the parts.
        fb_tokens = token_count(
            prompt + REVISE.format(counterexample=worst_counterexample(game)), model
        ) + FB_ANSWER_ALLOWANCE
        trials.append(
            {
                "step": step,
                "overrides": overrides,
                "f_prompt_tokens": f_tokens,
                "fb_chat_tokens": fb_tokens,
            }
        )
        if f_tokens <= budget and fb_tokens <= fb_budget:
            chosen = (caps, step, f_tokens, fb_tokens)
            break
    if chosen is None:
        caps = frames.FrameCaps(**TRIM_LADDER[-1])
        chosen = (
            caps,
            len(TRIM_LADDER) - 1,
            trials[-1]["f_prompt_tokens"],
            trials[-1]["fb_chat_tokens"],
        )
    caps, step, f_tokens, fb_tokens = chosen
    return caps, {
        "f_budget": budget,
        "fb_budget": fb_budget,
        "f_prompt_tokens": f_tokens,
        "fb_chat_tokens": fb_tokens,
        "f_within_budget": f_tokens <= budget,
        "fb_within_budget": fb_tokens <= fb_budget,
        "within_budget": f_tokens <= budget and fb_tokens <= fb_budget,
        # Rev 2.1: a cell whose FB chat will not fit even after the full trim runs F ONLY.
        # Recorded here so the readout reports it as a cell that had no feedback turn, rather
        # than as a cell whose feedback turn found nothing to say.
        "feedback_possible": fb_tokens <= fb_budget,
        "trim_step": step,
        "trimmed": step > 0,
        "caps": caps.__dict__.copy(),
        "trials": trials,
    }


def worst_counterexample(game: str) -> str:
    """The largest counterexample the FB turn could render for this game.

    A full board plus the prose around it. This is an upper bound by construction: the
    false-negative branch renders no board at all, and the false-positive branch renders
    exactly one, so nothing the arm can produce is larger than this.
    """
    store = store_for(game)
    if not store:
        return ""
    return "\n".join(
        [
            "YOUR CONDITION, AS WRITTEN: " + "x" * 120,
            "At step 99999 of this run it was TRUE of the board — and the level did NOT "
            "advance. A condition the board satisfies while nothing happens is not this "
            "level's completion condition. It survived 9999 earlier boards before this one "
            "refuted it.",
            "THE BOARD THAT REFUTED IT, in full, at that step:",
            *frames.render_grid(store[0].pre),
        ]
    )


def build_prompt(digest: dict[str, Any]) -> str:
    """The phase-1 prompt. Without frames this is slice 2's prompt, character for character.

    `frames_preamble` is the only slot that differs, and it is empty for a v3 digest — the
    template's own blank line does the spacing, so an unframed slice-3 run reproduces a
    slice-2 cell exactly. That equivalence is the point of the flag: the two slices are meant
    to differ by CONTEXT alone, and a prompt that drifted by a newline would make the
    slice-2-vs-slice-3 comparison an uncontrolled one.
    """
    if not digest["frames"].get("rendered"):
        return PROMPT.format(
            digest=digest["text"],
            predicate_grammar=dsl.PREDICATE_GRAMMAR_TEXT,
            counter_grammar=dsl.COUNTER_GRAMMAR_TEXT,
        )
    return PROMPT_V4.format(
        digest=digest["text"],
        predicate_grammar=dsl.PREDICATE_GRAMMAR_TEXT,
        counter_grammar=dsl.COUNTER_GRAMMAR_TEXT,
        latents_request=(
            LATENTS_REQUEST if has_alias_exhibit(digest["game"]) else LATENTS_SUPPRESSED
        ),
    )


def extract_payload(
    qwen: Qwen, answer: str, tag: str, seed: int, template: str = EXTRACT
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Phase 2: a separate mechanical transcription call over phase 1's own answer text.

    Thinking off by design — it re-reads, it does not reason — and greedy, because a sampled
    transcription can lose a proposal the analysis actually made and a parse failure costs
    the whole cell.
    """
    attempts: list[dict[str, Any]] = []
    payload = None
    for attempt in range(2):
        # Greedy decoding makes a bare retry a no-op — attempt 1 would reproduce attempt 0
        # byte for byte. The second attempt therefore changes the PROMPT, not the sampler,
        # so the retry can actually pay out while staying deterministic given the transcript.
        content = template.format(answer=answer)
        if attempt:
            content = (
                "Your previous reply was not valid JSON. Emit the JSON object only — no "
                "prose, no code fence, no trailing text.\n\n" + content
            )
        extract = qwen.generate(
            [{"role": "user", "content": content}],
            max_tokens=EXTRACT_BUDGET,
            thinking=False,
            temp=0.0,
            seed=seed + attempt,
        )
        attempts.append(extract)
        (TRACES / f"{tag}.extract{attempt}.json").write_text(json.dumps(extract, indent=2))
        payload = parse_json(extract["answer"])
        if payload is not None:
            break
    return payload, attempts


def parse_json(text: str) -> dict[str, Any] | None:
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


def prior_library(game: str) -> tuple[set[str], set[str]] | None:
    """The control's surviving predicates: `(canonical strings, shape skeletons)`.

    Two sets, because a novelty hit has two readings and the pre-committed readout scores
    them differently (`notes/e2-slice2.md` §readout 1, amended 2026-08-05). The canonical
    set answers "did the model write a predicate this control also wrote". The skeleton set
    answers "did it write one of the five stock SHAPES at all" — a proposal that clears the
    first test but not the second is a re-binding of a prior, not a goal the prior
    vocabulary cannot reach.

    None means the library has not been built yet — the novelty check then reports itself
    as not computed. Silently treating a missing control as an empty one would score every
    proposal as novel, which is the direction that flatters the channel.
    """
    if not PRIOR_LIBRARY.is_file():
        return None
    document = json.loads(PRIOR_LIBRARY.read_text())
    row = document.get("games", {}).get(game)
    if row is None or "shapes" not in row:
        return None
    surviving = [
        candidate["dsl"] for shape in row["shapes"].values() for candidate in shape["surviving"]
    ]
    return (
        {dsl.canonical(text) for text in surviving},
        {dsl.skeleton(text) for text in surviving},
    )


def channel_a(
    payload: dict[str, Any], game: str, used: list, post_missing: set[int], vocabulary: set[str]
) -> dict[str, Any]:
    """Parse, then the four mechanical scores. Adjudication against source is NOT here.

    Clause 1 of the rubric (store consistency) is row C's own three-valued survivorship.
    Clause 2 (refuter validity) is the S1 finding made mechanical: a refuter the stored
    evidence ALREADY satisfies refutes the proposal it was supposed to protect, and the
    reference's failure mode was exactly holding a falsifier and never applying it. Clause 4
    (novelty) is a canonical-string comparison against the prior library. Clause 3
    (correctness vs source) is deliberately absent — labels only, one adjudication pass over
    channel and control together, at scoring time.
    """
    goal = payload.get("goal")
    if not isinstance(goal, dict):
        return {"status": "absent", "raw": goal}

    out: dict[str, Any] = {}
    predicate = dsl.classify_predicate(goal.get("predicate"))
    out["predicate"] = {k: v for k, v in predicate.items() if k != "ast"}
    if predicate["status"] != "parsed":
        out["status"] = "prose_rejected"
        return out

    usable = [t for t in used if t.step not in post_missing]
    contexts = dsl.transition_contexts(usable)
    out["store_consistency"] = dsl.consistent_with(
        predicate["ast"], usable, contexts=contexts
    )
    out["store_consistency"]["negative_transitions"] = len(usable)
    # sp80 and lf52 are the two games whose store holds a completion, and in BOTH the
    # explorer never retained that row's post frame, so the count below is 0 everywhere.
    # Clause 1 of the rubric's own-completion-positive half is unmeasurable on the frozen
    # v2 store — see the header of `e2_prior_library.py`.
    out["store_consistency"]["positives_evaluable"] = sum(1 for t in usable if t.completed)

    refuter = dsl.classify_predicate(goal.get("refuter"))
    out["refuter"] = {k: v for k, v in refuter.items() if k != "ast"}
    if refuter["status"] == "parsed":
        satisfied = [
            transition.step
            for transition, context in zip(usable, contexts, strict=True)
            if dsl.evaluate(refuter["ast"], context) == dsl.TRUE
        ]
        out["refuter"]["satisfied_by_store_at"] = satisfied[:10]
        out["refuter"]["self_refuting"] = bool(satisfied)

    library = prior_library(game)
    if library is None:
        out["novelty"] = {
            "computed": False,
            "reason": f"{PRIOR_LIBRARY.name} absent or has no row for {game}",
        }
    else:
        canonical_set, skeleton_set = library
        in_library = predicate["canonical"] in canonical_set
        in_shapes = dsl.skeleton(predicate["ast"]) in skeleton_set
        out["novelty"] = {
            "computed": True,
            # readout clause 4, the binding verdict: this predicate is not one the control
            # also produced. `library_size` travels with it because the strength of the
            # claim depends on how wide the net was — 24 surviving candidates on m0r0
            # against 252 on dc22.
            "in_prior_library": in_library,
            "library_size": len(canonical_set),
            # the second reading: same stock shape, different colour binding. A proposal
            # that is novel by string but not by shape is a re-binding of a prior the
            # library already brings, and the readout does not count it as new goal
            # capability.
            "in_prior_shape_space": in_shapes,
            "skeleton": dsl.skeleton(predicate["ast"]),
            # distinct PREDICATE SKELETONS, not the five stock shapes: one shape generates
            # several skeletons (`align_two_matching` alone yields row_aligned, col_aligned,
            # bbox_overlap and exactly_one). lf52's 43 surviving candidates are 6 skeletons.
            "library_skeletons": len(skeleton_set),
            "novel_shape": not in_shapes,
        }

    action = goal.get("test_action")
    out["test_action"] = _test_action(action, vocabulary)
    out["status"] = "parsed"
    return out


_COMPLETION_CACHE: dict[str, Any] = {}
_ALIAS_CACHE: dict[str, Any] = {}

EVIDENCE_ID = re.compile(
    r"^(?:step\s*#?(?P<step>\d+)"
    r"|entity\s*#?(?P<entity>\d+)"
    r"|(?P<frame>initial board|solved board|next level board))$",
    re.I,
)


def load_completion(game: str) -> dict[str, Any] | None:
    """The captured completion (`e3_completion_capture.py`), or None.

    Only sp80 and lf52 of the protocol set have one. Absent is a normal state and is
    reported as absent — a game with no captured completion gets a block that says the
    record contains no solved board, not a block quietly missing.
    """
    if game not in _COMPLETION_CACHE:
        path = ROOT / f"logs/e1_completions/{game}.json"
        _COMPLETION_CACHE[game] = json.loads(path.read_text()) if path.is_file() else None
    return _COMPLETION_CACHE[game]


def load_alias_probe(game: str) -> dict[str, Any] | None:
    """The dual-history probe result (`e2_alias_probe.py`), or None."""
    if game not in _ALIAS_CACHE:
        path = ROOT / f"logs/e1_alias_probe/{game}.json"
        _ALIAS_CACHE[game] = json.loads(path.read_text()) if path.is_file() else None
    return _ALIAS_CACHE[game]


def has_alias_exhibit(game: str) -> bool:
    probe = load_alias_probe(game)
    return any(
        row.get("probed") and row.get("outcomes_differ")
        for row in ((probe or {}).get("probes") or [])
    )


class _CompletionTransition:
    """The completing action as an evaluable transition, from the capture.

    The frozen store cannot supply this: the explorer hashed the level-advance frame and
    never added it to `states.json`, so `e2_dose.load_store` substitutes the PRE frame and
    every consumer that reads `.post` has to skip the row. That is why `positives_evaluable`
    is 0 on all eight games and why slice 2's channel A was decided on negative evidence
    alone. `e3_completion_capture.py` re-executed the verified route and kept the frames, so
    the positive half of clause 1 is measurable here for the first time — on the two games
    that have a completion at all.
    """

    def __init__(self, capture: dict[str, Any]):
        roles = capture["completion"]["roles"] or []
        terminal = next(
            (frame for frame, role in zip(capture["frames"], roles) if role == "solved_terminal"),
            None,
        )
        self.pre = capture["last_incomplete_frame"]
        self.post = terminal
        self.completed = True
        self.step = capture["store"]["step"]
        self.usable = terminal is not None


def falsification(
    node: dict[str, Any], usable: list, contexts: list, capture: dict[str, Any] | None
) -> dict[str, Any]:
    """What refutes a completion condition, computed from the record instead of claimed.

    Rev 2 removed the refuter field; this is what replaces it. Two, and only two, things
    falsify a condition G:

      FALSE POSITIVE   G was true of a stored board and the level did not advance.
      FALSE NEGATIVE   the level completed and G was false of the solved board.

    The first is what row-C survivorship already measures. The second was unmeasurable in
    every previous slice and is measurable now, on the games with a captured completion.
    Both are counted; neither is asked for.
    """
    false_positives = []
    for transition, context in zip(usable, contexts, strict=True):
        if transition.completed:
            continue
        if dsl.evaluate(node, context) == dsl.TRUE:
            false_positives.append(transition.step)
    out: dict[str, Any] = {
        "false_positives": len(false_positives),
        "false_positive_steps": false_positives[:10],
        "negative_transitions": len(usable),
    }
    if capture is None or not capture.get("captured"):
        out["false_negative"] = None
        out["positive_evaluable"] = False
        out["positive_note"] = "no captured completion for this game"
        return out
    completion = _CompletionTransition(capture)
    if not completion.usable:
        out["false_negative"] = None
        out["positive_evaluable"] = False
        out["positive_note"] = "the capture holds no solved-terminal frame"
        return out
    context = dsl.transition_contexts([completion])[0]
    value = dsl.evaluate(node, context)
    out.update(
        {
            "positive_evaluable": True,
            "value_on_solved_board": value,
            # UNKNOWN is not a false negative: the three-valued grammar's `unknown` neither
            # confirms nor eliminates, and collapsing it into failure here would punish a
            # predicate the evidence simply cannot evaluate.
            "false_negative": value == dsl.FALSE,
            "completion_step": completion.step,
        }
    )
    return out


def evidence_validity(ids: Any, steps: set[int], entities: set[int]) -> dict[str, Any]:
    """Do the cited ids exist in the record? Computed, never counted from prose.

    A citation that names a step this run never took, or an entity the map does not list, is
    not grounding — it is the shape of grounding. The check is deliberately shallow: it
    verifies that the referent EXISTS, not that it supports the claim, and it says so.
    """
    if not isinstance(ids, list):
        return {"cited": 0, "resolvable": 0, "unresolvable": [], "malformed": ids is not None}
    resolvable = 0
    unresolvable: list[str] = []
    for item in ids:
        text = str(item).strip()
        match = EVIDENCE_ID.match(text)
        ok = False
        if match:
            if match.group("step") is not None:
                ok = int(match.group("step")) in steps
            elif match.group("entity") is not None:
                ok = int(match.group("entity")) in entities
            else:
                ok = True
        if ok:
            resolvable += 1
        else:
            unresolvable.append(text)
    return {
        "cited": len(ids),
        "resolvable": resolvable,
        "unresolvable": unresolvable[:10],
        "malformed": False,
        "checks": "the referent exists in the record; NOT that it supports the claim",
    }


def _test_action(action: Any, vocabulary: set[str]) -> dict[str, Any]:
    """WELL-FORMEDNESS only. Executability is the probe executor's job, at scoring time.

    ft09 held a fully solved goal for ten actions because nothing connected it to an untried
    action, so the action is part of the schema; but slice 2 executes no probes, and a form
    check reported as an execution check would be the same overclaim in a new place.
    """
    if not isinstance(action, dict):
        return {"well_formed": False, "reason": "absent", "raw": action}
    problems: list[str] = []
    action_id = action.get("action_id")
    if not isinstance(action_id, int) or not 1 <= action_id <= 7:
        problems.append(f"action_id {action_id!r} is not an integer 1-7")
    colour = action.get("click_colour")
    if action_id == 6 and colour is None:
        problems.append("ACTION6 without a click target colour")
    if action_id != 6 and colour is not None:
        problems.append(f"click target {colour!r} given for a non-click action")
    precondition = action.get("precondition")
    if precondition is not None:
        if not isinstance(precondition, dict) or not precondition.get("feature"):
            problems.append(f"precondition {precondition!r} is not a feature/value pair")
        elif not valid_guard(str(precondition["feature"]), vocabulary):
            problems.append(
                f"precondition feature {precondition['feature']!r} is not in the vocabulary"
            )
    return {
        "well_formed": not problems,
        "problems": problems,
        "action_id": action_id,
        "click_colour": colour,
        "precondition": precondition,
        "executability": "not tested — slice 2 executes no probes (notes/e2-slice2.md)",
    }


def channel_a_v4(
    payload: dict[str, Any],
    game: str,
    used: list,
    post_missing: set[int],
    vocabulary: set[str],
    entity_ids: set[int],
) -> dict[str, Any]:
    """Slice 3's channel A. Same clause 1, no refuter, plus three new fields.

    Everything clause 1 rests on is unchanged and shares code with `channel_a`: the parse,
    row-C survivorship over the store, the prior-library novelty comparison and the
    test-action form check. Those are the pre-committed comparison and they must not drift.

    What changes is what is asked and what is derived. The refuter is gone and FALSIFICATION
    is computed. `evidence_ids` is checked against the record. The free-form condition is
    recorded and scored NOWHERE here — it is adjudicated by source read, on its own line,
    and it is never a win against the prior library, which has no free-form output.
    """
    goal = payload.get("goal")
    if not isinstance(goal, dict):
        return {"status": "absent", "raw": goal}

    out: dict[str, Any] = {}
    predicate = dsl.classify_predicate(goal.get("predicate"))
    out["predicate"] = {k: v for k, v in predicate.items() if k != "ast"}
    if predicate["status"] != "parsed":
        out["status"] = "prose_rejected"
        # The free-form slot is recorded even when the DSL predicate fails to parse — it is
        # a separate measurement of understanding and does not depend on the grammar.
        out["free_form"] = _free_form(goal)
        return out

    usable = [t for t in used if t.step not in post_missing]
    contexts = dsl.transition_contexts(usable)
    out["store_consistency"] = dsl.consistent_with(predicate["ast"], usable, contexts=contexts)
    out["store_consistency"]["negative_transitions"] = len(usable)
    out["store_consistency"]["positives_evaluable"] = sum(1 for t in usable if t.completed)
    out["falsification"] = falsification(
        predicate["ast"], usable, contexts, load_completion(game)
    )
    out["evidence"] = evidence_validity(
        goal.get("evidence_ids"), {t.step for t in used}, entity_ids
    )
    out["free_form"] = _free_form(goal)

    library = prior_library(game)
    if library is None:
        out["novelty"] = {
            "computed": False,
            "reason": f"{PRIOR_LIBRARY.name} absent or has no row for {game}",
        }
    else:
        canonical_set, skeleton_set = library
        out["novelty"] = {
            "computed": True,
            "in_prior_library": predicate["canonical"] in canonical_set,
            "library_size": len(canonical_set),
            "in_prior_shape_space": dsl.skeleton(predicate["ast"]) in skeleton_set,
            "skeleton": dsl.skeleton(predicate["ast"]),
            "library_skeletons": len(skeleton_set),
            "novel_shape": dsl.skeleton(predicate["ast"]) not in skeleton_set,
        }

    out["test_action"] = _test_action(goal.get("test_action"), vocabulary)
    out["status"] = "parsed"
    return out


def _free_form(goal: dict[str, Any]) -> dict[str, Any]:
    text = goal.get("free_form")
    text = text.strip() if isinstance(text, str) else ""
    return {
        "given": bool(text),
        "text": text,
        "verdict": (
            "NOT SCORED HERE — adjudicated by source read, reported on its own line, and "
            "never counted as a win against the prior-library control, which produces no "
            "free-form output and so cannot be compared with one"
        ),
    }


def channel_b(payload: dict[str, Any], game: str) -> dict[str, Any]:
    """Parse the latents into counter expressions and emit the verifier's spec rows."""
    items = payload.get("latents")
    if not isinstance(items, list):
        return {"status": "absent", "raw": items, "parsed": [], "prose_rejected": []}
    parsed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(items[:3]):
        if not isinstance(item, dict):
            rejected.append({"index": index, "raw": item, "reason": "not an object"})
            continue
        outcome = dsl.classify_counter(item.get("definition"))
        name = str(item.get("name") or f"latent{index + 1}")
        if outcome["status"] != "parsed":
            rejected.append({"index": index, "name": name, **outcome})
            continue
        parsed.append(
            {"game": game, "name": name, "definition": outcome["canonical"], "as_written": outcome["text"]}
        )
    return {
        "status": "parsed" if parsed else "prose_rejected" if rejected else "none_proposed",
        "proposed": len(items),
        "parsed": parsed,
        "prose_rejected": rejected,
        "over_the_cap": max(0, len(items) - 3),
    }


def channel_c(payload: dict[str, Any], pending: list[tuple]) -> dict[str, Any]:
    """Record the proposals and whether each names a key the miner actually failed on.

    The note's in-slice score is targeting against the MEASURED failure typing. The committed
    floors carry `failure_split` per game and target, NOT per key, so a per-key
    guard-fixable/census-separable rate is not computable from them and is not invented here.
    What is computable is whether the proposal points at a key the miner left unresolved at
    all, which is the necessary condition; the rest is a readout-time join against a per-key
    typing that does not yet exist.
    """
    items = payload.get("vocabulary")
    if not isinstance(items, list):
        return {"status": "absent", "raw": items}
    keys = {_key_text(key) for key in pending}
    rows = []
    for index, item in enumerate(items[:2]):
        if not isinstance(item, dict):
            rows.append({"index": index, "raw": item, "malformed": True})
            continue
        targeted = [str(k) for k in (item.get("targeted_keys") or [])]
        rows.append(
            {
                "index": index,
                "name": item.get("name"),
                "definition_sketch": item.get("definition_sketch"),
                "targeted_keys": targeted,
                "expected_direction": item.get("expected_direction"),
                "targets_an_unresolved_key": [key in keys for key in targeted],
            }
        )
    return {
        "status": "recorded",
        "proposed": len(items),
        "over_the_cap": max(0, len(items) - 2),
        "unresolved_keys_available": sorted(keys),
        "proposals": rows,
        "targeting_rate": (
            "not computable from the committed floors: `failure_split` is per game and "
            "target, not per key. Joined at readout time."
        ),
    }


REVISE = """Your answer to A was checked mechanically against this run's own stored evidence,
before you were asked anything else. It does not survive that check. The counterexample is
below, from the same evidence you were given.

{counterexample}

Re-specify. Give a REVISED answer to A only — one predicate, its refuter, and one test
action, in the same grammar as before. B and C are not asked again and anything you write
about them is discarded unread.

You may keep your predicate only if you can say why the counterexample does not refute it;
otherwise change it. A predicate that fails the same way twice is worth nothing.
"""


def feedback_counterexample(
    scored: dict[str, Any], used: list, post_missing: set[int], with_frames: bool
) -> dict[str, Any] | None:
    """The concrete refutation of a failed channel-A answer, rendered.

    Arm FB, `notes/e2-slice3.md`. The S1 corpus is the reason this arm exists at all: what
    separated the reference's L2 recoveries from its L2 deaths was re-specification UNDER
    CONTRADICTION — ft09 recovered by taking "my decoded pattern is satisfied and the level
    did not advance" as evidence against its own decoding, while sb26 never re-specified and
    spent its whole budget enumerating inside a stale schema.

    Rev 2 removed the refuter, so the two things fed back are the two things that actually
    falsify a completion condition, both DERIVED from the record rather than claimed:

      false positive   the predicate was true of a stored board and the level did not
                       advance. That board is the counterexample, rendered in full.
      false negative   the level completed and the predicate was false of the solved board.
                       Measurable for the first time here, from the completion capture — and
                       it is the sharper of the two, because the solved board is the one
                       thing the condition must be true of.

    Returns None when the answer failed in neither way; the arm never invents a grievance.
    """
    consistency = scored.get("store_consistency") or {}
    checks = scored.get("falsification") or {}
    usable = [t for t in used if t.step not in post_missing]
    parts: list[str] = []
    kinds: list[str] = []

    index = consistency.get("contradicted_at")
    if consistency.get("outcome") == "falsified" and index is not None and index < len(usable):
        transition = usable[index]
        kinds.append("false_positive")
        parts.append(
            f"YOUR CONDITION, AS WRITTEN: {scored['predicate']['canonical']}\n"
            f"At step {transition.step} of this run it was TRUE of the board — and the level "
            f"did NOT advance. A condition the board satisfies while nothing happens is not "
            f"this level's completion condition. It survived "
            f"{consistency.get('definite_correct', 0)} earlier boards before this one "
            f"refuted it."
        )
        if with_frames:
            parts.append("THE BOARD THAT REFUTED IT, in full, at that step:")
            parts.append("\n".join(frames.render_grid(transition.pre)))

    if checks.get("false_negative"):
        kinds.append("false_negative")
        parts.append(
            f"YOUR CONDITION, AS WRITTEN: {scored['predicate']['canonical']}\n"
            f"The level was completed at step {checks.get('completion_step')} of this run, "
            f"and your condition is FALSE of the board that completed it. Whatever the "
            f"completion condition is, it is true of that board — the solved board shown in "
            f"the record above — so it is not this."
        )
    if not parts:
        return None
    return {"kinds": kinds, "text": "\n\n".join(parts)}


def run_cell(
    game: str,
    dose: int | None,
    qwen: Qwen | None,
    human: dict[str, list],
    seed: int = SEED,
    *,
    with_frames: bool = False,
    caps: Any = None,
    feedback: bool = False,
) -> dict[str, Any]:
    digest = build_digest(game, dose, with_frames=with_frames, caps=caps)
    used, baseline_rules, _ = mined(game, dose)
    pending = unresolved_keys(baseline_rules)
    vocabulary = {name for t in used for name in t.guards}

    floor = {
        "human_l1": score(baseline_rules, used, human["l1"], MODE),
        "human_l2": score(baseline_rules, used, human["l2"], MODE),
    }
    cell: dict[str, Any] = {
        "game": game,
        "dose": dose,
        "digest_chars": digest["chars"],
        "store_transitions": digest["store_transitions"],
        "miner_rules": digest["miner_rules"],
        "unresolved_keys": digest["unresolved_keys"],
        "inert_objects": digest["inert_objects"],
        "observed_invariants": digest["observed_invariants"],
        "negative_evidence": digest["negative_evidence"],
        "frames": digest["frames"],
        "floor": floor,
    }
    if qwen is None:
        cell["skipped"] = "dry-run"
        cell["prompt_chars"] = len(build_prompt(digest))
        return cell

    prompt = build_prompt(digest)
    cell["prompt_chars"] = len(prompt)
    think = qwen.generate(
        [{"role": "user", "content": prompt}],
        max_tokens=THINK_BUDGET,
        thinking=True,
        seed=seed,
    )
    verdict = thinking_verdict(think)
    TRACES.mkdir(parents=True, exist_ok=True)
    # seed-tagged so variance-arm reruns can never overwrite slice 1's committed traces.
    # SLICE-2 MARKER (2026-08-05, caught in the night's pre-flight): the seed tag alone is NOT
    # enough across slice generations. Slice 2 runs seeds 1 and 2 on the full dose, so
    # `{game}_full_s1` collides byte-for-byte with the twelve COMMITTED slice-1/1.1 trace names
    # (dc22_full_s1.think.json and siblings) — a defaulted slice-2 run would silently overwrite
    # the audit trail of a 3.5 h run that cannot be reproduced, only re-sampled. Same failure
    # class as the `--out` default that already ate the slice-1.1 result file once today.
    # `_s2r{seed}` is the tag `notes/e2-slice2-run.md` names; FORMAT_VERSION distinguishes the
    # result files, and this distinguishes the traces.
    #
    # SLICE 3 (2026-08-05): the same argument one generation on. Slice 3 runs the same eight
    # games on the same two seeds, so `_s2r1` would collide with slice 2's sixteen committed
    # traces from last night. `--frames` is what makes a cell a slice-3 cell, and it is what
    # switches the tag.
    generation = "s3r" if with_frames else "s2r"
    tag = f"{game}_{'full' if dose is None else dose}_{generation}{seed}"
    (TRACES / f"{tag}.think.json").write_text(
        json.dumps({"prompt": prompt, **think, "verdict": verdict}, indent=2)
    )
    cell["thinking"] = {k: v for k, v in think.items() if k not in ("raw", "answer")}
    cell["thinking_verdict"] = verdict
    if not all(verdict.values()):
        cell["outcome"] = "VOID — thinking check failed"
        return cell

    template = EXTRACT_V4 if with_frames else EXTRACT
    payload, attempts = extract_payload(qwen, think["answer"], tag, seed, template)
    cell["extract_attempts"] = len(attempts)
    wall = think["wall_seconds"] + sum(a["wall_seconds"] for a in attempts)
    if payload is None:
        cell["outcome"] = "unparsed extraction"
        cell["wall_seconds"] = wall
        return cell

    _, post_missing = store_with_gaps(game)
    entity_ids: set[int] = set()
    if with_frames:
        entity_ids = set(
            ((digest["frames"].get("blocks") or {}).get("scene") or {}).get("entity_ids") or []
        )
        scored_a = channel_a_v4(payload, game, used, post_missing, vocabulary, entity_ids)
        # Channel B is suppressed on games with no alias exhibit; the prompt says so and the
        # scorer records the suppression rather than reporting an empty channel as a failure.
        scored_b = (
            channel_b(payload, game)
            if has_alias_exhibit(game)
            else {
                "status": "not_asked",
                "reason": "no alias exhibit in this game's record — the request was suppressed",
                "parsed": [],
                "prose_rejected": [],
            }
        )
    else:
        scored_a = channel_a(payload, game, used, post_missing, vocabulary)
        scored_b = channel_b(payload, game)
    cell.update(
        {
            "outcome": "scored",
            "channel_a": scored_a,
            "channel_b": scored_b,
            "channel_c": channel_c(payload, pending),
            "payload": payload,
            "wall_seconds": wall,
        }
    )

    # ---- arm FB: one contradiction-feedback turn -------------------------------------
    # Within-night attribution, so it is the SAME cell continued rather than a new one: the
    # revision sees its own analysis and its own refutation in one conversation.
    if not feedback or scored_a.get("status") != "parsed":
        return cell
    counterexample = feedback_counterexample(scored_a, used, post_missing, with_frames)
    if counterexample is None:
        cell["feedback"] = {"attempted": False, "reason": "answer passed both checks"}
        return cell

    revision_prompt = REVISE.format(counterexample=counterexample["text"])
    revised_think = qwen.generate(
        [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": think["answer"]},
            {"role": "user", "content": revision_prompt},
        ],
        max_tokens=THINK_BUDGET,
        thinking=True,
        seed=seed,
    )
    revised_verdict = thinking_verdict(revised_think)
    (TRACES / f"{tag}.fb.think.json").write_text(
        json.dumps(
            {"prompt": revision_prompt, **revised_think, "verdict": revised_verdict}, indent=2
        )
    )
    block: dict[str, Any] = {
        "attempted": True,
        "kinds": counterexample["kinds"],
        "counterexample_chars": len(counterexample["text"]),
        "thinking": {k: v for k, v in revised_think.items() if k not in ("raw", "answer")},
        "thinking_verdict": revised_verdict,
    }
    cell["feedback"] = block
    if not all(revised_verdict.values()):
        block["outcome"] = "VOID — thinking check failed"
        cell["wall_seconds"] = wall + revised_think["wall_seconds"]
        return cell

    revised_payload, revised_attempts = extract_payload(
        qwen, revised_think["answer"], f"{tag}.fb", seed, template
    )
    block["extract_attempts"] = len(revised_attempts)
    wall += revised_think["wall_seconds"] + sum(a["wall_seconds"] for a in revised_attempts)
    cell["wall_seconds"] = wall
    if revised_payload is None:
        block["outcome"] = "unparsed extraction"
        return cell
    # Scored through the identical machinery, so "repaired" means the same thing before and
    # after. B and C are NOT rescored: the revision was not asked for them, and scoring a
    # section the prompt told the model to skip would report its silence as a failure.
    block["outcome"] = "scored"
    block["channel_a"] = (
        channel_a_v4(revised_payload, game, used, post_missing, vocabulary, entity_ids)
        if with_frames
        else channel_a(revised_payload, game, used, post_missing, vocabulary)
    )
    block["payload"] = revised_payload
    before = (scored_a.get("store_consistency") or {}).get("outcome")
    after = (block["channel_a"].get("store_consistency") or {}).get("outcome")
    checks_before = scored_a.get("falsification") or {}
    checks_after = block["channel_a"].get("falsification") or {}
    block["repair"] = {
        "outcome_before": before,
        "outcome_after": after,
        "false_positives_before": checks_before.get("false_positives"),
        "false_positives_after": checks_after.get("false_positives"),
        "false_negative_before": checks_before.get("false_negative"),
        "false_negative_after": checks_after.get("false_negative"),
        "predicate_changed": (
            (block["channel_a"].get("predicate") or {}).get("canonical")
            != (scored_a.get("predicate") or {}).get("canonical")
        ),
        # The readout's repair-rate line. "Repaired" is the MECHANICAL bar only: it survives
        # the store and is not false of a solved board this record actually holds. Whether it
        # is CORRECT is adjudication, and adjudication is not done here.
        "repaired": after == "survived" and not checks_after.get("false_negative"),
    }
    return cell


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(SLICE2_GAMES))
    parser.add_argument("--doses", type=int, nargs="*", default=None)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--dry-run", action="store_true", help="digests + floors, no model")
    parser.add_argument(
        "--seed", type=int, default=SEED, help="phase-1 sampling seed; tags traces and output"
    )
    parser.add_argument(
        "--print-digest",
        metavar="GAME",
        default=None,
        help="print one game's full digest text and exit (no model, no output file)",
    )
    parser.add_argument(
        "--latent-spec",
        type=Path,
        default=None,
        help="write channel B's parsed latents as an e2_latent_verify.py spec file",
    )
    parser.add_argument(
        "--frames",
        action="store_true",
        help="digest v4: append the rendered boards (slice 3, notes/e2-slice3.md)",
    )
    parser.add_argument(
        "--feedback",
        action="store_true",
        help="arm FB: one contradiction-feedback revision turn per failed channel-A answer",
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=TOKEN_BUDGET,
        help="F-prompt token ceiling; the record is trimmed until it fits",
    )
    parser.add_argument(
        "--fb-token-budget",
        type=int,
        default=FB_TOKEN_BUDGET,
        help="FB-chat token ceiling (F + answer + counterexample); breaching it also trims",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    # `logs/e2_slice_seed{seed}.json` is SLICE 1.1's committed results file (format_version
    # 1, 12 scored cells on seed 1). Slice 2 writes format_version 2 and the protocol runs
    # SEEDS 1 AND 2 — so the old default path put a night run on a collision course with
    # committed measurement data, and a stray `--seed 1 --dry-run` already overwrote it once
    # on 2026-08-05 (recovered from git). Different experiment, different file.
    #
    # Slice 3 is the same trap one generation on: it runs the same games on the same seeds,
    # so its default must not be slice 2's committed path either. `--frames` is what makes a
    # run a slice-3 run, and it moves the default with it. Always pass `--out` anyway.
    slice_number = 3 if args.frames else 2
    out = args.out or (ROOT / f"logs/e2_slice{slice_number}_seed{args.seed}.json")

    if args.print_digest:
        caps = fit_caps(args.print_digest, None, args.token_budget) if args.frames else None
        print(build_digest(args.print_digest, None, with_frames=args.frames, caps=caps)["text"])
        return 0

    doses = tuple(args.doses) if args.doses else DOSES
    qwen = None
    if not args.dry_run:
        print(f"loading {args.model.name} ...", flush=True)
        start = time.monotonic()
        qwen = Qwen(args.model)
        print(f"loaded in {time.monotonic() - start:.1f}s", flush=True)

    cells = []
    for game in args.games:
        human_all = load_game(game, max_level=2)
        human = {
            "l1": [t for t in human_all if t.level == 1],
            "l2": [t for t in human_all if t.level == 2],
        }
        for dose in doses:
            label = f"{game} dose={'full' if dose is None else dose}"
            print(f"\n=== {label} ===", flush=True)
            caps = fit_report = None
            if args.frames:
                caps, fit_report = fit_caps(
                    game, dose, args.token_budget, args.model, args.fb_token_budget
                )
                print(
                    f"{label}: F {fit_report['f_prompt_tokens']} tok "
                    f"(cap {args.token_budget}), FB chat {fit_report['fb_chat_tokens']} tok "
                    f"(cap {args.fb_token_budget})"
                    + (
                        f" — TRIMMED at ladder step {fit_report['trim_step']}: "
                        f"{fit_report['caps']}"
                        if fit_report["trimmed"]
                        else " — no trimming needed"
                    )
                    + ("" if fit_report["f_within_budget"] else "  *** F OVER CAP ***")
                    + (
                        ""
                        if fit_report["fb_within_budget"]
                        else "  *** FB CHAT OVER CAP — this cell runs F ONLY ***"
                    ),
                    flush=True,
                )
            cell = run_cell(
                game,
                dose,
                qwen,
                human,
                seed=args.seed,
                with_frames=args.frames,
                caps=caps,
                feedback=args.feedback,
            )
            if fit_report is not None:
                cell["prompt_fit"] = fit_report
            cells.append(cell)
            if cell.get("outcome") == "scored":
                a, b, c = cell["channel_a"], cell["channel_b"], cell["channel_c"]
                consistency = a.get("store_consistency") or {}
                novelty = a.get("novelty") or {}
                print(
                    f"{label}: A {a['status']}"
                    + (
                        f"/{consistency.get('outcome')}"
                        f"{' /SELF-REFUTING' if (a.get('refuter') or {}).get('self_refuting') else ''}"
                        f"{' /in-prior-library' if novelty.get('in_prior_library') else ''}"
                        f"{' /novel-shape' if novelty.get('novel_shape') else ''}"
                        f"{' /test-action-malformed' if not (a.get('test_action') or {}).get('well_formed') else ''}"
                        if a["status"] == "parsed"
                        else ""
                    )
                    + f" | B {len(b['parsed'])} parsed, {len(b['prose_rejected'])} rejected"
                    + f" | C {c.get('proposed', 0)} proposals"
                    + f" | think {cell['thinking']['think_chars']} chars "
                    f"{cell['wall_seconds']:.0f}s",
                    flush=True,
                )
                fb = cell.get("feedback")
                if fb and fb.get("attempted"):
                    repair = fb.get("repair") or {}
                    print(
                        f"{label}: FB {'/'.join(fb['kinds'])} -> {fb.get('outcome')}"
                        + (
                            f" | {repair.get('outcome_before')} -> "
                            f"{repair.get('outcome_after')}"
                            f"{' REPAIRED' if repair.get('repaired') else ''}"
                            f"{'' if repair.get('predicate_changed') else ' (predicate unchanged)'}"
                            if repair
                            else ""
                        ),
                        flush=True,
                    )
            elif cell.get("skipped") == "dry-run":
                print(
                    f"{label}: digest {cell['digest_chars']} chars, "
                    f"{cell['store_transitions']} transitions, "
                    f"{cell['unresolved_keys']} unresolved keys, "
                    f"{cell['inert_objects']} inert objects, "
                    f"{cell['negative_evidence']['satisfied_but_not_advanced']} refuted goal "
                    f"candidates",
                    flush=True,
                )
            else:
                print(f"{label}: {cell.get('outcome', 'dry-run')}", flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(
                    {
                        "format_version": (
                            FRAMES_FORMAT_VERSION if args.frames else FORMAT_VERSION
                        ),
                        "model": str(args.model),
                        "mode": MODE,
                        "seed": args.seed,
                        "doses": [d if d is not None else "full" for d in doses],
                        "budgets": {
                            "think": THINK_BUDGET,
                            "extract": EXTRACT_BUDGET,
                            "f_prompt_tokens": args.token_budget if args.frames else None,
                            "fb_chat_tokens": args.fb_token_budget if args.frames else None,
                        },
                        "arms": {"frames": args.frames, "feedback": args.feedback},
                        "cells": cells,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
    print(f"\nwrote {out}")

    if args.latent_spec:
        specs = [
            spec
            for cell in cells
            for spec in (cell.get("channel_b") or {}).get("parsed", [])
        ]
        args.latent_spec.parent.mkdir(parents=True, exist_ok=True)
        args.latent_spec.write_text(
            json.dumps(
                {
                    "generated_by": f"agent/harness/e2_slice.py --seed {args.seed}",
                    "specs": specs,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(f"wrote {args.latent_spec} ({len(specs)} latents for e2_latent_verify.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
