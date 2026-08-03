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

This increment exposes and asserts: the authored completion program (GI-2 A0 GIDSL gold,
with source provenance re-verified); SOURCE-DERIVED completion and non-completion truth —
every selected session is replayed through the executing game source
(``es_sources.replay_check`` over ``gi2_replay.ReplayDriver``) and the engine's own level
transitions are compared per step against the recording, so a consistently mislabeled
recording fails closed; full role-aware fidelity — every frame compared, settled /
solved-terminal / next-level frames byte-equal always, intermediate divergence tolerated
only under the accepted vc33 erratum, recomputed fresh and cross-checked against the
pinned GI-2 fidelity and forensics artifacts; recording-byte authentication (the file
actually read is hashed and must equal every stored pin); the two-source authored level
count L_g; and pinned digests of the reused GI-2 fork tables. Per-state
masks/properties/relations/lineage accessors and fork wiring are the next increment —
they are not stubbed here.

Custody (SS2.2): S/C session records are written to ``logs/es_source_gold_sc.jsonl``
(readable by the ordinary experiment process). R session records are Fernet-ENCRYPTED into
``logs/es_source_gold_r.sealed``; the key is surfaced exactly once for the operator and is
never written to disk, so no same-UID process can read R gold without the logged SS5.2
unseal event. The SC header pins sha256(key), the plaintext rows fingerprint (verification
without decryption), and the ciphertext sha256 (tamper evidence). The builder in
``es_sources/build.py`` acts as the pre-freeze CUSTODIAN the note permits: it validates R
rows but publishes only aggregate pass/fail and digests. Measurement-side modules (runtime
generator, packet builder, model runner) must never import this package's build path; the
SS6.3 isolation tests enforce that when those modules exist.
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

from gi2_traces import CORPUS, SESSIONS  # noqa: E402

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


def authenticate_recording(
    env: str, guid: str, path: Path, pins: dict[str, str]
) -> str:
    """Hash the recording that is actually about to be read and require equality with
    every stored pin (fidelity artifact, es_inventory). A file that drifted from either
    pin fails closed even if its completion structure happens to be preserved."""
    current = _sha256_file(path)
    for source, pinned in sorted(pins.items()):
        if pinned != current:
            raise ValueError(
                f"{env}:{guid}: recording bytes ({current}) do not match the "
                f"{source} pin ({pinned})"
            )
    return current


def settled_frame_assertion(
    env: str,
    guid: str,
    replay_result: dict[str, Any],
    *,
    erratum: bool,
) -> dict[str, Any]:
    """Erratum semantics over the RECOMPUTED full-session comparison.

    Inputs come from ``replay_check.replay_session``: engine-vs-recording labels per step
    and every frame divergence with its role. Settled, solved-terminal, and next-level
    frames must be byte-equal always; intermediate divergence is tolerated only under the
    accepted vc33 settled-frame erratum. Nothing here trusts a first-divergence shortcut.
    """
    if replay_result["label_mismatches"]:
        raise ValueError(
            f"{env}:{guid}: engine-derived completion labels disagree with the recording "
            f"at {len(replay_result['label_mismatches'])} step(s) — completion truth is "
            "not source-reproduced"
        )
    if replay_result["engine_completions"] != replay_result["recorded_completions"]:
        raise ValueError(
            f"{env}:{guid}: engine completion events differ from recorded completion events"
        )
    if replay_result["structural"]:
        raise ValueError(
            f"{env}:{guid}: frame-count mismatch at "
            f"{len(replay_result['structural'])} step(s) — structural divergence is never "
            "covered by the erratum"
        )
    divergences = replay_result["divergences"]
    if not divergences:
        return {
            "settled_frame_ok": True,
            "basis": "byte_exact_all_frames_recomputed",
            "engine_verified_non_completions": replay_result[
                "engine_verified_non_completions"
            ],
        }
    if not erratum:
        raise ValueError(
            f"{env}:{guid}: {len(divergences)} frame divergence(s) in a game without the "
            "settled-frame erratum — fidelity fails closed"
        )
    non_intermediate = [d for d in divergences if d["role"] != "intermediate"]
    if non_intermediate:
        raise ValueError(
            f"{env}:{guid}: {len(non_intermediate)} divergence(s) on non-intermediate "
            f"frames (first: {non_intermediate[0]}) — the settled-frame erratum does not "
            "cover them"
        )
    return {
        "settled_frame_ok": True,
        "basis": "accepted_2026-07-30_settled_frame_erratum_recomputed_all_frames",
        "divergence_count": len(divergences),
        "divergent_steps": sorted({d["step"] for d in divergences}),
        "max_changed_cells": max(d["changed_cells"] for d in divergences),
        "all_divergences_intermediate": True,
        "engine_verified_non_completions": replay_result["engine_verified_non_completions"],
    }


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
    replay_result: dict[str, Any],
    recording_sha256: str,
    session_fidelity: dict[str, Any],
    sessions_doc_levels: int,
) -> dict[str, Any]:
    completions = replay_result["engine_completions"]
    fidelity_levels = int(session_fidelity.get("levels_completed", -1))
    reproduction = {
        "engine_completions": len(completions),
        "recorded_completions": len(replay_result["recorded_completions"]),
        "engine_verified_non_completions": replay_result["engine_verified_non_completions"],
        "sessions_doc_levels_completed": sessions_doc_levels,
        "fidelity_doc_levels_completed": fidelity_levels,
        "ok": len(completions) == sessions_doc_levels == fidelity_levels,
    }
    if not reproduction["ok"]:
        raise ValueError(
            f"{adapter.env}:{guid}: completion cross-check failed — engine "
            f"{len(completions)}, sessions doc {sessions_doc_levels}, fidelity doc "
            f"{fidelity_levels}"
        )
    assertion = settled_frame_assertion(
        adapter.env,
        guid,
        replay_result,
        erratum=adapter.settled_frame_erratum,
    )
    recorded_first = session_fidelity.get("first_frame_divergence")
    if recorded_first is not None:
        expected = (int(recorded_first["step"]), int(recorded_first["detail"]["frame_index"]))
        recomputed = [
            (d["step"], d["frame_index"]) for d in replay_result["divergences"]
        ]
        if not recomputed or min(recomputed) != expected:
            raise ValueError(
                f"{adapter.env}:{guid}: recomputed first divergence "
                f"{min(recomputed) if recomputed else None} does not match the fidelity "
                f"artifact's {expected} — reused assertion drifted"
            )
    elif replay_result["divergences"]:
        raise ValueError(
            f"{adapter.env}:{guid}: recomputation found divergences where the fidelity "
            "artifact recorded none — reused assertion drifted"
        )
    return {
        "record": "session",
        "env": adapter.env,
        "guid": guid,
        "role": role,
        "recording": str((CORPUS / adapter.env / f"{guid}.recording.jsonl").relative_to(ROOT)),
        "recording_sha256": recording_sha256,
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
    key: bytes | None = None,
) -> dict[str, Any]:
    """Write the SC artifact and the ENCRYPTED sealed R artifact.

    Custody is enforced by knowledge, not file mode: R rows are Fernet-encrypted and the
    key is returned to the caller exactly once for the OPERATOR to store — it is never
    written to disk by this package, so no same-UID process can decrypt the sealed file
    without the logged unseal event supplying the key. The SC header pins sha256(key) so
    the unseal tool can verify the supplied key, the plaintext rows fingerprint so
    ``--verify`` can compare a source rebuild without decrypting, and the ciphertext
    sha256 so tampering is detectable.
    """
    from cryptography.fernet import Fernet

    sc_rows, r_rows = split_by_custody(records)
    if not r_rows:
        raise ValueError("no R rows — custody split would seal an empty artifact")

    if key is None:
        key = Fernet.generate_key()
    plaintext = "\n".join(json.dumps(row, sort_keys=True) for row in r_rows) + "\n"
    ciphertext = Fernet(key).encrypt(plaintext.encode())
    sealed_path.write_bytes(ciphertext)
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
        "r_plaintext_rows_fingerprint": rows_fingerprint(r_rows),
        "r_key_sha256": _sha256_bytes(key),
        "r_row_count": len(r_rows),
        "r_custody": "Fernet-encrypted; key held by the operator only, never on disk; "
        "unseal is the SS5.2 logged event",
    }
    sc_lines = [json.dumps(sc_header, sort_keys=True)]
    sc_lines += [json.dumps(row, sort_keys=True) for row in sc_rows]
    sc_path.write_text("\n".join(sc_lines) + "\n")
    return {
        "sc_rows_fingerprint": sc_header["rows_fingerprint"],
        "r_plaintext_rows_fingerprint": sc_header["r_plaintext_rows_fingerprint"],
        "r_sealed_sha256": sealed_sha256,
        "r_key": key,
    }


def read_jsonl(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = path.read_text().splitlines()
    header = json.loads(lines[0])
    if header.get("record") != "header":
        raise ValueError(f"{path}: first row is not a header")
    return header, [json.loads(line) for line in lines[1:]]
