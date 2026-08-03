#!/usr/bin/env python3
"""Build and verify the ES role-separated source-gold artifacts (custodian-side tool).

This is the pre-freeze CUSTODIAN process the governing note SS2.2 permits: it constructs
and validates BOTH custody sides, but publishes only aggregate pass/fail and the sealed
digest for R. Measurement-side modules must never import this file or read the sealed
path; the SS6.3 isolation tests enforce that once those modules exist.

Fail-closed checks (any failure aborts the build):
  * es_inventory self-consistency and partition shape (one session per role per game);
  * GIDSL gold provenance — the current source file must hash to what A0 pinned;
  * L_g two-source agreement (metadata baseline count == Level( constructions);
  * completion reproduction — trace-derived completions == sessions doc ==
    fidelity doc, and 123 in total across the 18 sessions;
  * replay fidelity under the accepted vc33 settled-frame erratum semantics, with the
    recorded first divergence re-verified to sit on an intermediate frame;
  * recording sha agreement between the fidelity artifact and es_inventory.

Run:
  .venv/bin/python agent/harness/es_sources/build.py            # build + self-verify
  .venv/bin/python agent/harness/es_sources/build.py --verify   # compare rebuild to disk
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_questions import canonical_payload, verify_against_disk  # noqa: E402
from es_questions import _canonical as _inventory_canonical  # noqa: E402
from es_questions import _sha256_bytes as _inventory_sha  # noqa: E402
from es_sources import (  # noqa: E402
    FIDELITY,
    FROZEN_GAMES,
    GIDSL_GOLD,
    INVENTORY,
    MANIFEST,
    R_SEALED_OUTPUT,
    SC_OUTPUT,
    SESSIONS,
    build_game_record,
    build_session_record,
    load_all_adapters,
    read_jsonl,
    rows_fingerprint,
    split_by_custody,
    write_gold,
    _sha256_file,
)


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


def build_records() -> tuple[list[dict[str, Any]], dict[str, str]]:
    adapters = load_all_adapters()
    inventory = json.loads(INVENTORY.read_text())
    partition = _inventory_partition(inventory)
    fidelity_doc = json.loads(FIDELITY.read_text())
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
            if session_fidelity["recording_sha256"] != assignment["recording_sha256"]:
                raise ValueError(
                    f"{env}:{guid}: recording sha disagrees between fidelity artifact and "
                    "es_inventory"
                )
            record = build_session_record(
                adapter,
                guid,
                assignment["role"],
                session_fidelity,
                sessions_levels[(env, guid)],
            )
            total_completions += len(record["completions"])
            records.append(record)

    if total_completions != 123:
        raise ValueError(f"completion total {total_completions} != expected 123")

    inputs = {
        "logs/es_inventory.json": inventory["fingerprint"],
        "logs/gi2_replay_fidelity.json": _sha256_file(FIDELITY),
        "logs/gi2_gidsl_gold_iteration.json": _sha256_file(GIDSL_GOLD),
        "logs/s2_replay_sessions.json": _sha256_file(SESSIONS),
        "gate_manifest.yaml": _sha256_file(MANIFEST),
    }
    return records, inputs


def verify(records: list[dict[str, Any]], inputs: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if not SC_OUTPUT.exists() or not R_SEALED_OUTPUT.exists():
        return [f"missing artifact: {SC_OUTPUT} or {R_SEALED_OUTPUT}"]
    sc_header, sc_rows = read_jsonl(SC_OUTPUT)
    sealed_header, sealed_rows = read_jsonl(R_SEALED_OUTPUT)
    expected_sc, expected_r = split_by_custody(records)

    if rows_fingerprint(sc_rows) != sc_header.get("rows_fingerprint"):
        problems.append("SC artifact is self-inconsistent (rows vs header fingerprint)")
    if rows_fingerprint(sc_rows) != rows_fingerprint(expected_sc):
        problems.append("SC rows differ from the deterministic rebuild")
    if sc_header.get("inputs") != dict(sorted(inputs.items())):
        problems.append("SC header inputs differ from the rebuild's inputs")

    sealed_sha = _sha256_file(R_SEALED_OUTPUT)
    if sealed_sha != sc_header.get("r_sealed_sha256"):
        problems.append("sealed R digest differs from the SC header pin")
    if rows_fingerprint(sealed_rows) != sealed_header.get("rows_fingerprint"):
        problems.append("sealed R artifact is self-inconsistent (rows vs header fingerprint)")
    if rows_fingerprint(sealed_rows) != rows_fingerprint(expected_r):
        problems.append("sealed R rows differ from the deterministic rebuild")
    if any(row.get("role") != "R" for row in sealed_rows):
        problems.append("sealed artifact contains a non-R row")
    if any(row.get("record") == "session" and row.get("role") == "R" for row in sc_rows):
        problems.append("SC artifact contains an R session row")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="rebuild and compare to disk")
    args = parser.parse_args()

    records, inputs = build_records()
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
        f"(aggregate: all fail-closed checks passed); sha256 "
        f"{digests['r_sealed_sha256'][:16]}..."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
