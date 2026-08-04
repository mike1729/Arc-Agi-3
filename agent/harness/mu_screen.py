#!/usr/bin/env python3
"""MU screen driver: inventory, context audit, freeze, run, score, summarize.

Implements MU SS5-SS7 (``notes/mu-representation-screen.md``) over ``mu_probes`` and
``mu_render``. The order of work is the note's SS6: everything here except ``--run`` is
zero-call, and ``--freeze`` refuses while ``gate_manifest.yaml -> mu`` is DRAFT, so no
measured call can precede manifest acceptance.

  --inventory  build logs/mu_inventory.json: the case inventory with gold, the model-free
               floor score of every case, the full per-arm context audit through the exact
               measurement tokenizer and chat template, the shortfall record, and the
               derived call budget.
  --audit      re-print the context audit of an existing inventory.
  --bringup    measure per-call latency at MU prompt sizes and validate guided-JSON
               decoding against the live measurement stack (discarded synthetic prompts,
               never case content); writes logs/mu_bringup.json, which --freeze requires.
  --freeze     build logs/mu_freeze.json (requires an accepted, frozen mu block AND the
               bring-up artifact, whose measured numbers the block must carry).
  --verify     rebuild the freeze and compare it to disk.
  --run        the measured S or C pass into logs/mu_raw.jsonl (resumable).
  --select     nominate one representation per probe from S only.
  --score      score logs/mu_raw.jsonl into logs/mu_results.json.
  --summary    print the representation x probe profile.

Determinizations recorded here (published before any measured call):

  * Anchor walk. For each (game, role, probe) the eligible anchors are placed in the frozen
    hash order of ``mu_probes.hash_order`` and walked; the first ``cases_per_probe``
    anchors that yield an ELIGIBLE case are kept. The walk stops after
    ``anchor_slack_factor x cases_per_probe`` anchors: exhausting the slack is a published
    shortfall for that cell, never a resample and never a relaxed rule.
  * Context feasibility is an anchor eligibility condition, not a post-hoc exclusion. An
    anchor is admissible only when ALL SEVEN arms fit ``PROMPT_TOKENS_MAX`` under the exact
    tokenizer and chat template. Screening on the largest arms during the walk and auditing
    all seven for the selected cases keeps the factorial matched: every arm sees exactly the
    same cases, which is what makes an arm difference a rendering difference. The number of
    anchors excluded this way is published per game — m0r0 reaches 879 objects on one level
    and is the reason the condition exists.
  * Floors are computed at inventory time from the same evidence window, so the model-free
    baseline of every case is on record before any model sees it.
  * T3 splits its cases between the executed-action and fork-action forms by the frozen
    ``T3_EXECUTED_SHARE``; each form has its own anchor walk.
  * Scoring. A case rate is the probe's per-case rate in [0,1]; case rates are averaged
    within game, then the six game means are averaged with equal weight (MU SS5). Parse,
    schema, and context failures score 0 and stay in the denominator (MU SS2).
  * Selection (MU SS5) uses S only and covers T2-T5. Contenders are limited to arms that
    pass the T1 legibility gate on S; among those the highest game-macro wins, and within
    ``selection_margin`` the cheaper arm wins (fewer prompt tokens, then the frozen arm
    order). No S-legible arm -> ``no_legible_arm`` for that probe and no C pass for it.
    T1 itself is never selected: its floor is exact by construction, so it is a gate on
    eligibility and interpretation, never a screen-positive cell. The C plan runs the
    selected arm on every T2-T5 C case PLUS T1 on every unique selected arm, so
    confirmation legibility is measured for every arm the profile actually uses.
  * Confirmation (MU SS4-SS5): a selected cell is SCREEN-POSITIVE — deliberately not
    called a capability, since C holds ~18 cases per probe and one binary case moves
    game-macro by ~0.056 — only when the arm is C-legible, beats its floor game-macro by
    ``screen_positive_margin``, and beats the floor's per-game mean in at least
    ``screen_positive_min_games`` of the six games.

Run:
  .venv/bin/python agent/harness/mu_screen.py --inventory --jobs 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/harness"))

import mu_probes as probes  # noqa: E402
import mu_render as render  # noqa: E402

MANIFEST = ROOT / "gate_manifest.yaml"
NOTE = ROOT / "notes/mu-representation-screen.md"
INVENTORY = ROOT / "logs/mu_inventory.json"
FREEZE = ROOT / "logs/mu_freeze.json"
BRINGUP = ROOT / "logs/mu_bringup.json"
RAW = ROOT / "logs/mu_raw.jsonl"
RESULTS = ROOT / "logs/mu_results.json"

FORMAT_VERSION = 1
MODEL_BASENAME = "Qwen3.6-27B-8bit"
DEV_MODEL_BASENAME = "Qwen3.6-35B-A3B-4bit"     # development only; non-evidentiary (MU SS1)
TOKENIZER_DIR = Path("/Users/michal/models/mlx/Qwen3.6-27B-8bit")
MAX_OUTPUT_TOKENS = 512
RETRY_RESERVE = 0.10                            # predeclared reserve over the planned calls
SELECTION_MARGIN = 0.09                         # OPERATOR 2026-08-03, mirrors manifest
SCREEN_POSITIVE_MARGIN = 0.09                   # OPERATOR 2026-08-03, mirrors manifest
SCREEN_POSITIVE_MIN_GAMES = 4                   # PROPOSED, mirrors gate_manifest mu
T1_LEGIBILITY_GATE = 0.70                       # PROPOSED, mirrors gate_manifest mu
BRINGUP_CALLS = 12                              # PROPOSED, mirrors gate_manifest mu; discarded
BRINGUP_PROMPT_TOKEN_TARGETS = (1400, 12600, 24500)  # census min/median/max, mirrored
SELECTABLE_PROBES = ("T2", "T3", "T4", "T5")    # T1 is a gate (MU SS2), never selected
FUNDING_PROBES = ("T3", "T4")                   # PROPOSED, mirrors gate_manifest mu; MU SS5.1
MIN_SCREEN_POSITIVE_CELLS = 1                   # PROPOSED, mirrors gate_manifest mu; MU SS5.1

FROZEN_FILES = (
    "agent/harness/mu_probes.py",
    "agent/harness/mu_render.py",
    "agent/harness/mu_screen.py",
    "notes/mu-representation-screen.md",
    "tests/test_mu_probes.py",
    "tests/test_mu_render.py",
    "tests/test_mu_screen.py",
)
GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "seed": 20260803,
    "chat_template_kwargs": {"enable_thinking": False},
}
# Arms in cost order (entailed by payload inclusion for grid < objects < events < card);
# map/verbal/film are independent renderings and are ordered after them for tie-breaks.
ARM_ORDER = render.ARMS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ====================================================================================
# Manifest access
# ====================================================================================


def manifest_block() -> dict[str, Any]:
    import yaml

    document = yaml.safe_load(MANIFEST.read_text())
    block = document.get("mu")
    if not isinstance(block, dict):
        raise ValueError("gate_manifest.yaml has no mu block")
    return block


def _mirrored() -> dict[str, Any]:
    """Manifest path -> the value this code actually applies."""
    return {
        "windows.prefix_window": probes.PREFIX_WINDOW,
        "cases.cases_per_probe_per_game_per_role": probes.CASES_PER_PROBE_PER_GAME_PER_ROLE,
        "cases.t3_executed_share": probes.T3_EXECUTED_SHARE,
        "cases.anchor_slack_factor": probes.ANCHOR_SLACK_FACTOR,
        "cases.t2_rows_max": probes.T2_ROWS_MAX,
        "cases.t3_objects_per_case": probes.T3_OBJECTS_PER_CASE,
        "cases.closed_action_options": probes.CLOSED_ACTION_OPTIONS,
        "cases.closed_action_options_min": probes.CLOSED_ACTION_OPTIONS_MIN,
        "cases.mouse_representative_cap": probes.MOUSE_REPRESENTATIVE_CAP,
        "map_arm.map_lattice": probes.MAP_LATTICE,
        "map_arm.card_click_block": probes.CARD_CLICK_BLOCK,
        "context.context_window_tokens": probes.CONTEXT_WINDOW_TOKENS,
        "context.output_headroom_tokens_min": probes.OUTPUT_HEADROOM_TOKENS,
        "selection.selection_margin": SELECTION_MARGIN,
        "floors.screen_positive_margin": SCREEN_POSITIVE_MARGIN,
        "floors.screen_positive_min_games": SCREEN_POSITIVE_MIN_GAMES,
        "floors.t1_legibility_gate": T1_LEGIBILITY_GATE,
        "bringup.calls": BRINGUP_CALLS,
        "bringup.prompt_token_targets": list(BRINGUP_PROMPT_TOKEN_TARGETS),
        "decision.funding_probes": list(FUNDING_PROBES),
        "decision.min_screen_positive_cells": MIN_SCREEN_POSITIVE_CELLS,
        "representations.arms": list(render.ARMS),
        "model.measurement": MODEL_BASENAME,
    }


def _dig(block: dict[str, Any], path: str) -> Any:
    node: Any = block
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def check_mirrors(block: dict[str, Any]) -> list[str]:
    """Every number this code applies must equal the manifest's, or the run fails closed."""
    problems = []
    for path, expected in _mirrored().items():
        found = _dig(block, path)
        if isinstance(expected, dict) and isinstance(found, dict):
            found = {str(name): value for name, value in found.items()}
            expected = {str(name): value for name, value in expected.items()}
        if found != expected:
            problems.append(f"mu.{path}: manifest {found!r} != implementation {expected!r}")
    return problems


# ====================================================================================
# Tokenizer (the exact measurement tokenizer and chat template)
# ====================================================================================


_TOKENIZER = None


def tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        from transformers import AutoTokenizer

        _TOKENIZER = AutoTokenizer.from_pretrained(str(TOKENIZER_DIR))
    return _TOKENIZER


def prompt_tokens(messages: list[dict[str, Any]]) -> int:
    text = tokenizer().apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        **GENERATION["chat_template_kwargs"],
    )
    return len(tokenizer()(text).input_ids)


# ====================================================================================
# Inventory
# ====================================================================================


def _anchor_pool(stubs: list[dict[str, Any]], probe: str) -> list[int]:
    span = probes.PREFIX_WINDOW[probe]
    return [
        index
        for index in range(len(stubs))
        if probes.window_members(stubs, index, span) is not None
    ]


def _successor(stubs: list[dict[str, Any]], index: int) -> int | None:
    following = index + 1
    if following >= len(stubs) or stubs[following]["starts_window"]:
        return None
    return following


def _window_for(
    env: str, guid: str, role: str, probe: str, stubs, grids, index: int
) -> probes.EvidenceWindow:
    members = probes.window_members(stubs, index, probes.PREFIX_WINDOW[probe])
    return probes.build_window(env, guid, role, probe, stubs, grids, members)


def _state_key(stub: dict[str, Any]) -> str:
    return f"{stub['step']}.{stub['frame_index']}"


def _feasibility(case: dict[str, Any], window, arms: tuple[str, ...]) -> dict[str, int]:
    tokens = {}
    for arm in arms:
        messages, _ = render.render_case(arm, case, window)
        tokens[arm] = prompt_tokens(messages)
    return tokens


SCREEN_ARMS = ("card", "verbal")   # the two candidates for the largest rendering


def _session_cases(job: dict[str, Any]) -> dict[str, Any]:
    """Build every probe's cases for one session; pure, so it parallelizes by session."""
    env, guid, role = job["env"], job["guid"], job["role"]
    stubs = probes.session_stubs(env, guid)
    tables = probes.ForkTables()
    completions = tables.completions(env, guid)
    completion_steps = set(completions)
    # A fork corpus exists only at completion pre-states: the state immediately before the
    # solved-terminal frame of a recorded completing action (the gi2_forks snapshot point).
    fork_anchors = [
        position - 1
        for position, stub in enumerate(stubs)
        if position > 0
        and stub["step"] in completion_steps
        and stub["role"] == probes.ROLE_SOLVED_TERMINAL
    ]
    cases: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    shortfalls: list[dict[str, Any]] = []
    excluded = {"context": 0, "ineligible": 0}

    def emit(case, window, index) -> bool:
        tokens = _feasibility(case, window, SCREEN_ARMS)
        if max(tokens.values()) > probes.PROMPT_TOKENS_MAX:
            excluded["context"] += 1
            return False
        case["window_members"] = probes.window_members(
            stubs, index, probes.PREFIX_WINDOW[case["probe"]]
        )
        floor = probes.FLOORS[case["probe"]](case, window)
        case["floor"] = probes.score_case(case, floor)
        case["floor_answer"] = floor
        full = _feasibility(case, window, render.ARMS)
        if max(full.values()) > probes.PROMPT_TOKENS_MAX:
            raise ValueError(
                f"{case['case_id']}: screened arms fit but "
                f"{max(full, key=full.get)} does not — screening set is wrong"
            )
        audit.append({"case_id": case["case_id"], "probe": case["probe"],
                      "env": env, "role": role, "tokens": full})
        cases.append(case)
        return True

    def walk(probe: str, pool: list[int], wanted: int, builder: Callable, tag: str) -> None:
        if wanted <= 0:
            return
        ordered = probes.hash_order(pool, f"{env}|{guid}|{probe}|{tag}")
        limit = wanted * probes.ANCHOR_SLACK_FACTOR
        kept = 0
        for tried, index in enumerate(ordered):
            if kept >= wanted or tried >= limit:
                break
            members = probes.window_members(stubs, index, probes.PREFIX_WINDOW[probe])
            if members is None:
                continue
            keys = {_state_key(stubs[position]) for position in members}
            extra = builder.extra_keys(stubs, index) if hasattr(builder, "extra_keys") else set()
            grids = probes.collect_grids(env, guid, keys | extra)
            window = _window_for(env, guid, role, probe, stubs, grids, index)
            case = builder(window, stubs, index, grids)
            if case is None:
                excluded["ineligible"] += 1
                continue
            if emit(case, window, index):
                kept += 1
        if kept < wanted:
            shortfalls.append(
                {"env": env, "role": role, "probe": probe, "form": tag,
                 "wanted": wanted, "kept": kept, "pool": len(pool)}
            )

    def t1_builder(window, _stubs, _index, _grids):
        return probes.build_t1(window)

    def t2_builder(window, _stubs, _index, _grids):
        return probes.build_t2(window)

    def t3_executed_builder(window, session_stubs, index, grids):
        following = _successor(session_stubs, index)
        if following is None:
            return None
        key = _state_key(session_stubs[following])
        transition = probes.executed_transition(window, session_stubs[following], grids[key])
        return probes.build_t3_executed(window, transition)

    def t3_executed_extra(session_stubs, index):
        following = _successor(session_stubs, index)
        return {_state_key(session_stubs[following])} if following is not None else set()

    t3_executed_builder.extra_keys = t3_executed_extra

    def fork_rows(window, step: int):
        row = tables.get(env, guid, step)
        if row is None:
            return None
        try:
            return probes.authenticate_forks(row, window.query.grid)
        except ValueError:
            return None

    def t3_fork_builder(window, session_stubs, index, _grids):
        following = _successor(session_stubs, index)
        if following is None:
            return None
        rows = fork_rows(window, session_stubs[following]["step"])
        return None if rows is None else probes.build_t3_fork(window, rows)

    def t4_builder(window, session_stubs, index, _grids):
        following = _successor(session_stubs, index)
        if following is None:
            return None
        rows = fork_rows(window, session_stubs[following]["step"])
        return None if rows is None else probes.build_t4(window, rows)

    def t5_builder(window, session_stubs, index, _grids):
        following = _successor(session_stubs, index)
        if following is None:
            return None
        rows = fork_rows(window, session_stubs[following]["step"])
        if rows is None:
            return None
        return probes.build_t5(window, rows, session_stubs[following]["action"])

    wanted = probes.CASES_PER_PROBE_PER_GAME_PER_ROLE
    walk("T1", _anchor_pool(stubs, "T1"), wanted["T1"], t1_builder, "state")
    walk("T2", _anchor_pool(stubs, "T2"), wanted["T2"], t2_builder, "state")
    executed = min(probes.T3_EXECUTED_SHARE, wanted["T3"])
    walk("T3", _anchor_pool(stubs, "T3"), executed, t3_executed_builder, "executed")
    walk("T3", fork_anchors, wanted["T3"] - executed, t3_fork_builder, "fork")
    walk("T4", fork_anchors, wanted["T4"], t4_builder, "fork")
    walk("T5", fork_anchors, wanted["T5"], t5_builder, "fork")
    return {
        "env": env,
        "guid": guid,
        "role": role,
        "cases": cases,
        "audit": audit,
        "shortfalls": shortfalls,
        "excluded": excluded,
        "states": len(stubs),
        "completions": len(completions),
    }


def build_inventory(jobs: int = 1) -> dict[str, Any]:
    partition = probes.es_partition()
    work = [
        {"env": env, "guid": row["guid"], "role": row["role"]}
        for env in probes.GAMES
        for row in partition[env]
        if row["role"] in probes.MEASURED_ROLES
    ]
    sealed = [
        {"env": env, "guid": row["guid"]}
        for env in probes.GAMES
        for row in partition[env]
        if row["role"] == probes.SEALED_ROLE
    ]
    if jobs > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(_session_cases, work))
    else:
        results = [_session_cases(job) for job in work]

    cases = [case for result in results for case in result["cases"]]
    audit = [row for result in results for row in result["audit"]]
    shortfalls = [row for result in results for row in result["shortfalls"]]
    sealed_guids = {row["guid"] for row in sealed}
    if any(case["guid"] in sealed_guids for case in cases):
        raise ValueError("an R-role session leaked into the MU inventory")

    per_cell: dict[str, dict[str, Any]] = {}
    for case in cases:
        key = f"{case['env']}|{case['role']}|{case['probe']}"
        cell = per_cell.setdefault(key, {"n": 0, "floor_rate": 0.0})
        cell["n"] += 1
        cell["floor_rate"] += case["floor"]["rate"]
    for cell in per_cell.values():
        cell["floor_rate"] = round(cell["floor_rate"] / cell["n"], 4)

    tokens_by_arm = {
        arm: {
            "max": max((row["tokens"][arm] for row in audit), default=0),
            "median": sorted(row["tokens"][arm] for row in audit)[len(audit) // 2]
            if audit
            else 0,
            "total_S": sum(
                row["tokens"][arm] for row in audit if row["role"] == "S"
            ),
        }
        for arm in render.ARMS
    }
    s_cases = sum(1 for case in cases if case["role"] == "S")
    c_cases = sum(1 for case in cases if case["role"] == "C")
    c_t1_cases = sum(
        1 for case in cases if case["role"] == "C" and case["probe"] == "T1"
    )
    # C = selected arm on every T2-T5 C case, plus T1 x every unique selected arm (1..4).
    # The unique-arm count is fixed only at selection, so the budget prices the worst case.
    max_unique = min(len(render.ARMS), len(SELECTABLE_PROBES))
    planned_worst = (
        s_cases * len(render.ARMS) + (c_cases - c_t1_cases) + c_t1_cases * max_unique
    )
    budget = {
        "s_pass_calls": s_cases * len(render.ARMS),
        "c_pass_calls_selected_arms": c_cases - c_t1_cases,
        "c_t1_confirm_calls_worst": c_t1_cases * max_unique,
        "c_pass_calls_worst": (c_cases - c_t1_cases) + c_t1_cases * max_unique,
        "planned_calls_worst": planned_worst,
        "retry_reserve_calls": int(round(planned_worst * RETRY_RESERVE)),
        "call_ceiling": planned_worst + int(round(planned_worst * RETRY_RESERVE)),
        "s_pass_prompt_tokens": sum(tokens_by_arm[arm]["total_S"] for arm in render.ARMS),
    }

    document = {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/mu_screen.py",
        "contract": {
            "governing_note": "notes/mu-representation-screen.md",
            "manifest_block": "gate_manifest.yaml -> mu",
            "manifest_status": manifest_block().get("status"),
            "roles": "S = selection, C = confirmation; R sealed and untouched by MU",
            "prefix_window": probes.PREFIX_WINDOW,
            "cases_per_probe_per_game_per_role": probes.CASES_PER_PROBE_PER_GAME_PER_ROLE,
            "prompt_tokens_max": probes.PROMPT_TOKENS_MAX,
            "tokenizer": str(TOKENIZER_DIR),
            "arms": list(render.ARMS),
        },
        "inputs": dict(
            sorted(
                {
                    "logs/es_inventory.json": probes.sha256_file(probes.ES_INVENTORY),
                    "logs/gi2_fork_table.json": probes.sha256_file(probes.FORK_TABLE),
                    "logs/gi2_ar_vc33_forks.json": probes.sha256_file(probes.AR_VC33_FORKS),
                    "gate_manifest.yaml": probes.sha256_file(MANIFEST),
                    "notes/mu-representation-screen.md": probes.sha256_file(NOTE),
                }.items()
            )
        ),
        "sealed_sessions": sorted(sealed, key=lambda row: (row["env"], row["guid"])),
        "sessions": [
            {
                "env": result["env"],
                "guid": result["guid"],
                "role": result["role"],
                "states": result["states"],
                "completions": result["completions"],
                "cases": len(result["cases"]),
                "excluded": result["excluded"],
            }
            for result in results
        ],
        "cells": dict(sorted(per_cell.items())),
        "shortfalls": shortfalls,
        "context_audit": {
            "prompt_tokens_max": probes.PROMPT_TOKENS_MAX,
            "by_arm": tokens_by_arm,
            "rows": sorted(audit, key=lambda row: row["case_id"]),
        },
        "call_budget": budget,
        "cases": sorted(cases, key=lambda case: case["case_id"]),
    }
    payload = dict(document)
    payload.pop("fingerprint", None)
    document["fingerprint"] = probes.fingerprint(payload)
    return document


def load_inventory() -> dict[str, Any]:
    document = json.loads(INVENTORY.read_text())
    payload = dict(document)
    stored = payload.pop("fingerprint", None)
    if probes.fingerprint(payload) != stored:
        raise ValueError("logs/mu_inventory.json is self-inconsistent")
    return document


# ====================================================================================
# Window rebuild for rendering
# ====================================================================================


class CaseIndex:
    """Rebuilds the evidence window of a case on demand, once per session."""

    def __init__(self, document: dict[str, Any]):
        self.cases = {case["case_id"]: case for case in document["cases"]}
        self._stubs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._grids: dict[tuple[str, str], dict[str, list]] = {}

    def stubs(self, env: str, guid: str) -> list[dict[str, Any]]:
        key = (env, guid)
        if key not in self._stubs:
            self._stubs[key] = probes.session_stubs(env, guid)
        return self._stubs[key]

    def window(self, case: dict[str, Any]) -> probes.EvidenceWindow:
        env, guid = case["env"], case["guid"]
        stubs = self.stubs(env, guid)
        members = case["window_members"]
        keys = {_state_key(stubs[position]) for position in members}
        if sorted(keys) != sorted(case["window"]):
            raise ValueError(f"{case['case_id']}: window drifted from the inventory")
        cache = self._grids.setdefault((env, guid), {})
        missing = keys - set(cache)
        if missing:
            cache.update(probes.collect_grids(env, guid, missing))
        grids = {key: cache[key] for key in keys}
        return probes.build_window(
            env, guid, case["role"], case["probe"], stubs, grids, members
        )


# ====================================================================================
# Freeze
# ====================================================================================


def build_freeze() -> dict[str, Any]:
    block = manifest_block()
    if block.get("status") != "frozen":
        raise ValueError(
            "gate_manifest.yaml -> mu is not frozen: every MU numeric is PROPOSED until the "
            "operator accepts the block (MU SS6 step 1). No freeze, and therefore no "
            "measured call, before acceptance."
        )
    problems = check_mirrors(block)
    if problems:
        raise ValueError("implementation/manifest mismatch: " + "; ".join(problems))
    if not BRINGUP.is_file():
        raise ValueError(
            "bring-up has not run: logs/mu_bringup.json is required before the freeze "
            "(--bringup measures per-call latency at MU prompt sizes and validates "
            "guided-JSON decoding on the live measurement stack; MU SS8.3)"
        )
    bringup = json.loads(BRINGUP.read_text())
    if bringup.get("guided_json_validated") is not True:
        raise ValueError(
            "bring-up did not validate guided-JSON decoding; fix the serving stack and "
            "rerun --bringup — a silent fallback to free-text decoding is not a repair"
        )
    accepted = (block.get("bringup") or {}).get("measured") or {}
    for key in ("p50_s", "p95_s", "max_prompt_tokens"):
        if accepted.get(key) != bringup.get(key):
            raise ValueError(
                f"gate_manifest.yaml -> mu.bringup.measured.{key} ({accepted.get(key)!r}) "
                f"does not match logs/mu_bringup.json ({bringup.get(key)!r}): the operator "
                "accepts the measured bring-up numbers into the block before the freeze"
            )
    document = load_inventory()
    stale = [
        relative
        for relative, digest in document["inputs"].items()
        if probes.sha256_file(ROOT / relative) != digest
    ]
    if stale:
        raise ValueError(
            "logs/mu_inventory.json was built against different inputs and must be rebuilt "
            "before the freeze: " + ", ".join(sorted(stale))
        )
    files = {}
    for relative in FROZEN_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"frozen file missing: {relative}")
        files[relative] = probes.sha256_file(path)
    contract = {
        "files": files,
        "inventory_fingerprint": document["fingerprint"],
        "inventory_sha256": probes.sha256_file(INVENTORY),
        "bringup_sha256": probes.sha256_file(BRINGUP),
        "manifest_block": probes.fingerprint(block),
        "model_basename": MODEL_BASENAME,
        "tokenizer": str(TOKENIZER_DIR),
        "generation": GENERATION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "arms": list(render.ARMS),
        "probes": list(probes.PROBES),
        "schema_fingerprints": {
            case["case_id"]: probes.fingerprint(probes.output_schema(case))
            for case in document["cases"]
        },
    }
    return {
        "format_version": FORMAT_VERSION,
        "frozen_at": _now(),
        "contract": contract,
        "contract_fingerprint": probes.fingerprint(contract),
    }


def verify_freeze() -> list[str]:
    try:
        existing = json.loads(FREEZE.read_text())
        expected = build_freeze()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if existing.get("contract") == expected["contract"]:
        return []
    problems = []
    for relative, digest in expected["contract"]["files"].items():
        if existing.get("contract", {}).get("files", {}).get(relative) != digest:
            problems.append(f"frozen file drift: {relative}")
    for key in ("inventory_fingerprint", "manifest_block", "model_basename", "generation"):
        if existing.get("contract", {}).get(key) != expected["contract"][key]:
            problems.append(f"contract drift: {key}")
    return problems or ["freeze differs"]


def require_freeze() -> dict[str, Any]:
    problems = verify_freeze()
    if problems:
        raise ValueError("MU implementation is not frozen: " + "; ".join(problems))
    return json.loads(FREEZE.read_text())


# ====================================================================================
# Bring-up: latency and guided-JSON validation on the live stack (discarded calls)
# ====================================================================================

# A fixed synthetic schema: bring-up validates that the serving stack honours
# response_format json_schema, never what the model answers.
BRINGUP_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["A1", "A2", "A3"]}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _bringup_prompt(tokens_target: int, call: int) -> str:
    """Deterministic filler at a target token size. Synthetic by construction: no session
    frame, case, or gold is readable here, so bring-up spends nothing measured."""
    text = (
        "SYNTHETIC BRING-UP PROMPT (discarded, non-evidentiary; MU SS8.3). "
        f"call={call}. Read to the end, then answer.\n"
    )
    unit = "row " + " ".join(str(value % 16) for value in range(64)) + "\n"
    block = unit * 32
    while prompt_tokens([{"role": "user", "content": text}]) < tokens_target:
        text += block
    text += (
        '\nANSWER\nReply with one bare JSON object satisfying this schema (any option): '
        + json.dumps(BRINGUP_SCHEMA, sort_keys=True, separators=(",", ":"))
    )
    return text


def run_bringup(*, model: str, base_url: str, timeout: float) -> dict[str, Any]:
    """MU SS8.3 items 2-3, made a gate: measure per-call latency at MU's prompt sizes and
    exercise guided-JSON decoding against the live measurement stack. The freeze refuses
    without the artifact this writes, and refuses again until the manifest carries its
    measured numbers as accepted values."""
    if Path(model).name != MODEL_BASENAME:
        raise ValueError(
            f"bring-up must measure the measurement stack itself: {MODEL_BASENAME}"
        )
    per_target = max(1, BRINGUP_CALLS // len(BRINGUP_PROMPT_TOKEN_TARGETS))
    rows = []
    for target in BRINGUP_PROMPT_TOKEN_TARGETS:
        for call in range(per_target):
            content = _bringup_prompt(target, call)
            messages = [{"role": "user", "content": content}]
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "mu_bringup",
                        "schema": BRINGUP_SCHEMA,
                        "strict": True,
                    },
                },
                **GENERATION,
            }
            response, elapsed = call_chat(base_url, payload, timeout)
            try:
                text = response["choices"][0]["message"]["content"]
                valid = json.loads(text).get("answer") in BRINGUP_SCHEMA["properties"][
                    "answer"
                ]["enum"]
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                valid = False
            rows.append(
                {
                    "target_prompt_tokens": target,
                    "prompt_tokens": prompt_tokens(messages),
                    "elapsed_seconds": round(elapsed, 3),
                    "guided_json_valid": valid,
                }
            )
    largest = [
        row["elapsed_seconds"]
        for row in rows
        if row["target_prompt_tokens"] == max(BRINGUP_PROMPT_TOKEN_TARGETS)
    ]
    ordered = sorted(largest)
    document = {
        "format_version": FORMAT_VERSION,
        "generated_at": _now(),
        "model": MODEL_BASENAME,
        "generation": GENERATION,
        "calls": len(rows),
        "prompt_token_targets": list(BRINGUP_PROMPT_TOKEN_TARGETS),
        "rows": rows,
        # The gating numbers are taken at the LARGEST target: the freeze wall-clock
        # question is the worst case, not the average case.
        "p50_s": ordered[len(ordered) // 2],
        "p95_s": ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))],
        "max_prompt_tokens": max(row["prompt_tokens"] for row in rows),
        "guided_json_validated": all(row["guided_json_valid"] for row in rows),
    }
    return document


# ====================================================================================
# Measured run
# ====================================================================================


class JsonlLog:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, row: dict[str, Any]) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


def call_chat(base_url: str, payload: dict[str, Any], timeout: float) -> tuple[dict, float]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=probes.canonical(payload),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"model request failed: {exc}") from exc
    elapsed = time.monotonic() - started
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("response is not an object")
    return value, elapsed


def plan_rows(document: dict[str, Any], *, role: str, arms: dict[str, str] | None) -> list[dict]:
    """S pass: every arm x every S case. C pass (MU SS5): the selected arm per T2-T5 case,
    plus T1 x every UNIQUE selected arm — confirmation legibility must be measured for
    every arm the selected profile uses, not only for a T1 winner."""
    rows = []
    unique_selected = tuple(sorted({arm for arm in (arms or {}).values() if arm}))
    for case in document["cases"]:
        if case["role"] != role:
            continue
        if arms is None:
            chosen: tuple[str, ...] = tuple(render.ARMS)
        elif case["probe"] == "T1":
            chosen = unique_selected
        else:
            selected = arms.get(case["probe"])
            chosen = (selected,) if selected else ()
        for arm in chosen:
            rows.append(
                {
                    "row_id": f"{case['case_id']}|{arm}",
                    "case_id": case["case_id"],
                    "probe": case["probe"],
                    "env": case["env"],
                    "role": case["role"],
                    "arm": arm,
                }
            )
    return sorted(rows, key=lambda row: row["row_id"])


def _execute(row, *, case, index: CaseIndex, model: str, base_url: str, timeout: float,
             freeze_fingerprint: str, chat=call_chat) -> dict[str, Any]:
    window = index.window(case)
    messages, meta = render.render_case(row["arm"], case, window)
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": f"mu_{case['probe'].lower()}",
                            "schema": probes.output_schema(case), "strict": True},
        },
        **GENERATION,
    }
    response, elapsed = chat(base_url, payload, timeout)
    try:
        text = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = None
    parsed, parse_error = None, None
    try:
        parsed = probes.parse_answer(case, text)
    except (ValueError, json.JSONDecodeError) as exc:
        parse_error = str(exc)
    return {
        **row,
        "status": "complete",
        "recorded_at": _now(),
        "model": model,
        "freeze_fingerprint": freeze_fingerprint,
        "request_sha256": probes.fingerprint(payload),
        "packet_meta": meta,
        "elapsed_seconds": elapsed,
        "usage": response.get("usage") if isinstance(response.get("usage"), dict) else {},
        "raw_output": text,
        "parse_valid": parsed is not None,
        "parse_error": parse_error,
        "parsed": parsed,
        "score": probes.score_case(case, parsed),
    }


def run_rows(rows, *, document, model: str, base_url: str, timeout: float, concurrency: int,
             continue_on_error: bool = False) -> dict[str, int]:
    if Path(model).name != MODEL_BASENAME:
        raise ValueError(f"the measurement model must be {MODEL_BASENAME} (MU SS1)")
    freeze = require_freeze()
    index = CaseIndex(document)
    logger = JsonlLog(RAW)
    existing = logger.records()
    for record in existing:
        if record.get("freeze_fingerprint") != freeze["contract_fingerprint"]:
            raise ValueError("logs/mu_raw.jsonl contains a different freeze")
    terminal = {record["row_id"] for record in existing if record.get("status") == "complete"}
    pending = [row for row in rows if row["row_id"] not in terminal]
    summary = {"planned": len(rows), "already_complete": len(rows) - len(pending),
               "complete": 0, "error": 0}

    def one(row):
        try:
            return _execute(
                row,
                case=index.cases[row["case_id"]],
                index=index,
                model=model,
                base_url=base_url,
                timeout=timeout,
                freeze_fingerprint=freeze["contract_fingerprint"],
            )
        except Exception as exc:  # noqa: BLE001 - the operational error is the record
            return {**row, "status": "error", "recorded_at": _now(), "model": model,
                    "freeze_fingerprint": freeze["contract_fingerprint"],
                    "error_type": type(exc).__name__, "error": str(exc)}

    fatal = None
    pool = ThreadPoolExecutor(max_workers=concurrency)
    futures: dict[Any, Any] = {}
    iterator = iter(pending)
    try:
        for row in iterator:
            futures[pool.submit(one, row)] = row
            if len(futures) == concurrency:
                break
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future, None)
                if future.cancelled():
                    continue
                result = future.result()
                logger.append(result)
                summary[result["status"]] += 1
                if result["status"] == "error" and not continue_on_error and fatal is None:
                    fatal = result
            if fatal:
                for future in futures:
                    future.cancel()
                break
            for row in iterator:
                futures[pool.submit(one, row)] = row
                if len(futures) == concurrency:
                    break
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if fatal:
        raise RuntimeError(f"{fatal['row_id']}: {fatal['error']}")
    return summary


# ====================================================================================
# Scoring, selection, summary
# ====================================================================================


def rescore_log(*, dry_run: bool = False) -> dict[str, Any]:
    """MU-E1: re-score collected rows under a corrected SCORER, never re-collect them.

    Legitimate only because the stimulus is unchanged. Every row's request payload is
    rebuilt under the current code and must reproduce the stored ``request_sha256``
    byte-for-byte; a row that does not is left alone and reported, never re-scored on the
    assumption that the prompt was the same. Re-scored rows carry ``rescored_from`` (the
    superseded freeze fingerprint) and ``rescored_at``, so the log says which rows were
    measured under which instrument.
    """
    freeze = require_freeze()
    document = load_inventory()
    index = CaseIndex(document)
    logger = JsonlLog(RAW)
    rows = logger.records()
    if not rows:
        return {"rows": 0, "rescored": 0, "already_current": 0, "stimulus_mismatch": 0}
    out: list[dict[str, Any]] = []
    summary = {"rows": len(rows), "rescored": 0, "already_current": 0,
               "stimulus_mismatch": 0, "changed_score": 0, "newly_valid": 0}
    for row in rows:
        if row.get("status") != "complete":
            out.append(row)
            continue
        if row.get("freeze_fingerprint") == freeze["contract_fingerprint"]:
            summary["already_current"] += 1
            out.append(row)
            continue
        case = index.cases[row["case_id"]]
        messages, meta = render.render_case(row["arm"], case, index.window(case))
        payload = {
            "model": row["model"],
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": f"mu_{case['probe'].lower()}",
                                "schema": probes.output_schema(case), "strict": True},
            },
            **GENERATION,
        }
        if probes.fingerprint(payload) != row.get("request_sha256"):
            summary["stimulus_mismatch"] += 1
            out.append(row)
            continue
        parsed, parse_error = None, None
        try:
            parsed = probes.parse_answer(case, row.get("raw_output"))
        except (ValueError, json.JSONDecodeError) as exc:
            parse_error = str(exc)
        score = probes.score_case(case, parsed)
        if score != row.get("score"):
            summary["changed_score"] += 1
        if parsed is not None and not row.get("parse_valid"):
            summary["newly_valid"] += 1
        summary["rescored"] += 1
        out.append({
            **row,
            "freeze_fingerprint": freeze["contract_fingerprint"],
            "rescored_from": row["freeze_fingerprint"],
            "rescored_at": _now(),
            "packet_meta": meta,
            "parse_valid": parsed is not None,
            "parse_error": parse_error,
            "parsed": parsed,
            "score": score,
        })
    if not dry_run and summary["rescored"]:
        RAW.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in out))
    return summary


def _complete_records() -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in JsonlLog(RAW).records():
        if row.get("status") == "complete":
            latest[row["row_id"]] = row
    return list(latest.values())


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def game_macro(rows: list[dict[str, Any]], value: Callable[[dict], float]) -> float:
    """Case rates averaged within game, then games averaged with equal weight (MU SS5)."""
    per_game: dict[str, list[float]] = {}
    for row in rows:
        per_game.setdefault(row["env"], []).append(value(row))
    return _mean([_mean(values) for _, values in sorted(per_game.items())])


def floor_profile(document: dict[str, Any], role: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for probe in probes.PROBES:
        rows = [
            {"env": case["env"], "rate": case["floor"]["rate"]}
            for case in document["cases"]
            if case["probe"] == probe and case["role"] == role
        ]
        out[probe] = {
            "game_macro": round(game_macro(rows, lambda row: row["rate"]), 4),
            "n": len(rows),
        }
    return out


def profile(records: list[dict[str, Any]], role: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for probe in probes.PROBES:
        out[probe] = {}
        for arm in render.ARMS:
            rows = [
                row
                for row in records
                if row["probe"] == probe and row["arm"] == arm and row["role"] == role
            ]
            if not rows:
                continue
            out[probe][arm] = {
                "n": len(rows),
                "games": len({row["env"] for row in rows}),
                "game_macro": round(game_macro(rows, lambda row: row["score"]["rate"]), 4),
                "exact_macro": round(
                    game_macro(rows, lambda row: 1.0 if row["score"]["exact"] else 0.0), 4
                ),
                "parse_valid": round(
                    _mean([1.0 if row["parse_valid"] else 0.0 for row in rows]), 4
                ),
                "median_prompt_tokens": sorted(
                    row["usage"].get("prompt_tokens", 0) for row in rows
                )[len(rows) // 2],
            }
    return out


def legibility(role_profile: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """MU SS2: an arm below the T1 gate has its T2-T5 rates REPORTED but not interpreted.

    T1 measures whether a rendering can be read at all, so a low T2-T5 rate under a failing
    T1 is an illegibility result, not a reasoning result. The flag is three-state: True or
    False where T1 was measured for the arm in that role, None where no T1 rows exist —
    an unmeasured arm is not labelled illegible, it is labelled unmeasured.
    """
    out = {}
    for arm in render.ARMS:
        entry = role_profile.get("T1", {}).get(arm)
        out[arm] = {
            "t1_game_macro": entry["game_macro"] if entry else None,
            "legible": (entry["game_macro"] >= T1_LEGIBILITY_GATE) if entry else None,
            "gate": T1_LEGIBILITY_GATE,
        }
    return out


def select_profile(s_profile: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """MU SS5: per T2-T5 probe, highest game-macro on S among S-LEGIBLE arms; within the
    margin the cheaper arm wins. T1 filters eligibility and is itself never selected: an
    arm that cannot be read must not be selectable, whatever its T2-T5 rates read."""
    flags = legibility(s_profile)
    legible_arms = {arm for arm, entry in flags.items() if entry["legible"] is True}
    selection: dict[str, Any] = {}
    for probe in SELECTABLE_PROBES:
        arms = s_profile.get(probe, {})
        if not arms:
            continue
        eligible = {arm: entry for arm, entry in arms.items() if arm in legible_arms}
        if not eligible:
            selection[probe] = {
                "status": "no_legible_arm",
                "s_legible_arms": sorted(legible_arms),
            }
            continue
        best = max(eligible.values(), key=lambda entry: entry["game_macro"])["game_macro"]
        contenders = [
            (arm, entry)
            for arm, entry in eligible.items()
            if best - entry["game_macro"] <= SELECTION_MARGIN
        ]
        winner = min(
            contenders,
            key=lambda item: (item[1]["median_prompt_tokens"], ARM_ORDER.index(item[0])),
        )
        selection[probe] = {
            "status": "selected",
            "arm": winner[0],
            "game_macro": winner[1]["game_macro"],
            "best_game_macro": best,
            "within_margin": [arm for arm, _ in contenders],
        }
    return selection


def per_game_means(rows: list[dict[str, Any]], value: Callable[[dict], float]) -> dict[str, float]:
    per_game: dict[str, list[float]] = {}
    for row in rows:
        per_game.setdefault(row["env"], []).append(value(row))
    return {env: _mean(values) for env, values in sorted(per_game.items())}


def screen_positive_verdict(
    *,
    probe: str,
    arm: str,
    c_records: list[dict[str, Any]],
    floor_cases: list[dict[str, Any]],
    c_legibility: dict[str, Any],
) -> dict[str, Any]:
    """MU SS4: the confirmed read of one selected cell — SCREEN-POSITIVE, not 'capability'.

    C holds ~18 cases per probe, so one binary case moves game-macro by ~0.056, already
    above the margin; a screen this size supports a screen verdict, not a capability
    claim. The verdict therefore requires all three of:
      1. the arm passed T1 on C (measured there, never assumed from S);
      2. C game-macro exceeds the floor game-macro by screen_positive_margin;
      3. the arm beats the floor's per-game mean in >= screen_positive_min_games of the
         six games — the paired per-game comparison, so a one-game spike cannot carry it.
    """
    rows = [row for row in c_records if row["probe"] == probe and row["arm"] == arm]
    if not rows:
        return {"status": "not_confirmed", "arm": arm}
    flag = c_legibility.get(arm, {})
    if flag.get("legible") is None:
        return {"status": "t1_unmeasured_on_C", "arm": arm}
    if flag["legible"] is False:
        return {
            "status": "arm_illegible_on_C",
            "arm": arm,
            "t1_game_macro": flag["t1_game_macro"],
        }
    model_by_game = per_game_means(rows, lambda row: row["score"]["rate"])
    floor_by_game = per_game_means(
        [{"env": case["env"], "rate": case["floor"]["rate"]} for case in floor_cases],
        lambda row: row["rate"],
    )
    games_beating_floor = sum(
        1
        for env, mean in model_by_game.items()
        if mean > floor_by_game.get(env, 0.0)
    )
    c_macro = _mean(list(model_by_game.values()))
    floor_macro = _mean(list(floor_by_game.values()))
    margin = c_macro - floor_macro
    return {
        "status": "confirmed",
        "arm": arm,
        "c_game_macro": round(c_macro, 4),
        "floor_game_macro": round(floor_macro, 4),
        "margin": round(margin, 4),
        "games_beating_floor": games_beating_floor,
        "min_games": SCREEN_POSITIVE_MIN_GAMES,
        "screen_positive": margin >= SCREEN_POSITIVE_MARGIN
        and games_beating_floor >= SCREEN_POSITIVE_MIN_GAMES,
    }


def decision_verdict(
    selection: dict[str, Any],
    screen_positive: dict[str, Any],
    *,
    s_complete: bool,
    c_complete: bool,
) -> dict[str, Any]:
    """MU SS5.1: the decision contract, computed rather than left to a reader.

    `stop` when no arm passes the T1 gate on S for any probe, or when no funding cell
    ({T3, T4}) is screen-positive on C. `continue` when at least
    ``min_screen_positive_cells`` funding cells are screen-positive. Until both passes are
    complete the verdict is `pending`: an incomplete pass is not evidence of absence, and
    a stop routed off a half-finished C pass would be the same error as selecting off a
    half-finished S pass. `adopt` is unreachable from MU by construction — it is not a
    branch here, it is a routing note carried alongside the verdict.
    """
    funding = [probe for probe in FUNDING_PROBES if probe in selection]
    positive = [
        probe
        for probe in funding
        if screen_positive.get(probe, {}).get("screen_positive") is True
    ]
    no_legible = all(
        selection.get(probe, {}).get("status") == "no_legible_arm"
        for probe in SELECTABLE_PROBES
        if probe in selection
    ) and bool(selection)
    routing = {
        "stop": "this representation menu is exhausted for Qwen mechanics use; advisor work "
                "proceeds programmatic-only (catalogue floors); a new menu requires a new "
                "registered protocol",
        "continue": "fund the continuation protocol — goal inference over the winning "
                    "interface — as a separately registered protocol; T5 informs that design "
                    "but cannot discharge its goal-inference burden",
        "pending": "neither branch is reachable yet; finish the pass before routing",
    }
    if s_complete and no_legible:
        verdict = "stop"
        reason = "no arm passes the T1 legibility gate on S for any probe"
    elif not (s_complete and c_complete):
        verdict = "pending"
        reason = (
            f"S pass complete: {s_complete}; C pass complete: {c_complete}. An unfinished "
            "pass is not evidence of absence."
        )
    elif len(positive) >= MIN_SCREEN_POSITIVE_CELLS:
        verdict = "continue"
        reason = f"screen-positive funding cells: {', '.join(positive)}"
    else:
        verdict = "stop"
        reason = (
            "no funding cell among "
            f"{{{', '.join(FUNDING_PROBES)}}} is screen-positive on C"
        )
    return {
        "verdict": verdict,
        "reason": reason,
        "routing": routing[verdict],
        "funding_probes": list(FUNDING_PROBES),
        "screen_positive_funding_cells": positive,
        "min_screen_positive_cells": MIN_SCREEN_POSITIVE_CELLS,
        "adopt": "never from MU: it is offline and makes no score-stack claim; adoption needs "
                 "a separate exact-stack protocol plus the docs/README.md register entry and a "
                 "dated SPEC amendment",
    }


def build_results() -> dict[str, Any]:
    document = load_inventory()
    records = _complete_records()
    s_profile = profile(records, "S")
    c_profile = profile(records, "C")
    # Selection reads a COMPLETE S pass only: a partial factorial would let call order, not
    # the representation, pick the winner.
    planned_s = {row["row_id"] for row in plan_rows(document, role="S", arms=None)}
    complete_s = {row["row_id"] for row in records if row["role"] == "S"}
    s_complete = planned_s.issubset(complete_s)
    selection = select_profile(s_profile) if s_complete else {}
    floors = {"S": floor_profile(document, "S"), "C": floor_profile(document, "C")}
    c_legibility = legibility(c_profile)
    c_records = [row for row in records if row["role"] == "C"]
    screen_positive = {}
    for probe, entry in selection.items():
        if entry.get("status") != "selected":
            screen_positive[probe] = {"status": entry.get("status", "no_legible_arm")}
            continue
        screen_positive[probe] = screen_positive_verdict(
            probe=probe,
            arm=entry["arm"],
            c_records=c_records,
            floor_cases=[
                case
                for case in document["cases"]
                if case["probe"] == probe and case["role"] == "C"
            ],
            c_legibility=c_legibility,
        )
    selected_arms = {
        probe: entry["arm"]
        for probe, entry in selection.items()
        if entry.get("status") == "selected"
    }
    planned_c = (
        {row["row_id"] for row in plan_rows(document, role="C", arms=selected_arms)}
        if selected_arms
        else set()
    )
    c_complete = bool(planned_c) and planned_c.issubset(
        {row["row_id"] for row in c_records}
    )
    document_out = {
        "format_version": FORMAT_VERSION,
        "generated_at": _now(),
        "inventory_fingerprint": document["fingerprint"],
        "records": len(records),
        "s_pass_complete": s_complete,
        "c_pass_complete": c_complete,
        "planned_s_rows": len(planned_s),
        "planned_c_rows": len(planned_c),
        "floors": floors,
        "legibility": {"S": legibility(s_profile), "C": c_legibility},
        "profile": {"S": s_profile, "C": c_profile},
        "selection": selection,
        "screen_positive": screen_positive,
        "decision": decision_verdict(
            selection, screen_positive, s_complete=s_complete, c_complete=c_complete
        ),
    }
    payload = dict(document_out)
    payload.pop("fingerprint", None)
    document_out["fingerprint"] = probes.fingerprint(payload)
    return document_out


# ====================================================================================
# CLI
# ====================================================================================


def _print_audit(document: dict[str, Any]) -> None:
    audit = document["context_audit"]
    print(f"prompt token ceiling: {audit['prompt_tokens_max']}")
    print(f"{'arm':>8} {'median':>8} {'max':>8} {'S-pass tokens':>14}")
    for arm, entry in audit["by_arm"].items():
        print(f"{arm:>8} {entry['median']:>8} {entry['max']:>8} {entry['total_S']:>14}")
    excluded = sum(row["excluded"]["context"] for row in document["sessions"])
    ineligible = sum(row["excluded"]["ineligible"] for row in document["sessions"])
    print(f"anchors rejected: {excluded} context-infeasible, {ineligible} probe-ineligible")
    per_game: dict[str, int] = {}
    for row in document["sessions"]:
        per_game[row["env"]] = per_game.get(row["env"], 0) + row["excluded"]["context"]
    print("context-infeasible anchors by game: " + ", ".join(
        f"{env}:{count}" for env, count in sorted(per_game.items())
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--bringup", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--rescore", action="store_true",
                        help="MU-E1: re-score collected rows under a corrected scorer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", choices=["S", "C"])
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--model", default=str(TOKENIZER_DIR))
    # The established local stack: VP Freeze 1 measured against 127.0.0.1:1234.
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    if args.inventory:
        document = build_inventory(args.jobs)
        INVENTORY.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        for key, cell in document["cells"].items():
            env, role, probe = key.split("|")
            print(f"{env} {role} {probe}: n={cell['n']} floor={cell['floor_rate']:.2f}")
        if document["shortfalls"]:
            print(f"SHORTFALLS ({len(document['shortfalls'])}):")
            for row in document["shortfalls"]:
                print(f"  {row['env']} {row['role']} {row['probe']}/{row['form']}: "
                      f"kept {row['kept']}/{row['wanted']} from a pool of {row['pool']}")
        _print_audit(document)
        print(f"call budget: {json.dumps(document['call_budget'])}")
        print(f"wrote {INVENTORY.relative_to(ROOT)}, "
              f"fingerprint {document['fingerprint'][:16]}...")
        return 0

    if args.audit:
        _print_audit(load_inventory())
        return 0

    if args.bringup:
        try:
            document = run_bringup(
                model=args.model, base_url=args.base_url, timeout=args.timeout
            )
        except (ValueError, RuntimeError) as exc:
            print(f"FAIL: {exc}")
            return 1
        BRINGUP.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        print(
            f"bring-up: {document['calls']} discarded calls, largest-target "
            f"p50 {document['p50_s']}s p95 {document['p95_s']}s, "
            f"guided JSON validated={document['guided_json_validated']}"
        )
        print(
            "accept mu.bringup.measured.{p50_s,p95_s,max_prompt_tokens} into "
            "gate_manifest.yaml -> mu before --freeze"
        )
        print(f"wrote {BRINGUP.relative_to(ROOT)}")
        return 0 if document["guided_json_validated"] else 1

    if args.freeze:
        try:
            document = build_freeze()
        except ValueError as exc:
            print(f"FAIL: {exc}")
            return 1
        FREEZE.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        print(f"wrote {FREEZE.relative_to(ROOT)}, "
              f"fingerprint {document['contract_fingerprint'][:16]}...")
        return 0

    if args.verify:
        problems = verify_freeze()
        if problems:
            print("MU freeze FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("MU freeze OK")
        return 0

    if args.rescore:
        try:
            summary = rescore_log(dry_run=args.dry_run)
        except ValueError as exc:
            print(f"FAIL: {exc}")
            return 1
        print(json.dumps(summary))
        return 1 if summary["stimulus_mismatch"] else 0

    if args.run:
        try:
            document = load_inventory()
            arms = None
            if args.run == "C":
                results = json.loads(RESULTS.read_text())
                if not results.get("selection"):
                    raise ValueError("run --select on a COMPLETE S pass before the C pass")
                arms = {
                    probe: entry["arm"]
                    for probe, entry in results["selection"].items()
                    if entry.get("status") == "selected"
                }
                if not arms:
                    raise ValueError(
                        "no probe has an S-legible selected arm (every selection row is "
                        "no_legible_arm): there is no C pass to run — that outcome routes "
                        "through the decision contract (MU SS5.1), not through more calls"
                    )
            rows = plan_rows(document, role=args.run, arms=arms)
            summary = run_rows(
                rows,
                document=document,
                model=args.model,
                base_url=args.base_url,
                timeout=args.timeout,
                concurrency=args.concurrency,
                continue_on_error=args.continue_on_error,
            )
        except ValueError as exc:
            print(f"FAIL: {exc}")
            return 1
        print(json.dumps(summary))
        return 0

    if args.select or args.score:
        document = build_results()
        RESULTS.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        print(json.dumps(document["selection"], indent=1))
        print(f"wrote {RESULTS.relative_to(ROOT)}")
        return 0

    if args.summary:
        document = json.loads(RESULTS.read_text())
        for role in ("S", "C"):
            print(f"--- {role} ---")
            legible = document["legibility"][role]
            for probe, arms in document["profile"][role].items():
                floor = document["floors"][role][probe]["game_macro"]
                marks = {True: "", False: "*", None: "?"}
                line = "  ".join(
                    f"{arm}:{entry['game_macro']:.2f}"
                    + ("" if probe == "T1" else marks[legible[arm]["legible"]])
                    for arm, entry in arms.items()
                )
                print(f"{probe} (floor {floor:.2f}): {line}")
            print("* below the T1 legibility gate (reported, not interpreted); "
                  "? no T1 rows in this role for the arm")
        for probe, entry in sorted(document.get("screen_positive", {}).items()):
            print(f"{probe}: {json.dumps(entry)}")
        decision = document.get("decision", {})
        print(f"--- decision (MU 5.1): {decision.get('verdict', 'unknown').upper()} ---")
        print(f"  {decision.get('reason', '')}")
        print(f"  routing: {decision.get('routing', '')}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
