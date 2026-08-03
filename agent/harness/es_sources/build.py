#!/usr/bin/env python3
"""Build and verify the ES role-separated source-gold artifacts (custodian-side tool).

This is the pre-freeze CUSTODIAN process the governing note SS2.2 permits: it constructs
and validates BOTH custody sides, but publishes only aggregate pass/fail and digests for
R. Measurement-side modules must never import this file; the SS6.3 isolation tests
enforce that once those modules exist.

Fail-closed checks (any failure aborts the build):
  * es_inventory self-consistency and partition shape (one session per role per game);
  * recording-byte authentication — the file actually read is hashed and must equal the
    fidelity-artifact pin AND the es_inventory pin;
  * GIDSL gold provenance — the current source file must hash to what A0 pinned;
  * L_g two-source agreement (metadata baseline count == Level( constructions);
  * SOURCE-DERIVED completion truth — each session is replayed through the executing game
    source and engine level transitions must match the recording at every step (123
    completions total), with engine-verified non-completions counted;
  * full role-aware fidelity, recomputed over every frame: settled / solved-terminal /
    next-level frames byte-equal always; intermediate divergence only under the accepted
    vc33 erratum; recomputed divergences must match the pinned GI-2 fidelity artifact
    (first divergence) and forensics artifact (complete inventory,
    all_divergence_intermediate_only).

Custody: R rows are Fernet-encrypted; the key is printed exactly once for the operator
and never written to disk.

Run:
  .venv/bin/python agent/harness/es_sources/build.py --jobs 6          # build + verify
  .venv/bin/python agent/harness/es_sources/build.py --verify --jobs 6 # compare to disk
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_questions import canonical_payload  # noqa: E402
from es_questions import _canonical as _inventory_canonical  # noqa: E402
from es_questions import _sha256_bytes as _inventory_sha  # noqa: E402
from es_sources import (  # noqa: E402
    CORPUS,
    FIDELITY,
    FROZEN_GAMES,
    GIDSL_GOLD,
    INVENTORY,
    MANIFEST,
    R_SEALED_OUTPUT,
    SC_OUTPUT,
    SESSIONS,
    authenticate_recording,
    build_game_record,
    build_session_record,
    load_all_adapters,
    read_jsonl,
    rows_fingerprint,
    split_by_custody,
    write_gold,
    _sha256_file,
)

FORENSICS = HARNESS.parents[1] / "logs/gi2_grounding_forensics.json"


def _inventory_partition(inventory: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """env -> guid -> {role, recording_sha256}; validates shape and self-consistency."""
    recomputed = _inventory_sha(_inventory_canonical(canonical_payload(inventory)))
    if recomputed != inventory.get("fingerprint"):
        raise ValueError("es_inventory.json is self-inconsistent — rebuild it first")
    partition: dict[str, dict[str, dict[str, Any]]] = {}
    for env in FROZEN_GAMES:
        sessions = inventory["partition"][env]["sessions"]
        roles = sorted(s["role"] for s in sessions)
        if roles != ["C", "R", "S"]:
            raise ValueError(f"{env}: partition roles are {roles}, expected one each of S/C/R")
        partition[env] = {
            s["guid"]: {"role": s["role"], "recording_sha256": s["recording_sha256"]}
            for s in sessions
        }
    return partition


def _replay_worker(job: tuple[str, str]) -> dict[str, Any]:
    """Runs in a worker process: replay one session through the game source."""
    from es_sources.replay_check import replay_session

    env, guid = job
    return replay_session(env, guid)


def _forensics_crosscheck(env: str, guid: str, replay_result: dict[str, Any],
                          forensics_doc: dict[str, Any]) -> None:
    """The reused GI-2 forensics assertion must agree with the fresh recomputation."""
    if env != "vc33":
        return
    entries = {e["guid"]: e for e in forensics_doc.get("vc33_divergence", [])}
    entry = entries.get(guid)
    if entry is None:
        raise ValueError(f"vc33:{guid}: session absent from the forensics artifact")
    if entry.get("all_divergence_intermediate_only") is not True:
        raise ValueError(f"vc33:{guid}: forensics does not assert intermediate-only")
    pinned = {
        (int(row["step"]), int(frame["frame_index"]))
        for row in entry.get("divergent_rows", [])
        for frame in row.get("divergent_frames", [])
    }
    recomputed = {
        (d["step"], d["frame_index"]) for d in replay_result["divergences"]
    }
    if pinned != recomputed:
        raise ValueError(
            f"vc33:{guid}: recomputed divergence inventory ({len(recomputed)} frames) "
            f"differs from the pinned forensics inventory ({len(pinned)} frames) — "
            "reused assertion drifted"
        )


def build_records(jobs: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    adapters = load_all_adapters()
    inventory = json.loads(INVENTORY.read_text())
    partition = _inventory_partition(inventory)
    fidelity_doc = json.loads(FIDELITY.read_text())
    forensics_doc = json.loads(FORENSICS.read_text())
    gold_doc = json.loads(GIDSL_GOLD.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())

    gold_by_env = {record["env"]: record for record in gold_doc["records"]}
    if sorted(gold_by_env) != sorted(FROZEN_GAMES):
        raise ValueError(f"GIDSL gold covers {sorted(gold_by_env)}, expected {FROZEN_GAMES}")
    fidelity_by_env = {game["env"]: game for game in fidelity_doc["games"]}
    sessions_levels = {
        (row["env"], row["guid"]): int(row["levels_completed"])
        for row in sessions_doc["sessions"]
    }

    jobs_list = [
        (env, guid) for env in FROZEN_GAMES for guid in sorted(partition[env])
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        replay_results = {
            (result["env"], result["guid"]): result
            for result in pool.map(_replay_worker, jobs_list)
        }

    records: list[dict[str, Any]] = []
    total_completions = 0
    for env in FROZEN_GAMES:
        adapter = adapters[env]
        records.append(build_game_record(adapter, gold_by_env[env]))
        fidelity_sessions = {s["guid"]: s for s in fidelity_by_env[env]["sessions"]}
        for guid, assignment in sorted(partition[env].items()):
            session_fidelity = fidelity_sessions.get(guid)
            if session_fidelity is None:
                raise ValueError(f"{env}:{guid}: session absent from the fidelity artifact")
            recording_path = CORPUS / env / f"{guid}.recording.jsonl"
            recording_sha256 = authenticate_recording(
                env,
                guid,
                recording_path,
                {
                    "fidelity-artifact": session_fidelity["recording_sha256"],
                    "es_inventory": assignment["recording_sha256"],
                },
            )
            replay_result = replay_results[(env, guid)]
            _forensics_crosscheck(env, guid, replay_result, forensics_doc)
            record = build_session_record(
                adapter,
                guid,
                assignment["role"],
                replay_result,
                recording_sha256,
                session_fidelity,
                sessions_levels[(env, guid)],
            )
            total_completions += len(record["completions"])
            records.append(record)

    if total_completions != 123:
        raise ValueError(f"engine-derived completion total {total_completions} != 123")

    inputs = {
        "logs/es_inventory.json": inventory["fingerprint"],
        "logs/gi2_replay_fidelity.json": _sha256_file(FIDELITY),
        "logs/gi2_grounding_forensics.json": _sha256_file(FORENSICS),
        "logs/gi2_gidsl_gold_iteration.json": _sha256_file(GIDSL_GOLD),
        "logs/s2_replay_sessions.json": _sha256_file(SESSIONS),
        "gate_manifest.yaml": _sha256_file(MANIFEST),
    }
    return records, inputs


def verify(records: list[dict[str, Any]], inputs: dict[str, str]) -> list[str]:
    """Full-content verification without decrypting the sealed side."""
    problems: list[str] = []
    if not SC_OUTPUT.exists() or not R_SEALED_OUTPUT.exists():
        return [f"missing artifact: {SC_OUTPUT} or {R_SEALED_OUTPUT}"]
    sc_header, sc_rows = read_jsonl(SC_OUTPUT)
    expected_sc, expected_r = split_by_custody(records)

    if rows_fingerprint(sc_rows) != sc_header.get("rows_fingerprint"):
        problems.append("SC artifact is self-inconsistent (rows vs header fingerprint)")
    if rows_fingerprint(sc_rows) != rows_fingerprint(expected_sc):
        problems.append("SC rows differ from the deterministic rebuild")
    if sc_header.get("inputs") != dict(sorted(inputs.items())):
        problems.append("SC header inputs differ from the rebuild's inputs")

    if _sha256_file(R_SEALED_OUTPUT) != sc_header.get("r_sealed_sha256"):
        problems.append("sealed R ciphertext digest differs from the SC header pin")
    if rows_fingerprint(expected_r) != sc_header.get("r_plaintext_rows_fingerprint"):
        problems.append(
            "rebuilt R rows differ from the pinned plaintext fingerprint "
            "(verified WITHOUT decryption)"
        )
    if sc_header.get("r_row_count") != len(expected_r):
        problems.append("R row count differs from the rebuild")
    if not sc_header.get("r_key_sha256"):
        problems.append("SC header does not pin the custody key digest")
    if any(row.get("record") == "session" and row.get("role") == "R" for row in sc_rows):
        problems.append("SC artifact contains an R session row")
    try:
        json.loads(R_SEALED_OUTPUT.read_bytes().split(b"\n", 1)[0])
        problems.append("sealed R artifact parses as JSON — it is not encrypted")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="rebuild and compare to disk")
    parser.add_argument("--jobs", type=int, default=6, help="parallel replay workers")
    args = parser.parse_args()

    records, inputs = build_records(args.jobs)
    if args.verify:
        problems = verify(records, inputs)
        if problems:
            for problem in problems:
                print(f"FAIL: {problem}")
            return 1
        print(f"OK: {SC_OUTPUT.name} and {R_SEALED_OUTPUT.name} verified")
        return 0

    digests = write_gold(records, inputs)
    problems = verify(records, inputs)
    if problems:
        for problem in problems:
            print(f"FAIL (post-write self-verify): {problem}")
        return 1
    sc_rows, r_rows = split_by_custody(records)
    games = sum(1 for row in sc_rows if row["record"] == "game")
    print(
        f"wrote {SC_OUTPUT.relative_to(HARNESS.parents[1])}: {games} game records + "
        f"{len(sc_rows) - games} S/C session records; fingerprint "
        f"{digests['sc_rows_fingerprint'][:16]}..."
    )
    print(
        f"sealed {R_SEALED_OUTPUT.relative_to(HARNESS.parents[1])}: {len(r_rows)} R rows "
        f"encrypted (aggregate: all fail-closed checks passed); ciphertext sha256 "
        f"{digests['r_sealed_sha256'][:16]}..."
    )
    print(
        "\nR CUSTODY KEY (shown once, never written to disk — store it now; the SS5.2 "
        "unseal event will require it):\n  "
        + digests["r_key"].decode()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
