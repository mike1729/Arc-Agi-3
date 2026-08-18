"""Resource guards and append-only ledgers (slice-4 protocol revision 4).

Three resources are counted separately and never conflated:

  1. local model work        -> logs/ledgers/local_generations.jsonl
  2. remote Kaggle compute   -> logs/ledgers/remote_compute.jsonl
  3. competition evaluations -> logs/ledgers/competition_evaluations.jsonl

`KAGGLE_EVAL_BUDGET = 0` is frozen for the scientific protocol through final
grading.  Every slice-4 command path must call `enforce_offline_scientific_run`
at entry: it fails closed on any submission-capable mode, environment flag, or
argv token, with no card-based override inside slice 4.  A later actor-system
evaluation uses a separate, operator-approved submission card validated by
`validate_submission_card` — outside this protocol.

Ledger records are hash-chained (`prev_sha256` -> `record_sha256`) so silent
edits break the chain; appends are the only legal operation.
"""

from __future__ import annotations

import datetime as _dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER_ROOT = ROOT / "logs/ledgers"

FORMAT_VERSION = 1

# Frozen for slice-4 revision 4: the scientific run is local/offline and may not
# spend a hidden-test submission to tune a carrier, rescue a control, or
# interpret Stage A.
KAGGLE_EVAL_BUDGET = 0

# Verified competition allowance (docs/CLAUDE.md): ceiling, not target.
COMPETITION_DAILY_LIMIT = 1
COMPETITION_FINAL_SELECTIONS = 2

_SUBMISSION_ENV_FLAGS = (
    "TRUE_SUBMISSION",
    "KAGGLE_RUN_AS_SUBMISSION",
    "KAGGLE_SUBMIT",
    "SUBMIT_TO_KAGGLE",
)
_SUBMISSION_ARGV_TOKENS = (
    "--submit", "--submission", "--true-submission", "competitions", "submissions",
)

LEDGERS = {
    "local_generations": {
        "required": {"module", "tag", "purpose", "model", "seed", "max_tokens"},
        "optional": {"generation_tokens", "wall_seconds", "outcome", "run_dir"},
    },
    "remote_compute": {
        "required": {"kind", "purpose", "approver", "gpu_hours_estimate"},
        "optional": {"kernel_id", "gpu_hours_actual", "true_submission", "notes"},
    },
    "competition_evaluations": {
        "required": {"status", "competition", "candidate_commit", "approver"},
        "optional": {
            "utc_attempt", "command", "payload_sha256", "kernel_sha256",
            "dataset_sha256", "kaggle_id", "public_score", "hypothesis",
            "quota_before", "quota_after", "decision_rule", "notes",
        },
    },
}

_COMPETITION_STATUSES = {
    "PREPARED", "ACCEPTED", "SCORED", "REJECTED_BEFORE_ACCEPTANCE", "AMBIGUOUS",
}


class SubmissionCapabilityRefused(RuntimeError):
    """A slice-4 command path was invoked with submission capability present."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ledger_path(name: str) -> Path:
    require(name in LEDGERS, f"unknown ledger {name!r}")
    return LEDGER_ROOT / f"{name}.jsonl"


def read_ledger(name: str) -> list[dict[str, Any]]:
    path = ledger_path(name)
    if not path.is_file():
        return []
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    verify_chain(name, records)
    return records


def verify_chain(name: str, records: list[dict[str, Any]]) -> None:
    prev = None
    for index, record in enumerate(records):
        require(record.get("prev_sha256") == prev,
                f"{name} ledger chain broken at record {index}")
        body = {k: v for k, v in record.items() if k != "record_sha256"}
        require(record.get("record_sha256") == _canonical_sha256(body),
                f"{name} ledger record {index} digest mismatch")
        prev = record["record_sha256"]


def append(name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Append one validated, chain-hashed record.  The only legal write."""
    schema = LEDGERS[name]
    require(isinstance(record, dict), "ledger record must be an object")
    unknown = set(record) - schema["required"] - schema["optional"]
    require(not unknown, f"{name}: unknown ledger fields {sorted(unknown)}")
    missing = schema["required"] - set(record)
    require(not missing, f"{name}: missing ledger fields {sorted(missing)}")
    if name == "competition_evaluations":
        require(record["status"] in _COMPETITION_STATUSES,
                f"invalid competition status {record['status']!r}")
    path = ledger_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = read_ledger(name)
        entry = {
            "format_version": FORMAT_VERSION,
            "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            **record,
            "prev_sha256": existing[-1]["record_sha256"] if existing else None,
        }
        entry["record_sha256"] = _canonical_sha256(entry)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return entry


def accepted_competition_evaluations(records: list[dict[str, Any]] | None = None) -> int:
    """ACCEPTED counts even if scoring later failed; AMBIGUOUS counts
    pessimistically until Kaggle history proves otherwise."""
    rows = read_ledger("competition_evaluations") if records is None else records
    return sum(1 for row in rows if row.get("status") in {"ACCEPTED", "SCORED", "AMBIGUOUS"})


def enforce_offline_scientific_run(context: str, argv: list[str] | None = None) -> None:
    """Fail closed on any submission capability inside a slice-4 command path.

    There is deliberately NO override parameter: a slice-4 module cannot accept a
    submission card.  Deployment evaluation is a different, separately approved
    protocol with its own entry points.
    """
    require(KAGGLE_EVAL_BUDGET == 0,
            "slice-4 revision 4 freezes KAGGLE_EVAL_BUDGET=0; refusing to run")
    for flag in _SUBMISSION_ENV_FLAGS:
        value = os.environ.get(flag, "")
        if value and value.strip().lower() not in {"0", "false", "no", ""}:
            raise SubmissionCapabilityRefused(
                f"{context}: environment sets {flag}={value!r}; slice-4 paths are "
                "offline-scientific and fail closed on submission capability"
            )
    for token in argv or []:
        lowered = str(token).lower()
        if any(marker in lowered for marker in _SUBMISSION_ARGV_TOKENS):
            raise SubmissionCapabilityRefused(
                f"{context}: argv token {token!r} looks submission-capable; slice-4 "
                "paths fail closed (a deployment study needs its own approved card)"
            )


def validate_submission_card(card: Any) -> dict[str, Any]:
    """Schema check for a FUTURE deployment-era submission card (never slice 4).

    Present so the fail-closed rule has a concrete artifact to demand; nothing in
    slice 4 accepts one.
    """
    require(isinstance(card, dict), "submission card must be an object")
    required = {
        "competition", "team", "candidate_commit", "payload_sha256", "kernel_sha256",
        "dataset_sha256", "code_provenance", "hypothesis", "expected_information",
        "quota_before", "max_accepted_submissions", "decision_rule", "approver",
    }
    missing = required - set(card)
    require(not missing, f"submission card missing fields: {sorted(missing)}")
    require(card["max_accepted_submissions"] == 1,
            "at most one accepted evaluation per frozen candidate")
    require(isinstance(card["decision_rule"], str) and card["decision_rule"].strip(),
            "submission card needs a predeclared decision rule")
    return card


# ------------------------------------------------- deployment budget report

# Measured historical anchors (kaggle_v4 public non-submission run) and pinned
# harness caps.  Working assumptions are labelled (w) and never silently promoted.
DEPLOYMENT_ANCHORS = {
    "internal_experiment_cap_minutes": 540,
    "per_game_cap_minutes": 132,
    "concurrent_jobs": 28,
    "kaggle_v4_games": 25,
    "kaggle_v4_wall_clock": "2h12m33s",
    "kaggle_v4_total_tokens": 1_779_674,
    "kaggle_v4_summed_game_seconds": 198_097.6,
    "kaggle_v4_actions": 3_833,
    "kaggle_v4_session_seconds": 7_953,
    "platform_request_ceiling_per_minute": 600,
    "hidden_games_estimate": "110 (w)",
    "live_wall_limit": "unverified; ~8h assumption is labelled (w) in the repo",
}


def deployment_budget_report() -> dict[str, Any]:
    """Non-blocking capacity report; a capacity warning, not a score forecast."""
    mean_game_minutes = DEPLOYMENT_ANCHORS["kaggle_v4_summed_game_seconds"] / 60 / \
        DEPLOYMENT_ANCHORS["kaggle_v4_games"]
    projected = 110 * mean_game_minutes / DEPLOYMENT_ANCHORS["concurrent_jobs"]
    envelope = DEPLOYMENT_ANCHORS["internal_experiment_cap_minutes"]
    aggregate_actions_per_second = (
        DEPLOYMENT_ANCHORS["kaggle_v4_actions"]
        / DEPLOYMENT_ANCHORS["kaggle_v4_session_seconds"]
    )
    return {
        "kind": "deployment_budget_report",
        "format_version": FORMAT_VERSION,
        "anchors": DEPLOYMENT_ANCHORS,
        "mean_game_minutes": round(mean_game_minutes, 1),
        "idealized_110_game_projection_minutes": round(projected, 1),
        "share_of_internal_envelope": round(projected / envelope, 3),
        "aggregate_actions_per_second": round(aggregate_actions_per_second, 3),
        "reading": (
            "The four-call, up-to-32,768-output-token P protocol is NOT additive "
            "deployment work; a deployment candidate must replace analyzer work and "
            "action waste, pass the per-game cap, and project <= 459 minutes "
            "end-to-end (15% envelope reserve). Failure of the deployment screen "
            "means 'not affordable in the current actor', never 'goal inference "
            "failed'."
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print the deployment budget report")
    parser.add_argument("--verify", action="store_true",
                        help="verify all ledger chains")
    args = parser.parse_args()
    enforce_offline_scientific_run("s4_ledgers", [])
    if args.report:
        print(json.dumps(deployment_budget_report(), indent=1))
    if args.verify:
        for name in LEDGERS:
            records = read_ledger(name)
            print(f"{name}: {len(records)} records, chain OK")
        print(f"accepted competition evaluations: {accepted_competition_evaluations()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
