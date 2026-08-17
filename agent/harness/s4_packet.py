#!/usr/bin/env python3
"""Build the source-blind Slice-4 evidence packet.

The builder consumes only the normalized Kaggle export, the explorer observation
store, and verified animation recaptures.  It verifies those artifacts before
selection, keeps original transition and episode identifiers, and emits matched
text/raw/overlay carriers with stable evidence ids.

The packet has exactly ten pages per visual carrier.  Sixteen is the end-to-end
image cap: the remaining six slots and their visual-token budget are reserved for
three all-frame probe storyboards and three retrieval composites.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_render as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OBSERVATION_ROOT = ROOT / "logs/s4_observation_log"
STORE_ROOT = ROOT / "logs/e1_store_v3"
E1_OUTCOMES = ROOT / "logs/e1_outcomes_v3.json"
E1_EXPLORER = HARNESS / "e1_explorer.py"
ALLOWED_ROOTS = (OBSERVATION_ROOT, STORE_ROOT)
ALLOWED_FILES = (E1_OUTCOMES,)
PACKET_ROOT = ROOT / "logs/s4_model_packet"
SEALED_ROOT = ROOT / "logs/s4_sealed"
MODEL = Path("/Users/michal/models/mlx/Qwen3.8-27B-8bit")

BLIND_SALT = "ship-jepa-s4-2026-08-17"
SEED = 4
FORMAT_VERSION = 3
TARGET_INITIAL_PAGES = 10
MAX_INITIAL_PAGES = 10
MAX_IMAGES = 16
INTERACTIVE_RESULT_HEADROOM = 3
RETRIEVAL_RESULT_HEADROOM = 3
MAX_VISUAL_TOKENS = 16_384
MAX_TEXT_TOKENS = 12_000
# Pinned maxima for the interactive compositor.  Three independent probes and
# three one-image retrievals must fit after either initial carrier.
MIN_RESULT_PAGE_VISUAL_TOKENS = 2_112
RESERVED_RESULT_VISUAL_TOKENS = INTERACTIVE_RESULT_HEADROOM * MIN_RESULT_PAGE_VISUAL_TOKENS
MAX_RETRIEVAL_PAGE_VISUAL_TOKENS = 1_200
RESERVED_RETRIEVAL_VISUAL_TOKENS = (
    RETRIEVAL_RESULT_HEADROOM * MAX_RETRIEVAL_PAGE_VISUAL_TOKENS
)
RESERVED_POST_INITIAL_VISUAL_TOKENS = (
    RESERVED_RESULT_VISUAL_TOKENS + RESERVED_RETRIEVAL_VISUAL_TOKENS
)
MAX_INITIAL_VISUAL_TOKENS = MAX_VISUAL_TOKENS - RESERVED_POST_INITIAL_VISUAL_TOKENS
ATLAS_STATES = 14
CAUSAL_TRANSITIONS = 12
TRANSFORM_FRAMES_PER_PAGE = 32
MATCH_CANDIDATES_PER_CLASS = 48
KAGGLE_FIELDS = {
    "action", "action_num", "board", "click", "done", "game_over", "level",
    "level_completed", "reward", "score", "seq", "state", "type",
}
STORE_PERFORMS_FIELDS = {
    "action", "episode_step", "levels", "post", "pre", "source", "state", "step",
}
STORE_TRANSITION_FIELDS = {
    "action", "completed", "effect", "episode_step", "frames", "level", "post",
    "pre", "prefix", "route_mode", "source", "state", "step", "tier",
}
# These are the only action issuers emitted by the model-free E1 explorer.  In
# particular there is deliberately no generic/imported/manual source class.
AUTONOMOUS_EXPLORER_SOURCES = {"boot", "test", "walk", "reset", "confirm"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(raw)


def blind_id(game: str) -> str:
    return "G" + hashlib.sha256((BLIND_SALT + game).encode()).hexdigest()[:6]


def seed_for_game(game: str, purpose: str = "packet-selection") -> int:
    """Order-independent uint64 seed; adding/reordering games cannot change a packet."""
    payload = f"{SEED}:{blind_id(game)}:{purpose}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def read_allowlisted(path: Path) -> str:
    resolved = path.resolve()
    allowed = any(resolved == root.resolve() or root.resolve() in resolved.parents
                  for root in ALLOWED_ROOTS)
    allowed = allowed or any(resolved == item.resolve() for item in ALLOWED_FILES)
    require(allowed, f"BLINDNESS VIOLATION: refused to read {resolved}")
    require(resolved.is_file(), f"missing allowlisted input: {resolved}")
    return resolved.read_text(encoding="utf-8")


def _read_json(path: Path) -> tuple[Any, str, str]:
    text = read_allowlisted(path)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"malformed JSON input {path.name}: {exc}") from exc
    return value, text, sha256_bytes(text.encode())


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str, str]:
    text = read_allowlisted(path)
    rows = []
    for line_no, line in enumerate(text.splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"malformed JSONL {path.name}:{line_no}: {exc}") from exc
        require(isinstance(value, dict), f"{path.name}:{line_no}: row is not an object")
        rows.append(value)
    return rows, text, sha256_bytes(text.encode())


def _normalise_grid(grid: Any, label: str) -> list[list[int]]:
    array = np.asarray(grid)
    require(array.shape == (64, 64), f"{label}: grid shape {array.shape} != (64, 64)")
    require(np.issubdtype(array.dtype, np.integer), f"{label}: non-integral grid")
    require(bool(np.all((array >= 0) & (array <= 15))), f"{label}: colour outside 0..15")
    return [[int(value) for value in row] for row in array.tolist()]


def validate_packet_root(path: Path) -> Path:
    resolved = path.resolve()
    logs = (ROOT / "logs").resolve()
    require(resolved != logs, "packet output may not replace the logs root")
    require(logs in resolved.parents, f"unsafe packet output outside {logs}: {resolved}")
    return resolved


def atomic_replace_dir(staged: Path, target: Path) -> None:
    require(staged.parent == target.parent, "staged and target must be siblings")
    backup = target.parent / f".{target.name}.backup-{os.getpid()}"
    require(not backup.exists(), f"stale packet backup exists: {backup}")
    moved = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved = True
        os.replace(staged, target)
    except Exception:
        if moved and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    require(not temporary.exists(), f"stale temporary file exists: {temporary}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


# --------------------------------------------------------------------------- inputs


def _validate_kaggle_rows(rows: list[dict[str, Any]], *, expected_rows: int) -> None:
    require(len(rows) == expected_rows, (
        f"normalized Kaggle row count {len(rows)} != manifest {expected_rows}"
    ))
    previous_seq: int | None = None
    for index, row in enumerate(rows):
        unknown = set(row) - KAGGLE_FIELDS
        missing = KAGGLE_FIELDS - set(row)
        require(not unknown and not missing, (
            f"normalized Kaggle row {index} schema mismatch; unknown={sorted(unknown)}, "
            f"missing={sorted(missing)}"
        ))
        require(row["type"] in {"initial", "action"}, (
            f"normalized Kaggle row {index}: invalid type {row['type']!r}"
        ))
        require(isinstance(row["action"], str) and (
            row["action"] == "RESET" or row["action"].startswith("ACTION")
        ), f"normalized Kaggle row {index}: malformed action")
        require(type(row["seq"]) is int and row["seq"] >= 0, (
            f"normalized Kaggle row {index}: malformed seq"
        ))
        if previous_seq is not None:
            require(row["seq"] == previous_seq + 1, (
                f"normalized Kaggle sequence discontinuity at row {index}"
            ))
        previous_seq = row["seq"]
        _normalise_grid(row["board"], f"normalized Kaggle row {index}")
        click = row["click"]
        require(click is None or (
            isinstance(click, list) and len(click) == 2
            and all(type(value) is int and 0 <= value < 64 for value in click)
        ), f"normalized Kaggle row {index}: malformed click")
        for flag in ("done", "game_over", "level_completed"):
            require(type(row[flag]) is bool, f"normalized Kaggle row {index}: {flag} not bool")


def _validate_store(
    performs: list[dict[str, Any]], states: dict[str, Any], historical: list[dict[str, Any]]
) -> None:
    require(performs, "empty performs store")
    require(isinstance(states, dict) and states, "empty states store")
    for index, row in enumerate(historical):
        require(set(row) == STORE_TRANSITION_FIELDS, (
            f"historical row {index}: schema mismatch; "
            f"unknown={sorted(set(row) - STORE_TRANSITION_FIELDS)}, "
            f"missing={sorted(STORE_TRANSITION_FIELDS - set(row))}"
        ))
        require(type(row.get("step")) is int and row["step"] > 0,
                f"historical row {index}: invalid global step")
        require(row.get("source") in AUTONOMOUS_EXPLORER_SOURCES,
                f"historical row {index}: non-autonomous/unknown source tag")
    old_by_step = {row.get("step"): row for row in historical}
    require(len(old_by_step) == len(historical), "duplicate/missing transition step")
    episode_index = -1
    expected_episode_step = 0
    expected_global_step = 1
    for index, row in enumerate(performs):
        require(set(row) == STORE_PERFORMS_FIELDS, (
            f"performs row {index}: schema mismatch; "
            f"unknown={sorted(set(row) - STORE_PERFORMS_FIELDS)}, "
            f"missing={sorted(STORE_PERFORMS_FIELDS - set(row))}"
        ))
        require(row["step"] == expected_global_step,
                f"performs row {index}: global step is not the canonical contiguous index")
        expected_global_step += 1
        require(row["source"] in AUTONOMOUS_EXPLORER_SOURCES,
                f"performs row {index}: non-autonomous/unknown source tag {row['source']!r}")
        require(isinstance(row["state"], str) and bool(row["state"]),
                f"performs row {index}: invalid response state")
        require(type(row["levels"]) is int and row["levels"] >= 0,
                f"performs row {index}: invalid levels-completed count")
        episode_step = row["episode_step"]
        require(type(episode_step) is int and episode_step >= 0, (
            f"performs row {index}: invalid episode_step"
        ))
        if episode_step == 0:
            episode_index += 1
            expected_episode_step = 0
        require(episode_index >= 0 and episode_step == expected_episode_step, (
            f"performs row {index}: episode discontinuity"
        ))
        expected_episode_step += 1
        action = row["action"]
        require(isinstance(action, list) and len(action) == 3
                and type(action[0]) is int and 0 <= action[0] <= 7
                and ((action[1] is None and action[2] is None)
                     or (action[0] == 6 and type(action[1]) is int
                         and type(action[2]) is int
                         and 0 <= action[1] < 64 and 0 <= action[2] < 64)),
                f"performs row {index}: malformed action")
        for field in ("pre", "post"):
            digest = row.get(field)
            require(digest is None or digest in states, (
                f"performs row {index}: unknown {field} digest {digest!r}"
            ))
        if row["step"] in old_by_step:
            old = old_by_step[row["step"]]
            require(old.get("source") == row["source"],
                    f"historical/store source disagreement at step {row['step']}")
            require(old.get("state") is None or isinstance(old["state"], str),
                    f"historical row {row['step']}: invalid state")
            require(old.get("frames") is None
                    or type(old["frames"]) is int and old["frames"] >= 0,
                    f"historical row {row['step']}: invalid frame count")
            require(old.get("completed") is None or type(old["completed"]) is bool,
                    f"historical row {row['step']}: invalid completion flag")
            for field in ("pre", "post", "episode_step"):
                require(old.get(field) == row.get(field), (
                    f"historical/store disagreement at step {row['step']} field {field}"
                ))


def load_evidence(game: str) -> dict[str, Any]:
    """Load and cryptographically bind all source-blind inputs for one game."""
    store_paths = {
        "performs": STORE_ROOT / f"{game}.performs.jsonl",
        "states": STORE_ROOT / f"{game}.states.json",
        "transitions": STORE_ROOT / f"{game}.transitions.jsonl",
        "graph": STORE_ROOT / f"{game}.graph.json",
    }
    performs, performs_text, performs_sha = _read_jsonl(store_paths["performs"])
    states, states_text, states_sha = _read_json(store_paths["states"])
    historical, transitions_text, transitions_sha = _read_jsonl(store_paths["transitions"])
    graph, graph_text, graph_sha = _read_json(store_paths["graph"])
    require(isinstance(graph, dict), "store graph is not an object")
    _validate_store(performs, states, historical)
    outcomes, outcomes_text, outcomes_sha = _read_json(E1_OUTCOMES)
    require(isinstance(outcomes, dict) and outcomes.get("format_version") == 1
            and isinstance(outcomes.get("games"), dict),
            "E1 producer outcome manifest is malformed")
    outcome = outcomes["games"].get(game)
    require(isinstance(outcome, dict) and outcome.get("game") == game,
            f"E1 producer outcome manifest lacks {game}")
    require(outcome.get("performs") == len(performs)
            and outcome.get("transitions") == len(historical),
            f"E1 producer outcome counts disagree with the admitted {game} store")
    observed_sources = sorted({row["source"] for row in performs})
    explorer_sha = sha256_file(E1_EXPLORER)

    kaggle_dir = OBSERVATION_ROOT / "kaggle_v4"
    fleet, fleet_text, fleet_sha = _read_json(kaggle_dir / "manifest.json")
    require(isinstance(fleet, dict) and isinstance(fleet.get("games"), list),
            "malformed normalized-export manifest")
    exporter_path = HARNESS / "s4_export_kaggle.py"
    exporter_sha = sha256_file(exporter_path)
    require(fleet.get("exporter_sha256") == exporter_sha,
            "normalized-export manifest does not match the live field-allowlist exporter")
    game_names = [entry.get("game") for entry in fleet["games"]]
    require(len(game_names) == len(set(game_names)), "duplicate game in normalized-export manifest")
    fleet_counts = Counter()
    for entry in fleet["games"]:
        require(isinstance(entry.get("output_sha256"), str)
                and len(entry["output_sha256"]) == 64,
                "normalized-export manifest contains a truncated output hash")
        require(isinstance(entry.get("source_sha256"), str)
                and len(entry["source_sha256"]) == 64,
                "normalized-export manifest contains a truncated source hash")
        for row_type, count in (entry.get("rows") or {}).items():
            fleet_counts[row_type] += int(count)
    require(dict(fleet_counts) == fleet.get("fleet_rows"),
            "normalized-export fleet totals disagree with game entries")
    matches = [entry for entry in fleet["games"] if entry.get("game") == game]
    require(len(matches) == 1, f"normalized-export manifest has {len(matches)} entries for game")
    kaggle_entry = matches[0]
    require(kaggle_entry.get("output") == f"{game}.observations.jsonl", (
        "normalized-export filename mismatch"
    ))
    kaggle_rows, kaggle_text, kaggle_sha = _read_jsonl(kaggle_dir / kaggle_entry["output"])
    require(kaggle_entry.get("output_sha256") == kaggle_sha, (
        "normalized Kaggle output hash mismatch"
    ))
    _validate_kaggle_rows(kaggle_rows, expected_rows=int(kaggle_entry["kept_rows"]))
    row_classes = Counter(row["type"] for row in kaggle_rows)
    manifest_rows = kaggle_entry.get("rows") or {}
    require(row_classes.get("action", 0) == int(manifest_rows.get("action", -1)),
            "normalized action-row count disagrees with manifest")
    require(row_classes.get("initial", 0) == int(manifest_rows.get("initial", -1)),
            "normalized initial-row count disagrees with manifest")
    require(sum(bool(row["level_completed"]) for row in kaggle_rows)
            == int(kaggle_entry.get("completions", -1)),
            "normalized completion count disagrees with manifest")
    aborted = kaggle_dir / "ABORTED.txt"
    aborted_status: dict[str, Any] | None = None
    if aborted.exists():
        manifest_mtime = (kaggle_dir / "manifest.json").stat().st_mtime_ns
        abort_mtime = aborted.stat().st_mtime_ns
        require(abort_mtime < manifest_mtime, (
            "normalized export has an abort marker at or after its manifest"
        ))
        aborted_status = {"present_but_superseded": True, "sha256": sha256_file(aborted)}

    recap_dir = OBSERVATION_ROOT / "recapture" / game
    recap, recap_text, recap_sha = _read_json(recap_dir / "manifest.json")
    require(recap.get("format_version") == 2, "recapture manifest is not fidelity-gated v2")
    require(recap.get("game") == game, "recapture manifest game mismatch")
    require(recap.get("status") == "complete", (
        f"recapture is incomplete: {recap.get('status')!r}"
    ))
    recap_records = []
    recap_files = []
    verified_steps = 0
    replayable_visual_steps = 0
    recaptured_store_indexes: set[int] = set()
    historical_by_step = {int(row["step"]): row for row in historical}
    for expected_index, summary in enumerate(recap.get("episodes") or []):
        require(summary.get("episode_index") == expected_index, (
            "recapture episode manifest is out of order"
        ))
        name = summary.get("file")
        require(isinstance(name, str) and Path(name).name == name, (
            f"unsafe recapture episode filename {name!r}"
        ))
        expected_sha = summary.get("sha256")
        require(isinstance(expected_sha, str) and len(expected_sha) == 64, (
            f"recapture episode {expected_index} lacks a full SHA-256"
        ))
        record, record_text, record_sha = _read_json(recap_dir / name)
        require(record_sha == expected_sha, f"recapture episode {expected_index} hash mismatch")
        require(record.get("episode_index") == expected_index, (
            f"recapture episode {expected_index} identity mismatch"
        ))
        require(record.get("divergence") is None, (
            f"recapture episode {expected_index} contains a divergence"
        ))
        require(record.get("steps_verified") == record.get("actions_expected"), (
            f"recapture episode {expected_index} is only a prefix"
        ))
        require(all(step.get("verified") is True for step in record.get("steps") or []),
                f"recapture episode {expected_index} contains unverified steps")
        require(sum(int(step["frame_count"]) for step in record.get("steps") or [])
                == int(record.get("total_frames", -1)),
                f"recapture episode {expected_index} frame total mismatch")
        for step in record.get("steps") or []:
            store_index = step.get("store_index")
            require(type(store_index) is int and 0 <= store_index < len(performs),
                    f"recapture episode {expected_index}: invalid store index {store_index!r}")
            require(store_index not in recaptured_store_indexes,
                    f"recapture store index {store_index} appears more than once")
            recaptured_store_indexes.add(store_index)
            store_row = performs[store_index]
            require(step.get("store_step") == store_row["step"],
                    f"recapture store-step mismatch at index {store_index}")
            require(step.get("episode_step") == store_row["episode_step"],
                    f"recapture episode-step mismatch at index {store_index}")
            require(step.get("action") == store_row["action"],
                    f"recapture action mismatch at index {store_index}")
            require(step.get("expected_store_digest") == store_row.get("post"),
                    f"recapture expected digest mismatch at index {store_index}")
            require(step.get("response_state") == store_row["state"],
                    f"recapture response-state mismatch at index {store_index}")
            require(step.get("expected_state") == store_row["state"],
                    f"recapture expected-state mismatch at index {store_index}")
            require(step.get("levels_completed") == store_row["levels"],
                    f"recapture completed-level mismatch at index {store_index}")
            require(step.get("expected_levels_completed") == store_row["levels"],
                    f"recapture expected completed-level mismatch at index {store_index}")
            require(all((step.get("checks") or {}).values()),
                    f"recapture step checks are not all true at index {store_index}")
            require(int(step["frame_count"]) == len(step.get("frames") or []), (
                f"recapture episode {expected_index} step frame-count mismatch"
            ))
            historical_row = historical_by_step.get(int(store_row["step"]))
            if historical_row is not None and historical_row.get("frames") is not None:
                require(int(step["frame_count"]) == int(historical_row["frames"]),
                        f"recapture historical frame-count mismatch at index {store_index}")
            normalised_frames = []
            for frame_index, frame in enumerate(step.get("frames") or []):
                normalised_frames.append(_normalise_grid(
                    frame, f"recapture episode {expected_index} frame {frame_index}"
                ))
            expected_digest = store_row.get("post")
            expected_grid = states.get(expected_digest) if expected_digest is not None else None
            settled = normalised_frames[-1] if normalised_frames else None
            require((settled is None) == (expected_grid is None),
                    f"recapture frame absence mismatch at index {store_index}")
            if expected_grid is not None:
                require(settled == expected_grid,
                        f"recapture settled grid mismatch at index {store_index}")
                replayable_visual_steps += 1
            settled_sha = canonical_sha256(settled) if settled is not None else None
            require(step.get("settled_grid_sha256") == settled_sha,
                    f"recapture settled-grid hash mismatch at index {store_index}")
        verified_steps += int(record["steps_verified"])
        recap_records.append(record)
        recap_files.append({
            "episode_index": expected_index, "sha256": record_sha,
            "bytes": len(record_text.encode()),
        })
    require(verified_steps == int(recap.get("steps_verified", -1)),
            "recapture manifest verified-step total mismatch")
    require(recaptured_store_indexes == set(range(len(performs))),
            "recapture does not cover every original performs row exactly once")
    require(replayable_visual_steps > 0,
            "recapture produced no verified visual prefix states for active probes")

    live_store = {
        "performs.jsonl": performs_sha,
        "states.json": states_sha,
        "transitions.jsonl": transitions_sha,
        "graph.json": graph_sha,
    }
    recap_store = (recap.get("provenance") or {}).get("store") or {}
    for suffix, digest in live_store.items():
        require((recap_store.get(suffix) or {}).get("sha256") == digest, (
            f"store input drift since recapture: {suffix}"
        ))
    engine_provenance = (recap.get("provenance") or {}).get("engine") or {}
    engine_hashes = {}
    for label, value in engine_provenance.items():
        if isinstance(value, dict) and isinstance(value.get("sha256"), str):
            engine_hashes[label] = value["sha256"]
    require("game_source" in engine_hashes and "recapture_script" in engine_hashes,
            "recapture lacks engine/source provenance hashes")

    return {
        "performs": performs,
        "states": states,
        "historical": historical,
        "kaggle": kaggle_rows,
        "recap": recap,
        "recap_dir": recap_dir,
        "recap_records": recap_records,
        "input_identity": {
            "normalized_export": {
                "fleet_manifest_sha256": fleet_sha,
                "exporter_sha256": exporter_sha,
                "output_sha256": kaggle_sha,
                "source_sha256": kaggle_entry.get("source_sha256"),
                "kept_rows": len(kaggle_rows),
                "dropped_analysis_rows": int(manifest_rows.get("analysis", 0)),
                "superseded_abort": aborted_status,
            },
            "store": {
                "performs": {"sha256": performs_sha, "bytes": len(performs_text.encode())},
                "states": {"sha256": states_sha, "bytes": len(states_text.encode())},
                "transitions": {
                    "sha256": transitions_sha, "bytes": len(transitions_text.encode()),
                },
                "graph": {"sha256": graph_sha, "bytes": len(graph_text.encode())},
                "producer_lineage": {
                    "actor": "deterministic_model_free_explorer",
                    "action_input": "closed_internal_policy_no_human_or_model_actions",
                    "explorer_script": {
                        "path": "agent/harness/e1_explorer.py", "sha256": explorer_sha,
                    },
                    "outcomes_manifest": {
                        "path": "logs/e1_outcomes_v3.json", "sha256": outcomes_sha,
                        "bytes": len(outcomes_text.encode()),
                    },
                    "closed_source_tags": sorted(AUTONOMOUS_EXPLORER_SOURCES),
                    "observed_source_tags": observed_sources,
                    "game_counts": {
                        "performs": len(performs), "transitions": len(historical),
                    },
                },
            },
            "recapture": {
                "manifest_sha256": recap_sha,
                "manifest_bytes": len(recap_text.encode()),
                "episodes": recap_files,
                "replayable_visual_steps": replayable_visual_steps,
                "engine_hashes": engine_hashes,
                "versions": (recap.get("provenance") or {}).get("versions") or {},
            },
        },
    }


# --------------------------------------------------------------------- transitions


def _action_label(action: Sequence[Any]) -> str:
    return f"A{int(action[0])}"


def transition_stream(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Return visual transitions without renumbering either source.

    Store ids encode the original performs-file index.  Kaggle ids encode the
    normalized-export index.  Thus filtering a null post never shifts another id.
    """
    out: list[dict[str, Any]] = []
    states = evidence["states"]
    historical = {int(row["step"]): row for row in evidence.get("historical") or []}
    episode_index = -1
    prior_levels = 0
    for store_index, row in enumerate(evidence["performs"]):
        if int(row["episode_step"]) == 0:
            episode_index += 1
            prior_levels = 0
        pre_digest, post_digest = row.get("pre"), row.get("post")
        pre = states.get(pre_digest) if pre_digest is not None else None
        post = states.get(post_digest) if post_digest is not None else None
        old = historical.get(int(row["step"]))
        level_count = int(row.get("levels") or 0)
        completed = bool((old or {}).get("completed")) or level_count > prior_levels
        prior_levels = max(prior_levels, level_count)
        action_id, row_y, col_x = row["action"]
        out.append({
            "tid": f"S{store_index:05d}",
            "source": "store",
            "source_index": store_index,
            "store_index": store_index,
            "store_step": int(row["step"]),
            "episode_index": episode_index,
            "episode_step": int(row["episode_step"]),
            "reset_boundary": int(row["episode_step"]) == 0,
            "source_tag": row.get("source"),
            "action": f"A{int(action_id)}",
            "action_tuple": [action_id, row_y, col_x],
            "click": None if row_y is None else [int(row_y), int(col_x)],
            "pre_digest": pre_digest,
            "post_digest": post_digest,
            "pre": pre,
            "post": post,
            "level": (old or {}).get("level"),
            "levels_completed": level_count,
            "completed": completed,
            "state": row.get("state"),
            "historical_frames": (old or {}).get("frames"),
        })

    episode_index = -1
    episode_step = -1
    previous: list[list[int]] | None = None
    for source_index, row in enumerate(evidence["kaggle"]):
        # `type` is mandatory at the normalized-export boundary.  Injected evidence
        # used by retrieval tests predates that field, so its first row is the
        # initial boundary and later RESET rows remain explicit boundaries.
        row_type = row.get("type", "initial" if source_index == 0 else "action")
        boundary = source_index == 0 or row_type == "initial" or row["action"] == "RESET"
        if boundary:
            episode_index += 1
            episode_step = 0
        else:
            require(episode_index >= 0, "normalized history does not begin at a boundary")
            episode_step += 1
        post = row["board"]
        action = "A0" if row["action"] == "RESET" else row["action"].replace("ACTION", "A")
        out.append({
            "tid": f"K{source_index:05d}",
            "source": "kaggle",
            "source_index": source_index,
            "store_index": None,
            "store_step": None,
            "episode_index": episode_index,
            "episode_step": episode_step,
            "reset_boundary": boundary,
            "source_tag": row_type,
            "action": action,
            "action_tuple": None,
            "click": row.get("click"),
            "pre_digest": (
                canonical_sha256(previous) if previous is not None and not boundary else None
            ),
            "post_digest": canonical_sha256(post),
            "pre": None if boundary else previous,
            "post": post,
            "level": row.get("level"),
            "levels_completed": row.get("score"),
            "completed": bool(row.get("level_completed")),
            "state": row.get("state"),
            "historical_frames": None,
            "seq": row.get("seq"),
            "done": row.get("done"),
            "game_over": row.get("game_over"),
            "reward": row.get("reward"),
            "score": row.get("score"),
        })
        previous = post
    return [transition for transition in out if transition["post"] is not None]


def effect_signature(transition: dict[str, Any]) -> tuple[Any, ...]:
    if transition["pre"] is None:
        return transition["action"], "reset-output"
    pre, post = np.asarray(transition["pre"]), np.asarray(transition["post"])
    changed = int(np.count_nonzero(pre != post))
    if changed == 0:
        return transition["action"], "none"
    bucket = "local" if changed <= 8 else "regional" if changed <= 200 else "global"
    mask = pre != post
    return (
        transition["action"], bucket,
        tuple(int(value) for value in np.unique(post[mask])),
        tuple(int(value) for value in np.unique(pre[mask])),
    )


def _transition_fact(transition: dict[str, Any]) -> dict[str, Any]:
    pre, post = transition["pre"], transition["post"]
    if pre is None:
        return {"tid": transition["tid"], "action": transition["action"],
                "click": transition["click"], "pre_available": False,
                "changed_cells": None, "changed_bbox": None}
    pre_array, post_array = np.asarray(pre), np.asarray(post)
    bbox = sr.changed_bbox(pre_array, post_array)
    return {
        "tid": transition["tid"], "action": transition["action"],
        "click": transition["click"], "pre_available": True,
        "changed_cells": int(np.count_nonzero(pre_array != post_array)),
        "changed_bbox": list(bbox) if bbox is not None else None,
    }


# ---------------------------------------------------------------------- text facts


def _grid_rle(grid: Any) -> str:
    """Exact 2-D RLE: cells use ``*N`` and repeated complete rows use ``^N``."""
    array = np.asarray(grid, dtype=np.uint8)
    rows = []
    for row in array:
        runs = []
        start = 0
        for index in range(1, len(row) + 1):
            if index == len(row) or row[index] != row[start]:
                count = index - start
                runs.append(f"{int(row[start]):x}" + (f"*{count}" if count > 1 else ""))
                start = index
        rows.append(",".join(runs))
    grouped_rows = []
    start = 0
    for index in range(1, len(rows) + 1):
        if index == len(rows) or rows[index] != rows[start]:
            count = index - start
            grouped_rows.append(rows[start] + (f"^{count}" if count > 1 else ""))
            start = index
    return "rle64:" + "/".join(grouped_rows)


def _text_board(frame_id: str, label: str, grid: Any, *, exact: bool = True) -> dict[str, Any]:
    array = np.asarray(grid, dtype=np.uint8)
    record = {
        "frame_id": frame_id,
        "label": label,
        "sha256": canonical_sha256(array.tolist()),
        "colour_counts": {
            str(int(value)): int(count)
            for value, count in zip(*np.unique(array, return_counts=True))
        },
    }
    if exact:
        # Private build-time payload; `_finalise_text_boards` replaces it with the
        # shortest tokenizer-measured lossless full/reference/delta representation.
        record["_grid"] = array.tolist()
    return record


def _base36(value: int) -> str:
    return np.base_repr(int(value), base=36).lower()


def _patch_rectangles(target: np.ndarray, base: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Exact non-overlapping changed-cell rectangles: colour,r0,c0,height,width."""
    changed = target != base
    active: dict[tuple[int, int, int], tuple[int, int]] = {}
    rectangles: list[tuple[int, int, int, int, int]] = []
    for row in range(64):
        runs: list[tuple[int, int, int]] = []
        col = 0
        while col < 64:
            if not changed[row, col]:
                col += 1
                continue
            colour = int(target[row, col])
            start = col
            col += 1
            while col < 64 and changed[row, col] and int(target[row, col]) == colour:
                col += 1
            runs.append((colour, start, col - 1))
        current = set(runs)
        for key, (first_row, last_row) in list(active.items()):
            if key not in current:
                colour, c0, c1 = key
                rectangles.append((colour, first_row, c0, last_row - first_row + 1,
                                   c1 - c0 + 1))
                del active[key]
        for key in runs:
            if key in active:
                active[key] = (active[key][0], row)
            else:
                active[key] = (row, row)
    for (colour, c0, c1), (first_row, last_row) in active.items():
        rectangles.append((colour, first_row, c0, last_row - first_row + 1, c1 - c0 + 1))
    return rectangles


def _grid_delta(target: Any, base: Any, base_frame_id: str) -> str:
    rectangles = _patch_rectangles(
        np.asarray(target, dtype=np.uint8), np.asarray(base, dtype=np.uint8)
    )
    patches = ";".join(
        f"{colour:x}@{_base36(row)},{_base36(col)},{_base36(height)},{_base36(width)}"
        for colour, row, col, height, width in rectangles
    )
    return f"delta64:{base_frame_id}|{patches}"


def decode_text_grid(encoded: str, prior: dict[str, list[list[int]]]) -> list[list[int]]:
    """Decode the manifest's lossless grid language; used by build and regression tests."""
    if encoded.startswith("ref64:"):
        frame_id = encoded.removeprefix("ref64:")
        require(frame_id in prior, f"text-grid reference precedes base {frame_id}")
        return [list(row) for row in prior[frame_id]]
    if encoded.startswith("delta64:"):
        header, patches = encoded.removeprefix("delta64:").split("|", 1)
        require(header in prior, f"text-grid delta precedes base {header}")
        result = np.asarray(prior[header], dtype=np.uint8).copy()
        if patches:
            for patch in patches.split(";"):
                colour_text, geometry = patch.split("@", 1)
                row, col, height, width = (int(value, 36) for value in geometry.split(","))
                result[row:row + height, col:col + width] = int(colour_text, 16)
        return [[int(value) for value in row] for row in result.tolist()]
    require(encoded.startswith("rle64:"), "unknown text-grid encoding")
    result_rows: list[list[int]] = []
    payload = encoded.removeprefix("rle64:")
    for grouped_row in payload.split("/"):
        row_text, repeat_text = (
            grouped_row.rsplit("^", 1) if "^" in grouped_row else (grouped_row, "1")
        )
        row: list[int] = []
        for run in row_text.split(","):
            colour_text, count_text = run.split("*", 1) if "*" in run else (run, "1")
            row.extend([int(colour_text, 16)] * int(count_text))
        require(len(row) == 64, f"decoded text-grid row has {len(row)} cells")
        result_rows.extend([list(row) for _ in range(int(repeat_text))])
    require(len(result_rows) == 64, f"decoded text grid has {len(result_rows)} rows")
    return result_rows


def _evidence_id(kind: str, transition_refs: Sequence[str], episode_refs: Sequence[str],
                 discriminator: str = "") -> str:
    payload = {
        "kind": kind, "transition_refs": list(transition_refs),
        "episode_refs": list(episode_refs), "discriminator": discriminator,
    }
    return "E" + canonical_sha256(payload)[:12]


# ------------------------------------------------------------------------- rendering


def visual_tokens(width: int, height: int) -> int:
    """Pinned geometry prediction retained for callers; emission uses the processor."""
    return (height // 16) * (width // 16) // 4


class ProcessorAuditor:
    """Run the checkpoint's PIL image processor and retain its real image_grid_thw."""

    def __init__(self, model: Path = MODEL):
        from transformers import AutoTokenizer  # noqa: PLC0415
        from transformers.models.qwen2_vl.image_processing_pil_qwen2_vl import (  # noqa: PLC0415
            Qwen2VLImageProcessorPil,
        )

        self.model = model.resolve()
        require((self.model / "preprocessor_config.json").is_file(), (
            f"missing checkpoint processor config: {self.model}"
        ))
        self.processor = Qwen2VLImageProcessorPil.from_pretrained(
            str(self.model), local_files_only=True
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(self.model), local_files_only=True, trust_remote_code=True
        )
        require((int(self.processor.patch_size), int(self.processor.merge_size)) == (16, 2),
                "processor geometry drift")
        serving_names = (
            "config.json", "tokenizer.json", "vocab.json", "merges.txt",
            "tokenizer_config.json", "chat_template.jinja", "preprocessor_config.json",
            "processor_config.json", "video_preprocessor_config.json",
            "model.safetensors.index.json",
        )
        serving_files = {}
        for name in serving_names:
            path = self.model / name
            require(path.is_file(), f"missing measurement checkpoint file: {name}")
            serving_files[name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        self.identity = {
            "implementation": (
                "transformers.models.qwen2_vl.image_processing_pil_qwen2_vl."
                "Qwen2VLImageProcessorPil"
            ),
            "preprocessor_config_sha256": sha256_file(self.model / "preprocessor_config.json"),
            "processor_config_sha256": sha256_file(self.model / "processor_config.json"),
            "tokenizer_config_sha256": sha256_file(self.model / "tokenizer_config.json"),
            "tokenizer_class": type(self.tokenizer).__name__,
            "patch_size": 16,
            "merge_size": 2,
            "pixel_limits": dict(self.processor.size),
            "serving_files": serving_files,
            "measurement_identity_sha256": canonical_sha256(serving_files),
        }

    def measure(self, image: Image.Image) -> dict[str, Any]:
        inputs = self.processor(images=[image.convert("RGB")], return_tensors="np")
        grid = np.asarray(inputs.get("image_grid_thw"))
        require(grid.shape == (1, 3), f"processor image_grid_thw shape {grid.shape}")
        grid_t, grid_h, grid_w = [int(value) for value in grid[0]]
        require(grid_t == 1, f"unexpected temporal grid {grid_t}")
        processed = [grid_w * 16, grid_h * 16]
        require(processed == [image.width, image.height], (
            f"processor resized page: source={[image.width, image.height]} processed={processed}"
        ))
        merged = grid_t * grid_h * grid_w
        require(merged % 4 == 0, "non-integral merged visual-token count")
        return {
            "image_grid_thw": [grid_t, grid_h, grid_w],
            "processed_size": processed,
            "visual_tokens": merged // 4,
            "measurement": "processor-real",
        }

    def measure_text(self, text: str) -> dict[str, Any]:
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        return {
            "text_tokens": len(token_ids),
            "text_chars": len(text),
            "measurement": "checkpoint-tokenizer-real",
        }

    def count_text_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))


def _pad_image(image: Image.Image, *, minimum: tuple[int, int] = (256, 256)) -> Image.Image:
    width = max(minimum[0], image.width)
    height = max(minimum[1], image.height)
    width += (-width) % 32
    height += (-height) % 32
    if (width, height) == image.size:
        return image.convert("RGB")
    canvas = Image.new("RGB", (width, height), sr.PAD_RGB)
    canvas.paste(image.convert("RGB"), (0, 0))
    return canvas


def _resize_nearest(image: Image.Image, *, max_width: int, max_height: int) -> Image.Image:
    scale = min(max_width / image.width, max_height / image.height, 1.0)
    if scale == 1.0:
        return image.convert("RGB")
    width = max(1, int(image.width * scale))
    height = max(1, int(image.height * scale))
    return image.resize((width, height), Image.Resampling.NEAREST)


def compose_row(plates: list[Image.Image], labels: list[str], gap: int = 16) -> Image.Image:
    require(len(plates) == len(labels) and plates, "compose_row needs paired panels")
    label_h = 24
    height = max(plate.height for plate in plates) + label_h
    width = sum(plate.width for plate in plates) + gap * (len(plates) + 1)
    canvas = Image.new("RGB", (width, height), sr.PAD_RGB)
    draw = ImageDraw.Draw(canvas)
    x = gap
    for plate, label in zip(plates, labels):
        canvas.paste(plate, (x, 0))
        draw.text((x, plate.height + 4), label, fill=(0, 0, 0))
        x += plate.width + gap
    return _pad_image(canvas)


def _stack(images: Sequence[Image.Image], gap: int = 16, max_width: int = 1024) -> Image.Image:
    require(bool(images), "cannot stack an empty image list")
    resized = [_resize_nearest(image, max_width=max_width, max_height=1024) for image in images]
    width = min(max_width, max(image.width for image in resized))
    height = sum(image.height for image in resized) + gap * (len(resized) - 1)
    canvas = Image.new("RGB", (width, height), sr.PAD_RGB)
    y = 0
    for image in resized:
        if image.width > width:
            image = _resize_nearest(image, max_width=width, max_height=1024)
        canvas.paste(image, ((width - image.width) // 2, y))
        y += image.height + gap
    if canvas.height > 1024:
        canvas = _resize_nearest(canvas, max_width=1024, max_height=1024)
    return _pad_image(canvas)


def _note_panel(lines: Sequence[str], height: int = 256) -> Image.Image:
    # These panels are sub-images.  Applying the processor's 256px minimum here
    # wastes budget when a one-line absence declaration only needs 128px; the
    # completed page is padded and audited after composition.
    height = max(32, int(height))
    height += (-height) % 32
    panel = Image.new("RGB", (1024, height), sr.PAD_RGB)
    draw = ImageDraw.Draw(panel)
    for index, line in enumerate(lines):
        draw.text((24, 24 + 24 * index), line, fill=(0, 0, 0))
    return panel


def _exact_storyboard(
    frames: Sequence[Any], *, cell_px: int = 4, max_cols: int = 8
) -> tuple[Image.Image, int]:
    """Choose a compact storyboard without ever rescaling rendered game cells."""
    require(bool(frames), "exact storyboard needs at least one frame")
    candidates = []
    for cols in range(1, min(max_cols, len(frames)) + 1):
        image = sr.storyboard(
            [np.asarray(frame) for frame in frames], cols=cols, cell_px=cell_px, gap=0
        ).image
        aspect = max(image.width / image.height, image.height / image.width)
        if aspect <= 3.0:
            candidates.append((visual_tokens(image.width, image.height),
                               max(image.width, image.height), cols, image))
    if not candidates:
        cols = min(max_cols, len(frames))
        image = sr.storyboard(
            [np.asarray(frame) for frame in frames], cols=cols, cell_px=cell_px, gap=0
        ).image
        return image, cols
    _, _, cols, image = min(candidates, key=lambda value: value[:3])
    return image, cols


def _annotate_causal_gutters(
    image: Image.Image, actions: Sequence[dict[str, Any]], *, cols: int, cell_px: int = 4
) -> Image.Image:
    """Put action arrows in storyboard gutters, never over a board cell."""
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    tile = 64 * cell_px
    row_pitch = tile + 16
    for index, action in enumerate(actions):
        row, col = divmod(index, cols)
        x = col * tile + 34
        y = row * row_pitch + tile + 2
        draw.text((x, y), f"{action['action']} ->[{index + 1}]", fill=sr.MARKER_RGB)
    return annotated


def _compose_exact_row(images: Sequence[Image.Image], gap: int = 8) -> Image.Image:
    """Place complete panels side by side without any evidence downscaling."""
    require(bool(images), "cannot compose an empty exact row")
    width = sum(image.width for image in images) + gap * (len(images) - 1)
    height = max(image.height for image in images)
    canvas = Image.new("RGB", (width, height), sr.PAD_RGB)
    x = 0
    for image in images:
        canvas.paste(image, (x, 0))
        x += image.width + gap
    return _pad_image(canvas)


def scaled(plate: sr.Plate, width: int = 500) -> Image.Image:
    return _resize_nearest(plate.image, max_width=width, max_height=width)


def _raw_transition_row(transition: dict[str, Any], label: str) -> Image.Image:
    if transition["pre"] is None:
        # Four rendered pixels per game cell retains an exact, integer-cell board
        # while leaving room for the bounded probe and retrieval additions.
        board = scaled(sr.render_board(np.asarray(transition["post"])), 256)
        return compose_row([board], [f"{label}: post; no recorded pre"])
    pre = scaled(sr.render_board(np.asarray(transition["pre"])), 256)
    post = scaled(sr.render_board(np.asarray(transition["post"])), 256)
    return compose_row([pre, post], [f"{label}: pre", f"{label}: settled post"])


def _overlay_transition_row(transition: dict[str, Any], label: str) -> Image.Image:
    if transition["pre"] is None:
        board = scaled(sr.render_board(np.asarray(transition["post"])), 256)
        return compose_row([board], [f"{label}: reset output; no recorded pre"])
    panels = sr.exhibit(
        np.asarray(transition["pre"]), np.asarray(transition["post"]),
        transition["action"], tuple(transition["click"]) if transition["click"] else None,
    )
    marker_board = panels["marker"].image.crop((0, 0, 1024, 1024)).resize(
        (256, 256), Image.Resampling.NEAREST
    )
    settled_board = scaled(sr.render_board(np.asarray(transition["post"])), 256)
    diff_board = scaled(panels["diff_mask"], 256)
    require(marker_board.size == settled_board.size == diff_board.size == (256, 256),
            "overlay full-board panels must remain exactly four pixels per game cell")
    row = compose_row(
        [marker_board, settled_board, diff_board],
        [f"{label} marked pre {transition['action']}", "settled post", "diff"],
        gap=8,
    )
    return _resize_nearest(row, max_width=1024, max_height=480)


def _contrast_page(effect: dict[str, Any] | None, no_effect: dict[str, Any] | None,
                   reset_only: dict[str, Any] | None, *, overlay: bool) -> Image.Image:
    renderer = _overlay_transition_row if overlay else _raw_transition_row
    rows = []
    if effect is not None:
        rows.append(renderer(effect, "EFFECT"))
    if no_effect is not None:
        rows.append(renderer(no_effect, "NO EFFECT"))
    if not rows and reset_only is not None:
        rows.append(renderer(reset_only, "RESET/INITIAL"))
    # Unavailable classes are stated exactly in the delivered caption, ledger,
    # text carrier, and exclusions.  Do not spend most of a visual page on a
    # blank banner when the observed board itself can remain larger.
    require(bool(rows), "observed action has neither a contrast nor reset frame")
    return _stack(rows, gap=8)


def _component_records(initial: Any, boards: Sequence[Any]) -> list[dict[str, Any]]:
    grid = np.asarray(initial, dtype=np.uint8)
    arrays = [np.asarray(board, dtype=np.uint8) for board in boards]
    seen = np.zeros(grid.shape, dtype=bool)
    components = []
    for row in range(64):
        for col in range(64):
            if seen[row, col]:
                continue
            colour = int(grid[row, col])
            queue = deque([(row, col)])
            seen[row, col] = True
            cells = []
            while queue:
                rr, cc = queue.popleft()
                cells.append((rr, cc))
                for nr, nc in ((rr - 1, cc), (rr + 1, cc), (rr, cc - 1), (rr, cc + 1)):
                    if 0 <= nr < 64 and 0 <= nc < 64 and not seen[nr, nc] \
                            and int(grid[nr, nc]) == colour:
                        seen[nr, nc] = True
                        queue.append((nr, nc))
            rows = [cell[0] for cell in cells]
            cols = [cell[1] for cell in cells]
            stable = all(all(int(board[rr, cc]) == colour for rr, cc in cells)
                         for board in arrays)
            components.append({
                "component_id": f"C{len(components):03d}", "colour": colour,
                "cells": len(cells), "bbox": [min(rows), min(cols), max(rows), max(cols)],
                "static_over_observed_posts": stable,
            })
    # A dominant field is still recorded, but overlays focus on bounded components.
    components.sort(key=lambda item: (-item["cells"], item["colour"], item["bbox"]))
    return components


def _component_overlay(initial: Any, components: Sequence[dict[str, Any]]) -> Image.Image:
    image = sr.render_board(np.asarray(initial)).image.copy()
    draw = ImageDraw.Draw(image)
    bounded = [component for component in components if component["cells"] < 2048][:24]
    for component in bounded:
        r0, c0, r1, c1 = component["bbox"]
        colour = (0, 255, 255) if component["static_over_observed_posts"] else sr.MARKER_RGB
        # Exact cell boundaries: the one-pixel line does not cover a cell interior.
        draw.rectangle([c0 * 16, r0 * 16, (c1 + 1) * 16 - 1, (r1 + 1) * 16 - 1],
                       outline=colour, width=1)
    return image


class PageBook:
    def __init__(self, out_dir: Path, carrier: str, auditor: Any):
        require(carrier in {"raw", "overlay"}, f"unknown carrier {carrier}")
        self.carrier = carrier
        # Flat names keep the packet compatible with the sealed inventory, while
        # the carrier prefix prevents collisions and remains safe as a basename.
        self.dir = out_dir / "pages"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.auditor = auditor
        self.pages: list[dict[str, Any]] = []

    def add(self, kind: str, evidence_id: str, image: Image.Image, caption: str) -> dict[str, Any]:
        image = _pad_image(image)
        number = len(self.pages) + 1
        name = f"{self.carrier}_page_{number:02d}_{kind}.png"
        require(image.width % 32 == 0 and image.height % 32 == 0,
                f"{name}: dimensions not divisible by 32")
        require(image.width * image.height >= 65_536, f"{name}: below processor minimum")
        path = self.dir / name
        image.save(path)
        measurement = self.auditor.measure(image)
        entry = {
            "page": number, "kind": kind, "evidence_id": evidence_id,
            "file": name, "caption": caption,
            "width": image.width, "height": image.height,
            "sha256": sha256_file(path), "bytes": path.stat().st_size,
            **measurement,
        }
        self.pages.append(entry)
        return entry


# ------------------------------------------------------------------------ selection


def _sample_evenly(items: Sequence[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    if len(items) <= cap:
        return list(items)
    indexes = np.linspace(0, len(items) - 1, cap, dtype=int)
    return [items[int(index)] for index in indexes]


def _matched_action_cases(transitions: Sequence[dict[str, Any]]) -> tuple[
    dict[str, dict[str, dict[str, Any] | None]], list[dict[str, Any]]
]:
    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for transition in transitions:
        by_action[transition["action"]].append(transition)
    selections = {}
    trim_log = []
    for action, rows in sorted(by_action.items()):
        with_pre = [row for row in rows if row["pre"] is not None]
        effects = [row for row in with_pre if effect_signature(row)[1] != "none"]
        no_effects = [row for row in with_pre if effect_signature(row)[1] == "none"]
        sampled_effects = _sample_evenly(effects, MATCH_CANDIDATES_PER_CLASS)
        sampled_none = _sample_evenly(no_effects, MATCH_CANDIDATES_PER_CLASS)
        effect = sampled_effects[0] if sampled_effects else None
        no_effect = sampled_none[0] if sampled_none else None
        distance = None
        if sampled_effects and sampled_none:
            best = None
            for effect_row in sampled_effects:
                pre_effect = np.asarray(effect_row["pre"])
                for none_row in sampled_none:
                    candidate = (
                        int(np.count_nonzero(pre_effect != np.asarray(none_row["pre"]))),
                        effect_row["tid"], none_row["tid"], effect_row, none_row,
                    )
                    if best is None or candidate[:3] < best[:3]:
                        best = candidate
            require(best is not None, "matched-pair selection failed")
            distance, _, _, effect, no_effect = best
        reset_only = next((row for row in rows if row["pre"] is None), None)
        selections[action] = {
            "effect": effect, "no_effect": no_effect, "reset_only": reset_only,
            "counts": {
                "observed": len(rows), "with_pre": len(with_pre),
                "effect": len(effects), "no_effect": len(no_effects),
                "without_pre": len(rows) - len(with_pre),
            },
            "pre_board_hamming_distance": distance,
        }
        trim_log.append({
            "operation": "matched-contrast-candidate-cap", "action": action,
            "effect_candidates": len(effects), "no_effect_candidates": len(no_effects),
            "effect_candidates_compared": len(sampled_effects),
            "no_effect_candidates_compared": len(sampled_none),
            "cap_per_class": MATCH_CANDIDATES_PER_CLASS,
        })
    return selections, trim_log


def _diverse_indices(transitions: Sequence[dict[str, Any]], count: int) -> list[int]:
    require(bool(transitions), "cannot select from empty transitions")
    chosen = [0]
    candidates = list(range(0, len(transitions), max(1, len(transitions) // 500)))
    while len(chosen) < min(count, len(transitions)):
        chosen_arrays = [np.asarray(transitions[index]["post"]) for index in chosen]
        best: tuple[int, int] | None = None
        for index in candidates:
            if index in chosen:
                continue
            distance = min(int(np.count_nonzero(np.asarray(transitions[index]["post"]) != board))
                           for board in chosen_arrays)
            candidate = (distance, -index)
            if best is None or candidate > best:
                best = candidate
                best_index = index
        if best is None or best[0] <= 0:
            break
        chosen.append(best_index)
    return chosen


def _causal_window(transitions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    episodes: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for transition in transitions:
        if transition["pre"] is not None:
            episodes[(transition["source"], transition["episode_index"])].append(transition)
    best: tuple[tuple[Any, ...], list[dict[str, Any]]] | None = None
    for key, episode in episodes.items():
        episode.sort(key=lambda row: row["episode_step"])
        for start in range(len(episode)):
            window = episode[start:start + CAUSAL_TRANSITIONS]
            if not window:
                continue
            # Reject any inferred discontinuity inside the window.
            if any(window[index]["episode_step"] + 1 != window[index + 1]["episode_step"]
                   for index in range(len(window) - 1)):
                continue
            score = (
                len({row["action"] for row in window}),
                len({effect_signature(row) for row in window}),
                sum(bool(row["completed"]) for row in window),
                len(window),
                -sum(row["source_index"] for row in window),
            )
            if best is None or score > best[0]:
                best = score, window
    require(best is not None, "no consecutive episode with recorded pre/post boards")
    return best[1]


def _history_conflict(transitions: Sequence[dict[str, Any]]) -> tuple[
    list[dict[str, Any]] | None, int
]:
    groups: dict[tuple[str, str, tuple[int, int] | None], dict[str, dict[str, Any]]] = defaultdict(dict)
    for transition in transitions:
        if transition["pre"] is None:
            continue
        key = (
            canonical_sha256(transition["pre"]), transition["action"],
            tuple(transition["click"]) if transition["click"] else None,
        )
        groups[key].setdefault(canonical_sha256(transition["post"]), transition)
    conflicts = [sorted(posts.values(), key=lambda row: row["tid"])
                 for posts in groups.values() if len(posts) > 1]
    conflicts.sort(key=lambda rows: (-len(rows), rows[0]["tid"]))
    return (conflicts[0][:2] if conflicts else None), len(conflicts)


def _richest_animation(
    evidence: dict[str, Any], preferred_store_indexes: set[int] | None = None
) -> dict[str, Any] | None:
    preferred_store_indexes = preferred_store_indexes or set()
    candidates = []
    for record in evidence["recap_records"]:
        for step in record.get("steps") or []:
            if int(step["frame_count"]) > 1:
                candidates.append((
                    int(step.get("store_index") in preferred_store_indexes),
                    int(step["frame_count"]), -int(record["episode_index"]),
                    -int(step["episode_step"]), record, step,
                ))
    if not candidates:
        return None
    preferred, _, _, _, record, step = max(candidates, key=lambda value: value[:4])
    return {
        "record": record, "step": step,
        "selection_reason": "completion-transition" if preferred else "richest-animation",
    }


def _transition_boards(rows: Sequence[dict[str, Any]], *, exact: bool = True) -> list[dict[str, Any]]:
    boards = []
    seen = set()
    for transition in rows:
        for suffix in ("pre", "post"):
            board = transition[suffix]
            if board is None:
                continue
            digest = canonical_sha256(board)
            if digest in seen:
                continue
            seen.add(digest)
            boards.append(_text_board(
                f"{transition['tid']}:{suffix}", suffix, board, exact=exact
            ))
    return boards


def _build_identity(auditor: Any) -> dict[str, Any]:
    packages = {}
    for name in ("numpy", "Pillow", "transformers"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "packet_builder_sha256": sha256_file(Path(__file__).resolve()),
        "renderer_sha256": sha256_file(HARNESS / "s4_render.py"),
        "packages": packages,
        "processor": getattr(auditor, "identity", {"implementation": type(auditor).__name__}),
    }


def _add_item(
    items: list[dict[str, Any]], raw: PageBook, overlay: PageBook, *, kind: str,
    transition_refs: Sequence[str], episode_refs: Sequence[str], action_sequence: Sequence[Any],
    text: str, text_boards: Sequence[dict[str, Any]], derived: Sequence[Any],
    raw_image: Image.Image, overlay_image: Image.Image, caption: str,
    discriminator: str = "", provenance: str = "OBSERVED / DERIVED-EXACT",
) -> dict[str, Any]:
    eid = _evidence_id(kind, transition_refs, episode_refs, discriminator)
    raw_page = raw.add(kind, eid, raw_image, caption)
    overlay_page = overlay.add(kind, eid, overlay_image, caption)
    require(raw_page["page"] == overlay_page["page"], "carrier page-number drift")
    item = {
        "evidence_id": eid, "kind": kind, "provenance": provenance,
        "transition_refs": list(transition_refs), "episode_refs": list(episode_refs),
        "action_sequence": list(action_sequence), "text": text,
        "carriers": {
            "raw": {"page": raw_page["page"], "file": raw_page["file"],
                    "pages": [raw_page["file"]]},
            "overlay": {"page": overlay_page["page"], "file": overlay_page["file"],
                        "pages": [overlay_page["file"]]},
            "text": {"boards": list(text_boards), "actions": list(action_sequence),
                     "derived": list(derived)},
        },
    }
    items.append(item)
    return item


def _text_carrier_payload(ledger: str, items: Sequence[dict[str, Any]]) -> str:
    """Byte-for-byte structure used by ``s4_run._text_evidence`` for arm T."""
    blocks = ["== EXACT LEDGER ==\n" + ledger]
    for item in items:
        text_carrier = (item.get("carriers") or {}).get("text") or {}
        block = [
            f"== EVIDENCE {item.get('evidence_id')} ==",
            f"kind={item.get('kind')} provenance={item.get('provenance')}",
            str(item.get("text") or ""),
        ]
        actions = text_carrier.get("actions") or item.get("action_sequence") or []
        if actions:
            block.append("actions=" + json.dumps(actions, sort_keys=True, separators=(",", ":")))
        for board in text_carrier.get("boards") or []:
            block.append(
                f"board {board.get('frame_id')} {board.get('label', '')}\n{board.get('hex', '')}"
            )
        derived = text_carrier.get("derived") or []
        if derived:
            block.append("derived=" + json.dumps(derived, sort_keys=True, separators=(",", ":")))
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def _finalise_text_boards(items: Sequence[dict[str, Any]], auditor: Any) -> dict[str, Any]:
    """Choose lossless global references/deltas with the checkpoint tokenizer.

    Bases always precede their users in carrier order.  Every encoded board is
    decoded immediately and checked against its advertised full grid hash, so the
    compact carrier cannot become a lossy modality-specific summary.
    """
    require(hasattr(auditor, "count_text_tokens"),
            "auditor lacks tokenizer-real candidate measurement")
    first_by_digest: dict[str, str] = {}
    digest_by_frame: dict[str, str] = {}
    prior_unique: list[tuple[str, list[list[int]]]] = []
    decoded_by_frame: dict[str, list[list[int]]] = {}
    stats = Counter()
    encoded_tokens = 0
    for item in items:
        for board in item["carriers"]["text"]["boards"]:
            require("_grid" in board, (
                f"matched text board {board.get('frame_id')} lacks an exact build-time grid"
            ))
            target = board.pop("_grid")
            digest = canonical_sha256(target)
            require(board.get("sha256") == digest,
                    f"text board {board.get('frame_id')} hash changed before encoding")
            frame_id = str(board["frame_id"])
            require(frame_id not in digest_by_frame or digest_by_frame[frame_id] == digest,
                    f"text frame id {frame_id} was reused for a different board")
            digest_by_frame[frame_id] = digest
            if digest in first_by_digest:
                base_id = first_by_digest[digest]
                encoded = f"ref64:{base_id}"
                encoding = "lossless-reference-to-prior-frame"
                stats["reference"] += 1
            else:
                full = _grid_rle(target)
                best = (
                    int(auditor.count_text_tokens(full)), len(full), 0, full,
                    "2d-rle-64x64 (*=cell run, ^=repeated row)", None,
                )
                for base_order, (base_id, base_grid) in enumerate(prior_unique, 1):
                    delta = _grid_delta(target, base_grid, base_id)
                    candidate = (
                        int(auditor.count_text_tokens(delta)), len(delta), base_order,
                        delta, "lossless-delta64 (base|colour@row,col,height,width)", base_id,
                    )
                    if candidate[:3] < best[:3]:
                        best = candidate
                _, _, _, encoded, encoding, base_id = best
                stats["delta" if base_id is not None else "full"] += 1
                first_by_digest[digest] = frame_id
                prior_unique.append((frame_id, target))
            decoded = decode_text_grid(encoded, decoded_by_frame)
            require(canonical_sha256(decoded) == digest,
                    f"lossless text-grid verification failed for {frame_id}")
            decoded_by_frame[frame_id] = decoded
            board["hex"] = encoded  # legacy runner field; contents declare their codec
            board["encoding"] = encoding
            encoded_tokens += int(auditor.count_text_tokens(encoded))
    stats["unique_boards"] = len(prior_unique)
    stats["board_records"] = sum(stats[key] for key in ("full", "delta", "reference"))
    stats["encoded_board_tokens"] = encoded_tokens
    stats["lossless_decode_hash_checks"] = stats["board_records"]
    return dict(stats)


def _build_into(game: str, out_dir: Path, evidence: dict[str, Any], auditor: Any) -> dict[str, Any]:
    bid = blind_id(game)
    transitions = transition_stream(evidence)
    require(transitions, "no visual transitions")
    boards = [transition["post"] for transition in transitions]
    initial = boards[0]
    game_seed = seed_for_game(game)
    rng = np.random.default_rng(game_seed)
    raw = PageBook(out_dir, "raw", auditor)
    overlay = PageBook(out_dir, "overlay", auditor)
    items: list[dict[str, Any]] = []
    trim_log: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    null_posts = sum(row.get("post") is None for row in evidence["performs"])
    if null_posts:
        exclusions.append({
            "kind": "nonvisual-zero-frame-store-rows", "count": null_posts,
            "reason": "post is null; preserved by recapture accounting but has no image",
        })

    # 1: opening scene plus exact connected components/static-over-record status.
    # Eight pixels per cell keeps the opening/component geometry crisp while
    # avoiding a duplicate full-resolution page.
    opening = _resize_nearest(
        sr.render_board(np.asarray(initial)).image, max_width=512, max_height=512
    )
    components = _component_records(initial, boards)
    dominant = components[0]
    bounded = [component for component in components if component["cells"] < 2048]
    component_derived = [{key: component[key] for key in (
        "component_id", "colour", "cells", "bbox", "static_over_observed_posts"
    )} for component in bounded[:64]]
    if len(bounded) > 64:
        trim_log.append({
            "operation": "component-ledger-cap", "kept": 64, "excluded": len(bounded) - 64,
            "criterion": "largest-first deterministic component ordering",
        })
    if len(bounded) > 24:
        trim_log.append({
            "operation": "component-overlay-box-cap", "kept": 24,
            "excluded": len(bounded) - 24,
            "criterion": "largest-first deterministic component ordering; all retained in counts",
        })
    _add_item(
        items, raw, overlay, kind="opening_components",
        transition_refs=[transitions[0]["tid"]],
        episode_refs=[f"{transitions[0]['source']}:{transitions[0]['episode_index']}"],
        action_sequence=[],
        text=("First admitted observed board. Four-connected same-colour components are "
              "computed on it; static means every listed cell retained its colour over all "
              "admitted settled posts."),
        text_boards=[_text_board(f"{transitions[0]['tid']}:post", "opening", initial)],
        derived=[{"component_count": len(components), "bounded_component_count": len(bounded),
                  "dominant_component": dominant}, *component_derived],
        raw_image=opening,
        overlay_image=_resize_nearest(
            _component_overlay(initial, components), max_width=512, max_height=512
        ),
        caption="Opening board. Raw is clean; overlay has exact four-connected boxes "
                "(cyan static, magenta changed).",
        provenance="OBSERVED / DERIVED-EXACT",
    )

    # 2: source-blind structural atlas.
    atlas_indices = _diverse_indices(transitions, ATLAS_STATES)
    atlas_rows = [transitions[index] for index in atlas_indices]
    atlas_stride = max(1, len(transitions) // 500)
    trim_log.append({
        "operation": "state-atlas-candidate-stride", "input_transitions": len(transitions),
        "candidate_stride": atlas_stride,
        "candidates_considered": len(range(0, len(transitions), atlas_stride)),
        "selected": len(atlas_rows), "target": ATLAS_STATES,
    })
    if len(atlas_rows) < 12:
        exclusions.append({
            "kind": "state-atlas-under-12", "count": len(atlas_rows),
            "reason": "fewer than twelve distinct candidates under exact max-min selection",
        })
    atlas, atlas_cols = _exact_storyboard(
        [row["post"] for row in atlas_rows], cell_px=4, max_cols=7
    )
    _add_item(
        items, raw, overlay, kind="state_atlas",
        transition_refs=[row["tid"] for row in atlas_rows], episode_refs=[], action_sequence=[],
        text="Greedy max-min settled-board atlas selected without source semantics.",
        text_boards=[_text_board(f"{row['tid']}:post", "atlas settled post", row["post"])
                     for row in atlas_rows],
        derived=[{"selection": "greedy-max-min-cell-hamming", "states": len(atlas_rows),
                  "visual_cell_px": 4, "storyboard_cols": atlas_cols}],
        raw_image=atlas, overlay_image=atlas,
        caption=f"{len(atlas_rows)} structurally diverse observed settled states at 4px/cell.",
        provenance="OBSERVED / DERIVED-EXACT-SELECTION",
    )

    # 3: one genuinely consecutive episode window with exact action alignment.
    causal = _causal_window(transitions)
    causal_episode_size = sum(
        row["source"] == causal[0]["source"]
        and row["episode_index"] == causal[0]["episode_index"]
        and row["pre"] is not None
        for row in transitions
    )
    trim_log.append({
        "operation": "causal-window-cap", "episode": (
            f"{causal[0]['source']}:{causal[0]['episode_index']}"
        ),
        "episode_transitions_with_pre": causal_episode_size,
        "selected_episode_steps": [causal[0]["episode_step"], causal[-1]["episode_step"]],
        "selected": len(causal), "cap": CAUSAL_TRANSITIONS,
        "excluded_from_selected_episode": max(0, causal_episode_size - len(causal)),
    })
    causal_frames = [causal[0]["pre"], *[row["post"] for row in causal]]
    causal_story = sr.storyboard(
        [np.asarray(frame) for frame in causal_frames], cols=4, cell_px=4, gap=0
    ).image
    causal_actions = [{
        "from_frame": index, "to_frame": index + 1, "tid": row["tid"],
        "action": row["action"], "click": row["click"],
        "episode_step": row["episode_step"],
    } for index, row in enumerate(causal)]
    causal_overlay = _annotate_causal_gutters(
        causal_story, causal_actions, cols=4, cell_px=4
    )
    _add_item(
        items, raw, overlay, kind="causal_episode",
        transition_refs=[row["tid"] for row in causal],
        episode_refs=[f"{causal[0]['source']}:{causal[0]['episode_index']}"],
        action_sequence=causal_actions,
        text="Consecutive frames 0..N from one episode; each action maps frame i to i+1.",
        text_boards=[_text_board(
            f"{causal[0]['tid']}:pre" if index == 0 else f"{causal[index - 1]['tid']}:post",
            f"causal frame {index}", frame,
        ) for index, frame in enumerate(causal_frames)],
        derived=[{"window_length": len(causal), "selection": "max action/effect diversity",
                  "visual_cell_px": 4, "storyboard_cols": 4}],
        raw_image=causal_story, overlay_image=causal_overlay,
        caption="One consecutive episode window at 4px/cell; gutters align each action.",
        provenance="OBSERVED / DERIVED-EXACT-SELECTION",
    )

    # 4..: every observed action, each with its matched effect/no-effect pair if present.
    action_cases, action_trims = _matched_action_cases(transitions)
    trim_log.extend(action_trims)
    action_records = []
    for action, cases in sorted(action_cases.items(), key=lambda item: int(item[0][1:])):
        selected = [row for row in (cases["effect"], cases["no_effect"], cases["reset_only"])
                    if row is not None]
        transition_refs = list(dict.fromkeys(row["tid"] for row in selected))
        facts = [_transition_fact(row) for row in selected]
        counts = cases["counts"]
        missing = []
        if cases["effect"] is None:
            missing.append("effect-with-pre")
        if cases["no_effect"] is None:
            missing.append("no-effect-with-pre")
        if missing:
            exclusions.append({
                "kind": "unavailable-action-contrast", "action": action,
                "missing": missing, "observed_counts": counts,
                "reason": "class was absent in the complete admitted transition stream",
            })
        action_records.append({
            "action": action,
            "transition_refs": transition_refs,
            "action_sequence": [{
                "tid": row["tid"], "action": row["action"], "click": row["click"],
                "class": ("unclassified-reset-output" if row["pre"] is None else
                          "no-effect" if effect_signature(row)[1] == "none" else "effect"),
            } for row in selected],
            "text": (f"{action} contrast. Counts are over all admitted observations; when "
                     "both classes exist, the shown pair minimizes pre-board cell Hamming "
                     "distance within deterministic candidate caps. "
                     f"Missing classes: {missing or 'none'}."),
            "text_boards": _transition_boards(selected),
            "derived": [{
                "action": action, "counts": counts, "missing": missing,
                "matched_pre_board_hamming_distance": cases["pre_board_hamming_distance"],
                "visual_full_board_cell_px": 4,
                "overlay_full_board_panels": ["marked_pre", "settled_post", "diff"],
            }, *facts],
            "raw_image": _contrast_page(
                cases["effect"], cases["no_effect"], cases["reset_only"], overlay=False
            ),
            "overlay_image": _contrast_page(
                cases["effect"], cases["no_effect"], cases["reset_only"], overlay=True
            ),
            "caption": f"{action}: observed contrast; missing={missing or 'none'}.",
        })

    # At most six action pages: when all seven/eight controls are observed, pair
    # the final low-cost contrast sections side by side without rescaling either.
    pairs_needed = max(0, len(action_records) - 6)
    pair_start = len(action_records) - 2 * pairs_needed
    action_groups = [[record] for record in action_records[:pair_start]]
    for index in range(pair_start, len(action_records), 2):
        action_groups.append(action_records[index:index + 2])
    grouped_actions = [[record["action"] for record in group]
                       for group in action_groups if len(group) > 1]
    if grouped_actions:
        trim_log.append({
            "operation": "action-contrast-page-grouping",
            "groups": grouped_actions,
            "visual_rescaling": False,
            "facts_retained": "all transition refs, actions, boards, counts, and absences",
        })

    for group in action_groups:
        action_names = [record["action"] for record in group]
        refs = list(dict.fromkeys(
            tid for record in group for tid in record["transition_refs"]
        ))
        sequences = [value for record in group for value in record["action_sequence"]]
        text_boards = [value for record in group for value in record["text_boards"]]
        derived = [value for record in group for value in record["derived"]]
        raw_images = [record["raw_image"] for record in group]
        overlay_images = [record["overlay_image"] for record in group]
        _add_item(
            items, raw, overlay, kind="action_" + "_".join(
                action.lower() for action in action_names
            ),
            transition_refs=refs, episode_refs=[], action_sequence=sequences,
            text="\n".join(record["text"] for record in group),
            text_boards=text_boards, derived=derived,
            raw_image=(raw_images[0] if len(raw_images) == 1
                       else _compose_exact_row(raw_images)),
            overlay_image=(overlay_images[0] if len(overlay_images) == 1
                           else _compose_exact_row(overlay_images)),
            caption=" | ".join(record["caption"] for record in group),
        )

    # Temporal/history/completion/static/coverage/reserve evidence is complete and composited.
    completions = [row for row in transitions if row["completed"]]
    recapture_by_store_index = {
        int(step["store_index"]): step
        for record in evidence["recap_records"] for step in record.get("steps") or []
    }
    completion = next((
        row for row in completions
        if row["source"] == "store"
        and int((recapture_by_store_index.get(int(row["store_index"])) or {}).get(
            "frame_count", 0
        )) > 1
    ), completions[0] if completions else None)
    completion_store_indexes = {
        int(row["store_index"]) for row in completions
        if row["source"] == "store" and row["store_index"] is not None
    }
    animation = _richest_animation(evidence, completion_store_indexes)
    animation_chunks: list[list[Any]] = []
    animation_ref = None
    animation_action = None
    if animation is not None:
        step = animation["step"]
        frames = step["frames"]
        require(len(frames) == int(step["frame_count"]), "selected animation was truncated")
        animation_chunks = [frames[index:index + TRANSFORM_FRAMES_PER_PAGE]
                            for index in range(0, len(frames), TRANSFORM_FRAMES_PER_PAGE)]
        animation_ref = f"S{int(step['store_index']):05d}"
        animation_action = _action_label(step["action"])
        trim_log.append({
            "operation": "animation-page-split", "transition": animation_ref,
            "total_frames": len(frames), "frames_per_page": TRANSFORM_FRAMES_PER_PAGE,
            "chunks": [len(chunk) for chunk in animation_chunks],
            "settled_frame_included": True,
        })
    else:
        exclusions.append({"kind": "transformation-strip", "count": 0,
                           "reason": "no verified multi-frame action observed"})

    conflict, conflict_count = _history_conflict(transitions)
    if conflict is None:
        exclusions.append({"kind": "history-conflict", "count": 0,
                           "reason": "no same-board+action+click pair had distinct posts"})
    if not completions:
        exclusions.append({"kind": "autonomous-completion", "count": 0,
                           "reason": "no completion flag in either autonomous source"})
    with_pre = [row for row in transitions if row["pre"] is not None]
    require(with_pre, "no transition with a recorded pre board")
    reserve = with_pre[int(rng.integers(0, len(with_pre)))]
    coverage = Counter(row["action"] for row in transitions)
    effect_coverage = {
        action: {
            "effect": int(cases["counts"]["effect"]),
            "no_effect": int(cases["counts"]["no_effect"]),
            "without_pre": int(cases["counts"]["without_pre"]),
        } for action, cases in action_cases.items()
    }

    auxiliary_frames: list[Any] = []
    auxiliary_labels: list[str] = []
    auxiliary_frame_ids: list[str] = []
    summary_refs = [reserve["tid"]]
    summary_boards: list[dict[str, Any]] = []
    summary_actions = []
    if animation_chunks:
        summary_refs.append(animation_ref)
        summary_actions.append({
            "tid": animation_ref, "action": animation_action,
            "returned_frames": int(animation["step"]["frame_count"]),
            "selection_reason": animation["selection_reason"],
        })
        # Every frame is an exact text fact.  The visual chunk contains the same sequence.
        summary_boards.extend(_text_board(
            f"{animation_ref}:frame:{index}", f"animation frame {index}", frame
        ) for index, frame in enumerate(animation_chunks[0]))
    if conflict:
        auxiliary_frames.extend([
            conflict[0]["pre"], conflict[0]["post"], conflict[1]["post"],
        ])
        auxiliary_labels.extend([
            "history same pre", f"history post {conflict[0]['tid']}",
            f"history post {conflict[1]['tid']}",
        ])
        auxiliary_frame_ids.extend([
            f"{conflict[0]['tid']}:pre", f"{conflict[0]['tid']}:post",
            f"{conflict[1]['tid']}:post",
        ])
        summary_refs.extend(row["tid"] for row in conflict)
        summary_boards.extend(_transition_boards(conflict))
    completion_next = None
    completion_recapture = None
    completion_frame_ids: list[str] = []
    if completion is not None:
        completion_next = min((
            row for row in transitions
            if row["source"] == completion["source"]
            and row["source_index"] > completion["source_index"]
        ), key=lambda row: row["source_index"], default=None)
        if completion["source"] == "store":
            completion_recapture = recapture_by_store_index.get(int(completion["store_index"]))
        if completion_recapture is not None:
            completion_frame_ids = [
                f"{completion['tid']}:frame:{index}"
                for index in range(int(completion_recapture["frame_count"]))
            ]
        if completion["pre"] is not None:
            auxiliary_frames.append(completion["pre"])
            auxiliary_labels.append(f"completion pre {completion['tid']}")
            auxiliary_frame_ids.append(f"{completion['tid']}:pre")
        auxiliary_frames.append(completion["post"])
        auxiliary_labels.append(f"completion post {completion['tid']}")
        auxiliary_frame_ids.append(f"{completion['tid']}:post")
        if completion_next is not None:
            auxiliary_frames.append(completion_next["post"])
            auxiliary_labels.append(f"next observed {completion_next['tid']}")
            auxiliary_frame_ids.append(f"{completion_next['tid']}:post")
        summary_refs.append(completion["tid"])
        if completion_next is not None:
            summary_refs.append(completion_next["tid"])
        summary_boards.extend(_transition_boards([completion]))
        if completion_recapture is not None and animation_ref != completion["tid"]:
            summary_boards.extend(_text_board(
                f"{completion['tid']}:frame:{index}", f"completion returned frame {index}", frame
            ) for index, frame in enumerate(completion_recapture["frames"]))
        if completion_next is not None:
            summary_boards.append(_text_board(
                f"{completion_next['tid']}:post", "next observed board after completion",
                completion_next["post"],
            ))
        summary_actions.append({
            "tid": completion["tid"], "action": completion["action"],
            "click": completion["click"], "completed": True,
            "pre_frame": f"{completion['tid']}:pre" if completion["pre"] is not None else None,
            "returned_frames": completion_frame_ids,
            "settled_frame": (
                completion_frame_ids[-1] if completion_frame_ids
                else f"{completion['tid']}:post"
            ),
            "store_or_export_post": f"{completion['tid']}:post",
            "next_observed_tid": completion_next["tid"] if completion_next else None,
            "next_observed_frame": (
                f"{completion_next['tid']}:post" if completion_next else None
            ),
            "response_state": completion["state"],
            "post_level": completion["level"],
            "levels_completed_or_score": completion["levels_completed"],
            "done": completion.get("done"), "game_over": completion.get("game_over"),
            "reward": completion.get("reward"),
        })
    auxiliary_frames.extend([reserve["pre"], reserve["post"]])
    auxiliary_labels.extend([
        f"reserve pre {reserve['tid']}", f"reserve post {reserve['tid']}",
    ])
    auxiliary_frame_ids.extend([f"{reserve['tid']}:pre", f"{reserve['tid']}:post"])
    summary_boards.extend(_transition_boards([reserve]))
    summary_actions.append({"tid": reserve["tid"], "action": reserve["action"],
                            "click": reserve["click"], "selection_seed": game_seed})
    # Every temporal board is rendered once at an audited four pixels per game
    # cell.  Animation and auxiliary evidence share one indexed storyboard so no
    # later stack operation can silently shrink either sequence.
    require(len(auxiliary_frames) == len(auxiliary_labels) == len(auxiliary_frame_ids),
            "auxiliary temporal frame metadata drift")
    require(len(auxiliary_frames) <= 8, "unexpected auxiliary temporal evidence overflow")
    animation_visual_frames = animation_chunks[0] if animation_chunks else []
    animation_visual_ids = [
        f"{animation_ref}:frame:{index}" for index in range(len(animation_visual_frames))
    ]
    visual_frames = [*animation_visual_frames, *auxiliary_frames]
    visual_ids = [*animation_visual_ids, *auxiliary_frame_ids]
    visual_labels = [
        *[f"animation frame {index}" for index in range(len(animation_visual_frames))],
        *auxiliary_labels,
    ]
    summary_story, summary_cols = _exact_storyboard(
        visual_frames, cell_px=4, max_cols=8
    )
    summary_visual_index = [
        {"index": index, "frame_id": frame_id, "label": label}
        for index, (frame_id, label) in enumerate(zip(visual_ids, visual_labels))
    ]
    summary_refs = list(dict.fromkeys(summary_refs))
    _add_item(
        items, raw, overlay, kind="temporal_history_coverage",
        transition_refs=summary_refs,
        episode_refs=([f"store:{animation['record']['episode_index']}"] if animation else []),
        action_sequence=summary_actions,
        text=("Complete selected transformation, same-visible-input conflict when observed, "
              "first autonomous completion when observed, exact static-component and action "
              "coverage counts, and a seeded reserve transition."),
        text_boards=summary_boards,
        derived=[
            {"coverage": dict(sorted(coverage.items())), "effect_coverage": effect_coverage},
            {"visual_frame_index": summary_visual_index, "visual_cell_px": 4,
             "storyboard_cols": summary_cols},
            {"history_conflict_groups": conflict_count},
            {"completion_transition_count": len(completions)},
            {"completion_evidence": None if completion is None else {
                "tid": completion["tid"], "source": completion["source"],
                "action": completion["action"], "click": completion["click"],
                "response_state": completion["state"], "post_level": completion["level"],
                "levels_completed_or_score": completion["levels_completed"],
                "returned_frame_count": len(completion_frame_ids),
                "settled_frame": (
                    completion_frame_ids[-1] if completion_frame_ids
                    else f"{completion['tid']}:post"
                ),
                "next_observed_tid": completion_next["tid"] if completion_next else None,
            }},
            {"static_component_count": sum(
                bool(component["static_over_observed_posts"]) for component in components)},
            {"reserve_seed": game_seed, "reserve_tid": reserve["tid"]},
            {"animation": None if animation is None else {
                "tid": animation_ref, "action": animation_action,
                "frame_count": int(animation["step"]["frame_count"]),
                "settled_frame_index": int(animation["step"]["frame_count"]) - 1,
                "rendered_cell_px": 4,
                "selection_reason": animation["selection_reason"],
            }},
        ],
        raw_image=summary_story, overlay_image=summary_story,
        caption="Transformation/history/completion/static/coverage/reserve evidence; "
                "unavailable categories are declared in the manifest.",
    )

    # Additional full animation chunks are mandatory evidence, never a silent trim.
    for chunk_index, chunk in enumerate(animation_chunks[1:], 1):
        start = chunk_index * TRANSFORM_FRAMES_PER_PAGE
        story, continuation_cols = _exact_storyboard(chunk, cell_px=4, max_cols=8)
        _add_item(
            items, raw, overlay, kind=f"transformation_cont_{chunk_index}",
            transition_refs=[animation_ref],
            episode_refs=[f"store:{animation['record']['episode_index']}"],
            action_sequence=[{"tid": animation_ref, "action": animation_action,
                              "frame_range": [start, start + len(chunk) - 1]}],
            text=f"Continuation of every returned frame for {animation_ref}.",
            text_boards=[_text_board(f"{animation_ref}:frame:{start + index}",
                                    f"animation frame {start + index}", frame)
                         for index, frame in enumerate(chunk)],
            derived=[{"frame_range": [start, start + len(chunk) - 1],
                      "settled_frame_included": start + len(chunk) == int(
                          animation["step"]["frame_count"]),
                      "visual_cell_px": 4, "storyboard_cols": continuation_cols}],
            raw_image=story,
            overlay_image=story,
            caption=f"Complete animation continuation frames {start}..{start + len(chunk) - 1}.",
            provenance="OBSERVED",
        )

    # Fill to exactly ten with diverse transitions; never repeat an already cited TID.
    cited = {tid for item in items for tid in item["transition_refs"]}
    signatures_by_tid = {row["tid"]: effect_signature(row) for row in transitions}
    signature_counts = Counter(signatures_by_tid.values())
    fillers = sorted(
        (row for row in transitions if row["pre"] is not None and row["tid"] not in cited),
        key=lambda row: (signature_counts[signatures_by_tid[row["tid"]]], row["tid"]),
    )
    filler_index = 0
    while len(items) < TARGET_INITIAL_PAGES:
        require(filler_index < len(fillers), "not enough distinct transitions to fill packet")
        row = fillers[filler_index]
        filler_index += 1
        _add_item(
            items, raw, overlay, kind=f"diverse_reserve_{filler_index}",
            transition_refs=[row["tid"]],
            episode_refs=[f"{row['source']}:{row['episode_index']}"],
            action_sequence=[{"tid": row["tid"], "action": row["action"],
                              "click": row["click"]}],
            text="Deterministic rare-effect filler used to reach the frozen ten-page target.",
            text_boards=_transition_boards([row]), derived=[_transition_fact(row)],
            raw_image=_raw_transition_row(row, "DIVERSE RESERVE"),
            overlay_image=_overlay_transition_row(row, "DIVERSE RESERVE"),
            caption=f"Deterministic rare-effect transition {row['tid']}.",
            provenance="OBSERVED / DERIVED-EXACT-SELECTION",
        )
    text_encoding_stats = _finalise_text_boards(items, auditor)
    require(len(raw.pages) == len(overlay.pages) == len(items), "carrier/item count drift")
    require(len(items) <= MAX_INITIAL_PAGES, (
        f"initial packet needs {len(items)} pages, over cap {MAX_INITIAL_PAGES}"
    ))

    carrier_totals = {}
    for carrier, pages in (("raw", raw.pages), ("overlay", overlay.pages)):
        tokens = sum(int(page["visual_tokens"]) for page in pages)
        require(tokens <= MAX_INITIAL_VISUAL_TOKENS, (
            f"{carrier} initial carrier has {tokens} visual tokens, over "
            f"{MAX_INITIAL_VISUAL_TOKENS} after probe/retrieval reserves"
        ))
        require(tokens + RESERVED_POST_INITIAL_VISUAL_TOKENS <= MAX_VISUAL_TOKENS, (
            f"{carrier} carrier leaves insufficient headroom for "
            f"{INTERACTIVE_RESULT_HEADROOM} probe storyboards and "
            f"{RETRIEVAL_RESULT_HEADROOM} retrieval composites"
        ))
        carrier_totals[carrier] = {
            "page_count": len(pages), "visual_tokens": tokens,
            "visual_token_headroom": MAX_VISUAL_TOKENS - tokens,
            "reserved_minimal_result_visual_tokens": RESERVED_RESULT_VISUAL_TOKENS,
            "reserved_retrieval_visual_tokens": RESERVED_RETRIEVAL_VISUAL_TOKENS,
            "reserved_post_initial_visual_tokens": RESERVED_POST_INITIAL_VISUAL_TOKENS,
            "initial_visual_token_ceiling": MAX_INITIAL_VISUAL_TOKENS,
            "processor_measurements": "per-page image_grid_thw",
        }

    page_count = len(items)
    headroom = MAX_IMAGES - page_count
    selection = {
        "algorithm_version": FORMAT_VERSION,
        "base_seed": SEED,
        "game_seed": game_seed,
        "target_initial_pages": TARGET_INITIAL_PAGES,
        "actual_initial_pages": page_count,
        "above_target_declared": page_count > TARGET_INITIAL_PAGES,
        "image_cap_headroom": headroom,
        "interactive_three_result_pages_fit": headroom >= INTERACTIVE_RESULT_HEADROOM,
        "three_retrieval_pages_fit": headroom >= RETRIEVAL_RESULT_HEADROOM,
        "probe_and_retrieval_six_pages_fit": headroom >= (
            INTERACTIVE_RESULT_HEADROOM + RETRIEVAL_RESULT_HEADROOM
        ),
        "interactive_three_minimal_result_pages_fit_token_cap": all(
            total["visual_token_headroom"] >= RESERVED_RESULT_VISUAL_TOKENS
            for carrier, total in carrier_totals.items() if carrier in {"raw", "overlay"}
        ),
        "probe_and_retrieval_pages_fit_token_cap": all(
            total["visual_token_headroom"] >= RESERVED_POST_INITIAL_VISUAL_TOKENS
            for carrier, total in carrier_totals.items() if carrier in {"raw", "overlay"}
        ),
        "atlas_transition_refs": [row["tid"] for row in atlas_rows],
        "causal_transition_refs": [row["tid"] for row in causal],
        "text_grid_encoding": text_encoding_stats,
        "trim_log": trim_log,
        "exclusions": exclusions,
    }

    ledger_lines = [
        f"GAME {bid}",
        "PROVENANCE OBSERVED = recorded engine/environment output; DERIVED-EXACT = "
        "deterministic counts, diffs, connected components, or source-blind selection.",
        f"PACKET pages_per_carrier={page_count} target={TARGET_INITIAL_PAGES} "
        f"post_initial_image_headroom={headroom} seed={game_seed}",
        "TEXT_GRID_CODEC lossless 64x64: rle64 uses hex-colour*cell-run and "
        "^repeated-row; ref64 names an earlier frame; delta64 names an earlier base then "
        "base36 colour@row,col,height,width patches applied in listed order.",
    ]
    for page, item in enumerate(items, 1):
        ledger_lines.append(
            f"PAGE {page:02d} evidence={item['evidence_id']} kind={item['kind']} "
            f"transitions={','.join(item['transition_refs']) or '-'}"
        )
        for action in item["action_sequence"]:
            ledger_lines.append("  ACTION " + json.dumps(action, sort_keys=True,
                                                         separators=(",", ":")))
    ledger_lines.extend([
        "COVERAGE " + json.dumps(dict(sorted(coverage.items())), separators=(",", ":")),
        "EFFECT_COVERAGE " + json.dumps(effect_coverage, sort_keys=True, separators=(",", ":")),
        "EPISODES " + json.dumps({
            source: sorted({row["episode_index"] for row in transitions if row["source"] == source})
            for source in ("store", "kaggle")
        }, separators=(",", ":")),
        "TRIMS " + json.dumps(trim_log, sort_keys=True, separators=(",", ":")),
        "EXCLUSIONS " + json.dumps(exclusions, sort_keys=True, separators=(",", ":")),
    ])
    ledger_text = "\n".join(ledger_lines) + "\n"
    ledger_path = out_dir / "ledger.txt"
    ledger_path.write_text(ledger_text, encoding="utf-8")
    require(hasattr(auditor, "measure_text"), "auditor lacks tokenizer-real text measurement")
    text_measurement = auditor.measure_text(_text_carrier_payload(ledger_text, items))
    require(int(text_measurement["text_tokens"]) <= MAX_TEXT_TOKENS, (
        f"text carrier has {text_measurement['text_tokens']} tokens, over {MAX_TEXT_TOKENS}"
    ))
    carrier_totals["text"] = text_measurement

    manifest = {
        "format_version": FORMAT_VERSION,
        "blind_id": bid,
        "evidence_items": items,
        "carrier_pages": {"raw": raw.pages, "overlay": overlay.pages},
        "carrier_totals": carrier_totals,
        # Legacy alias used by older read-only consumers: the raw carrier.
        "pages": raw.pages,
        "page_count": page_count,
        "visual_tokens_total": carrier_totals["raw"]["visual_tokens"],
        "ledger_sha256": sha256_file(ledger_path),
        "ledger_bytes": ledger_path.stat().st_size,
        "selection": selection,
        "caps": {
            "max_images": MAX_IMAGES, "max_visual_tokens": MAX_VISUAL_TOKENS,
            "max_initial_pages": MAX_INITIAL_PAGES,
            "max_initial_visual_tokens": MAX_INITIAL_VISUAL_TOKENS,
            "max_text_tokens": MAX_TEXT_TOKENS,
            "interactive_result_headroom": INTERACTIVE_RESULT_HEADROOM,
            "retrieval_result_headroom": RETRIEVAL_RESULT_HEADROOM,
            "minimal_result_page_visual_tokens": MIN_RESULT_PAGE_VISUAL_TOKENS,
            "reserved_minimal_result_visual_tokens": RESERVED_RESULT_VISUAL_TOKENS,
            "max_retrieval_page_visual_tokens": MAX_RETRIEVAL_PAGE_VISUAL_TOKENS,
            "reserved_retrieval_visual_tokens": RESERVED_RETRIEVAL_VISUAL_TOKENS,
            "reserved_post_initial_visual_tokens": RESERVED_POST_INITIAL_VISUAL_TOKENS,
        },
        "inputs": evidence["input_identity"],
        "input_bundle_sha256": canonical_sha256(evidence["input_identity"]),
        "build_identity": _build_identity(auditor),
    }
    manifest_path = out_dir / "packet_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def build_game(
    game: str,
    rng: np.random.Generator | None = None,
    *,
    packet_root: Path = PACKET_ROOT,
    evidence: dict[str, Any] | None = None,
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Verify, stage, and atomically install one complete packet.

    ``rng`` is accepted for compatibility but deliberately ignored: the effective
    selection seed is derived from the blinded game id and is independent of build
    order.
    """
    del rng
    packet_root = validate_packet_root(packet_root)
    packet_root.mkdir(parents=True, exist_ok=True)
    evidence = load_evidence(game) if evidence is None else evidence
    auditor = ProcessorAuditor() if auditor is None else auditor
    bid = blind_id(game)
    target = packet_root / bid
    staging_parent = Path(tempfile.mkdtemp(prefix=f".{bid}.staging-", dir=packet_root))
    build_dir = staging_parent / bid
    ready = packet_root / f".{bid}.ready-{os.getpid()}"
    require(not ready.exists(), f"stale ready directory exists: {ready}")
    try:
        build_dir.mkdir()
        manifest = _build_into(game, build_dir, evidence, auditor)
        os.replace(build_dir, ready)
        shutil.rmtree(staging_parent)
        atomic_replace_dir(ready, target)
        return {"game": game, **manifest}
    except Exception:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
        if ready.exists():
            shutil.rmtree(ready)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=["ls20", "ft09", "m0r0", "sp80"])
    parser.add_argument("--packet-root", type=Path, default=PACKET_ROOT)
    parser.add_argument("--sealed-root", type=Path, default=SEALED_ROOT)
    parser.add_argument("--model", type=Path, default=MODEL)
    args = parser.parse_args()
    validate_packet_root(args.packet_root)
    validate_packet_root(args.sealed_root)
    auditor = ProcessorAuditor(args.model)
    blind_map = {}
    for game in args.games:
        manifest = build_game(game, packet_root=args.packet_root, auditor=auditor)
        blind_map[game] = manifest["blind_id"]
        totals = manifest["carrier_totals"]
        print(
            f"{game:5s} -> {manifest['blind_id']} pages {manifest['page_count']:2d} "
            f"raw {totals['raw']['visual_tokens']:,} overlay "
            f"{totals['overlay']['visual_tokens']:,}",
            flush=True,
        )
    atomic_write_text(args.sealed_root / "blind_map.json",
                      json.dumps(blind_map, indent=1, sort_keys=True))
    print(f"blind map -> {args.sealed_root / 'blind_map.json'} (sealed side)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
