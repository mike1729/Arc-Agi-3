#!/usr/bin/env python3
"""E2 hidden-state loop closure — m0r0's parity hypothesis, machine-checked.

`notes/e2-hidden-state.md`. Zero model calls. The one stable model win across both slices is
that every m0r0 cell names a hidden action counter whose parity drives a mode switch. This
file converts "the human read it as correct" into a measurement, and dry-runs the template a
re-scoped slice 2 would be built on: model proposes a latent -> machinery encodes it ->
measured acceptance.

TWO HALVES, BOTH REPORTED
-------------------------
  (A) ALIASING     does the proposed counter separate genuinely aliased outcomes?
  (B) LOAD-BEARING does mining with the counter as a guard feature beat the v2 floor on
                   held-out HUMAN replays?

A without B is still a template win (the verify step ran and returned a real answer); neither
is adjudication error. All three outcomes are decision-grade, so every arm is reported
including the dead ones.

THE ARMS
--------
  c1_global        parity of the count of ALL actions since environment creation
  c2_episode       parity of the count of actions since the last RESET (RESET not counted)
  c2_episode_incl  same, counting the RESET itself       -- the convention control
  c1_global_m3/m4  mod 3 and mod 4 of the winning base   -- "is it PARITY or just a counter?"
  randN            a seeded arbitrary bit of the same step index, seeds 1-5 -- specificity floor

Counter conventions are stated once and applied identically on both sides: the feature value
is the counter AT THE PRE-STATE, i.e. the number of actions the environment executed BEFORE
the action being predicted. Store side that is `step - 1` (the explorer's `step` is the
1-indexed global index of the action that produced the row); human side likewise, since
`rs_transitions.iter_session_transitions` increments `step` once per framed response row,
RESETs included. Global parity therefore aligns by construction on both sides. RESET does not
itself increment the in-episode count (`c2_episode_incl` is the arm that says it does), and
ENVIRONMENT CREATION counts as an implicit RESET on both sides, which is what makes the
in-episode count defined for every row rather than only after the first explicit RESET.
The in-episode count is not recoverable from the store -- the log holds no RESET rows -- so it
comes from the instrumented rerun, joined by step index under a passing gate.

DEVIATION FROM THE NOTE (recorded, not silent) -- see `parity_probe`
--------------------------------------------------------------------
Step 1 as written assumes the transitions log contains repeated `(pre, action)` observations
whose outcomes can disagree. It does not, and cannot: the explorer records a row only from
`test()`, and `test()` pops each candidate from a state's frontier exactly once. The census
over the log is therefore EMPTY by construction, and the instrumented rerun adds only the
routing actions (m0r0: 37 of 3000). A census of that size cannot decide half A.

So half A is answered by an ACTIVE probe instead of a passive census (`parity_probe`), in two
families that each vary ONE counter with the board held fixed:

  P1  RESET; k filler; RESET; path; target -- the in-episode count is `len(path)` for every
      k while the count since environment creation is `2 + k + len(path)`. Isolates a counter
      that SURVIVES RESET.
  P2  RESET; path; target, over several executed paths of different LENGTH that land on the
      same grid digest. Isolates the in-episode count. Several distinct paths per length are
      kept as the control that separates "the count matters" from "the route content
      matters" -- without it the design cannot make the claim at all.

Both are branch-and-deviate probes on a public game against the local deterministic engine
(REPLAY-DET); they regenerate nothing and write only this task's own files. Two abandoned
instruments are recorded because their failure is evidence: a store-observed SELF-LOOP is not
one (applying the same click twice at the same board changes the board the second time), and
the explorer's stored `graph["prefix"]` does not replay to its own state (12 of 15 targets),
independent of how many RESETs precede it -- so all routing here is built by execution.

Run:
  .venv/bin/python agent/harness/e2_hidden_state.py --stage census
  .venv/bin/python agent/harness/e2_hidden_state.py --stage rerun
  .venv/bin/python agent/harness/e2_hidden_state.py --stage rerun_all --jobs 8
  .venv/bin/python agent/harness/e2_hidden_state.py --stage probe
  .venv/bin/python agent/harness/e2_hidden_state.py --stage mine
  .venv/bin/python agent/harness/e2_hidden_state.py --stage cross --arm c2_episode --jobs 8
  .venv/bin/python agent/harness/e2_hidden_state.py --stage all --jobs 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
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

from e2_dose import load_store  # noqa: E402  (the loader pattern the note names)
from gi2_traces import normalize_action_id  # noqa: E402
from rs_e0 import memorizer, mine, score  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    CORPUS,
    EXCLUDED_GAMES,
    EXCLUDED_SESSIONS,
    ROOT,
    Transition,
    load_game,
    set_vocab,
    vocab,
)

GAME = "m0r0"
STORE = ROOT / "logs/e1_store_v2"
OUTPUT = ROOT / "logs/e2_hidden_state.json"
RERUN_DIR = ROOT / "logs/e2_hidden_state_rerun"
FLOOR = ROOT / "logs/e2_dose_vocab_v2.json"
FORMAT_VERSION = 1

MODES = ("full", "moveset")  # matches the floor file; `changed` is degenerate
DOSES = (125, None)  # (w) the note's dose endpoints
PROBE_OFFSETS = (0, 1, 2, 3, 4, 5)  # (w) two full periods of the parity hypothesis
CONTROL_SEEDS = (1, 2, 3, 4, 5)  # never 20260804 (the reserved draw seed)


# ======================================================================================
# Counter definitions -- the arms
# ======================================================================================


def _rand_bit(seed: int, index: int) -> int:
    """A seeded arbitrary bit of the same step index the real arms are built on.

    The specificity floor has to be matched in FORM, not just in entropy: a feature that
    varies per transition but carries no mechanism should be available to tier 1 exactly as
    the parity features are. Deriving it from the step index (rather than from a stream
    position) makes it reproducible on both sides from the same quantity.
    """
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    return digest[0] & 1


def arm_values(counters: dict[str, int], step: int) -> dict[str, Any]:
    """Every arm's feature value for one transition.

    `counters` holds the raw counts AT THE PRE-STATE: `global` = actions since environment
    creation, `episode` = actions since the last RESET (RESET not counted), `episode_incl` =
    the same counting the RESET. A missing key means the arm is not computable for this row
    and it is omitted -- never defaulted, because a defaulted guard is a fabricated one.
    """
    out: dict[str, Any] = {}
    if "global" in counters:
        out["c1_global"] = counters["global"] % 2
        out["c1_global_m3"] = counters["global"] % 3
        out["c1_global_m4"] = counters["global"] % 4
    if "episode" in counters:
        out["c2_episode"] = counters["episode"] % 2
        out["c2_episode_m3"] = counters["episode"] % 3
        out["c2_episode_m4"] = counters["episode"] % 4
    if "episode_incl" in counters:
        out["c2_episode_incl"] = counters["episode_incl"] % 2
    for seed in CONTROL_SEEDS:
        out[f"rand{seed}"] = _rand_bit(seed, step)
    return out


ARMS = (
    "c1_global",
    "c2_episode",
    "c2_episode_incl",
    "c1_global_m3",
    "c1_global_m4",
    "c2_episode_m3",
    "c2_episode_m4",
    *(f"rand{seed}" for seed in CONTROL_SEEDS),
)


def inject(transitions: list[Transition], counters: list[dict[str, int]]) -> list[str]:
    """Write `parity:<arm>` into each transition's `guards` in place.

    `rs_e0.mine` reads features straight off `Transition.guards`, so an injected key is
    picked up with no edits to any shared file -- the isolation the note requires.
    """
    present: set[str] = set()
    for transition, counter in zip(transitions, counters, strict=True):
        for arm, value in arm_values(counter, transition.step).items():
            transition.guards[f"parity:{arm}"] = value
            present.add(arm)
    return sorted(present)


# ======================================================================================
# Human side -- counters from the recordings
# ======================================================================================


def human_counters(game: str) -> dict[tuple[str, int], dict[str, int]]:
    """`(guid, step) -> counters at the pre-state`, mirroring `iter_session_transitions`.

    That function increments `step` once for every response row carrying a `frame` key, RESETs
    and zero-frame rows included, so replicating the count exactly is a five-line loop and no
    shared file has to be touched. `global` is `step - 1`; the episode counters need the index
    of the last RESET, which only this pass has.
    """
    out: dict[tuple[str, int], dict[str, int]] = {}
    for path in sorted((CORPUS / game).glob("*.recording.jsonl")):
        guid = path.name.split(".")[0]
        if (game, guid[:8]) in EXCLUDED_SESSIONS:
            continue
        step = 0
        # Environment creation is an implicit RESET: the count since the last reset is the
        # count since the session began until a RESET row appears. The explorer side starts
        # the same way (its first action IS a RESET), so the two sides mean the same thing.
        last_reset: int = 0
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
                counters = {
                    "global": step - 1,
                    # actions executed since the RESET, at the pre-state of this action
                    "episode": (step - 1) - last_reset,
                    "episode_incl": step - last_reset,
                }
                out[(guid, step)] = counters
                if action_id == 0:
                    last_reset = step
    return out


def counters_for(transitions: list[Transition], table: dict) -> list[dict[str, int]]:
    return [table.get((t.guid, t.step), {"global": t.step - 1}) for t in transitions]


# ======================================================================================
# Step 1 -- conflict census over the store as recorded
# ======================================================================================


def store_census(store: Path, game: str) -> dict[str, Any]:
    """Aliasing census over a store that CAN hold repeated observations.

    `census` below reads the v2 store, whose transitions log cannot disagree with itself; this
    reads a v3-shaped store, whose log carries confirmation rows and whose `performs.jsonl`
    carries every action including routing. A repeated `(pre, action)` group is classified by
    whether its observations were taken at the same in-episode count, and conflating the two
    cases is what made the old census uninterpretable even in principle:

      different count, different outcome   ALIASING by the in-episode counter
      same count, different outcome        hidden state the `(board, count)` pair does NOT
                                           capture. Do not read this as non-determinism
                                           without checking: measured on g50t, each variant
                                           is highly reproducible (one group holds 33
                                           identical repeats of the minority outcome), which
                                           is a further latent, not a flaky engine.
    """
    out: dict[str, Any] = {"store": str(store), "game": game}
    for label, name, key in (
        ("transitions", f"{game}.transitions.jsonl", "episode_step"),
        ("performs", f"{game}.performs.jsonl", "episode_step"),
    ):
        path = store / name
        if not path.exists():
            out[label] = {"missing": str(path)}
            continue
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            if row.get("pre") is None or row.get("post") is None:
                continue
            groups[(row["pre"], tuple(row["action"]))].append(row)
        repeated = {k: v for k, v in groups.items() if len(v) > 1}
        aliased = same_count = 0
        for observations in repeated.values():
            if len({o["post"] for o in observations}) == 1:
                continue
            counts = {o[key] for o in observations}
            if len(counts) > 1:
                aliased += 1
            else:
                same_count += 1
        out[label] = {
            "rows": len(rows),
            "groups": len(groups),
            "repeated_groups": len(repeated),
            "aliased_different_count": aliased,
            "disagreeing_same_count": same_count,
            "observations_in_repeated_groups": sum(len(v) for v in repeated.values()),
        }
    graph = json.loads((store / f"{game}.graph.json").read_text())
    confirmations = graph.get("confirmations", [])
    out["confirmations"] = {
        "attempted": len(confirmations),
        "landed": sum(1 for r in confirmations if r["outcome"] != "route_diverged"),
        "disagreed": sum(1 for r in confirmations if r["outcome"] == "disagrees"),
        "route_diverged": sum(1 for r in confirmations if r["outcome"] == "route_diverged"),
    }
    out["recorded_conflict_records"] = len(graph.get("conflict_records", []))
    return out


def census(game: str = GAME) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in (STORE / f"{game}.transitions.jsonl").read_text().splitlines()
        if line
    ]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["pre"], tuple(row["action"]))].append(row)
    repeated = {key: value for key, value in groups.items() if len(value) > 1}
    aliased_post = {
        key: value for key, value in repeated.items() if len({r["post"] for r in value}) > 1
    }
    aliased_effect = {
        key: value
        for key, value in repeated.items()
        if len({json.dumps(r["effect"]) for r in value}) > 1
    }
    graph = json.loads((STORE / f"{game}.graph.json").read_text())
    return {
        "rows": len(rows),
        "distinct_pre_action_groups": len(groups),
        "repeated_groups": len(repeated),
        "aliased_groups_by_post_hash": len(aliased_post),
        "aliased_groups_by_effect_signature": len(aliased_effect),
        "recorded_conflict_records": len(graph["conflict_records"]),
        "recorded_conflicted_edges": len(graph["conflicted"]),
        "recorded_suspect_nodes": len(graph["suspect"]),
        "conflict_records": graph["conflict_records"],
        "note": (
            "the log records only test actions and `test()` pops each candidate from a "
            "state's frontier exactly once, so repeated (pre, action) rows cannot occur; "
            "the census over the log is empty BY CONSTRUCTION, not by absence of aliasing"
        ),
    }


# ======================================================================================
# Step 2 -- instrumented rerun
# ======================================================================================


def _recorder_class():
    """Import the explorer lazily: it pulls in arcengine, which `--stage census` need not."""
    from e1_explorer import _hash, Explorer  # noqa: N813

    class Recorder(Explorer):
        """`Explorer` with every `perform()` logged. The store is never touched."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.performs: list[dict[str, Any]] = []
            self.last_reset: int = 0  # environment creation is an implicit RESET

        def perform(self, action):  # type: ignore[override]
            source = self.current
            result = super().perform(action)
            index = self.actions_used  # 1-indexed global action index
            grid = result["grid"]
            counters = {
                "global": index - 1,
                "episode": (index - 1) - self.last_reset,
                "episode_incl": index - self.last_reset,
            }
            self.performs.append(
                {
                    "index": index,
                    "action": list(action),
                    "pre": source,
                    "post": _hash(self.level, grid) if grid is not None else None,
                    "levels": result["levels"],
                    "state": result["state"],
                    "counters": counters,
                }
            )
            if action[0] == 0:
                self.last_reset = index
            return result

    return Recorder


def rerun(game: str = GAME, *, budget: int, wall: float, cap: int) -> dict[str, Any]:
    Recorder = _recorder_class()
    explorer = Recorder(game, budget=budget, wall=wall, cap=cap, policy="v2")
    summary = explorer.run()

    RERUN_DIR.mkdir(parents=True, exist_ok=True)
    with (RERUN_DIR / f"{game}.performs.jsonl").open("w") as handle:
        for row in explorer.performs:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    with (RERUN_DIR / f"{game}.transitions.jsonl").open("w") as handle:
        for row in explorer.transitions:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    # -- the gate: the rerun's transition rows must match the store ---------------------
    stored = [
        json.loads(line)
        for line in (STORE / f"{game}.transitions.jsonl").read_text().splitlines()
        if line
    ]
    fresh = explorer.transitions
    head = min(50, len(stored), len(fresh))
    gate = {
        "stored_rows": len(stored),
        "rerun_rows": len(fresh),
        "counts_match": len(stored) == len(fresh),
        "first_50_match": stored[:head] == fresh[:head],
        "last_50_match": stored[-head:] == fresh[-head:],
        "all_rows_match": stored == fresh,
    }
    gate["passed"] = bool(gate["counts_match"] and gate["first_50_match"] and gate["last_50_match"])

    # -- census over ALL performs, routing actions included -----------------------------
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in explorer.performs:
        if row["pre"] is None or row["post"] is None:
            continue
        groups[(row["pre"], tuple(row["action"]))].append(row)
    repeated = {k: v for k, v in groups.items() if len(v) > 1}
    aliased = {k: v for k, v in repeated.items() if len({r["post"] for r in v}) > 1}

    # Every arm, controls included. The binary random bits are the fair match for a binary
    # parity feature -- the mod-3/mod-4 arms have more cells and separate more by arithmetic
    # alone, so they bound the artifact rather than competing on equal terms. Cell count is
    # reported per arm for exactly that reason.
    per_arm: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        separated = 0
        computable = 0
        cells_used: set = set()
        for observations in aliased.values():
            values = [arm_values(r["counters"], r["index"]).get(arm) for r in observations]
            if any(value is None for value in values):
                continue
            computable += 1
            cells: dict[Any, set[str]] = defaultdict(set)
            for value, row in zip(values, observations, strict=True):
                cells[value].add(row["post"])
            cells_used.update(cells)
            if all(len(posts) == 1 for posts in cells.values()) and len(cells) > 1:
                separated += 1
        per_arm[arm] = {
            "aliased_groups_computable": computable,
            "separated_perfectly": separated,
            "fraction": round(separated / computable, 4) if computable else None,
            "distinct_feature_values": len(cells_used),
        }

    # state-level restatement: conflicts remaining when the hash is (digest, feature)
    augmented: dict[str, int] = {}
    for arm in per_arm:
        remaining = 0
        for (pre, action), observations in groups.items():
            cells: dict[tuple, set[str]] = defaultdict(set)
            for row in observations:
                value = arm_values(row["counters"], row["index"]).get(arm)
                cells[(pre, value, action)].add(row["post"])
            remaining += sum(1 for posts in cells.values() if len(posts) > 1)
        augmented[arm] = remaining

    return {
        "summary": {
            key: summary[key]
            for key in (
                "outcome",
                "actions",
                "test_actions",
                "routing_actions",
                "unique_states",
                "transitions",
                "alias_conflicts",
                "reset_anomalies",
                "wall_clock",
            )
        },
        "gate": gate,
        "performs": len(explorer.performs),
        "performs_with_both_digests": sum(len(v) for v in groups.values()),
        "distinct_pre_action_groups": len(groups),
        "repeated_groups": len(repeated),
        "aliased_groups": len(aliased),
        "aliased_examples": [
            {
                "pre": pre,
                "action": list(action),
                "observations": [
                    {"index": r["index"], "post": r["post"], "counters": r["counters"]}
                    for r in observations
                ],
            }
            for (pre, action), observations in sorted(aliased.items())
        ],
        "separation_by_arm": per_arm,
        "conflicts_remaining_under_augmented_hash": augmented,
        "baseline_conflicts_unaugmented": sum(
            1 for observations in groups.values() if len({r["post"] for r in observations}) > 1
        ),
    }


# ======================================================================================
# Step 2b (deviation) -- the active parity probe
# ======================================================================================


class _Engine:
    """Thin fresh-engine driver: RESET, a sequence, and the digest after each action."""

    def __init__(self, game: str):
        from arcengine import ActionInput, GameAction  # noqa: PLC0415
        from e1_explorer import _hash, _plain_frames  # noqa: PLC0415
        from gi2_replay import ReplayDriver  # noqa: PLC0415

        self._input = ActionInput
        self._action = GameAction
        self._hash = _hash
        self._frames = _plain_frames
        self.driver = ReplayDriver(game)

    def act(self, action: tuple):
        action_id, row, col = action
        return self._input(
            id=self._action.from_id(action_id),
            data={} if row is None else {"y": row, "x": col},
        )

    def new(self):
        return self.driver.new_game()

    def step(self, engine, action: tuple) -> tuple[str | None, int]:
        response = self.driver.perform(engine, self.act(action))
        frames = self._frames(response.frame or [])
        digest = self._hash(1, frames[-1]) if frames else None
        return digest, int(response.levels_completed or 0)


RESET_ACTION = (0, None, None)


def verified_paths(
    engine: "_Engine",
    origin: str,
    *,
    max_length: int,
    actions: tuple[tuple, ...],
    width: int,
    per_length: int = 3,
) -> dict[str, dict[int, list[list[tuple]]]]:
    """Per digest and length, up to `per_length` EXECUTED action paths of that length.

    Paths chained out of the explorer's edge list do not replay: the edges were recorded at
    whatever hidden phase the explorer happened to be in, so a chain of them lands somewhere
    else more often than not (measured: 12 of 15 P1 targets, at every RESET count). So the
    paths are BUILT by execution instead — breadth-first over `(digest, length)` from a fresh
    game, every edge taken for real, every digest observed rather than assumed. Nothing here
    can be stale, because nothing here is remembered from another run.

    `(digest, length)` and not `digest` is the search state on purpose: the whole hypothesis
    under test is that the pair, not the digest, is what determines the outcome. Collapsing
    lengths would erase the instrument.

    SEVERAL paths per `(digest, length)` are kept because path length is confounded with path
    CONTENT: two routes to one board that differ in length also differ in which actions were
    taken, and a counter is only one of the things that could explain a difference in what
    happens next. Distinct same-length routes are the control that separates the two, and
    without it "the outcome depends on the count" is not a claim this design can make.
    """
    paths: dict[str, dict[int, list[list[tuple]]]] = defaultdict(lambda: defaultdict(list))
    paths[origin][0].append([])
    layer: list[tuple[str, list[tuple]]] = [(origin, [])]
    for length in range(1, max_length + 1):
        found: dict[str, list[list[tuple]]] = defaultdict(list)
        for digest, path in layer:
            for action in actions:
                handle = engine.new()
                engine.step(handle, RESET_ACTION)
                current = origin
                for step_action in path:
                    current, _ = engine.step(handle, step_action)
                if current != digest:  # cannot happen: the path was executed to get here
                    break
                target, levels = engine.step(handle, action)
                if target is None or levels:
                    continue
                if len(found[target]) >= per_length:
                    continue
                found[target].append(path + [action])
        for digest, routes in sorted(found.items()):
            paths[digest][length].extend(routes)
        # deterministic width cap: the search is for INSTRUMENTS, not for coverage. Only the
        # first route per digest is expanded; the alternates exist to be compared, not walked.
        layer = [(digest, routes[0]) for digest, routes in sorted(found.items())[:width]]
        if not layer:
            break
    return {digest: dict(lengths) for digest, lengths in paths.items()}


def parity_probe(
    game: str = GAME,
    *,
    targets: int = 12,
    max_path: int = 10,
    path_width: int = 400,
    p2_min_lengths: int = 3,
) -> dict[str, Any]:
    """Two probe families, each varying ONE counter with the pre-state digest held fixed.

    P1 GLOBAL   `new_game(); RESET; k filler actions; RESET; prefix; target`.
                The second RESET restores the visible board, so the in-episode count at the
                target is `len(prefix)` for every k while the count since ENVIRONMENT
                CREATION is `2 + k + len(prefix)`. Outcome varying with k means a counter
                that survives RESET; outcome constant across k refutes the global reading.

    P2 EPISODE  `new_game(); RESET; path; target` for two or more distinct paths of
                DIFFERENT length that land on the same grid digest. The in-episode count at
                the target is the path length; the board is identical by construction.
                Outcome varying with path length -- and cleanly with its parity -- is the
                in-episode counter.

    Every instance is its own engine, so nothing here can contaminate anything else, and each
    instance re-checks the digest it claims to be standing on before executing the target.
    """
    graph = json.loads((STORE / f"{game}.graph.json").read_text())
    origin = graph["origin"]
    engine = _Engine(game)
    conflicted = [(source, tuple(action)) for source, action in graph["conflicted"]]

    # The search moves on the simple actions only -- they are advertised at every state, so
    # the reachable set does not depend on which clicks happened to be sampled. Clicks are
    # still available as TARGETS below, taken from the store's own outgoing edges.
    search_actions = tuple((action_id, None, None) for action_id in (1, 2, 3, 4, 5))
    paths = verified_paths(
        engine, origin, max_length=max_path, actions=search_actions, width=path_width
    )

    outgoing: dict[str, list[tuple]] = defaultdict(list)
    for source, action, _ in graph["edges"]:
        outgoing[source].append(tuple(action))

    # ---- target selection -------------------------------------------------------------
    # The three conflicted edges first (the explorer caught them live), then a deterministic
    # spread over clean edges as the within-game control.
    clean = sorted(
        {
            (source, tuple(action))
            for source, action, _ in graph["edges"]
            if (source, tuple(action)) not in conflicted and source in paths
        },
        key=lambda pair: (min(paths[pair[0]]), pair[0], str(pair[1])),
    )
    stride = max(1, len(clean) // max(1, targets))
    p1_targets = conflicted + clean[::stride][:targets]

    def _parity_verdict(live: list[dict], field: str) -> dict[str, Any]:
        """Does `field mod 2` account for the outcome -- and could it have failed to?

        With two observations at consecutive counts, "parity explains it" is unfalsifiable:
        any function that separates the two values agrees. The verdict therefore records
        `falsifiable` separately, true only when some parity class holds two or more
        observations, and `mod3_also_explains` as the shape control -- a finer modulus with
        more cells separates more by arithmetic alone, which is exactly the multiple-arm
        hazard the note warns about.
        """
        posts = {o["post"] for o in live}
        cells: dict[int, set] = defaultdict(set)
        for o in live:
            cells[o[field] % 2].add(o["post"])
        cells3: dict[int, set] = defaultdict(set)
        for o in live:
            cells3[o[field] % 3].add(o["post"])
        return {
            "distinct_posts": len(posts),
            "varies": len(posts) > 1,
            "parity_explains": (
                len(posts) > 1 and len(cells) > 1 and all(len(v) == 1 for v in cells.values())
            ),
            # Falsifiable only when one parity class holds two DISTINCT counts. Repeated
            # observations at the same count are the route-content control, not a parity
            # test: with counts {2, 3} every function that separates 2 from 3 agrees with
            # parity, so "parity explains it" is unfalsifiable however many routes are run.
            # Counts {6, 8} in one class is what lets parity be wrong.
            "parity_falsifiable": any(
                len({o[field] for o in live if o[field] % 2 == value}) > 1 for value in cells
            ),
            "mod3_also_explains": (
                len(posts) > 1 and len(cells3) > 1 and all(len(v) == 1 for v in cells3.values())
            ),
            "counts_by_parity": {
                str(value): sorted(o[field] for o in live if o[field] % 2 == value)
                for value in sorted(cells)
            },
        }

    # ---- P1: global counter, in-episode count held fixed --------------------------------
    filler = (1, None, None)  # (w) an advertised simple action; its effect is irrelevant
    p1: list[dict[str, Any]] = []
    for source, action in p1_targets:
        route = paths.get(source)
        if not route:
            p1.append({"state": source, "action": list(action), "skipped": "no executed path"})
            continue
        prefix = route[min(route)][0]
        observations: list[dict[str, Any]] = []
        for offset in PROBE_OFFSETS:
            handle = engine.new()
            engine.step(handle, RESET_ACTION)
            for _ in range(offset):
                engine.step(handle, filler)
            digest, _ = engine.step(handle, RESET_ACTION)
            if digest != origin:
                observations.append({"offset": offset, "discarded": "RESET did not restore origin"})
                continue
            for step_action in prefix:
                digest, _ = engine.step(handle, step_action)
            if digest != source:
                observations.append({"offset": offset, "discarded": "path replay diverged"})
                continue
            post, levels = engine.step(handle, action)
            observations.append(
                {
                    "offset": offset,
                    "global_count_at_pre": 2 + offset + len(prefix),
                    "episode_count_at_pre": len(prefix),
                    "post": post,
                    "levels": levels,
                }
            )
        live = [o for o in observations if "post" in o]
        p1.append(
            {
                "state": source,
                "action": list(action),
                "conflicted_in_store": (source, action) in conflicted,
                "path_length": len(prefix),
                "usable_offsets": len(live),
                "observations": observations,
                "verdict": _parity_verdict(live, "global_count_at_pre") if live else None,
            }
        )

    # ---- P2: in-episode counter, board held fixed ---------------------------------------
    # `p2_min_lengths = 3` is the default because two counts of the SAME parity are what make
    # the parity question falsifiable. Where the game offers only two lengths at a shared
    # digest, dropping to 2 still answers the prior question -- does the count matter at all,
    # and is it the count rather than the route content -- and the tally reports how many
    # targets could have refuted parity, which is then zero. Never read a parity verdict off a
    # run whose `targets_where_parity_was_falsifiable` is 0.
    multi = sorted(
        (state for state, lengths in paths.items() if len(lengths) >= p2_min_lengths),
        key=lambda state: (-len(paths[state]), min(paths[state]), state),
    )
    p2: list[dict[str, Any]] = []
    for state in multi[: targets * 2]:
        # the store's own outgoing actions where it has any, else the simple actions --
        # a state the explorer never stood on is still a legitimate probe site
        actions = sorted(set(outgoing.get(state, ())), key=str) or list(search_actions)
        chosen = [a for s, a in conflicted if s == state] or actions[
            :: max(1, len(actions) // 3)
        ][:3]
        for action in chosen:
            observations = []
            for length, routes in sorted(paths[state].items()):
                for variant, path in enumerate(routes):
                    handle = engine.new()
                    digest, _ = engine.step(handle, RESET_ACTION)
                    for step_action in path:
                        digest, _ = engine.step(handle, step_action)
                    if digest != state:  # cannot happen for executed paths; checked anyway
                        observations.append(
                            {"path_length": length, "variant": variant, "discarded": "diverged"}
                        )
                        continue
                    post, levels = engine.step(handle, action)
                    observations.append(
                        {
                            "path_length": length,
                            "variant": variant,
                            "episode_count_at_pre": length,
                            "global_count_at_pre": 1 + length,
                            "post": post,
                            "levels": levels,
                        }
                    )
            live = [o for o in observations if "post" in o]
            if len({o["path_length"] for o in live}) < 2:
                continue
            # CONTROL: distinct routes of the SAME length. Disagreement here means the
            # outcome tracks path content, and no counter reading survives it.
            same_length: dict[int, set] = defaultdict(set)
            for o in live:
                same_length[o["path_length"]].add(o["post"])
            tested = {k: v for k, v in same_length.items() if sum(
                1 for o in live if o["path_length"] == k
            ) > 1}
            p2.append(
                {
                    "state": state,
                    "action": list(action),
                    "conflicted_in_store": (state, action) in conflicted,
                    "path_lengths": sorted(paths[state]),
                    "routes_per_length": {
                        str(k): len(v) for k, v in sorted(paths[state].items())
                    },
                    "usable_paths": len(live),
                    "same_length_control": {
                        "lengths_with_two_or_more_routes": len(tested),
                        "lengths_where_routes_agree": sum(
                            1 for posts in tested.values() if len(posts) == 1
                        ),
                        "outcome_is_a_function_of_length": bool(tested)
                        and all(len(posts) == 1 for posts in tested.values()),
                    },
                    "observations": observations,
                    "verdict": _parity_verdict(live, "episode_count_at_pre"),
                }
            )

    def _tally(rows: list[dict], minimum: int, field: str) -> dict[str, Any]:
        live = [r for r in rows if r.get("verdict") and r[field] >= minimum]
        falsifiable = [r for r in live if r["verdict"]["parity_falsifiable"]]
        return {
            "targets": len(rows),
            "targets_usable": len(live),
            "varying": sum(1 for r in live if r["verdict"]["varies"]),
            "parity_explains": sum(1 for r in live if r["verdict"]["parity_explains"]),
            "targets_where_parity_was_falsifiable": len(falsifiable),
            "parity_explains_among_falsifiable": sum(
                1 for r in falsifiable if r["verdict"]["parity_explains"]
            ),
            "mod3_also_explains": sum(1 for r in live if r["verdict"]["mod3_also_explains"]),
        }

    return {
        "search_actions": [list(a) for a in search_actions],
        "path_search": {
            "max_length": max_path,
            "width": path_width,
            "digests_reached": len(paths),
            "per_length_routes": 3,
            "digests_with_3plus_lengths": sum(1 for v in paths.values() if len(v) > 2),
            # Which length TRIPLES the search can actually offer. The parity test needs two
            # counts of the same parity, so this is the instrument's real resolution and a
            # limit on any claim about the counter's functional form.
            "length_bands_with_3plus": {
                str(sorted(v)): count
                for v, count in Counter(
                    tuple(sorted(lengths)) for lengths in paths.values() if len(lengths) > 2
                ).items()
            },
        },
        "p1_global": {
            "definition": (
                "RESET; k filler; RESET; path; target -- in-episode count held fixed at "
                "len(path), count since environment creation varies with k"
            ),
            "offsets": list(PROBE_OFFSETS),
            "conflicted_probed": sum(1 for r in p1 if r.get("conflicted_in_store")),
            **_tally(p1, 2, "usable_offsets"),
            "results": p1,
        },
        "p2_episode": {
            "definition": (
                "RESET; path; target over EXECUTED paths of different length to one digest "
                "-- board identical, in-episode count = path length"
            ),
            "min_lengths_required": p2_min_lengths,
            "conflicted_probed": sum(1 for r in p2 if r["conflicted_in_store"]),
            "outcome_is_a_function_of_length": sum(
                1 for r in p2 if r["same_length_control"]["outcome_is_a_function_of_length"]
            ),
            # The observed length -> outcome shape, as an equivalence pattern over the
            # probed lengths: `(0, 0, 1)` reads "the first two counts agree, the third does
            # not". Uniformity across targets is what makes the parity refutation a finding
            # rather than an artifact of one state.
            "length_outcome_patterns": dict(
                Counter(
                    str(
                        [
                            sorted(
                                {
                                    o["post"]
                                    for o in r["observations"]
                                    if "post" in o and o["path_length"] == length
                                }
                            )
                            == sorted(
                                {
                                    o["post"]
                                    for o in r["observations"]
                                    if "post" in o
                                    and o["path_length"] == min(r["path_lengths"])
                                }
                            )
                            for length in sorted(r["path_lengths"])
                        ]
                    )
                    for r in p2
                )
            ),
            "same_length_routes_disagree": sum(
                1
                for r in p2
                if r["same_length_control"]["lengths_with_two_or_more_routes"]
                > r["same_length_control"]["lengths_where_routes_agree"]
            ),
            **_tally(p2, 2, "usable_paths"),
            "results": p2,
        },
    }


# ======================================================================================
# Step 3 -- mining with the injected feature
# ======================================================================================


def store_counters(game: str, transitions: list[Transition]) -> tuple[list[dict[str, int]], str]:
    """Counters for the store rows: episode counts come from the instrumented rerun.

    The store's own `step` is a GLOBAL action index and the log holds no RESETs, so the
    in-episode count is not recoverable from it -- that is what the rerun is for. The rerun
    gate (`rerun.gate.all_rows_match`) is what licenses joining the two by step index; without
    a passing gate this falls back to the global counter alone and says so.
    """
    performs = RERUN_DIR / f"{game}.performs.jsonl"
    if not performs.exists():
        return [{"global": t.step - 1} for t in transitions], "global_only_no_rerun"
    by_index: dict[int, dict[str, int]] = {}
    with performs.open() as handle:
        for line in handle:
            row = json.loads(line)
            by_index[row["index"]] = row["counters"]
    missing = sum(1 for t in transitions if t.step not in by_index)
    if missing:
        return (
            [by_index.get(t.step, {"global": t.step - 1}) for t in transitions],
            f"rerun_join_incomplete:{missing}",
        )
    return [by_index[t.step] for t in transitions], "rerun_join"


def feature_purity(train: list[Transition], mode: str, feature: str) -> dict[str, Any]:
    """How much of each UNRESOLVED key one feature explains, below the tier-1 bar.

    Tier 1 is all-or-nothing (``rs_e0.mine``): a feature is selected only if every cell of its
    partition holds exactly one effect, so `rules mined` cannot tell "carries no signal" from
    "carries most of the signal and not all of it". Purity is the fraction of a key's
    transitions landing in a single-effect cell. It is REPORTED, never mined on -- lowering
    the tier-1 bar is a rule-model change and adopting one on the strength of the pass that
    motivated it is how a measurement becomes a story.
    """
    from rs_e0 import _hashable, abstract  # noqa: PLC0415

    by_key: dict[tuple, list[int]] = defaultdict(list)
    for index, transition in enumerate(train):
        by_key[transition.key()].append(index)
    rows: list[dict[str, Any]] = []
    for key, indices in sorted(by_key.items(), key=lambda item: str(item[0])):
        if len({abstract(train[i].effect, mode) for i in indices}) == 1:
            continue  # tier 0 resolves it; no guard is needed
        if any(feature not in train[i].guards for i in indices):
            continue
        partition: dict[Any, list[int]] = defaultdict(list)
        for i in indices:
            partition[_hashable(train[i].guards[feature])].append(i)
        pure = sum(
            len(cell)
            for cell in partition.values()
            if len({abstract(train[i].effect, mode) for i in cell}) == 1
        )
        rows.append(
            {
                "key": str(key),
                "transitions": len(indices),
                "purity": round(pure / len(indices), 4),
                "cells": len(partition),
            }
        )
    covered = sum(row["transitions"] for row in rows)
    return {
        "rows_with_feature": sum(1 for t in train if feature in t.guards),
        "rows_total": len(train),
        "unresolved_keys": len(rows),
        "transitions_under_unresolved_keys": covered,
        "weighted_purity": (
            round(sum(row["purity"] * row["transitions"] for row in rows) / covered, 4)
            if covered
            else None
        ),
        "max_purity": max((row["purity"] for row in rows), default=None),
        "keys_fully_resolved_by_feature": sum(1 for row in rows if row["purity"] == 1.0),
    }


def _floor(game: str) -> dict[str, Any]:
    document = json.loads(FLOOR.read_text())
    row = document["games"][game]
    out: dict[str, Any] = {}
    for mode in MODES:
        cell = row["mechanics"][mode]
        doses = {
            (d["dose"] if not d.get("full_store") else "full"): d
            for d in cell["doses"]
            if "skipped" not in d
        }
        out[mode] = {
            "doses": {
                str(k): {
                    "on_human_l1": v["on_human_l1"],
                    "on_human_l2": v["on_human_l2"],
                    "rules": v["rules"],
                }
                for k, v in doses.items()
            },
            "human_ceiling_on_l2": cell["human_ceiling_on_l2"],
        }
    return out


def _slim(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "coverage",
            "correct",
            "accuracy_over_covered",
            "accuracy_over_all",
            "rules_fired",
            "rule_survival_rate",
            "failure_split",
        )
    }


def mine_arms(game: str = GAME, *, arms: tuple[str, ...] = ARMS) -> dict[str, Any]:
    """Baseline plus one run per arm: store->human L1/L2 at both dose endpoints, and the
    CEILING arm (mine human L1, score human L2) which is the direct load-bearing test."""
    table = human_counters(game)
    human = load_game(game, max_level=2)
    human_l1 = [t for t in human if t.level == 1]
    human_l2 = [t for t in human if t.level == 2]
    explorer, _post_missing = load_store(game)

    store_counter_rows, join = store_counters(game, explorer)
    human_l1_counters = counters_for(human_l1, table)
    human_l2_counters = counters_for(human_l2, table)

    available_store = inject(explorer, store_counter_rows)
    available_l1 = inject(human_l1, human_l1_counters)
    available_l2 = inject(human_l2, human_l2_counters)

    out: dict[str, Any] = {
        "store_transitions": len(explorer),
        "human_l1": len(human_l1),
        "human_l2": len(human_l2),
        "store_counter_source": join,
        "arms_available_store": available_store,
        "arms_available_human_l1": available_l1,
        "arms_available_human_l2": available_l2,
        "human_episode_counter_coverage": round(
            sum(1 for c in human_l1_counters + human_l2_counters if "episode" in c)
            / max(1, len(human_l1_counters) + len(human_l2_counters)),
            4,
        ),
        "floor_of_record": _floor(game),
        "by_arm": {},
    }

    def run(keep: str | None) -> dict[str, Any]:
        """`keep=None` is the baseline: strip every injected feature."""

        def masked(transitions: list[Transition]) -> list[Transition]:
            for transition in transitions:
                for arm in ARMS:
                    key = f"parity:{arm}"
                    if arm != keep and key in transition.guards:
                        transition.guards.pop(key)
            return transitions

        # guards are rebuilt from scratch each call, so re-inject then mask
        inject(explorer, store_counter_rows)
        inject(human_l1, human_l1_counters)
        inject(human_l2, human_l2_counters)
        masked(explorer)
        masked(human_l1)
        masked(human_l2)

        cell: dict[str, Any] = {}
        for mode in MODES:
            per_dose: dict[str, Any] = {}
            for dose in DOSES:
                prefix = explorer if dose is None else explorer[:dose]
                rules, _ = mine(prefix, mode, "none")
                label = "full" if dose is None else str(dose)
                per_dose[label] = {
                    "rules": len(rules),
                    "guard_selected": sum(
                        1
                        for rule in rules.values()
                        if rule.guard == f"parity:{keep}"
                    )
                    if keep
                    else 0,
                    "on_human_l1": _slim(score(rules, prefix, human_l1, mode)),
                    "on_human_l2": _slim(score(rules, prefix, human_l2, mode)),
                }
            ceiling_rules, _ = mine(human_l1, mode, "none")
            cell[mode] = {
                "doses": per_dose,
                "purity_on_store": feature_purity(explorer, mode, f"parity:{keep}")
                if keep
                else None,
                "purity_on_human_l1": feature_purity(human_l1, mode, f"parity:{keep}")
                if keep
                else None,
                "ceiling_rules": len(ceiling_rules),
                "ceiling_guard_selected": sum(
                    1 for rule in ceiling_rules.values() if rule.guard == f"parity:{keep}"
                )
                if keep
                else 0,
                "human_ceiling_on_l2": _slim(score(ceiling_rules, human_l1, human_l2, mode)),
            }
        return cell

    out["by_arm"]["baseline"] = run(None)
    for arm in arms:
        if arm not in available_store or arm not in available_l1:
            out["by_arm"][arm] = {"skipped": "arm not computable on both sides"}
            continue
        out["by_arm"][arm] = run(arm)

    # memorizer floor is arm-independent; recorded once as the reference
    out["memorizer_on_human_l1"] = {
        mode: memorizer(explorer, human_l1, mode) for mode in MODES
    }

    # SELF-CHECK. Every arm above reports `guard_selected: 0`, and that reading is only worth
    # anything if an injected key CAN be selected. So inject an oracle -- a feature equal to
    # the effect the miner is trying to predict -- and confirm tier 1 takes it. A zero here
    # would mean the wiring is broken, not that the arms carry no signal.
    from rs_e0 import abstract  # noqa: PLC0415

    for transition in explorer:
        for arm in ARMS:
            transition.guards.pop(f"parity:{arm}", None)
    baseline_rules, _ = mine(explorer, "moveset", "none")
    for transition in explorer:
        transition.guards["parity:oracle"] = str(abstract(transition.effect, "moveset"))
    oracle_rules, _ = mine(explorer, "moveset", "none")
    for transition in explorer:
        transition.guards.pop("parity:oracle", None)
    out["injection_selfcheck"] = {
        "mode": "moveset",
        "rules_without_oracle": len(baseline_rules),
        "rules_with_oracle": len(oracle_rules),
        "oracle_selected": sum(
            1 for rule in oracle_rules.values() if rule.guard == "parity:oracle"
        ),
    }
    return out


# ======================================================================================
# Step 4 -- cross-game sanity
# ======================================================================================


def cross_game(game: str, arm: str) -> dict[str, Any]:
    table = human_counters(game)
    human = load_game(game, max_level=2)
    human_l1 = [t for t in human if t.level == 1]
    human_l2 = [t for t in human if t.level == 2]
    explorer, _ = load_store(game)
    if not explorer or not human_l1:
        return {"game": game, "skipped": "empty store or no human L1"}
    rows, join = store_counters(game, explorer)

    baseline: dict[str, Any] = {}
    for mode in MODES:
        rules, _ = mine(explorer, mode, "none")
        baseline[mode] = {
            "on_human_l1": _slim(score(rules, explorer, human_l1, mode)),
            "on_human_l2": _slim(score(rules, explorer, human_l2, mode)),
        }

    inject(explorer, rows)
    inject(human_l1, counters_for(human_l1, table))
    inject(human_l2, counters_for(human_l2, table))
    for transitions in (explorer, human_l1, human_l2):
        for transition in transitions:
            for other in ARMS:
                if other != arm:
                    transition.guards.pop(f"parity:{other}", None)

    with_arm: dict[str, Any] = {}
    for mode in MODES:
        rules, _ = mine(explorer, mode, "none")
        with_arm[mode] = {
            "rules": len(rules),
            "guard_selected": sum(
                1 for rule in rules.values() if rule.guard == f"parity:{arm}"
            ),
            "on_human_l1": _slim(score(rules, explorer, human_l1, mode)),
            "on_human_l2": _slim(score(rules, explorer, human_l2, mode)),
        }

    deltas = {
        mode: {
            target: round(
                (with_arm[mode][target]["accuracy_over_all"] or 0)
                - (baseline[mode][target]["accuracy_over_all"] or 0),
                4,
            )
            for target in ("on_human_l1", "on_human_l2")
        }
        for mode in MODES
    }
    return {
        "game": game,
        "store_transitions": len(explorer),
        "store_counter_source": join,
        "arm_present_on_store": sum(1 for t in explorer if f"parity:{arm}" in t.guards),
        "arm_present_on_human_l1": sum(1 for t in human_l1 if f"parity:{arm}" in t.guards),
        "baseline": baseline,
        "with_arm": with_arm,
        "delta": deltas,
    }


def _rerun_job(args: tuple[str, int, float, int]) -> dict[str, Any]:
    game, budget, wall, cap = args
    try:
        row = rerun(game, budget=budget, wall=wall, cap=cap)
    except Exception as error:
        return {"game": game, "error": f"{type(error).__name__}: {error}"}
    return {
        "game": game,
        "gate": row["gate"],
        "summary": row["summary"],
        "aliased_groups": row["aliased_groups"],
        "repeated_groups": row["repeated_groups"],
    }


def _cross_job(args: tuple[str, str, str]) -> dict[str, Any]:
    game, arm, vocab_version = args
    set_vocab(vocab_version)
    try:
        return cross_game(game, arm)
    except Exception as error:
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


# ======================================================================================
# Runner
# ======================================================================================


def _load(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())
    return {"format_version": FORMAT_VERSION, "game": GAME}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=(
            "census", "store_census", "rerun", "rerun_all", "probe", "mine", "cross", "all"
        ),
        default="all",
    )
    parser.add_argument("--game", default=GAME)
    parser.add_argument("--arm", default="c1_global", help="winning arm for stages cross")
    parser.add_argument("--budget", type=int, default=3000)
    parser.add_argument("--wall", type=float, default=1200.0)
    parser.add_argument("--cap", type=int, default=96)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument(
        "--p2-min-lengths",
        type=int,
        default=3,
        dest="p2_min_lengths",
        help="distinct path lengths a digest needs to enter P2; 3 makes parity falsifiable",
    )
    parser.add_argument("--vocab", choices=("v1", "v2"), default="v2")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument(
        "--store-dir",
        type=Path,
        default=ROOT / "logs/e1_store_v3",
        help="store read by --stage store_census",
    )
    args = parser.parse_args()

    set_vocab(args.vocab)
    document = _load(args.out)
    document["format_version"] = FORMAT_VERSION
    document["game"] = args.game
    document["guard_vocabulary"] = vocab()
    document["store"] = str(STORE.relative_to(ROOT))
    document["floor_of_record"] = str(FLOOR.relative_to(ROOT))
    stages = (
        ("census", "rerun", "rerun_all", "probe", "mine", "cross")
        if args.stage == "all"
        else (args.stage,)
    )

    for stage in stages:
        if stage == "census":
            document["census"] = census(args.game)
            row = document["census"]
            print(
                f"census: rows={row['rows']} groups={row['distinct_pre_action_groups']} "
                f"repeated={row['repeated_groups']} aliased={row['aliased_groups_by_post_hash']} "
                f"recorded_conflicts={row['recorded_conflict_records']}",
                flush=True,
            )
        elif stage == "store_census":
            games = [g for g in ALL_GAMES if g not in EXCLUDED_GAMES]
            rows = {}
            for game in games:
                if not (args.store_dir / f"{game}.transitions.jsonl").exists():
                    continue
                row = store_census(args.store_dir, game)
                rows[game] = row
                t, p, c = row["transitions"], row["performs"], row["confirmations"]
                print(
                    f"{game:5s} trans rows={t['rows']:5d} rep={t['repeated_groups']:4d} "
                    f"alias={t['aliased_different_count']:4d} nondet={t['disagreeing_same_count']:3d} | "
                    f"performs rep={p['repeated_groups']:4d} alias={p['aliased_different_count']:4d} "
                    f"nondet={p['disagreeing_same_count']:3d} | confirm {c['landed']}/{c['attempted']} "
                    f"dis={c['disagreed']}",
                    flush=True,
                )
            document["store_census"] = {"store": str(args.store_dir), "games": rows}
        elif stage == "rerun":
            document["rerun"] = rerun(
                args.game, budget=args.budget, wall=args.wall, cap=args.cap
            )
            row = document["rerun"]
            print(
                f"rerun: gate={'PASS' if row['gate']['passed'] else 'FAIL'} "
                f"performs={row['performs']} repeated={row['repeated_groups']} "
                f"aliased={row['aliased_groups']}",
                flush=True,
            )
        elif stage == "rerun_all":
            games = [g for g in ALL_GAMES if g not in EXCLUDED_GAMES]
            jobs = [(game, args.budget, args.wall, args.cap) for game in games]
            rows = []
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
                for row in pool.map(_rerun_job, jobs):
                    rows.append(row)
                    if "error" in row:
                        print(f"{row['game']:5s} ERROR {row['error']}", flush=True)
                        continue
                    print(
                        f"{row['game']:5s} gate={'PASS' if row['gate']['passed'] else 'FAIL'} "
                        f"rows={row['gate']['rerun_rows']} aliased={row['aliased_groups']}",
                        flush=True,
                    )
            document["rerun_all"] = {
                "games": {r["game"]: r for r in rows},
                "gate_passed": sum(1 for r in rows if r.get("gate", {}).get("passed")),
                "games_run": len(rows),
            }
        elif stage == "probe":
            document["probe"] = parity_probe(
                args.game, p2_min_lengths=args.p2_min_lengths
            )
            search = document["probe"]["path_search"]
            print(
                f"probe paths: digests={search['digests_reached']} "
                f"with_3plus_lengths={search['digests_with_3plus_lengths']}",
                flush=True,
            )
            for family in ("p1_global", "p2_episode"):
                row = document["probe"][family]
                print(
                    f"probe {family}: targets={row['targets']} usable={row['targets_usable']} "
                    f"varying={row['varying']} parity_explains={row['parity_explains']} "
                    f"falsifiable={row['targets_where_parity_was_falsifiable']} "
                    f"parity_among_falsifiable={row['parity_explains_among_falsifiable']} "
                    f"mod3_also={row['mod3_also_explains']}",
                    flush=True,
                )
        elif stage == "mine":
            document["mine"] = mine_arms(args.game)
            base = document["mine"]["by_arm"]["baseline"]["full"]["doses"]["full"]
            print(
                f"mine: baseline full L1={base['on_human_l1']['accuracy_over_all']} "
                f"L2={base['on_human_l2']['accuracy_over_all']}",
                flush=True,
            )
            for arm in ARMS:
                cell = document["mine"]["by_arm"].get(arm, {})
                if "skipped" in cell:
                    print(f"  {arm:18s} skipped: {cell['skipped']}", flush=True)
                    continue
                dose = cell["full"]["doses"]["full"]
                print(
                    f"  {arm:18s} L1={dose['on_human_l1']['accuracy_over_all']:.4f} "
                    f"L2={dose['on_human_l2']['accuracy_over_all']:.4f} "
                    f"selected={dose['guard_selected']} "
                    f"ceilL2={cell['full']['human_ceiling_on_l2']['accuracy_over_all']:.4f}",
                    flush=True,
                )
        elif stage == "cross":
            games = [g for g in ALL_GAMES if g not in EXCLUDED_GAMES]
            rows = []
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
                jobs = [(game, args.arm, args.vocab) for game in games]
                for row in pool.map(_cross_job, jobs):
                    rows.append(row)
                    if "error" in row or "skipped" in row:
                        print(f"{row['game']:5s} {row.get('error') or row['skipped']}", flush=True)
                        continue
                    print(
                        f"{row['game']:5s} full dL1={row['delta']['full']['on_human_l1']:+.4f} "
                        f"dL2={row['delta']['full']['on_human_l2']:+.4f} "
                        f"moveset dL1={row['delta']['moveset']['on_human_l1']:+.4f} "
                        f"dL2={row['delta']['moveset']['on_human_l2']:+.4f} "
                        f"sel={row['with_arm']['full']['guard_selected']}",
                        flush=True,
                    )
            document["cross_game"] = {"arm": args.arm, "games": {r["game"]: r for r in rows}}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
