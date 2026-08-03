#!/usr/bin/env python3
"""ES session-atomic partition, transfer-case inventory, and passive dose construction.

Implements the frozen contract:
  * ``gate_manifest.yaml -> es`` (FROZEN 2026-08-03): ``corpus.partition_rule``, roles,
    cohort floors;
  * ``notes/qwen-evidence-sufficiency-screen.md`` SS2.1 (session-atomic partition, published
    dependency graph) and SS3.3 (fixed nested passive doses DOSE-0..DOSE-3).

Scope: model-free and threshold-light. It publishes the partition, per-case dose
availability, and the case-to-evidence dependency graph BEFORE any survivor curve, per
SS2.1. DOSE-4 (source-simulated fork probes), the ``tractable``/``covered``/
``critical_panelable`` indicators, and packets belong to later modules (``es_sources``
adapters, ``es_candidates``).

Estate reuse (governing note SS8): sessions and traces come from ``gi2_traces``
(``selected_sessions``, ``iter_trace``); componentization comes from
``gi2_observation.componentize``. Nothing here re-authors an audited assertion.

Determinizations recorded here (implementation level, published before any survivor set):

  * Case anchor. A transfer case is the k-th completion of a session with k >= 2. The
    query state is the settled pre-state of the completing action (non-terminal), its
    DOSE-0 label is non-completion, and the query action class is the completing action's
    class. This matches the ceiling arithmetic in the governing note SS2.1 (completions
    minus first-per-session).
  * DOSE-1: the chronologically earliest earlier completion (pre-state, action, solved
    state). DOSE-2: the next earlier completion, in chronological order after DOSE-1,
    whose completed level differs from DOSE-1's completed level. Both must lie strictly
    before the query step.
  * DOSE-3 selection follows erratum ES-E2 (``gate_manifest.yaml -> errata``). Pool =
    strictly-earlier frame-bearing non-completion transitions with an observable pre-state
    and the same action class as the case's completing action, any recorded action
    including RESET. DELTA* = the smallest complexity distance such that at least two pool
    members lie within it of the query pre-state complexity; DOSE-3 = the two
    chronologically earliest members of that matched pool (step order; steps are unique).
    Reduces to exact complexity matching whenever two exact matches exist. DELTA* and the
    realized per-pick deltas are published in every case row.
  * Pre-state complexity = number of non-background 4-connected components of the settled
    pre-state; background = modal colour of the frame, ties resolved to the smaller value
    (GI-2 R-1 convention).
  * A step is evidence-bearing iff it returned at least one frame. The settled state
    after a step is its last frame (ordinary: ``settled``; completion: ``solved_terminal``
    for WIN, else ``next_level_initial``).

Run:
  .venv/bin/python agent/harness/es_questions.py            # build + self-verify
  .venv/bin/python agent/harness/es_questions.py --verify   # compare rebuild to disk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_observation import componentize  # noqa: E402
from gi2_traces import (  # noqa: E402
    CORPUS,
    DRAW,
    SESSIONS,
    iter_trace,
    selected_sessions,
)

OUTPUT = ROOT / "logs/es_inventory.json"
MANIFEST = ROOT / "gate_manifest.yaml"

FORMAT_VERSION = 1
SESSIONS_PER_GAME = 3
ROLES = ("S", "C", "R")

# Mirror of gate_manifest.yaml -> es -> corpus.games (FROZEN 2026-08-03). The inventory fails
# closed on any deviation from this exact set, including duplicates: the draw document is an
# input, not an authority over the frozen corpus.
FROZEN_GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")

# Frozen in gate_manifest.yaml -> es -> corpus.partition_rule (2026-08-03). The list is the
# frozen enumeration order; roles are assigned to sessions ordered chronologically by
# recorded session start (ties by GUID ascending).
PERMUTATIONS = (
    ("S", "C", "R"),
    ("S", "R", "C"),
    ("C", "S", "R"),
    ("C", "R", "S"),
    ("R", "S", "C"),
    ("R", "C", "S"),
)

# gate_manifest.yaml -> es -> cohort_floors (reported here, gated later).
PASSIVE_COMPLETE_FLOOR_PER_GAME = 3

DOSE3_REQUIRED = 2


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def partition_index(env: str) -> int:
    """p = int(sha256(('es-partition:'+env).encode('ascii')).hexdigest()[:8], 16) mod 6."""
    return int(
        hashlib.sha256(f"es-partition:{env}".encode("ascii")).hexdigest()[:8], 16
    ) % len(PERMUTATIONS)


def assign_roles(env: str, ordered_guids: list[str]) -> dict[str, str]:
    """Map guid -> role for sessions already ordered by (session start, guid)."""
    if len(ordered_guids) != SESSIONS_PER_GAME:
        raise ValueError(f"{env}: expected {SESSIONS_PER_GAME} sessions, got {len(ordered_guids)}")
    permutation = PERMUTATIONS[partition_index(env)]
    return {guid: role for guid, role in zip(ordered_guids, permutation)}


def session_start(path: Path) -> str:
    """Recorded session start = the first line's timestamp field."""
    with path.open(encoding="utf-8") as handle:
        first = json.loads(handle.readline())
    stamp = first.get("timestamp")
    if not isinstance(stamp, str) or not stamp:
        raise ValueError(f"{path}: first line has no timestamp")
    return stamp


def modal_color(grid: list) -> int:
    counts: Counter[int] = Counter()
    for row in grid:
        counts.update(int(value) for value in row)
    best_count = max(counts.values())
    return min(color for color, count in counts.items() if count == best_count)


def pre_state_complexity(grid: list) -> int:
    """Non-background 4-connected component count; background = modal colour."""
    background = modal_color(grid)
    return sum(1 for component in componentize(grid) if component.color != background)


def extract_session(env: str, guid: str) -> list[dict[str, Any]]:
    """Stream one recording into the plain-dict step rows that dose construction reads."""
    path = CORPUS / env / f"{guid}.recording.jsonl"
    rows: list[dict[str, Any]] = []
    settled_row: int | None = None
    settled_complexity: int | None = None
    for step in iter_trace(path):
        has_frames = len(step.frames) > 0
        row = {
            "step": step.index,
            "action_class": step.action_id,
            "is_completion": step.is_completion,
            "completed_level": step.levels_completed if step.is_completion else None,
            "has_frames": has_frames,
            "has_pre": settled_row is not None,
            "pre_state_row": settled_row,
            "pre_complexity": settled_complexity,
            "solved": step.solved_terminal is not None,
        }
        rows.append(row)
        if has_frames:
            settled_row = step.index
            settled_complexity = pre_state_complexity(step.frames[-1].grid)
    return rows


def build_cases(env: str, guid: str, role: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transfer cases with DOSE-1..DOSE-3 construction over extracted step rows."""
    completions = [
        row for row in rows if row["is_completion"] and row["has_frames"]
    ]
    pool = [
        row
        for row in rows
        if not row["is_completion"] and row["has_frames"] and row["has_pre"]
    ]
    cases = []
    for k, query in enumerate(completions):
        if k == 0:
            continue  # first completion per session anchors no transfer case
        earlier = [c for c in completions[:k] if c["step"] < query["step"]]
        dose1 = earlier[0] if earlier else None
        dose2 = None
        if dose1 is not None:
            for candidate in earlier[1:]:
                if candidate["completed_level"] != dose1["completed_level"]:
                    dose2 = candidate
                    break
        query_ok = bool(query["has_pre"])
        dose3_picks: list[dict[str, Any]] = []
        dose3_delta_star: int | None = None
        if query_ok:
            matched = [
                row
                for row in pool
                if row["step"] < query["step"]
                and row["action_class"] == query["action_class"]
            ]
            if len(matched) >= DOSE3_REQUIRED:
                # ES-E2: DELTA* = smallest distance admitting two members; selection within
                # the matched pool is purely chronological.
                distances = sorted(
                    abs(row["pre_complexity"] - query["pre_complexity"]) for row in matched
                )
                dose3_delta_star = distances[DOSE3_REQUIRED - 1]
                eligible = sorted(
                    (
                        row
                        for row in matched
                        if abs(row["pre_complexity"] - query["pre_complexity"])
                        <= dose3_delta_star
                    ),
                    key=lambda row: row["step"],
                )
                dose3_picks = eligible[:DOSE3_REQUIRED]

        def _completion_ref(entry: dict[str, Any] | None) -> dict[str, Any] | None:
            if entry is None:
                return None
            return {
                "step": entry["step"],
                "pre_state_row": entry["pre_state_row"],
                "completed_level": entry["completed_level"],
                "action_class": entry["action_class"],
            }

        availability = {
            "dose1": dose1 is not None and bool(dose1["has_pre"]) and bool(dose1["solved"]),
            "dose2": dose2 is not None and bool(dose2["has_pre"]) and bool(dose2["solved"]),
            "dose3": len(dose3_picks) == DOSE3_REQUIRED,
            "query_pre_state": query_ok,
        }
        availability["passive_complete"] = all(availability.values())
        cases.append(
            {
                "case_id": f"es:{env}:{guid}:{query['step']}",
                "env": env,
                "guid": guid,
                "role": role,
                "query": {
                    "step": query["step"],
                    "pre_state_row": query["pre_state_row"],
                    "pre_complexity": query["pre_complexity"],
                    "action_class": query["action_class"],
                    "completed_level": query["completed_level"],
                    "dose0_label": "non_complete",
                },
                "dose3_delta_star": dose3_delta_star,
                "doses": {
                    "DOSE-1": _completion_ref(dose1),
                    "DOSE-2": _completion_ref(dose2),
                    "DOSE-3": [
                        {
                            "step": row["step"],
                            "pre_state_row": row["pre_state_row"],
                            "action_class": row["action_class"],
                            "pre_complexity": row["pre_complexity"],
                            "delta_complexity": abs(
                                row["pre_complexity"] - query["pre_complexity"]
                            ),
                        }
                        for row in dose3_picks
                    ],
                },
                "availability": availability,
            }
        )
    return cases


def _evidence_steps(case: dict[str, Any]) -> list[int]:
    steps = []
    doses = case["doses"]
    for key in ("DOSE-1", "DOSE-2"):
        if doses[key] is not None:
            steps.append(doses[key]["step"])
    steps.extend(row["step"] for row in doses["DOSE-3"])
    return steps


def frozen_iteration(draw_doc: dict[str, Any]) -> list[str]:
    """Fail closed unless the draw's iteration list is exactly the frozen ES corpus."""
    iteration = draw_doc.get("iteration")
    if not isinstance(iteration, list) or not iteration:
        raise ValueError("draw is missing its iteration list")
    if len(iteration) != len(set(iteration)):
        raise ValueError(f"iteration list contains duplicates: {sorted(iteration)}")
    if set(iteration) != set(FROZEN_GAMES):
        raise ValueError(
            f"iteration set {sorted(iteration)} does not equal the frozen ES corpus "
            f"{sorted(FROZEN_GAMES)}"
        )
    return list(FROZEN_GAMES)


def canonical_payload(document: dict[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("fingerprint", None)
    return payload


def verify_against_disk(rebuilt: dict[str, Any], on_disk: dict[str, Any]) -> list[str]:
    """Full-content verification: the stored fingerprint string alone proves nothing."""
    problems = []
    disk_payload = canonical_payload(on_disk)
    stored = on_disk.get("fingerprint")
    recomputed = _sha256_bytes(_canonical(disk_payload))
    if recomputed != stored:
        problems.append(
            f"on-disk artifact is self-inconsistent: stored fingerprint {stored}, "
            f"payload recomputes to {recomputed}"
        )
    if _canonical(disk_payload) != _canonical(canonical_payload(rebuilt)):
        problems.append("on-disk payload differs from the deterministic rebuild")
    if stored != rebuilt.get("fingerprint"):
        problems.append(
            f"fingerprint mismatch (disk {stored}, rebuild {rebuilt.get('fingerprint')})"
        )
    return problems


def build_inventory() -> dict[str, Any]:
    sessions_doc = json.loads(SESSIONS.read_text())
    draw_doc = json.loads(DRAW.read_text())
    iteration = frozen_iteration(draw_doc)

    partition: dict[str, Any] = {}
    all_cases: list[dict[str, Any]] = []
    input_hashes: dict[str, str] = {
        "logs/s2_replay_sessions.json": _sha256_file(SESSIONS),
        "logs/gi1_game_draw.json": _sha256_file(DRAW),
        "gate_manifest.yaml": _sha256_file(MANIFEST),
    }

    for env in iteration:
        chosen = selected_sessions(env, sessions_doc, draw_doc)
        if len(chosen) != SESSIONS_PER_GAME:
            raise ValueError(f"{env}: selected {len(chosen)} sessions")
        ordered = []
        for row in chosen:
            guid = row["guid"]
            path = CORPUS / env / f"{guid}.recording.jsonl"
            ordered.append(
                {
                    "guid": guid,
                    "session_start": session_start(path),
                    "recording_sha256": _sha256_file(path),
                }
            )
            input_hashes[f"recording:{env}:{guid}"] = ordered[-1]["recording_sha256"]
        ordered.sort(key=lambda item: (item["session_start"], item["guid"]))
        roles = assign_roles(env, [item["guid"] for item in ordered])
        partition[env] = {
            "permutation_index": partition_index(env),
            "permutation": list(PERMUTATIONS[partition_index(env)]),
            "sessions": [
                {**item, "role": roles[item["guid"]]} for item in ordered
            ],
        }
        for item in ordered:
            rows = extract_session(env, item["guid"])
            all_cases.extend(build_cases(env, item["guid"], roles[item["guid"]], rows))

    for case in all_cases:
        query_step = case["query"]["step"]
        for step in _evidence_steps(case):
            if step >= query_step:
                raise ValueError(f"{case['case_id']}: evidence step {step} not before query")

    summary: dict[str, Any] = {}
    for env in iteration:
        summary[env] = {}
        for role in ROLES:
            cohort = [
                case
                for case in all_cases
                if case["env"] == env and case["role"] == role
            ]
            passive = sum(1 for case in cohort if case["availability"]["passive_complete"])
            summary[env][role] = {
                "transfer_cases": len(cohort),
                "dose1_available": sum(1 for c in cohort if c["availability"]["dose1"]),
                "dose2_available": sum(1 for c in cohort if c["availability"]["dose2"]),
                "dose3_available": sum(1 for c in cohort if c["availability"]["dose3"]),
                "passive_complete": passive,
                "meets_floor_3": passive >= PASSIVE_COMPLETE_FLOOR_PER_GAME,
            }

    totals = {
        role: {
            "transfer_cases": sum(summary[env][role]["transfer_cases"] for env in iteration),
            "passive_complete": sum(
                summary[env][role]["passive_complete"] for env in iteration
            ),
        }
        for role in ROLES
    }

    document = {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/es_questions.py",
        "contract": {
            "manifest_block": "gate_manifest.yaml -> es (FROZEN 2026-08-03)",
            "governing_note": "notes/qwen-evidence-sufficiency-screen.md",
            "partition_rule": (
                "sessions ordered by (recorded session start, guid); "
                "p = int(sha256(('es-partition:'+env).encode('ascii')).hexdigest()[:8], 16) "
                "mod 6 over [(S,C,R),(S,R,C),(C,S,R),(C,R,S),(R,S,C),(R,C,S)]"
            ),
            "dose3_rule": (
                "ES-E2 (gate_manifest.yaml -> errata): pool = strictly-earlier frame-bearing "
                "non-completions with observable pre-state and the completing action's class; "
                "DELTA* = smallest complexity distance admitting two pool members; DOSE-3 = the "
                "two chronologically earliest members within DELTA*, by step order; complexity "
                "= non-background 4-connected components, background = modal colour with ties "
                "to the smaller value"
            ),
        },
        "inputs": dict(sorted(input_hashes.items())),
        "partition": partition,
        "summary": summary,
        "totals": totals,
        "cases": sorted(all_cases, key=lambda case: case["case_id"]),
    }
    payload = dict(document)
    payload.pop("fingerprint", None)
    document["fingerprint"] = _sha256_bytes(_canonical(payload))
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="rebuild and compare to disk")
    args = parser.parse_args()

    document = build_inventory()
    if args.verify:
        if not OUTPUT.exists():
            print(f"FAIL: {OUTPUT} does not exist")
            return 1
        on_disk = json.loads(OUTPUT.read_text())
        problems = verify_against_disk(document, on_disk)
        if problems:
            for problem in problems:
                print(f"FAIL: {problem}")
            return 1
        print(f"OK: {OUTPUT} verified, fingerprint {document['fingerprint'][:16]}...")
        return 0

    rebuild = build_inventory()
    if rebuild["fingerprint"] != document["fingerprint"]:
        print("FAIL: build is not deterministic across two in-process runs")
        return 1
    OUTPUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    for env, per_role in sorted(document["summary"].items()):
        line = " ".join(
            f"{role}:{per_role[role]['transfer_cases']}/{per_role[role]['passive_complete']}"
            for role in ROLES
        )
        print(f"{env}: transfer/passive_complete {line}")
    print(
        f"totals: "
        + " ".join(
            f"{role}:{document['totals'][role]['transfer_cases']}"
            f"/{document['totals'][role]['passive_complete']}"
            for role in ROLES
        )
    )
    print(f"wrote {OUTPUT}, fingerprint {document['fingerprint'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
