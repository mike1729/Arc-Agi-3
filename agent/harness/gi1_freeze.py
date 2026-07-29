#!/usr/bin/env python3
"""Create and verify the GI-1 implementation freeze.

The measured 27B pass is allowed to run only when this manifest exactly matches the
implementation on disk.  The freeze covers the prompt renderer, digest, retrieval contract,
shared predicate schema, strict output parser, and mechanical scorer.  The experiment runner
is deliberately outside the scientific treatment freeze: it may receive operational fixes,
but it cannot change any model-facing or scoring behavior without changing one of the frozen
dependencies below.

Creation is an explicit operator action performed after MoE-only development:

    .venv/bin/python agent/harness/gi1_freeze.py --write

Every measured invocation uses ``--verify`` semantics through ``require_frozen()``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from gi1_predicate_gold import CURRENT_STATUS, schema_fingerprint
from gi1_retrieval import INDEX_CACHE, SPEC, validate_index_artifact

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/gi1_implementation_freeze.json"
FORMAT_VERSION = 1
FROZEN_STATUS = "frozen"
FROZEN_GOLD_STATUS = "frozen"

FROZEN_FILES = (
    "agent/harness/gi1_render.py",
    "agent/harness/gi1_digest.py",
    "agent/harness/gi1_retrieval.py",
    "agent/harness/gi1_predicate_schema.py",
    "agent/harness/gi1_output_parser.py",
    "agent/harness/gi1_k4_scorer.py",
)

# These are part of the measured treatment.  The runner sends exactly this mapping and refuses
# caller overrides in measured mode.
MEASURED_GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "seed": 20260729,
    "max_tokens": 2048,
    "chat_template_kwargs": {"enable_thinking": False},
}

MEASUREMENT_MODEL_BASENAME = "Qwen3.6-27B-8bit"
DEVELOPMENT_MODEL_BASENAME = "Qwen3.6-35B-A3B-4bit"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def build_manifest(root: Path = ROOT) -> dict[str, Any]:
    if CURRENT_STATUS != FROZEN_GOLD_STATUS:
        raise ValueError(
            f"predicate gold status is {CURRENT_STATUS!r}; set it to "
            f"{FROZEN_GOLD_STATUS!r} only after MoE development is complete"
        )
    files = {}
    for relative in FROZEN_FILES:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"frozen input missing: {relative}")
        files[relative] = _sha256(path)
    try:
        index_relative = str(INDEX_CACHE.relative_to(root))
    except ValueError as exc:
        raise ValueError(f"retrieval index is outside the repository: {INDEX_CACHE}") from exc
    if not INDEX_CACHE.is_file():
        raise ValueError(
            f"frozen input missing: {index_relative}; build the retrieval index first"
        )
    try:
        index_artifact = json.loads(INDEX_CACHE.read_text())
        draw = json.loads((root / "logs/gi1_game_draw.json").read_text())
        library_games = sorted(draw["iteration"] + draw["one_shot"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"cannot validate retrieval index for freeze: {exc}") from exc
    index_problems = validate_index_artifact(index_artifact, library_games)
    if index_problems:
        raise ValueError(
            "retrieval index is not frozen-compatible: " + "; ".join(index_problems)
        )
    contract = {
        "files": files,
        "retrieval_index": {
            "path": index_relative,
            "sha256": _sha256(INDEX_CACHE),
        },
        "schema_fingerprint": schema_fingerprint(),
        "retrieval_spec": json.loads(json.dumps(SPEC)),
        "measured_generation": json.loads(json.dumps(MEASURED_GENERATION)),
        "measurement_model_basename": MEASUREMENT_MODEL_BASENAME,
        "development_model_basename": DEVELOPMENT_MODEL_BASENAME,
    }
    return {
        "format_version": FORMAT_VERSION,
        "status": FROZEN_STATUS,
        "scope": "gi1_iteration_pre_measurement",
        "contract": contract,
        "contract_fingerprint": hashlib.sha256(_canonical(contract)).hexdigest(),
    }


def verify_manifest(
    path: Path = OUT,
    *,
    root: Path = ROOT,
) -> list[str]:
    try:
        actual = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"cannot read implementation freeze {path}: {exc}"]
    try:
        expected = build_manifest(root)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    if actual == expected:
        return []
    problems = []
    if not isinstance(actual, dict):
        return ["implementation freeze must be a JSON object"]
    for key in ("format_version", "status", "scope", "contract_fingerprint"):
        if actual.get(key) != expected[key]:
            problems.append(
                f"{key}: artifact {actual.get(key)!r} != current {expected[key]!r}"
            )
    actual_contract = actual.get("contract")
    if not isinstance(actual_contract, dict):
        problems.append("contract: expected an object")
        return problems
    actual_contract_fingerprint = hashlib.sha256(_canonical(actual_contract)).hexdigest()
    if actual.get("contract_fingerprint") != actual_contract_fingerprint:
        problems.append("contract_fingerprint: does not digest the artifact contract")
    expected_contract = expected["contract"]
    actual_files = actual_contract.get("files")
    if not isinstance(actual_files, dict):
        problems.append("contract.files: expected an object")
    else:
        for relative in sorted(set(actual_files) | set(expected_contract["files"])):
            if actual_files.get(relative) != expected_contract["files"].get(relative):
                problems.append(f"frozen file drift: {relative}")
    for key in (
        "retrieval_index",
        "schema_fingerprint",
        "retrieval_spec",
        "measured_generation",
        "measurement_model_basename",
        "development_model_basename",
    ):
        if actual_contract.get(key) != expected_contract[key]:
            problems.append(f"contract drift: {key}")
    return problems or ["implementation freeze differs from current contract"]


def require_frozen(path: Path = OUT) -> dict[str, Any]:
    problems = verify_manifest(path)
    if problems:
        raise ValueError("GI-1 implementation is not frozen: " + "; ".join(problems))
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if args.write:
        manifest = build_manifest()
        args.output.write_text(json.dumps(manifest, indent=2) + "\n")
        print(
            f"wrote {args.output.relative_to(ROOT)} — "
            f"{manifest['contract_fingerprint'][:16]}"
        )
        return 0
    problems = verify_manifest(args.output)
    if problems:
        print(f"GI-1 implementation freeze FAILED — {len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("GI-1 implementation freeze OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
