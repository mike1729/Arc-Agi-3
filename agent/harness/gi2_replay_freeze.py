#!/usr/bin/env python3
"""Build and verify the GI-2 A0 replay-environment freeze artifact.

The artifact pins everything needed before source replay becomes measurement-bearing in A1:
the six game sources and metadata, the selected human action streams, requested seed behavior,
the installed distribution versions, and the engine files that implement reset and local
loading.  It deliberately reads distribution metadata instead of importing ``arc_agi``:
imports pull in rendering dependencies and ``arcengine.__version__`` is known to misreport.

Run:
  .venv/bin/python agent/harness/gi2_replay_freeze.py --build
  .venv/bin/python agent/harness/gi2_replay_freeze.py --verify
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

from gi2_traces import (
    CORPUS,
    DRAW,
    OUTPUT as FRAME_VALIDATION,
    ROOT,
    SESSIONS,
    normalize_action_id,
    selected_sessions,
)

OUTPUT = ROOT / "logs/gi2_replay_environment_freeze.json"
ENVIRONMENTS = ROOT / "data/environment_files"
FORMAT_VERSION = 1
REQUESTED_SEED = 0
EXPECTED_DISTRIBUTIONS = {"arcengine": "0.9.3", "arc-agi": "0.9.9"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _class_seed_contract(source: Path) -> tuple[str, bool]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    game_classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "ARCBaseGame" for base in node.bases)
    ]
    if len(game_classes) != 1:
        raise ValueError(f"{source}: expected exactly one ARCBaseGame subclass")
    cls = game_classes[0]
    init = next(
        (
            node for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        ),
        None,
    )
    if init is None:
        return cls.name, False
    signature_names = {
        arg.arg for arg in (init.args.posonlyargs + init.args.args + init.args.kwonlyargs)
    }
    return cls.name, "seed" in signature_names


def _action_stream(path: Path) -> tuple[str, int, int]:
    actions = []
    reset_count = 0
    action_rows = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            data = json.loads(line).get("data")
            if not isinstance(data, dict) or "frame" not in data:
                continue
            action_rows += 1
            action = data.get("action_input") or {}
            action_id = normalize_action_id(action.get("id"))
            action_data = dict(action.get("data") or {})
            action_data.pop("game_id", None)
            actions.append({"id": action_id, "data": action_data})
            if action_id == 0:
                reset_count += 1
    return hashlib.sha256(_canonical(actions)).hexdigest(), action_rows, reset_count


def _distribution_record(name: str) -> dict[str, Any]:
    dist = distribution(name)
    package = "arcengine" if name == "arcengine" else "arc_agi"
    package_root = Path(dist.locate_file(package))
    files = (
        ["base_game.py"]
        if name == "arcengine"
        else ["base.py", "local_wrapper.py", "wrapper.py"]
    )
    return {
        "name": name,
        "version": dist.version,
        "python_requires": dist.metadata.get("Requires-Python"),
        "implementation_files": {
            f"{package}/{filename}": _sha256(package_root / filename)
            for filename in files
        },
    }


def build_freeze() -> dict[str, Any]:
    draw_doc = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    games = []
    for env in draw_doc["iteration"]:
        versions = sorted(path for path in (ENVIRONMENTS / env).iterdir() if path.is_dir())
        if len(versions) != 1:
            raise ValueError(f"{env}: expected exactly one environment version")
        version_dir = versions[0]
        source = version_dir / f"{env}.py"
        metadata = version_dir / "metadata.json"
        if not source.is_file() or not metadata.is_file():
            raise ValueError(f"{env}: source or metadata missing")
        metadata_doc = json.loads(metadata.read_text())
        class_name, accepts_seed = _class_seed_contract(source)
        action_streams = []
        for selected in selected_sessions(env, sessions_doc, draw_doc):
            recording = CORPUS / env / f"{selected['guid']}.recording.jsonl"
            digest, action_rows, reset_count = _action_stream(recording)
            action_streams.append(
                {
                    "guid": selected["guid"],
                    "rank": selected["rank"],
                    "actions_sha256": digest,
                    "action_rows": action_rows,
                    "reset_actions": reset_count,
                }
            )
        games.append(
            {
                "env": env,
                "game_id": metadata_doc.get("game_id"),
                "class_name": class_name,
                "source": str(source.relative_to(ROOT)),
                "source_sha256": _sha256(source),
                "metadata": str(metadata.relative_to(ROOT)),
                "metadata_sha256": _sha256(metadata),
                "seed": {
                    "requested": REQUESTED_SEED,
                    "constructor_accepts_seed": accepts_seed,
                    "effective": REQUESTED_SEED if accepts_seed else None,
                    "reason": (
                        "LocalEnvironmentWrapper passes seed only when the game constructor "
                        "declares a seed parameter"
                    ),
                },
                "action_streams": action_streams,
            }
        )
    distributions = {
        name: _distribution_record(name) for name in EXPECTED_DISTRIBUTIONS
    }
    return {
        "format_version": FORMAT_VERSION,
        "status": "a0_frozen",
        "scope": "iteration",
        "inputs": {
            "draw": str(DRAW.relative_to(ROOT)),
            "draw_sha256": _sha256(DRAW),
            "sessions": str(SESSIONS.relative_to(ROOT)),
            "sessions_sha256": _sha256(SESSIONS),
            "frame_validation": str(FRAME_VALIDATION.relative_to(ROOT)),
            "frame_validation_sha256": _sha256(FRAME_VALIDATION),
        },
        "local_replay": {
            "operation_mode": "offline",
            "requested_seed": REQUESTED_SEED,
            "only_reset_levels": os.getenv("ONLY_RESET_LEVELS"),
            "reset_semantics": {
                "initial_or_after_win": "full_reset",
                "after_action": "level_reset",
                "only_reset_levels_true": "level_reset unless state is WIN",
                "action_count": "RESET does not increment action_count",
            },
        },
        "distributions": distributions,
        "games": games,
    }


def verify_freeze(document: Any) -> list[str]:
    problems = []
    if not isinstance(document, dict):
        return ["artifact: expected an object"]
    if document.get("format_version") != FORMAT_VERSION:
        problems.append("artifact.format_version: unexpected")
    if document.get("status") != "a0_frozen":
        problems.append("artifact.status: expected a0_frozen")
    local = document.get("local_replay")
    if not isinstance(local, dict):
        problems.append("artifact.local_replay: expected an object")
    else:
        if local.get("requested_seed") != REQUESTED_SEED:
            problems.append("artifact.local_replay.requested_seed: drift")
        if local.get("only_reset_levels") != os.getenv("ONLY_RESET_LEVELS"):
            problems.append("ONLY_RESET_LEVELS changed since freeze")
    inputs = document.get("inputs")
    for name, path in (
        ("draw", DRAW),
        ("sessions", SESSIONS),
        ("frame_validation", FRAME_VALIDATION),
    ):
        if not path.is_file():
            problems.append(f"{name}: missing {path}")
        elif not isinstance(inputs, dict) or inputs.get(f"{name}_sha256") != _sha256(path):
            problems.append(f"artifact.inputs.{name}_sha256: input drift")
    dist_records = document.get("distributions")
    if not isinstance(dist_records, dict):
        problems.append("artifact.distributions: expected an object")
    else:
        for name, expected_version in EXPECTED_DISTRIBUTIONS.items():
            try:
                current = _distribution_record(name)
            except (PackageNotFoundError, OSError, UnicodeError) as exc:
                problems.append(f"{name}: cannot inspect distribution: {exc}")
                continue
            frozen = dist_records.get(name)
            if current["version"] != expected_version:
                problems.append(
                    f"{name}: expected distribution {expected_version}, got {current['version']}"
                )
            if frozen != current:
                problems.append(f"{name}: distribution or implementation file drift")
    games = document.get("games")
    if not isinstance(games, list) or len(games) != 6:
        problems.append("artifact.games: expected six rows")
    else:
        for game in games:
            if not isinstance(game, dict):
                problems.append("artifact.games: invalid row")
                continue
            env = game.get("env")
            for key in ("source", "metadata"):
                path = ROOT / str(game.get(key, ""))
                if not path.is_file():
                    problems.append(f"{env}: {key} missing")
                elif game.get(f"{key}_sha256") != _sha256(path):
                    problems.append(f"{env}: {key} digest drift")
            streams = game.get("action_streams")
            if not isinstance(streams, list) or len(streams) != 3:
                problems.append(f"{env}: expected three action streams")
                continue
            for stream in streams:
                if not isinstance(stream, dict):
                    problems.append(f"{env}: invalid action stream")
                    continue
                recording = CORPUS / str(env) / f"{stream.get('guid')}.recording.jsonl"
                if not recording.is_file():
                    problems.append(f"{env}/{stream.get('guid')}: recording missing")
                    continue
                digest, rows, resets = _action_stream(recording)
                if (
                    stream.get("actions_sha256") != digest
                    or stream.get("action_rows") != rows
                    or stream.get("reset_actions") != resets
                ):
                    problems.append(f"{env}/{stream.get('guid')}: action stream drift")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.build:
        document = build_freeze()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        print(
            "GI-2 replay environment frozen — "
            f"{len(document['games'])} games, "
            f"{sum(len(game['action_streams']) for game in document['games'])} action streams"
        )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            document = json.loads(OUTPUT.read_text())
            problems = verify_freeze(document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print(f"GI-2 replay freeze FAILED — {len(problems)} problem(s)")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 replay environment freeze OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
