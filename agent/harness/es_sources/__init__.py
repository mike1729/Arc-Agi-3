#!/usr/bin/env python3
"""ES versioned source adapters — framework (increment 1).

Implements the frozen contract:
  * ``gate_manifest.yaml -> es`` (FROZEN 2026-08-03): ``corpus.reuse`` (adapters are thin
    versioned wrappers over the audited GI-2 estate), ``corpus.vc33_fidelity`` (the accepted
    2026-07-30 settled-frame erratum), and the L_g derivation rule
    (``es_value.trial.primary_endpoint``);
  * ``notes/qwen-evidence-sufficiency-screen.md`` SS2.2: per-game versioned adapters,
    role-separated immutable source-gold artifacts with source locations, input hashes, and
    independent replay assertions; fail-closed on completion reproduction and fidelity.

Increment 1 exposes and asserts: the authored completion program (GI-2 A0 GIDSL gold, with
source provenance re-verified), completion/non-completion truth per selected session (from
``gi2_traces`` streaming, cross-checked three ways), replay fidelity under the accepted
erratum semantics, the two-source authored level count L_g, and pinned digests of the
reused GI-2 fork tables. Per-state masks/properties/relations/lineage accessors and fork
wiring are increment 2 — they are not stubbed here.

Custody (SS2.2): S/C session records are written to ``logs/es_source_gold_sc.jsonl``
(readable by the ordinary experiment process). R session records are written only to
``logs/es_source_gold_r.sealed`` (mode 0600); the SC header carries that file's sha256 and
never its contents. The builder in ``es_sources/build.py`` acts as the pre-freeze CUSTODIAN
the note permits: it validates R rows but publishes only aggregate pass/fail and the sealed
digest. Measurement-side modules (runtime generator, packet builder, model runner) must
never import this package's build path or read the sealed file; the SS6.3 isolation tests
enforce that when those modules exist.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "agent/harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from gi2_traces import CORPUS, SESSIONS, iter_trace  # noqa: E402

FORMAT_VERSION = 1
FROZEN_GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")
EXPECTED_TOTAL_COMPLETIONS = 123

ENVIRONMENT_FILES = ROOT / "data/environment_files"
GIDSL_GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
FIDELITY = ROOT / "logs/gi2_replay_fidelity.json"
INVENTORY = ROOT / "logs/es_inventory.json"
MANIFEST = ROOT / "gate_manifest.yaml"
FORK_TABLES = (
    ROOT / "logs/gi2_fork_table.json",
    ROOT / "logs/gi2_ar_vc33_forks.json",
)
SC_OUTPUT = ROOT / "logs/es_source_gold_sc.jsonl"
R_SEALED_OUTPUT = ROOT / "logs/es_source_gold_r.sealed"


@dataclass(frozen=True)
class GameAdapter:
    """One versioned per-game adapter declaration. Behaviour is framework-generic;
    per-game modules exist to version the wrapper and carry game-specific flags."""

    env: str
    adapter_version: int
    settled_frame_erratum: bool = False  # vc33 only — accepted 2026-07-30


def load_adapter(env: str) -> GameAdapter:
    module = importlib.import_module(f"es_sources.{env}")
    adapter = getattr(module, "ADAPTER", None)
    if not isinstance(adapter, GameAdapter) or adapter.env != env:
        raise ValueError(f"es_sources.{env} does not declare a matching ADAPTER")
    return adapter


def load_all_adapters() -> dict[str, GameAdapter]:
    return {env: load_adapter(env) for env in FROZEN_GAMES}


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


def source_paths(env: str) -> tuple[Path, Path]:
    """The single hash-directory under data/environment_files/<env> holds source+metadata."""
    base = ENVIRONMENT_FILES / env
    subdirs = [p for p in base.iterdir() if p.is_dir()]
    if len(subdirs) != 1:
        raise ValueError(f"{env}: expected one hash directory under {base}, got {len(subdirs)}")
    return subdirs[0] / f"{env}.py", subdirs[0] / "metadata.json"


def verify_gold_provenance(env: str, gold_record: dict[str, Any], source_path: Path) -> str:
    """The A0 gold pinned the source it was authored from; fail closed on drift."""
    provenance = gold_record.get("provenance") or {}
    recorded = provenance.get("source_sha256")
    declared_path = provenance.get("source")
    current = _sha256_file(source_path)
    if declared_path != str(source_path.relative_to(ROOT)):
        raise ValueError(
            f"{env}: gold provenance path {declared_path!r} != adapter source "
            f"{source_path.relative_to(ROOT)}"
        )
    if recorded != current:
        raise ValueError(
            f"{env}: source file drifted since A0 gold was authored "
            f"(gold pins {recorded}, file is {current})"
        )
    return current


def authored_level_count(env: str, source_path: Path, metadata_path: Path) -> dict[str, int]:
    """Frozen L_g derivation: two independent mechanical reads that must agree."""
    metadata = json.loads(metadata_path.read_text())
    baselines = metadata.get("baseline_actions")
    if not isinstance(baselines, list) or not baselines:
        raise ValueError(f"{env}: metadata.json has no baseline_actions")
    from_metadata = len(baselines)
    from_source = len(re.findall(r"\bLevel\(", source_path.read_text()))
    if from_metadata != from_source:
        raise ValueError(
            f"{env}: L_g disagreement — metadata baseline_actions has {from_metadata} "
            f"levels, source constructs {from_source} Level(...) instances"
        )
    return {
        "from_metadata": from_metadata,
        "from_source_level_constructions": from_source,
        "value": from_metadata,
    }


def settled_frame_assertion(
    env: str,
    session_fidelity: dict[str, Any],
    *,
    erratum: bool,
    first_divergence_intermediate: bool | None,
) -> dict[str, Any]:
    """Erratum semantics (gate_manifest -> es -> corpus.vc33_fidelity).

    Byte-exact sessions pass outright. A divergent session passes only when the game
    carries the accepted settled-frame erratum AND its recorded first divergence has been
    re-verified to sit on an intermediate frame; the full all-divergences-intermediate
    claim rests on the pinned GI-2 forensics and the dated erratum acceptance.
    """
    frame_fidelity = bool(session_fidelity.get("frame_fidelity"))
    divergence = session_fidelity.get("first_frame_divergence")
    if frame_fidelity and divergence is None:
        return {"settled_frame_ok": True, "basis": "byte_exact_all_frames"}
    if not erratum:
        raise ValueError(
            f"{env}:{session_fidelity.get('guid')}: replay/recording divergence in a game "
            "without the settled-frame erratum — fidelity fails closed"
        )
    if first_divergence_intermediate is not True:
        raise ValueError(
            f"{env}:{session_fidelity.get('guid')}: recorded first divergence is not on an "
            "intermediate frame — settled-frame erratum does not cover it"
        )
    return {
        "settled_frame_ok": True,
        "basis": "accepted_2026-07-30_settled_frame_erratum",
        "first_divergence": divergence,
        "first_divergence_verified_intermediate": True,
        "full_assertion": "GI-2 forensics + dated erratum acceptance, pinned by input digests",
    }


def extract_completions(
    env: str, guid: str, divergence: tuple[int, int] | None
) -> tuple[list[dict[str, int]], bool | None]:
    """Stream one recording: completion events plus, when a recorded (step, frame_index)
    divergence is given, whether that frame is intermediate (never the settled, terminal,
    or next-level frame)."""
    path = CORPUS / env / f"{guid}.recording.jsonl"
    completions: list[dict[str, int]] = []
    divergence_intermediate: bool | None = None
    for step in iter_trace(path):
        if step.is_completion:
            completions.append({"step": step.index, "completed_level": step.levels_completed})
        if divergence is not None and step.index == divergence[0]:
            frame_index = divergence[1]
            divergence_intermediate = (
                0 <= frame_index < len(step.frames)
                and step.frames[frame_index].role == "intermediate"
            )
    return completions, divergence_intermediate


def build_game_record(adapter: GameAdapter, gold_record: dict[str, Any]) -> dict[str, Any]:
    source_path, metadata_path = source_paths(adapter.env)
    source_sha256 = verify_gold_provenance(adapter.env, gold_record, source_path)
    level_count = authored_level_count(adapter.env, source_path, metadata_path)
    return {
        "record": "game",
        "env": adapter.env,
        "adapter_version": adapter.adapter_version,
        "source": str(source_path.relative_to(ROOT)),
        "source_sha256": source_sha256,
        "metadata_path": str(metadata_path.relative_to(ROOT)),
        "metadata_sha256": _sha256_file(metadata_path),
        "authored_completion_program": {
            "gidsl_class": gold_record.get("class"),
            "skeleton": gold_record.get("skeleton"),
            "ast": gold_record.get("ast"),
            "vocabulary": gold_record.get("vocabulary"),
            "summary": gold_record.get("summary"),
            "provenance_verified": True,
        },
        "authored_level_count": level_count,
        "settled_frame_erratum": adapter.settled_frame_erratum,
        "fork_tables": {
            str(path.relative_to(ROOT)): _sha256_file(path) for path in FORK_TABLES
        },
    }


def build_session_record(
    adapter: GameAdapter,
    guid: str,
    role: str,
    session_fidelity: dict[str, Any],
    sessions_doc_levels: int,
) -> dict[str, Any]:
    divergence = session_fidelity.get("first_frame_divergence")
    divergence_ref = None
    if divergence is not None:
        divergence_ref = (int(divergence["step"]), int(divergence["detail"]["frame_index"]))
    completions, divergence_intermediate = extract_completions(
        adapter.env, guid, divergence_ref
    )
    fidelity_levels = int(session_fidelity.get("levels_completed", -1))
    reproduction = {
        "trace_completions": len(completions),
        "sessions_doc_levels_completed": sessions_doc_levels,
        "fidelity_doc_levels_completed": fidelity_levels,
        "ok": len(completions) == sessions_doc_levels == fidelity_levels,
    }
    if not reproduction["ok"]:
        raise ValueError(
            f"{adapter.env}:{guid}: completion reproduction failed — trace "
            f"{len(completions)}, sessions doc {sessions_doc_levels}, fidelity doc "
            f"{fidelity_levels}"
        )
    assertion = settled_frame_assertion(
        adapter.env,
        session_fidelity,
        erratum=adapter.settled_frame_erratum,
        first_divergence_intermediate=divergence_intermediate,
    )
    return {
        "record": "session",
        "env": adapter.env,
        "guid": guid,
        "role": role,
        "recording": str((CORPUS / adapter.env / f"{guid}.recording.jsonl").relative_to(ROOT)),
        "recording_sha256": session_fidelity["recording_sha256"],
        "completions": completions,
        "completion_reproduction": reproduction,
        "replay_assertion": assertion,
    }


def split_by_custody(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Game records and S/C session records are SC-side; R session records are sealed."""
    sc_rows, r_rows = [], []
    for row in records:
        if row["record"] == "session" and row["role"] == "R":
            r_rows.append(row)
        else:
            sc_rows.append(row)
    return sc_rows, r_rows


def rows_fingerprint(rows: list[dict[str, Any]]) -> str:
    return _sha256_bytes(_canonical(rows))


def write_gold(
    records: list[dict[str, Any]],
    inputs: dict[str, str],
    sc_path: Path = SC_OUTPUT,
    sealed_path: Path = R_SEALED_OUTPUT,
) -> dict[str, str]:
    sc_rows, r_rows = split_by_custody(records)
    if not r_rows:
        raise ValueError("no R rows — custody split would seal an empty artifact")

    sealed_header = {
        "record": "header",
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/es_sources/build.py",
        "custody": "R — sealed until the SS5.2 unseal event; do not read from measurement code",
        "rows_fingerprint": rows_fingerprint(r_rows),
    }
    sealed_lines = [json.dumps(sealed_header, sort_keys=True)]
    sealed_lines += [json.dumps(row, sort_keys=True) for row in r_rows]
    sealed_path.write_text("\n".join(sealed_lines) + "\n")
    sealed_path.chmod(0o600)
    sealed_sha256 = _sha256_file(sealed_path)

    sc_header = {
        "record": "header",
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/es_sources/build.py",
        "custody": "SC — readable by the ordinary experiment process",
        "inputs": dict(sorted(inputs.items())),
        "rows_fingerprint": rows_fingerprint(sc_rows),
        "r_sealed_path": (
            str(sealed_path.relative_to(ROOT))
            if sealed_path.is_relative_to(ROOT)
            else sealed_path.name
        ),
        "r_sealed_sha256": sealed_sha256,
        "r_row_count": len(r_rows),
    }
    sc_lines = [json.dumps(sc_header, sort_keys=True)]
    sc_lines += [json.dumps(row, sort_keys=True) for row in sc_rows]
    sc_path.write_text("\n".join(sc_lines) + "\n")
    return {
        "sc_rows_fingerprint": sc_header["rows_fingerprint"],
        "r_rows_fingerprint": sealed_header["rows_fingerprint"],
        "r_sealed_sha256": sealed_sha256,
    }


def read_jsonl(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = path.read_text().splitlines()
    header = json.loads(lines[0])
    if header.get("record") != "header":
        raise ValueError(f"{path}: first row is not a header")
    return header, [json.loads(line) for line in lines[1:]]
