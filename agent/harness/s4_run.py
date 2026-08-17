#!/usr/bin/env python3
"""Slice-4 pilot runner — matched arms, managed uncertainty, certificate-gated.

`notes/qwen-3.8-slice4-design.md` → sections 6–7, review round 1 findings 2/3/6,
and the frozen pre-registration. One cell = one (game, arm, seed) conversation.
Passive carrier arms T/V/O are matched on evidence IDs; R/A/C add retrieval,
model-selected probing, and seeded-control probing over the overlay carrier; P is
the full retrieval + model-selected-probe system.  Fixed calls remove the generation-
count/self-refinement confound, but added evidence is not token/image-length matched
to neutral updates, so the interactive contrasts are incremental system effects.

Discipline inherited from the certified probe (`e2_probe_vlm`, imported, not
reimplemented): hardened template invariants, per-tag deterministic seeds via the
global MLX RNG, xhigh + the pinned sampler, full per-call traces, atomic
checkpoints, run locking. The runner REFUSES to start unless the gate certificate
verifies: verdict PASS, pinned runtime versions equal live versions, checkpoint
config-file hashes, and every local weight shard re-verified.

Never constrain the first decoded token. The primary answer is the ranked-hypotheses
JSON (rev 2 §6); the DSL is not requested — it is a sealed-side translation.

Dry run (no model, no GPU):
  .venv/bin/python agent/harness/s4_run.py --arms T V --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import traceback
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_probe_vlm as probe  # noqa: E402  (certified serving layer)
import s4_packet as spk  # noqa: E402
from s4_probes import (  # noqa: E402
    PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS,
    RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS,
    ProbeSession,
)

ROOT = spk.ROOT
CERTIFICATE = ROOT / "logs/e2_probe_vlm_38_8bit.json"
FROZEN = ROOT / "logs/s4_sealed/FROZEN.json"
RUNS = ROOT / "logs/s4_runs"
PILOT_GAMES = ("ls20", "ft09", "m0r0", "sp80")
MAX_ANSWER_TOKENS = 20_000       # (w) fleet-calibrated at the gate night before use
MAX_INITIAL_PROMPT_TEXT_TOKENS = 14_000  # 12k evidence + request/template envelope
INTERACTION_ROUNDS = 3           # fixed update calls after r0, for every arm
RETRIEVALS_PER_ROUND = 1         # one bounded visual result can be delivered each round
ACTIVE_PROBES = 3
MAX_IMAGES = probe.MAX_PACKET_IMAGES
MAX_VISUAL_TOKENS = probe.MAX_VISUAL_TOKENS
PROBE_PAGE_VISUAL_RESERVE = PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS
ALL_ARMS = ("T", "V", "O", "R", "A", "C", "P")
INTERACTIVE_ARMS = frozenset({"R", "A", "C", "P"})
RETRIEVAL_ARMS = frozenset({"R", "P"})
MODEL_PROBE_ARMS = frozenset({"A", "P"})
CONTROL_PROBE_ARMS = frozenset({"C"})
NO_NEW_OBSERVATION_MAX_CHARS = 256
NO_NEW_OBSERVATION = (
    "NO NEW OBSERVATION: This update round supplies no additional environment "
    "evidence. Keep, revise, or narrow your hypotheses using only the evidence "
    "already in context."
)
UPDATE_REQUEST = (
    "Update your analysis. Answer with the same JSON object schema, complete, "
    "on the last line."
)
LOCK_PATH = ROOT / "logs/.s4_run.lock"
EXPECTED_GATE_NAMES = frozenset({
    "gate1_palette_production",
    "gate2_grey_fill_colour",
    "gate3_packet_binding",
    "gate4_spatial_grounding",
    "gate5_sampler_stability",
})
EXPECTED_FROZEN_SCRIPTS = frozenset({
    "agent/harness/s4_run.py",
    "agent/harness/s4_packet.py",
    "agent/harness/s4_probes.py",
    "agent/harness/s4_recapture.py",
    "agent/harness/s4_grade.py",
    "agent/harness/s4_render.py",
})

REQUEST = """\
You are studying an unfamiliar interactive grid environment from recorded evidence
only. Everything shown is either OBSERVED (recorded frames and actions) or
DERIVED-EXACT (deterministic computation over observations). Nothing else is known.

Think first, at length. Then answer with ONLY a JSON object on the last line:
{
  "hypotheses": [
    {"probability": <0..1>, "necessary_conditions": ["..."],
     "sufficient_condition": "...", "evidence_for": ["<page or transition ids>"],
     "evidence_against": ["..."], "predicted_counterexample": "..."}
  ],
  "best_goal": {"plain_causal_condition": "...", "structured_factors": ["..."]},
  "next_probe": {"start_state_id": "<transition id>" or null,
                 "action": {"id": <0..7>, "click": [row, col] or null} or null,
                 "predictions_by_hypothesis": {"<index>": "..."}},
  "retrieval_requests": [{"op": "SHOW_FRAME|SHOW_TRANSITION|SHOW_EPISODE|\
SHOW_ACTION_CONTRAST|SHOW_COLOUR_HISTORY", "args": ["..."]}],
  "goal_directed_plan": [{"action": {"id": <0..7>, "click": [row, col] or null}}]
}
Probabilities must sum to at most 1. Rank hypotheses by probability. If the evidence
underdetermines the objective, say so through the probabilities and design
"next_probe" to discriminate between your top hypotheses.

Tool argument contract (JSON strings are literal; requests are never repaired):
- SHOW_FRAME args=["S00000" or "K00000"]
- SHOW_TRANSITION args=["S00000" or "K00000"]
- SHOW_EPISODE args=["S00000" or "K00000", "1".."16"]
- SHOW_ACTION_CONTRAST args=["A0".."A7"]
- SHOW_COLOUR_HISTORY args=["0".."15"] (ARC colour ID, never a Cxxx component ID)
For a live next_probe, start_state_id must be a recapture-backed Sxxxxx transition;
Kxxxxx transitions are retrieval-only. Action A6 requires click=[row,col]. Every
other action requires click=null. Invalid or redundant requests consume their budget.
"""


class InstrumentCellError(RuntimeError):
    """A live retrieval/probe failed; it is neither model evidence nor model failure."""


def hex_grid(board: list[list[int]]) -> str:
    return "\n".join("".join(format(v, "x") for v in row) for row in board)


def sha256_file(path: Path) -> str:
    return probe.sha256_file(path)


def canonical_sha256(payload: dict[str, Any]) -> str:
    return probe.canonical_sha256(payload)


def extract_final_json(answer: str) -> dict[str, Any] | None:
    """Decode the complete final JSON object, including arbitrarily nested values.

    The vision probe's regex parser is intentionally for its flat gate payloads and
    must never be reused here.  A candidate is accepted only when nothing but
    whitespace follows it, so an earlier object in a truncated response cannot pass.
    """
    decoder = json.JSONDecoder()
    for start in (m.start() for m in reversed(list(re.finditer(r"\{", answer)))):
        try:
            value, used = decoder.raw_decode(answer[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not answer[start + used:].strip():
            return value
    return None


def _string_list(value: Any, where: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        errors.append(f"{where} must be a list of strings")
        return []
    return value


def _valid_click(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, list)
        and len(value) == 2
        and all(type(v) is int and 0 <= v <= 63 for v in value)
    )


def validate_answer(payload: Any) -> list[str]:
    """Return every schema defect; an invalid object is a missing observation."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["root must be an object"]
    required = {
        "hypotheses", "best_goal", "next_probe", "retrieval_requests",
        "goal_directed_plan",
    }
    missing = sorted(required - set(payload))
    extra = sorted(set(payload) - required)
    if missing:
        errors.append(f"missing keys: {missing}")
    if extra:
        errors.append(f"unknown keys: {extra}")

    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        errors.append("hypotheses must be a non-empty list")
        hypotheses = []
    probabilities: list[float] = []
    hkeys = {
        "probability", "necessary_conditions", "sufficient_condition",
        "evidence_for", "evidence_against", "predicted_counterexample",
    }
    for index, hypothesis in enumerate(hypotheses):
        where = f"hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            errors.append(f"{where} must be an object")
            continue
        if set(hypothesis) != hkeys:
            errors.append(f"{where} keys must be exactly {sorted(hkeys)}")
        probability = hypothesis.get("probability")
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            errors.append(f"{where}.probability must be numeric")
        elif not 0.0 <= float(probability) <= 1.0:
            errors.append(f"{where}.probability outside 0..1")
        else:
            probabilities.append(float(probability))
        _string_list(hypothesis.get("necessary_conditions"),
                     f"{where}.necessary_conditions", errors)
        _string_list(hypothesis.get("evidence_for"), f"{where}.evidence_for", errors)
        _string_list(hypothesis.get("evidence_against"),
                     f"{where}.evidence_against", errors)
        for key in ("sufficient_condition", "predicted_counterexample"):
            if not isinstance(hypothesis.get(key), str) or not hypothesis[key].strip():
                errors.append(f"{where}.{key} must be a non-empty string")
    if probabilities and sum(probabilities) > 1.0 + 1e-9:
        errors.append(f"hypothesis probabilities sum to {sum(probabilities):.9f} > 1")
    if probabilities and any(a < b for a, b in zip(probabilities, probabilities[1:])):
        errors.append("hypotheses are not ranked by descending probability")

    best = payload.get("best_goal")
    if not isinstance(best, dict) or set(best) != {"plain_causal_condition", "structured_factors"}:
        errors.append("best_goal has the wrong object schema")
    else:
        if not isinstance(best.get("plain_causal_condition"), str) or not best["plain_causal_condition"].strip():
            errors.append("best_goal.plain_causal_condition must be non-empty")
        _string_list(best.get("structured_factors"), "best_goal.structured_factors", errors)

    next_probe = payload.get("next_probe")
    if not isinstance(next_probe, dict) or set(next_probe) != {
        "start_state_id", "action", "predictions_by_hypothesis"
    }:
        errors.append("next_probe has the wrong object schema")
    else:
        start = next_probe.get("start_state_id")
        if start is not None and (not isinstance(start, str) or not start.strip()):
            errors.append("next_probe.start_state_id must be a non-empty string or null")
        action = next_probe.get("action")
        if action is not None:
            if not isinstance(action, dict) or set(action) != {"id", "click"}:
                errors.append("next_probe.action has the wrong object schema")
        if (start is None) != (action is None):
            errors.append("next_probe start_state_id and action must both be null or both present")
        predictions = next_probe.get("predictions_by_hypothesis")
        if not isinstance(predictions, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in predictions.items()
        ):
            errors.append("next_probe.predictions_by_hypothesis must map strings to strings")

    retrievals = payload.get("retrieval_requests")
    if not isinstance(retrievals, list):
        errors.append("retrieval_requests must be a list")
    else:
        for index, request in enumerate(retrievals):
            if not isinstance(request, dict) or set(request) != {"op", "args"}:
                errors.append(f"retrieval_requests[{index}] has the wrong object schema")
                continue
            if not isinstance(request.get("op"), str):
                errors.append(f"retrieval_requests[{index}].op must be a string")
            if not isinstance(request.get("args"), list):
                errors.append(f"retrieval_requests[{index}].args must be a list")

    plan = payload.get("goal_directed_plan")
    if not isinstance(plan, list):
        errors.append("goal_directed_plan must be a list")
    else:
        for index, step in enumerate(plan):
            action = step.get("action") if isinstance(step, dict) else None
            if not isinstance(step, dict) or set(step) != {"action"} or not isinstance(action, dict):
                errors.append(f"goal_directed_plan[{index}] has the wrong object schema")
                continue
            if set(action) != {"id", "click"}:
                errors.append(f"goal_directed_plan[{index}].action has the wrong keys")
            if type(action.get("id")) is not int or not 0 <= action["id"] <= 7:
                errors.append(f"goal_directed_plan[{index}].action.id is invalid")
            if not _valid_click(action.get("click")):
                errors.append(f"goal_directed_plan[{index}].action.click is invalid")
    return errors


def acquire_run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another Slice-4 runner holds the global run lock") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({
        "pid": os.getpid(),
        "acquired_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }))
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def verify_frozen_manifest() -> tuple[dict[str, Any], str]:
    """Verify only public hashes/configuration; never open sealed gold contents."""
    probe.require(FROZEN.exists(), "pre-registration is not frozen — run s4_grade.py --freeze first")
    frozen = json.loads(FROZEN.read_text())
    probe.require(frozen.get("format_version") == 2, "unsupported FROZEN format")
    blind_map = ROOT / "logs/s4_sealed/blind_map.json"
    probe.require(blind_map.is_file(), "sealed blind map is missing")
    probe.require(sha256_file(blind_map) == frozen.get("blind_map_sha256"),
                  "sealed blind-map drift")
    scripts = frozen.get("scripts") or {}
    probe.require(set(scripts) == EXPECTED_FROZEN_SCRIPTS,
                  "frozen protocol-script inventory is incomplete or unknown")
    for relative, digest in scripts.items():
        path = ROOT / relative
        probe.require(path.is_file() and sha256_file(path) == digest,
                      f"frozen script drift: {relative}")
    git = probe.capture_git_state()
    probe.require(git.get("dirty") is False and git.get("commit") == frozen.get("git_commit"),
                  "live git state differs from the clean frozen protocol commit")
    prereg = frozen.get("preregistration") or {}
    expected_digest = frozen.get("preregistration_sha256")
    probe.require(expected_digest == canonical_sha256(prereg),
                  "frozen preregistration digest mismatch")
    budgets = prereg.get("budgets") or {}
    probe.require(set(budgets) == {
        "answer_tokens", "interaction_rounds", "retrievals_per_round",
        "active_probes", "max_images", "max_visual_tokens",
    }, "frozen budget inventory is incomplete or unknown")
    probe.require(budgets.get("active_probes") == ACTIVE_PROBES,
                  "frozen active-probe budget differs from runner")
    probe.require(budgets.get("interaction_rounds") == INTERACTION_ROUNDS,
                  "frozen interaction-round budget differs from runner")
    probe.require(budgets.get("retrievals_per_round") == RETRIEVALS_PER_ROUND,
                  "frozen retrieval budget differs from runner")
    probe.require(budgets.get("answer_tokens") == MAX_ANSWER_TOKENS,
                  "frozen answer-token budget differs from runner")
    probe.require(budgets.get("max_images") == MAX_IMAGES,
                  "frozen image-count budget differs from runner")
    probe.require(budgets.get("max_visual_tokens") == MAX_VISUAL_TOKENS,
                  "frozen visual-token budget differs from runner")
    return frozen, sha256_file(FROZEN)


def verify_packet_frozen(packet: dict[str, Any], frozen: dict[str, Any]) -> None:
    expected = (frozen.get("packets") or {}).get(packet["blind_id"])
    probe.require(isinstance(expected, dict),
                  f"packet {packet['blind_id']} is absent from the frozen manifest")
    probe.require(expected.get("manifest_sha256") == packet["manifest_sha256"],
                  f"frozen packet manifest drift: {packet['blind_id']}")
    probe.require(expected.get("ledger_sha256") == packet["ledger_sha256"],
                  f"frozen packet ledger drift: {packet['blind_id']}")
    expected_pages = expected.get("pages") or {}
    actual_files = set()
    for pages in (packet["manifest"].get("carrier_pages") or {}).values():
        for page in pages:
            actual_files.add(page["file"])
    probe.require(actual_files == set(expected_pages),
                  f"frozen packet page set drift: {packet['blind_id']}")
    for name, digest in expected_pages.items():
        probe.require(sha256_file(packet["dir"] / "pages" / name) == digest,
                      f"frozen packet page drift: {packet['blind_id']}/{name}")


def verify_certificate(model: Path) -> dict[str, Any]:
    """Fail closed on the complete serving identity used by the visual PASS."""
    require = probe.require
    require(CERTIFICATE.exists(), f"gate certificate missing: {CERTIFICATE}")
    cert = json.loads(CERTIFICATE.read_text())
    require(cert.get("status") == "done" and cert.get("passed") is True,
            f"gate certificate is not a completed PASS: {cert.get('status')!r}")
    require(cert.get("verdict") == "PASS", f"gate certificate verdict {cert.get('verdict')!r}")
    statuses = cert.get("gate_statuses")
    require(isinstance(statuses, dict) and set(statuses) == EXPECTED_GATE_NAMES,
            "gate certificate has an incomplete or unknown gate inventory")
    require(all(v == "PASS" for v in statuses.values()),
            "gate certificate contains a non-PASS gate")
    compat = cert.get("serving_compatibility") or {}
    compat_payload = {k: v for k, v in compat.items() if k != "sha256"}
    require(compat.get("sha256") == canonical_sha256(compat_payload),
            "gate certificate serving-compatibility digest is invalid")
    live = {p: pkg_version(p) for p in ("mlx-vlm", "mlx", "mlx-lm", "transformers")}
    require(compat.get("versions") == live,
            f"runtime drift vs certificate: {compat.get('versions')} != {live}")
    identity = probe.fingerprint(model)  # mandatory: full six-shard verification
    for key in ("checkpoint_sha256", "script_sha", "renderer_sha", "versions"):
        require(identity.get(key) == compat.get(key),
                f"serving identity drift for {key}: {identity.get(key)!r} != {compat.get(key)!r}")
    require(compat.get("production_sampler") == probe.PRODUCTION_SAMPLER,
            "production sampler drift vs certificate")
    require(compat.get("reasoning_effort") == probe.REASONING_EFFORT,
            "reasoning-effort drift vs certificate")
    experiment = compat.get("experiment_config") or {}
    require(experiment.get("max_packet_images") == MAX_IMAGES,
            "certificate image-count envelope differs from runner")
    require(experiment.get("max_visual_tokens") == MAX_VISUAL_TOKENS,
            "certificate visual-token envelope differs from runner")
    require(
        type(experiment.get("stability_replicates")) is int
        and experiment["stability_replicates"] >= 3
        and experiment.get("stability_required_passes")
        == experiment["stability_replicates"],
        "certificate production-sampler stability panel is insufficient",
    )
    return {
        "certificate_path": str(CERTIFICATE),
        "certificate_sha256": sha256_file(CERTIFICATE),
        "certificate_run_dir": cert.get("run_dir"),
        "checkpoint_sha256": identity.get("checkpoint_sha256"),
        "serving_compatibility": compat,
        "checkpoint_identity": identity,
        "certificate_verified_shards": True,
    }


def verify_packet_serving_identity(
    packet: dict[str, Any], certificate: dict[str, Any]
) -> dict[str, Any]:
    """Bind packet token/image measurements to the certified serving checkpoint."""
    build = packet["manifest"].get("build_identity") or {}
    processor = build.get("processor") or {}
    packet_files = processor.get("serving_files")
    checkpoint = certificate.get("checkpoint_identity") or {}
    certified_files = checkpoint.get("model_files")
    probe.require(isinstance(packet_files, dict) and packet_files,
                  f"{packet['blind_id']}: packet lacks measurement serving files")
    probe.require(isinstance(certified_files, dict) and certified_files,
                  "certificate lacks checkpoint model-file identity")
    probe.require(set(packet_files) <= set(certified_files),
                  f"{packet['blind_id']}: packet used files outside certified checkpoint")
    for name, packet_identity in packet_files.items():
        probe.require(packet_identity == certified_files[name],
                      f"{packet['blind_id']}: packet measurement identity drift for {name}")
    packet_transformers = (build.get("packages") or {}).get("transformers")
    certified_transformers = (checkpoint.get("versions") or {}).get("transformers")
    probe.require(
        packet_transformers == certified_transformers == pkg_version("transformers"),
        f"{packet['blind_id']}: packet tokenizer runtime differs from certified serving runtime",
    )
    expected_measurement = canonical_sha256(packet_files)
    probe.require(processor.get("measurement_identity_sha256") == expected_measurement,
                  f"{packet['blind_id']}: packet measurement-identity digest is invalid")
    return {
        "blind_id": packet["blind_id"],
        "measurement_identity_sha256": expected_measurement,
        "checkpoint_sha256": certificate.get("checkpoint_sha256"),
    }


def load_packet(game: str) -> dict[str, Any]:
    from PIL import Image

    def require_full_hash_fields(value: Any, label: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_label = f"{label}.{key}"
                if key == "sha256" or key.endswith("_sha256"):
                    probe.require(
                        isinstance(child, str)
                        and re.fullmatch(r"[0-9a-f]{64}", child) is not None,
                        f"{child_label} must be a full lowercase SHA-256",
                    )
                else:
                    require_full_hash_fields(child, child_label)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                require_full_hash_fields(child, f"{label}[{index}]")

    bid = spk.blind_id(game)
    pdir = spk.PACKET_ROOT / bid
    manifest_path = pdir / "packet_manifest.json"
    ledger_path = pdir / "ledger.txt"
    probe.require(manifest_path.is_file() and ledger_path.is_file(),
                  f"packet missing for {bid}")
    manifest = json.loads(manifest_path.read_text())
    ledger = ledger_path.read_text()
    probe.require(manifest.get("format_version") == spk.FORMAT_VERSION == 3,
                  f"packet {bid} is not closure-grade format v3")
    probe.require(manifest.get("blind_id") == bid, f"packet blind-id mismatch for {bid}")
    actual_ledger = sha256_file(ledger_path)
    probe.require(manifest.get("ledger_sha256") == actual_ledger,
                  f"packet ledger hash mismatch for {bid}")
    probe.require(manifest.get("ledger_bytes") == ledger_path.stat().st_size,
                  f"packet ledger byte count mismatch for {bid}")

    expected_caps = {
        "max_images": MAX_IMAGES,
        "max_visual_tokens": MAX_VISUAL_TOKENS,
        "max_initial_pages": spk.MAX_INITIAL_PAGES,
        "max_initial_visual_tokens": spk.MAX_INITIAL_VISUAL_TOKENS,
        "max_text_tokens": spk.MAX_TEXT_TOKENS,
        "interactive_result_headroom": ACTIVE_PROBES,
        "retrieval_result_headroom": INTERACTION_ROUNDS,
        "minimal_result_page_visual_tokens": PROBE_PAGE_VISUAL_RESERVE,
        "reserved_minimal_result_visual_tokens": ACTIVE_PROBES * PROBE_PAGE_VISUAL_RESERVE,
        "max_retrieval_page_visual_tokens": RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS,
        "reserved_retrieval_visual_tokens": (
            INTERACTION_ROUNDS * RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
        ),
        "reserved_post_initial_visual_tokens": (
            ACTIVE_PROBES * PROBE_PAGE_VISUAL_RESERVE
            + INTERACTION_ROUNDS * RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
        ),
    }
    probe.require(manifest.get("caps") == expected_caps,
                  f"packet {bid} caps differ from the runner envelope")

    carrier_pages = manifest.get("carrier_pages")
    probe.require(isinstance(carrier_pages, dict) and set(carrier_pages) == {"raw", "overlay"},
                  f"packet {bid} must contain exactly raw and overlay carriers")
    raw_pages, overlay_pages = carrier_pages["raw"], carrier_pages["overlay"]
    items = manifest.get("evidence_items")
    page_count = manifest.get("page_count")
    probe.require(
        type(page_count) is int
        and page_count == spk.TARGET_INITIAL_PAGES == spk.MAX_INITIAL_PAGES
        and isinstance(items, list) and len(items) == page_count
        and isinstance(raw_pages, list) and len(raw_pages) == page_count
        and isinstance(overlay_pages, list) and len(overlay_pages) == page_count,
        f"packet {bid} does not have the exact matched ten-page carriers",
    )
    probe.require(manifest.get("pages") == raw_pages,
                  f"packet {bid} raw-page alias differs from carrier_pages.raw")

    evidence_ids = [item.get("evidence_id") for item in items]
    probe.require(
        all(isinstance(eid, str) and eid for eid in evidence_ids)
        and len(set(evidence_ids)) == page_count,
        f"packet {bid} evidence IDs are missing or duplicated",
    )
    page_entries: dict[str, dict[str, Any]] = {}
    totals: dict[str, int] = {}
    pages_dir = pdir / "pages"
    probe.require(pages_dir.is_dir(), f"packet pages missing for {bid}")
    for carrier_name, pages in (("raw", raw_pages), ("overlay", overlay_pages)):
        carrier_tokens = 0
        for index, (item, entry) in enumerate(zip(items, pages), 1):
            carriers = item.get("carriers") or {}
            item_carrier = carriers.get(carrier_name) or {}
            name = entry.get("file")
            probe.require(
                entry.get("page") == index
                and entry.get("kind") == item.get("kind")
                and entry.get("evidence_id") == item.get("evidence_id")
                and item_carrier.get("page") == index
                and item_carrier.get("file") == name
                and item_carrier.get("pages") == [name],
                f"packet {bid} {carrier_name} page {index} is not evidence-matched",
            )
            probe.require(isinstance(name, str) and Path(name).name == name
                          and name not in page_entries,
                          f"packet {bid} has unsafe or duplicate page name {name!r}")
            path = pages_dir / name
            probe.require(path.is_file(), f"packet page missing: {bid}/{name}")
            probe.require(entry.get("sha256") == sha256_file(path)
                          and entry.get("bytes") == path.stat().st_size,
                          f"packet page bytes/hash mismatch: {bid}/{name}")
            width, height = entry.get("width"), entry.get("height")
            probe.require(type(width) is int and type(height) is int
                          and width % 32 == height % 32 == 0
                          and width * height >= 65_536,
                          f"packet page geometry invalid: {bid}/{name}")
            with Image.open(path) as image:
                probe.require(image.size == (width, height),
                              f"packet page dimensions mismatch: {bid}/{name}")
            expected_grid = [1, height // 16, width // 16]
            expected_tokens = expected_grid[1] * expected_grid[2] // 4
            probe.require(
                entry.get("measurement") == "processor-real"
                and entry.get("image_grid_thw") == expected_grid
                and entry.get("processed_size") == [width, height]
                and entry.get("visual_tokens") == expected_tokens,
                f"packet processor measurement mismatch: {bid}/{name}",
            )
            carrier_tokens += expected_tokens
            page_entries[name] = entry
        totals[carrier_name] = carrier_tokens
        declared = (manifest.get("carrier_totals") or {}).get(carrier_name) or {}
        probe.require(
            declared.get("page_count") == page_count
            and declared.get("visual_tokens") == carrier_tokens
            and declared.get("visual_token_headroom") == MAX_VISUAL_TOKENS - carrier_tokens
            and declared.get("reserved_minimal_result_visual_tokens")
            == expected_caps["reserved_minimal_result_visual_tokens"]
            and declared.get("reserved_retrieval_visual_tokens")
            == expected_caps["reserved_retrieval_visual_tokens"]
            and declared.get("reserved_post_initial_visual_tokens")
            == expected_caps["reserved_post_initial_visual_tokens"]
            and declared.get("initial_visual_token_ceiling") == spk.MAX_INITIAL_VISUAL_TOKENS
            and declared.get("processor_measurements") == "per-page image_grid_thw"
            and carrier_tokens <= spk.MAX_INITIAL_VISUAL_TOKENS,
            f"packet {bid} {carrier_name} totals/headroom are inconsistent",
        )
    probe.require(manifest.get("visual_tokens_total") == totals["raw"],
                  f"packet {bid} legacy visual total differs from raw carrier")

    actual_page_files = {
        path.name for path in pages_dir.iterdir() if path.is_file()
    }
    probe.require(
        actual_page_files == set(page_entries),
        f"packet page inventory mismatch for {bid}: "
        f"missing={sorted(set(page_entries) - actual_page_files)}, "
        f"extra={sorted(actual_page_files - set(page_entries))}",
    )

    selection = manifest.get("selection") or {}
    probe.require(
        selection.get("algorithm_version") == 3
        and selection.get("target_initial_pages") == spk.TARGET_INITIAL_PAGES
        and selection.get("actual_initial_pages") == page_count
        and selection.get("above_target_declared") is False
        and selection.get("image_cap_headroom") == MAX_IMAGES - page_count
        and selection.get("interactive_three_result_pages_fit") is True
        and selection.get("three_retrieval_pages_fit") is True
        and selection.get("probe_and_retrieval_six_pages_fit") is True
        and selection.get("interactive_three_minimal_result_pages_fit_token_cap") is True
        and selection.get("probe_and_retrieval_pages_fit_token_cap") is True,
        f"packet {bid} selection/headroom contract is inconsistent",
    )

    decoded: dict[str, list[list[int]]] = {}
    board_records = 0
    for item in items:
        text_carrier = ((item.get("carriers") or {}).get("text") or {})
        probe.require(text_carrier.get("actions") == item.get("action_sequence"),
                      f"packet {bid} text/action carrier drift")
        for board in text_carrier.get("boards") or []:
            frame_id = board.get("frame_id")
            encoded = board.get("hex")
            probe.require(isinstance(frame_id, str) and isinstance(encoded, str),
                          f"packet {bid} has malformed text-grid record")
            grid = spk.decode_text_grid(encoded, decoded)
            probe.require(board.get("sha256") == canonical_sha256(grid),
                          f"packet {bid} lossless text-grid hash mismatch for {frame_id}")
            if frame_id in decoded:
                probe.require(decoded[frame_id] == grid,
                              f"packet {bid} text frame ID was reused with new pixels")
            decoded[frame_id] = grid
            board_records += 1
    codec_stats = selection.get("text_grid_encoding") or {}
    probe.require(codec_stats.get("board_records") == board_records
                  and codec_stats.get("lossless_decode_hash_checks") == board_records,
                  f"packet {bid} text-grid codec accounting is inconsistent")

    result = {
        "blind_id": bid, "dir": pdir, "manifest": manifest, "ledger": ledger,
        "manifest_path": manifest_path, "manifest_sha256": sha256_file(manifest_path),
        "ledger_path": ledger_path, "ledger_sha256": actual_ledger,
    }
    text_total = (manifest.get("carrier_totals") or {}).get("text") or {}
    text_payload = _text_evidence(result)
    probe.require(
        text_total.get("measurement") == "checkpoint-tokenizer-real"
        and type(text_total.get("text_tokens")) is int
        and 0 < text_total["text_tokens"] <= spk.MAX_TEXT_TOKENS
        and text_total.get("text_chars") == len(text_payload),
        f"packet {bid} checkpoint-tokenizer text total is invalid",
    )
    probe.require(manifest.get("input_bundle_sha256") == canonical_sha256(manifest.get("inputs")),
                  f"packet {bid} input-bundle digest is invalid")
    build = manifest.get("build_identity") or {}
    probe.require(build.get("packet_builder_sha256") == sha256_file(HARNESS / "s4_packet.py")
                  and build.get("renderer_sha256") == sha256_file(HARNESS / "s4_render.py"),
                  f"packet {bid} was not built by the live frozen scripts")
    require_full_hash_fields(manifest, f"packet[{bid}]")
    return result


def load_packet_bound_evidence(game: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Load the live retrieval/probe corpus and require the packet's exact inputs.

    The initial pages and later interaction must never come from two independently
    valid but different observation builds.  Passing this returned object into
    ``ProbeSession`` also closes the check/use gap for the manifest and store data.
    """
    evidence = spk.load_evidence(game)
    identity = evidence.get("input_identity")
    manifest = packet["manifest"]
    probe.require(isinstance(identity, dict), f"{game}: live evidence lacks input identity")
    probe.require(manifest.get("inputs") == identity,
                  f"{game}: live interaction inputs differ from packet inputs")
    actual = canonical_sha256(identity)
    probe.require(manifest.get("input_bundle_sha256") == actual,
                  f"{game}: packet input-bundle hash differs from live interaction inputs")
    return evidence


def _carrier_pages(packet: dict[str, Any], carrier: str) -> list[dict[str, Any]]:
    manifest = packet["manifest"]
    pages = (manifest.get("carrier_pages") or {}).get(carrier)
    if pages is None and carrier == "raw":
        pages = manifest.get("pages")
    probe.require(isinstance(pages, list) and pages,
                  f"packet has no {carrier!r} carrier pages")
    return pages


def _text_evidence(packet: dict[str, Any]) -> str:
    items = packet["manifest"].get("evidence_items")
    probe.require(isinstance(items, list) and items,
                  "packet has no matched evidence_items text carrier")
    blocks = ["== EXACT LEDGER ==\n" + packet["ledger"]]
    for item in items:
        eid = str(item.get("evidence_id"))
        text_carrier = (item.get("carriers") or {}).get("text") or {}
        block = [
            f"== EVIDENCE {eid} ==",
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


def initial_turn(game: str, arm: str, packet: dict[str, Any]) -> tuple[list[dict], list[Path]]:
    probe.require(arm in ALL_ARMS, f"unknown arm {arm}")
    items: list[dict[str, str]] = [{"type": "text", "text": REQUEST}]
    images: list[Path] = []
    if arm == "T":
        items.append({"type": "text", "text": _text_evidence(packet)})
    else:
        items.append({"type": "text", "text": "== EXACT LEDGER ==\n" + packet["ledger"]})
        carrier = "raw" if arm == "V" else "overlay"
        for page in _carrier_pages(packet, carrier):
            items.append({"type": "text", "text":
                          f"Page {page['page']} evidence {page.get('evidence_id')} "
                          f"({page['kind']}): {page['caption']}"})
            items.append({"type": "image"})
            images.append(packet["dir"] / "pages" / page["file"])
    if arm in INTERACTIVE_ARMS:
        capabilities = []
        if arm in RETRIEVAL_ARMS:
            capabilities.append(f"up to {RETRIEVALS_PER_ROUND} retrievals per round")
        if arm in MODEL_PROBE_ARMS:
            capabilities.append(f"up to {ACTIVE_PROBES} model-selected live probes total")
        if arm in CONTROL_PROBE_ARMS:
            capabilities.append(f"{ACTIVE_PROBES} seeded control probes; your requested probe is diagnostic only")
        items.append({"type": "text", "text":
                      "Interactive condition: " + "; ".join(capabilities) + ". "
                      "Invalid or redundant model-selected probes consume budget; "
                      "requests are never repaired. "
                      f"There are {INTERACTION_ROUNDS} fixed update rounds."})
    return items, images


def ask_chat(
    vlm, messages, images, *, seed, max_tokens, run_dir, tag,
    max_input_text_tokens: int | None = None,
):
    """Closure-grade multi-turn serving path with the probe's hard invariants."""
    import mlx.core as mx
    from PIL import Image as PILImage
    from mlx_vlm import generate

    probe.require(type(seed) is int and 0 <= seed < 2 ** 64, f"invalid seed {seed!r}")
    probe.require(type(max_tokens) is int and max_tokens > 0, "invalid output-token budget")
    prompt = vlm.processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=True, reasoning_effort=probe.REASONING_EFFORT,
    )
    marker = prompt.rfind("<|im_start|>assistant")
    probe.require(marker != -1, "assistant marker missing")
    probe.require(prompt.rstrip().endswith("<think>"), "generation tail does not open <think>")
    probe.require(not re.search(r"<think>\s*</think>", prompt[marker:]),
                  "pre-filled think in generation region")

    flattened: list[dict[str, str]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            flattened.extend(content)
    image_items = [item for item in flattened if item.get("type") == "image"]
    probe.require(len(image_items) == len(images),
                  f"image items {len(image_items)} != supplied images {len(images)}")
    probe.require(len(images) <= MAX_IMAGES, f"image count {len(images)} exceeds {MAX_IMAGES}")
    pads = list(re.finditer(rf"(?:{re.escape(probe.VISION_PAD)})+", prompt))
    probe.require(len(pads) == len(images),
                  f"serialized image pads {len(pads)} != images {len(images)}")
    # Verify every list-content text/image item remains serialized in original order.
    cursor = 0
    pad_index = 0
    for item in flattened:
        if item.get("type") == "text":
            text_item = item.get("text", "")
            position = prompt.find(text_item, cursor)
            probe.require(position != -1,
                          f"text item lost from prompt: {text_item[:60]!r}")
            if pad_index < len(pads):
                probe.require(position < pads[pad_index].start(),
                              "text/image interleaving order changed")
            cursor = position + len(text_item)
        else:
            probe.require(pad_index < len(pads) and pads[pad_index].start() >= cursor,
                          "image placeholder precedes its label")
            cursor = pads[pad_index].start()
            pad_index += 1

    pil = []
    image_meta = []
    for path in images:
        with PILImage.open(path) as opened:
            image = opened.convert("RGB").copy()
        probe.require(image.width % 32 == 0 and image.height % 32 == 0,
                      f"{path}: image dimensions are not multiples of 32")
        probe.require(image.width * image.height >= 65_536,
                      f"{path}: image below processor minimum")
        pil.append(image)
        image_meta.append({
            "path": str(path), "sha256": sha256_file(path),
            "source_size": [image.width, image.height],
        })
    inputs = vlm.processor(text=prompt, images=pil or None, return_tensors="np")
    grid_thw = inputs.get("image_grid_thw")
    visual_tokens = 0
    grid_list: list[list[int]] = []
    if images:
        probe.require(grid_thw is not None, "processor omitted image_grid_thw")
        grid = np.asarray(grid_thw)
        probe.require(grid.shape == (len(images), 3),
                      f"image_grid_thw shape {grid.shape} != {(len(images), 3)}")
        image_processor = vlm.processor.image_processor
        patch_size = int(getattr(image_processor, "patch_size", 0))
        merge_size = int(getattr(image_processor, "merge_size", 0))
        probe.require((patch_size, merge_size) == (16, 2),
                      f"processor geometry drift: {(patch_size, merge_size)}")
        grid_list = [[int(x) for x in row] for row in grid.tolist()]
        for meta, (grid_t, grid_h, grid_w) in zip(image_meta, grid_list):
            probe.require(grid_t == 1, f"unexpected temporal grid {grid_t}")
            processed = [grid_w * patch_size, grid_h * patch_size]
            meta["processed_size"] = processed
            probe.require(processed == meta["source_size"],
                          f"processor resized {Path(meta['path']).name}")
            merged = grid_t * grid_h * grid_w
            probe.require(merged % merge_size ** 2 == 0,
                          "non-integral visual token count")
            visual_tokens += merged // merge_size ** 2
    else:
        probe.require(grid_thw is None or np.asarray(grid_thw).size == 0,
                      "text-only turn unexpectedly produced an image grid")
    probe.require(visual_tokens <= MAX_VISUAL_TOKENS,
                  f"visual-token budget {visual_tokens} exceeds {MAX_VISUAL_TOKENS}")
    expanded = int(np.asarray(inputs["input_ids"]).shape[-1])
    text_tokens = expanded - visual_tokens
    probe.require(text_tokens >= 0, "expanded prompt is smaller than its visual-token count")
    if max_input_text_tokens is not None:
        probe.require(
            text_tokens <= max_input_text_tokens,
            f"initial prompt text-token count {text_tokens} exceeds "
            f"{max_input_text_tokens}",
        )
    mx.random.seed(seed)
    started = time.monotonic()
    out = generate(vlm.model, vlm.processor, prompt,
                   image=[str(p) for p in images] or None,
                   max_tokens=max_tokens, verbose=False, **probe.PRODUCTION_SAMPLER)
    text = out.text if hasattr(out, "text") else str(out)
    full = "<think>" + text
    closed = "</think>" in full
    think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
    answer = full.split("</think>", 1)[-1].strip() if closed else ""
    parsed = extract_final_json(answer) if closed else None
    schema_errors = validate_answer(parsed) if parsed is not None else []
    payload = parsed if parsed is not None and not schema_errors else None
    stats = {k: getattr(out, k, None) for k in (
        "prompt_tokens", "generation_tokens", "prompt_tps", "generation_tps",
        "peak_memory", "total_tokens", "cached_tokens", "finish_reason",
    )}
    completeness = probe.classify_completion(
        stats.get("finish_reason"), stats.get("generation_tokens"), max_tokens,
        closed, parsed,
    )
    if completeness == "complete" and schema_errors:
        completeness = "malformed_schema"
    prompt_tokens_match = stats.get("prompt_tokens") == expanded
    token_accounting_match = (
        stats.get("total_tokens") == stats.get("prompt_tokens") + stats.get("generation_tokens")
        if type(stats.get("prompt_tokens")) is int and type(stats.get("generation_tokens")) is int
        else False
    )
    record = {
        "tag": tag,
        "seed": seed,
        "sampler": probe.PRODUCTION_SAMPLER,
        "reasoning_effort": probe.REASONING_EFFORT,
        "max_tokens": max_tokens,
        "messages": messages,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "images": image_meta,
        "image_grid_thw": grid_list,
        "visual_tokens": visual_tokens,
        "expanded_prompt_tokens": expanded,
        "derived_text_tokens": text_tokens,
        "initial_text_token_cap": max_input_text_tokens,
        "generator_prompt_tokens": stats.get("prompt_tokens"),
        "prompt_tokens_match": prompt_tokens_match,
        "token_accounting_match": token_accounting_match,
        "think_chars": len(think.strip()),
        "completion_contains_close": closed,
        "payload_present": payload is not None,
        "schema_errors": schema_errors,
        "completeness": completeness,
        "stats": stats,
        "wall_seconds": round(time.monotonic() - started, 1),
    }
    probe.atomic_write(run_dir / f"{tag}.trace.json",
                       {**record, "prompt": prompt, "raw": text, "think": think,
                        "answer": answer, "parsed_payload": parsed})
    probe.require(completeness != "instrument_error",
                  f"invalid generation termination metadata: {stats}")
    probe.require(prompt_tokens_match,
                  f"generator prompt tokens {stats.get('prompt_tokens')} != {expanded}")
    probe.require(token_accounting_match, "generation token-accounting mismatch")
    return record, payload, answer


def _source_visual_tokens(path: Path) -> int:
    from PIL import Image

    with Image.open(path) as image:
        return ((image.height + 15) // 16) * ((image.width + 15) // 16) // 4


def _append_result(
    feedback_items: list[dict[str, str]],
    feedback_images: list[Path],
    existing_images: list[Path],
    label: str,
    result: dict[str, Any],
    delivery_log: list[dict[str, Any]],
    *,
    image_limit: int = MAX_IMAGES,
    visual_token_limit: int = MAX_VISUAL_TOKENS,
) -> dict[str, Any]:
    """Deliver a complete result without ever leaving the visual envelope.

    Delivery is transactional.  If any page would cross a frozen limit, none of
    the result (including its text) enters model context.  The caller records the
    cell as budget-indeterminate and supplies the same neutral update used by a
    no-request round; a partial storyboard would be a silent evidence rewrite.
    """
    probe.require(type(image_limit) is int and 0 <= image_limit <= MAX_IMAGES,
                  f"invalid result image limit {image_limit!r}")
    probe.require(
        type(visual_token_limit) is int
        and 0 <= visual_token_limit <= MAX_VISUAL_TOKENS,
        f"invalid result visual-token limit {visual_token_limit!r}",
    )
    image_count = len(existing_images) + len(feedback_images)
    visual_tokens = sum(_source_visual_tokens(path) for path in existing_images + feedback_images)
    requested: list[dict[str, Any]] = []
    for raw in result.get("images") or []:
        path = Path(raw)
        cost = _source_visual_tokens(path)
        requested.append({"path": str(path), "visual_tokens": cost})
    result_fits = (
        image_count + len(requested) <= image_limit
        and visual_tokens + sum(item["visual_tokens"] for item in requested)
        <= visual_token_limit
    )
    delivered: list[str] = []
    omitted: list[dict[str, Any]] = []
    if result_fits:
        feedback_items.append({
            "type": "text",
            "text": f"{label}: " + str(result.get("text") or result.get("error", "")),
        })
        for item in requested:
            path = Path(item["path"])
            feedback_items.append({"type": "image"})
            feedback_images.append(path)
            image_count += 1
            visual_tokens += item["visual_tokens"]
            delivered.append(str(path))
    else:
        omitted = requested
    delivery = {
        "label": label,
        "result_ok": result.get("ok"),
        "result_image_count": len(delivered) + len(omitted),
        "delivered_images": delivered,
        "omitted_images": omitted,
        "all_images_delivered": result_fits,
        "image_limit": image_limit,
        "visual_token_limit": visual_token_limit,
        "context_images_after": image_count,
        "estimated_visual_tokens_after": visual_tokens,
        "model_visible": result_fits,
    }
    delivery_log.append(delivery)
    return delivery


def _probe_click(value: Any) -> Any:
    """Decode the protocol's JSON coordinate array without repairing its values."""
    return tuple(value) if isinstance(value, list) else value


def _require_observation_result(
    result: dict[str, Any], cell: dict[str, Any], session: ProbeSession,
    checkpoint,
) -> None:
    if result.get("instrument_error") is not True:
        return
    cell["probe_log"] = session.log
    cell["probes_spent"] = session.probes_spent
    cell["outcome"] = "instrument_error"
    cell["final_answer"] = None
    checkpoint(cell)
    stage = result.get("failure_stage") or "interaction"
    raise InstrumentCellError(f"Slice-4 interaction instrument failed at {stage}")


def _outcome_for(record: dict[str, Any]) -> str | None:
    completeness = record.get("completeness")
    if completeness == "complete":
        return None
    if completeness == "truncated":
        return "indeterminate_budget"
    if completeness in {"unclosed", "no_json", "malformed_schema"}:
        return "missing_malformed_or_refusal"
    raise RuntimeError(f"unexpected completion classification {completeness!r}")


def run_cell(vlm, game: str, arm: str, run_dir: Path, seed_base: int,
             dry_run: bool, max_tokens: int = MAX_ANSWER_TOKENS,
             checkpoint=lambda _cell: None) -> dict[str, Any]:
    packet = load_packet(game)
    bid = packet["blind_id"]
    tag = f"{bid}_{arm}_s{seed_base}"
    items, images = initial_turn(game, arm, packet)
    live_evidence = (
        load_packet_bound_evidence(game, packet) if arm in INTERACTIVE_ARMS else None
    )
    cell: dict[str, Any] = {
        "game_blind": bid, "arm": arm,
        "packet_manifest_sha256": packet["manifest_sha256"],
        "packet_ledger_sha256": packet["ledger_sha256"],
        "scheduled_generation_calls": INTERACTION_ROUNDS + 1,
        "per_call_max_tokens": max_tokens,
    }
    if arm == "T":
        cell["packet_pages"] = len(packet["manifest"].get("evidence_items") or [])
        cell["packet_visual_tokens"] = 0
    else:
        carrier = "raw" if arm == "V" else "overlay"
        pages = _carrier_pages(packet, carrier)
        cell["packet_pages"] = len(pages)
        cell["packet_visual_tokens"] = sum(int(p.get("visual_tokens", 0)) for p in pages)
    if dry_run:
        text_chars = sum(len(i["text"]) for i in items if i["type"] == "text")
        cell.update(dry_run=True, text_chars=text_chars, images=len(images))
        return cell

    messages = [{"role": "user", "content": items}]
    record, payload, answer = ask_chat(
        vlm, messages, images, seed=probe.seed_for(seed_base, f"{bid}_r0"),
        max_tokens=max_tokens, run_dir=run_dir, tag=tag + "_r0",
        max_input_text_tokens=MAX_INITIAL_PROMPT_TEXT_TOKENS,
    )
    cell["pre_probe_answer"] = payload
    cell["rounds"] = [record]
    cell["update_log"] = []
    checkpoint(cell)
    pending_outcome = _outcome_for(record)

    session: ProbeSession | None = None
    interaction_disabled = False
    if arm in INTERACTIVE_ARMS:
        session = ProbeSession(
            game, run_dir / f"{tag}_probe_assets", evidence=live_evidence,
            enforce_engine_identity=True,
        )
        probe.require(
            session.provenance.get("input_bundle_sha256")
            == packet["manifest"].get("input_bundle_sha256"),
            f"{game}: live probe session is not bound to the packet input bundle",
        )
        cell["delivery_log"] = []
    probe.require(
        len(NO_NEW_OBSERVATION) <= NO_NEW_OBSERVATION_MAX_CHARS,
        "neutral update text exceeds its frozen length bound",
    )
    for round_no in range(1, INTERACTION_ROUNDS + 1):
        feedback_items: list[dict[str, str]] = []
        feedback_images: list[Path] = []
        update_audit: dict[str, Any] = {
            "round": round_no,
            "input_kind": None,
            "delivered_labels": [],
            "reason_codes": [],
        }
        if arm not in INTERACTIVE_ARMS:
            update_audit["reason_codes"].append("matched_passive_arm")
        elif interaction_disabled:
            update_audit["reason_codes"].append("interaction_disabled_after_budget_failure")
        else:
            probe.require(session is not None, "interactive arm has no probe session")
            # Probe evidence is the primary intervention channel.  Deliver it before
            # retrieval and reserve one image slot for every still-possible future
            # probe.  A probe that cannot be delivered in full makes the cell
            # indeterminate.  It is not partially shown: that would rewrite evidence.
            future_probe_rounds = (
                INTERACTION_ROUNDS - round_no
                if arm in (MODEL_PROBE_ARMS | CONTROL_PROBE_ARMS)
                else 0
            )
            future_retrieval_rounds = (
                INTERACTION_ROUNDS - round_no if arm in RETRIEVAL_ARMS else 0
            )
            current_and_future_retrievals = (
                future_retrieval_rounds + 1 if arm in RETRIEVAL_ARMS else 0
            )
            probe_image_limit = (
                MAX_IMAGES - future_probe_rounds - current_and_future_retrievals
            )
            probe_visual_limit = (
                MAX_VISUAL_TOKENS
                - future_probe_rounds * PROBE_PAGE_VISUAL_RESERVE
                - current_and_future_retrievals
                * RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
            )
            retrieval_image_limit = (
                MAX_IMAGES - future_probe_rounds - future_retrieval_rounds
            )
            retrieval_visual_limit = (
                MAX_VISUAL_TOKENS
                - future_probe_rounds * PROBE_PAGE_VISUAL_RESERVE
                - future_retrieval_rounds
                * RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
            )
            probe_delivery: dict[str, Any] | None = None
            if arm in MODEL_PROBE_ARMS:
                requested = (payload or {}).get("next_probe") or {}
                action = requested.get("action")
                start = requested.get("start_state_id")
                if start is not None or action is not None:
                    action = action if isinstance(action, dict) else {}
                    result = session.probe(
                        start, action.get("id"), _probe_click(action.get("click"))
                    )
                    _require_observation_result(result, cell, session, checkpoint)
                    if result.get("ok") is True:
                        probe_delivery = _append_result(
                            feedback_items, feedback_images, images,
                            "PROBE RESULT", result, cell["delivery_log"],
                            image_limit=probe_image_limit,
                            visual_token_limit=probe_visual_limit,
                        )
                    else:
                        update_audit["reason_codes"].append("probe_result_unavailable")
                else:
                    update_audit["reason_codes"].append("no_probe_request")
            elif arm in CONTROL_PROBE_ARMS:
                result = session.control_probe(
                    round_no=round_no - 1,
                    seed=probe.seed_for(seed_base, f"{bid}_control"),
                )
                _require_observation_result(result, cell, session, checkpoint)
                if result.get("ok") is True:
                    probe_delivery = _append_result(
                        feedback_items, feedback_images, images,
                        "SEEDED CONTROL PROBE RESULT", result, cell["delivery_log"],
                        image_limit=probe_image_limit,
                        visual_token_limit=probe_visual_limit,
                    )
                else:
                    update_audit["reason_codes"].append("control_probe_result_unavailable")
            if probe_delivery is not None and not probe_delivery["all_images_delivered"]:
                update_audit["reason_codes"].append("probe_result_not_deliverable")
                pending_outcome = pending_outcome or "indeterminate_visual_budget"
                interaction_disabled = True
            elif probe_delivery is not None:
                update_audit["delivered_labels"].append(probe_delivery["label"])

            if arm in RETRIEVAL_ARMS and not interaction_disabled:
                requests = (payload or {}).get("retrieval_requests") or []
                if not requests:
                    update_audit["reason_codes"].append("no_retrieval_request")
                for request_index, req in enumerate(requests):
                    if request_index >= RETRIEVALS_PER_ROUND:
                        rejected = {
                            "kind": "retrieval", "ok": False,
                            "error": "per-round retrieval budget exhausted",
                            "request": req, "round": round_no,
                        }
                        session.log.append(rejected)
                        update_audit["reason_codes"].append("retrieval_budget_exhausted")
                        continue
                    result = session.retrieve(req.get("op"), *(req.get("args") or []))
                    _require_observation_result(result, cell, session, checkpoint)
                    if result.get("ok") is not True:
                        update_audit["reason_codes"].append("retrieval_result_unavailable")
                        continue
                    retrieval_delivery = _append_result(
                        feedback_items, feedback_images, images,
                        f"RETRIEVAL {req.get('op')}", result, cell["delivery_log"],
                        image_limit=retrieval_image_limit,
                        visual_token_limit=retrieval_visual_limit,
                    )
                    if not retrieval_delivery["all_images_delivered"]:
                        update_audit["reason_codes"].append(
                            "retrieval_result_not_deliverable"
                        )
                        pending_outcome = pending_outcome or "indeterminate_visual_budget"
                        interaction_disabled = True
                    else:
                        update_audit["delivered_labels"].append(
                            retrieval_delivery["label"]
                        )

        if not feedback_items:
            feedback_items.append({"type": "text", "text": NO_NEW_OBSERVATION})
            update_audit["input_kind"] = "neutral_no_new_observation"
        else:
            update_audit["input_kind"] = "environment_evidence"
        feedback_items.append({"type": "text", "text": UPDATE_REQUEST})
        cell["update_log"].append(update_audit)
        messages.append({"role": "assistant", "content": answer})
        messages.append({"role": "user", "content": feedback_items})
        images = images + feedback_images
        record, payload, answer = ask_chat(
            vlm, messages, images,
            seed=probe.seed_for(seed_base, f"{bid}_r{round_no}"),
            max_tokens=max_tokens, run_dir=run_dir, tag=f"{tag}_r{round_no}",
        )
        cell["rounds"].append(record)
        if session is not None:
            cell["probe_log"] = session.log
            cell["probes_spent"] = session.probes_spent
        checkpoint(cell)
        pending_outcome = pending_outcome or _outcome_for(record)

    probe.require(
        len(cell["rounds"]) == INTERACTION_ROUNDS + 1,
        "completed cell did not execute the fixed generation schedule",
    )
    if session is not None:
        cell["probe_log"] = session.log
        cell["probes_spent"] = session.probes_spent

    cell["final_answer"] = payload if pending_outcome is None else None
    cell["outcome"] = pending_outcome or "answered"
    checkpoint(cell)
    return cell


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=None)
    parser.add_argument("--arms", nargs="*", default=None, choices=list(ALL_ARMS))
    parser.add_argument("--seeds", nargs="*", type=probe.uint64_seed, default=None)
    parser.add_argument("--seed", type=probe.uint64_seed, default=None,
                        help="deprecated single-seed alias for --seeds")
    parser.add_argument("--attempt", type=int, default=0,
                        help="0 for the frozen primary run; 1 for a permitted missing-cell rerun")
    parser.add_argument("--role", choices=["qwen"], default="qwen")
    parser.add_argument("--model", type=Path, default=probe.MODEL)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="assemble every cell, count text/images, no model")
    args = parser.parse_args()
    if args.seed is not None and args.seeds is not None:
        parser.error("pass --seed or --seeds, not both")
    if args.attempt not in (0, 1):
        parser.error("--attempt must be 0 or 1")
    args.model = args.model.expanduser().resolve()
    if not args.dry_run and not args.model.is_dir():
        parser.error(f"--model is not a directory: {args.model}")

    frozen = None
    frozen_sha = None
    if args.dry_run:
        games = args.games or list(PILOT_GAMES)
        arms = args.arms or list(ALL_ARMS)
        seeds = args.seeds or ([args.seed] if args.seed is not None else [4])
        max_tokens = MAX_ANSWER_TOKENS
    else:
        frozen, frozen_sha = verify_frozen_manifest()
        prereg = frozen["preregistration"]
        frozen_games = list(prereg.get("games") or [])
        frozen_arms = list(prereg.get("arms") or [])
        frozen_seeds = list(prereg.get("seeds") or [])
        games = args.games or frozen_games
        arms = args.arms or frozen_arms
        seeds = args.seeds or ([args.seed] if args.seed is not None else frozen_seeds)
        probe.require(set(arms) <= set(ALL_ARMS), f"frozen arms unsupported by runner: {arms}")
        probe.require(set(games) <= set(frozen_games), "requested games are outside the freeze")
        probe.require(set(arms) <= set(frozen_arms), "requested arms are outside the freeze")
        probe.require(set(seeds) <= set(frozen_seeds), "requested seeds are outside the freeze")
        probe.require(args.role in (prereg.get("roles") or []),
                      f"role {args.role!r} is outside the freeze")
        expected = {
            (cell["game_blind"], cell["arm"], int(cell["seed"]))
            for cell in prereg.get("expected_cells") or []
            if cell.get("role") == args.role
        }
        blind_map = json.loads((ROOT / "logs/s4_sealed/blind_map.json").read_text())
        selected = {(blind_map[game], arm, seed) for game in games for arm in arms for seed in seeds}
        if args.attempt == 0:
            probe.require(selected == expected,
                          "primary run must execute the exact frozen role/game/arm/seed matrix")
        else:
            probe.require(selected <= expected and selected,
                          "rerun cells must be a non-empty subset of the frozen matrix")
        budgets = prereg.get("budgets") or {}
        max_tokens = budgets.get("answer_tokens")
        probe.require(type(max_tokens) is int and max_tokens > 0,
                      "frozen answer-token budget is invalid")

    probe.require(games and len(games) == len(set(games)), "games must be non-empty and unique")
    probe.require(arms and len(arms) == len(set(arms)), "arms must be non-empty and unique")
    probe.require(seeds and len(seeds) == len(set(seeds)), "seeds must be non-empty and unique")

    try:
        run_lock = acquire_run_lock(LOCK_PATH)
    except RuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    out_path = (args.out or run_dir / "cells.json").expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        run_lock.close()
        parser.error(f"output already exists; runs are append-only: {out_path}")
    manifest_path = run_dir / "run_manifest.json"

    doc: dict[str, Any] = {
        "note": "notes/qwen-3.8-slice4-design.md -> pilot runner",
        "format_version": 2,
        "status": "initializing",
        "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "argv": list(sys.argv),
        "git": probe.capture_git_state(),
        "role": args.role,
        "attempt": args.attempt,
        "games_blind": [spk.blind_id(game) for game in games],
        "arms": arms,
        "seeds": seeds,
        "run_dir": str(run_dir),
        "output_path": str(out_path),
        "frozen_manifest_sha256": frozen_sha,
        "budgets": {"answer_tokens": max_tokens,
                    "interaction_rounds": INTERACTION_ROUNDS,
                    "retrievals_per_round": RETRIEVALS_PER_ROUND,
                    "active_probes": ACTIVE_PROBES,
                    "max_images": MAX_IMAGES,
                    "max_visual_tokens": MAX_VISUAL_TOKENS},
        "interaction_preflight": [],
        "cells": [],
    }

    def persist() -> None:
        probe.atomic_write(out_path, doc)
        probe.atomic_write(manifest_path, doc)

    persist()
    try:
        # Packet integrity is checked before loading the model.
        for game in games:
            packet = load_packet(game)
            if frozen is not None:
                verify_packet_frozen(packet, frozen)
            for arm in arms:
                _, initial_images = initial_turn(game, arm, packet)
                probe.require(len(initial_images) <= MAX_IMAGES,
                              f"{game}/{arm}: initial image count exceeds cap")
                initial_visual_tokens = sum(
                    _source_visual_tokens(path) for path in initial_images
                )
                probe.require(
                    initial_visual_tokens <= MAX_VISUAL_TOKENS,
                    f"{game}/{arm}: initial visual-token count "
                    f"{initial_visual_tokens} exceeds {MAX_VISUAL_TOKENS}",
                )
                reserved_probe_pages = (
                    ACTIVE_PROBES if arm in (MODEL_PROBE_ARMS | CONTROL_PROBE_ARMS) else 0
                )
                reserved_retrieval_pages = (
                    INTERACTION_ROUNDS if arm in RETRIEVAL_ARMS else 0
                )
                reserved_images = reserved_probe_pages + reserved_retrieval_pages
                reserved_visual_tokens = (
                    reserved_probe_pages * PROBE_PAGE_VISUAL_RESERVE
                    + reserved_retrieval_pages
                    * RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
                )
                probe.require(
                    len(initial_images) <= MAX_IMAGES - reserved_images,
                    f"{game}/{arm}: packet lacks {reserved_images} interactive image slots",
                )
                probe.require(
                    initial_visual_tokens <= MAX_VISUAL_TOKENS - reserved_visual_tokens,
                    f"{game}/{arm}: packet lacks {reserved_visual_tokens} interactive "
                    "visual-token headroom",
                )
            if set(arms) & INTERACTIVE_ARMS:
                live_evidence = load_packet_bound_evidence(game, packet)
                preflight_session = ProbeSession(
                    game,
                    run_dir / "preflight" / packet["blind_id"] / "probe_assets",
                    budget=ACTIVE_PROBES,
                    evidence=live_evidence,
                    enforce_engine_identity=True,
                )
                probe.require(
                    preflight_session.provenance.get("input_bundle_sha256")
                    == packet["manifest"].get("input_bundle_sha256"),
                    f"{game}: preflight session is not bound to the packet input bundle",
                )
                replayable = preflight_session.replayable_tids()
                probe.require(replayable, f"{game}: no recapture-verified probe start states")
                capacity = preflight_session.control_capacity()
                if set(arms) & (MODEL_PROBE_ARMS | CONTROL_PROBE_ARMS):
                    probe.require(
                        capacity >= ACTIVE_PROBES,
                        f"{game}: only {capacity} distinct verified probe controls; "
                        f"need {ACTIVE_PROBES}",
                    )
                    live_engine_identity = preflight_session.verify_live_engine_identity()
                else:
                    live_engine_identity = None
                controls = []
                if set(arms) & CONTROL_PROBE_ARMS:
                    control_seed = probe.seed_for(seeds[0], f"{packet['blind_id']}_control")
                    controls = [
                        preflight_session.control_request(round_no, control_seed)
                        for round_no in range(ACTIVE_PROBES)
                    ]
                doc["interaction_preflight"].append({
                    "game_blind": packet["blind_id"],
                    "replayable_state_count": len(replayable),
                    "control_capacity": capacity,
                    "control_requests_seed0": controls,
                    "live_engine_identity": live_engine_identity,
                    "input_bundle_sha256": preflight_session.provenance.get(
                        "input_bundle_sha256"
                    ),
                    "provenance_sha256": canonical_sha256(preflight_session.provenance),
                })
                persist()

        vlm = None
        if not args.dry_run:
            doc["status"] = "verifying_certificate"
            persist()
            doc["certificate"] = verify_certificate(args.model)
            frozen_certificate = frozen.get("certificate") or {}
            probe.require(
                doc["certificate"]["certificate_sha256"]
                == frozen_certificate.get("sha256"),
                "live PASS certificate bytes differ from the frozen certificate",
            )
            probe.require(
                doc["certificate"]["checkpoint_sha256"]
                == frozen_certificate.get("checkpoint_sha256"),
                "live verified checkpoint differs from the frozen checkpoint",
            )
            doc["packet_serving_bindings"] = [
                verify_packet_serving_identity(load_packet(game), doc["certificate"])
                for game in games
            ]
            doc["runner_identity"] = {
                "script_sha256": sha256_file(Path(__file__)),
                "packet_builder_sha256": sha256_file(HARNESS / "s4_packet.py"),
                "probe_executor_sha256": sha256_file(HARNESS / "s4_probes.py"),
                "renderer_sha256": sha256_file(HARNESS / "s4_render.py"),
            }
            doc["status"] = "loading_model"
            persist()
            print(f"certificate and freeze verified; loading {args.model.name} ...", flush=True)
            vlm = probe.Vlm(args.model)

        doc["status"] = "running"
        persist()
        for seed in seeds:
            for game in games:
                for arm in arms:
                    base = {
                        "role": args.role,
                        "game_blind": spk.blind_id(game),
                        "arm": arm,
                        "seed": seed,
                        "attempt": args.attempt,
                        "status": "running",
                    }
                    slot = dict(base)
                    doc["cells"].append(slot)
                    persist()

                    def save_partial(partial: dict[str, Any]) -> None:
                        slot.clear()
                        slot.update(base)
                        slot.update(partial)
                        slot["status"] = "done" if partial.get("outcome") else "running"
                        persist()

                    try:
                        cell = run_cell(
                            vlm, game, arm, run_dir, seed, args.dry_run,
                            max_tokens=max_tokens, checkpoint=save_partial,
                        )
                        save_partial(cell)
                        if args.dry_run:
                            slot["status"] = "dry_run"
                            persist()
                    except BaseException as exc:
                        slot.update({
                            "status": "instrument_error",
                            "outcome": "instrument_error",
                            "error": {
                                "type": type(exc).__name__, "message": str(exc),
                                "traceback": traceback.format_exc(),
                            },
                        })
                        doc["status"] = "aborted_instrument"
                        doc["completed_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                        persist()
                        raise
                    print(
                        f"{game:5s} arm {arm} seed {seed}: "
                        + (f"dry text {slot['text_chars']:6,}ch images {slot['images']:2d}"
                           if args.dry_run else slot.get("outcome", "?")),
                        flush=True,
                    )
        missing = [cell for cell in doc["cells"] if cell.get("outcome") not in (None, "answered")]
        doc["status"] = "dry_run_done" if args.dry_run else ("done_with_missing" if missing else "done")
        doc["completed_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        persist()
        print(f"wrote {out_path}")
        return 0 if args.dry_run or not missing else 3
    finally:
        run_lock.close()


if __name__ == "__main__":
    sys.exit(main())
