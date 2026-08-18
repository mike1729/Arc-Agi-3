#!/usr/bin/env python3
"""Sealed Slice-4 grader with a frozen protocol and append-only adjudication.

The workflow is deliberately two phase:

1. ``--freeze`` validates and seals gold, the blind map, packets, serving
   certificate, grader/runner scripts, budgets, and the exact expected cell matrix.
2. ``--answers`` creates adjudication material exactly once.  Stage A emits one
   role-visible diagnostic worksheet.  Stage B emits two separately shuffled,
   role/cell/game/arm/seed-blinded worksheets whose judges fill independently and
   Ed25519-sign with ``--seal-adjudication``.  A no-key
   ``--commit-adjudications`` phase authenticates both complete opaque verdict trees
   and writes their receipt.  Only then may scoring load the private HMAC rejoin key
   supplied with ``--adjudication-key``; it writes a new content-addressed artifact
   and never overwrites an input.  Unsigned/v1 material fails closed.

An answered cell whose JSON does not implement the requested nested answer schema is
treated as a malformed missing observation, not as a semantic failure.  Expected but
absent cells, exhausted missing-output remedies, pending adjudications, and an
unmatched ceiling all make closure indeterminate.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import hmac
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

ROOT = Path(__file__).resolve().parents[2]
SEALED = ROOT / "logs/s4_sealed"
GOLD = SEALED / "gold"
FROZEN = SEALED / "FROZEN.json"
PACKET_ROOT = ROOT / "logs/s4_model_packet"
KAGGLE_OBSERVATIONS = ROOT / "logs/s4_observation_log/kaggle_v4"
STORE_ROOT = ROOT / "logs/e1_store_v3"
E1_OUTCOMES = ROOT / "logs/e1_outcomes_v3.json"
E1_EXPLORER = HARNESS / "e1_explorer.py"
CERTIFICATE = ROOT / "logs/e2_probe_vlm_38_8bit.json"

FORMAT_VERSION = 2
PACKET_FORMAT_VERSION = 3
PACKET_TARGET_INITIAL_PAGES = 10
PACKET_MAX_INITIAL_PAGES = 10
PACKET_MAX_TEXT_TOKENS = 12_000
PACKET_INTERACTIVE_RESULT_HEADROOM = 3
PACKET_RETRIEVAL_RESULT_HEADROOM = 3
PACKET_MIN_RESULT_PAGE_VISUAL_TOKENS = 2_112
PACKET_RESERVED_RESULT_VISUAL_TOKENS = (
    PACKET_INTERACTIVE_RESULT_HEADROOM * PACKET_MIN_RESULT_PAGE_VISUAL_TOKENS
)
PACKET_MAX_RETRIEVAL_PAGE_VISUAL_TOKENS = 1_200
PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS = (
    PACKET_RETRIEVAL_RESULT_HEADROOM * PACKET_MAX_RETRIEVAL_PAGE_VISUAL_TOKENS
)
PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS = (
    PACKET_RESERVED_RESULT_VISUAL_TOKENS + PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS
)
PACKET_MAX_INITIAL_VISUAL_TOKENS = (
    16_384 - PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS
)
PLAN_BUDGET_DEFAULT = 150
SCRIPT_RELATIVE = (
    "agent/harness/s4_run.py",
    "agent/harness/s4_packet.py",
    "agent/harness/s4_probes.py",
    "agent/harness/s4_recapture.py",
    "agent/harness/s4_grade.py",
    "agent/harness/s4_render.py",
)
DEFAULT_BUDGETS = {
    "answer_tokens": 20_000,
    "interaction_rounds": 3,
    "retrievals_per_round": 1,
    "active_probes": 3,
    "max_images": 16,
    "max_visual_tokens": 16_384,
}
RUN_BUDGET_KEYS = tuple(DEFAULT_BUDGETS)
ALL_ARMS = ("T", "V", "O", "R", "A", "C", "P")
INTERACTIVE_ARMS = frozenset({"R", "A", "C", "P"})
PILOT_GAMES = frozenset({"ls20", "ft09", "m0r0", "sp80"})
KNOWN_PRIOR_EXPOSED_GAMES = frozenset({
    "ar25", "bp35", "cd82", "cn04", "dc22", "ft09", "g50t", "ka59", "lf52",
    "lp85", "ls20", "m0r0", "r11l", "re86", "s5i5", "sb26", "sc25", "sk48",
    "sp80", "su15", "tn36", "tr87", "tu93", "vc33", "wa30",
})
STAGE_B_SELECTION_PROTOCOL = "s4-stage-b-holdout-selection-v2"
STAGE_B_SELECTION_PER_STRATUM = 3
STAGE_B_EXPOSURE_ATTESTATION = (
    "complete_known_prior_game_specific_goal_inference_and_development_exposure_"
    "before_stage_b_selection"
)
STORE_INPUT_SUFFIXES = {
    "performs": "performs.jsonl",
    "states": "states.json",
    "transitions": "transitions.jsonl",
    "graph": "graph.json",
}
AUTONOMOUS_EXPLORER_SOURCES = frozenset({"boot", "test", "walk", "reset", "confirm"})
NORMALIZED_KAGGLE_FIELDS = frozenset({
    "action", "action_num", "board", "click", "done", "game_over", "level",
    "level_completed", "reward", "score", "seq", "state", "type",
})
NORMALIZED_KAGGLE_STATES = frozenset({"NOT_FINISHED", "NOT_PLAYED", "WIN", "GAME_OVER"})
CEILING_ELIGIBLE_FAMILIARITY = ("unfamiliar", "no_prior_exposure")
STAGE_B_PRIMARY_ARM = "P"
STAGE_B_GAME_PASS_MIN_SEEDS = 2
STAGE_B_CLOSURE = {
    "qwen_max_pass_games": 0,
    "ceiling_min_pass_games": 4,
    "ceiling_min_pass_games_per_stratum": 2,
}
ADJUDICATION_PROTOCOL_VERSION = 2
ADJUDICATION_REQUIRED_JUDGES = 2
ADJUDICATION_ITEM_PREFIX = "J"
ADJUDICATION_SIGNATURE_DOMAIN = b"s4-role-blinded-adjudication-v2\x00"
ADJUDICATION_RECEIPT_TYPE = "s4_opaque_adjudication_commitment_receipt"
ADJUDICATION_INDEPENDENCE_DECLARATION = (
    "completed_without_access_to_role_or_cell_mapping_or_other_adjudicator_verdicts"
)
ADJUDICATION_AGGREGATION = {
    "rule": "unanimous_two_judges",
    "disagreement": "indeterminate_no_closure",
}
ADJUDICATION_BLINDING = {
    "item_id_scheme": "hmac-sha256-v1",
    "ordering_scheme": "hmac-sha256-v1",
    "hidden_fields": ["role", "logical_cell", "game", "arm", "seed"],
}
EXPECTED_GATE_NAMES = frozenset({
    "gate1_palette_production",
    "gate2_grey_fill_colour",
    "gate3_packet_binding",
    "gate4_spatial_grounding",
    "gate5_sampler_stability",
})
CERTIFICATE_RUNTIME_PACKAGES = ("mlx-vlm", "mlx", "mlx-lm", "transformers")
CERTIFICATE_WIRING_SAMPLER = {"temperature": 0.0, "top_p": 1.0}
CERTIFICATE_PRODUCTION_SAMPLER = {
    "temperature": 1.0, "top_p": 0.95, "top_k": 20,
}
CERTIFICATE_REASONING_EFFORT = "xhigh"
FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
TID_PATTERN = re.compile(r"(?<![A-Za-z0-9])[SK]\d{5}(?![A-Za-z0-9])", re.I)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def stage_b_generation_seeds() -> list[int]:
    """Protocol-derived generation seeds; no operator-controlled draw is admitted."""
    return [
        int.from_bytes(hashlib.sha256(
            f"{STAGE_B_SELECTION_PROTOCOL}|generation-seed|{index}".encode()
        ).digest()[:4], "big") & 0x7fff_ffff
        for index in range(3)
    ]


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"required package is not installed: {name}") from exc


def load_object(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid {label} {path}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object: {path}")
    return value


def atomic_create(path: Path, payload: Any, *, mode: int = 0o444) -> None:
    """Publish complete bytes atomically and fail if the destination already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"refusing to overwrite append-only artifact: {path}")
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise RuntimeError(f"refusing to overwrite append-only artifact: {path}") from exc
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        temporary_path.unlink(missing_ok=True)


def current_git_state() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"cannot capture git state: {exc}") from exc
    require(bool(commit), "git returned an empty commit id")
    return {"commit": commit, "dirty": bool(status), "status": status}


# --------------------------------------------------------------------------- freeze


def validate_blind_map(mapping: Any) -> dict[str, str]:
    require(isinstance(mapping, dict) and mapping, "blind_map.json must be a non-empty object")
    out: dict[str, str] = {}
    for game, blind_id in mapping.items():
        require(isinstance(game, str) and re.fullmatch(r"[A-Za-z0-9_-]+", game) is not None,
                f"invalid game key in blind map: {game!r}")
        require(isinstance(blind_id, str) and re.fullmatch(r"G[0-9a-f]{6}", blind_id) is not None,
                f"invalid blind id for {game}: {blind_id!r}")
        out[game] = blind_id
    require(len(set(out.values())) == len(out), "blind map is not one-to-one")
    return out


def read_blind_map() -> dict[str, str]:
    return validate_blind_map(load_object(SEALED / "blind_map.json", "blind map"))


def validate_board(board: Any, label: str) -> None:
    require(isinstance(board, list) and board, f"{label} must be a non-empty row list")
    width = None
    for row_index, row in enumerate(board):
        require(isinstance(row, list) and row, f"{label} row {row_index} is empty or invalid")
        width = len(row) if width is None else width
        require(len(row) == width, f"{label} is not rectangular")
        for value in row:
            require(type(value) is int and 0 <= value <= 15,
                    f"{label} contains a non-palette value: {value!r}")


def validate_gold(game: str, gold: Any) -> dict[str, Any]:
    require(isinstance(gold, dict), f"gold {game} must be an object")
    paraphrase = gold.get("paraphrase")
    require(isinstance(paraphrase, str) and paraphrase.strip(),
            f"gold {game}.paraphrase must be non-empty")
    constraints = gold.get("constraints")
    require(isinstance(constraints, list) and constraints,
            f"gold {game}.constraints must be non-empty")
    require(all(isinstance(item, str) and item.strip() for item in constraints),
            f"gold {game}.constraints must contain non-empty strings")
    require(len(set(constraints)) == len(constraints), f"gold {game}.constraints has duplicates")
    counterfactuals = gold.get("counterfactuals")
    require(isinstance(counterfactuals, list) and counterfactuals,
            f"gold {game}.counterfactuals must be non-empty")
    for index, counterfactual in enumerate(counterfactuals):
        require(isinstance(counterfactual, dict),
                f"gold {game}.counterfactuals[{index}] must be an object")
        validate_board(counterfactual.get("board"), f"gold {game}.counterfactuals[{index}].board")
        require(type(counterfactual.get("objective_holds")) is bool,
                f"gold {game}.counterfactuals[{index}].objective_holds must be boolean")
        require(isinstance(counterfactual.get("note"), str),
                f"gold {game}.counterfactuals[{index}].note must be a string")
    familiarity = gold.get("familiarity")
    require(isinstance(familiarity, str) and familiarity.strip(),
            f"gold {game}.familiarity must be a non-empty operator statement")
    if "axis_rubric" in gold:
        require(isinstance(gold["axis_rubric"], dict),
                f"gold {game}.axis_rubric must be an object")
    return gold


def snapshot_gold(mapping: dict[str, str]) -> dict[str, str]:
    require(GOLD.is_dir(), f"missing gold directory: {GOLD}")
    actual = {path.name for path in GOLD.glob("*.json")}
    expected = {f"{game}.json" for game in mapping}
    require(actual == expected,
            f"gold set mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    result: dict[str, str] = {}
    for name in sorted(actual):
        validate_gold(Path(name).stem, load_object(GOLD / name, "gold file"))
        result[name] = sha256_file(GOLD / name)
    return result


def require_full_sha256(value: Any, label: str) -> str:
    require(isinstance(value, str) and FULL_SHA256.fullmatch(value) is not None,
            f"{label} must be a full lowercase SHA-256")
    return value


def expected_e1_producer_lineage(
    game: str, performs: list[dict[str, Any]], transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconstruct the model-free E1 producer identity bound into packet/store inputs."""
    outcomes = load_object(E1_OUTCOMES, "E1 producer outcome manifest")
    require(outcomes.get("format_version") == 1 and isinstance(outcomes.get("games"), dict),
            "E1 producer outcome manifest is malformed")
    outcome = outcomes["games"].get(game)
    require(isinstance(outcome, dict) and outcome.get("game") == game,
            f"E1 producer outcome manifest lacks {game}")
    require(outcome.get("performs") == len(performs)
            and outcome.get("transitions") == len(transitions),
            f"E1 producer outcome counts disagree with the admitted {game} store")
    require(all(isinstance(row, dict)
                and row.get("source") in AUTONOMOUS_EXPLORER_SOURCES for row in performs),
            f"E1 performs store for {game} has a non-autonomous/unknown source tag")
    require(all(isinstance(row, dict)
                and row.get("source") in AUTONOMOUS_EXPLORER_SOURCES for row in transitions),
            f"E1 transition store for {game} has a non-autonomous/unknown source tag")
    observed_sources = sorted({row["source"] for row in performs})
    outcomes_identity = _file_identity(E1_OUTCOMES, "E1 producer outcome manifest")
    return {
        "actor": "deterministic_model_free_explorer",
        "action_input": "closed_internal_policy_no_human_or_model_actions",
        "explorer_script": {
            "path": "agent/harness/e1_explorer.py",
            "sha256": sha256_file(E1_EXPLORER),
        },
        "outcomes_manifest": {
            "path": "logs/e1_outcomes_v3.json",
            **outcomes_identity,
        },
        "closed_source_tags": sorted(AUTONOMOUS_EXPLORER_SOURCES),
        "observed_source_tags": observed_sources,
        "game_counts": {
            "performs": len(performs), "transitions": len(transitions),
        },
    }


def validate_sha256_fields(value: Any, label: str) -> None:
    """Reject truncated provenance hashes anywhere in a v3 identity object."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_label = f"{label}.{key}"
            if key == "sha256" or key.endswith("_sha256"):
                require_full_sha256(child, child_label)
            else:
                validate_sha256_fields(child, child_label)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_sha256_fields(child, f"{label}[{index}]")


def snapshot_packet(
    game: str, blind_id: str, certificate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet_dir = PACKET_ROOT / blind_id
    manifest_path = packet_dir / "packet_manifest.json"
    ledger_path = packet_dir / "ledger.txt"
    manifest = load_object(manifest_path, f"packet manifest for {game}")
    require(manifest.get("format_version") == PACKET_FORMAT_VERSION,
            f"packet {game} must be closure-grade format_version={PACKET_FORMAT_VERSION}")
    require(manifest.get("blind_id") == blind_id,
            f"packet {game} blind id drift: {manifest.get('blind_id')!r} != {blind_id}")

    caps = manifest.get("caps")
    expected_caps = {
        "max_images": DEFAULT_BUDGETS["max_images"],
        "max_visual_tokens": DEFAULT_BUDGETS["max_visual_tokens"],
        "max_initial_pages": PACKET_MAX_INITIAL_PAGES,
        "max_initial_visual_tokens": PACKET_MAX_INITIAL_VISUAL_TOKENS,
        "max_text_tokens": PACKET_MAX_TEXT_TOKENS,
        "interactive_result_headroom": PACKET_INTERACTIVE_RESULT_HEADROOM,
        "retrieval_result_headroom": PACKET_RETRIEVAL_RESULT_HEADROOM,
        "minimal_result_page_visual_tokens": PACKET_MIN_RESULT_PAGE_VISUAL_TOKENS,
        "reserved_minimal_result_visual_tokens": PACKET_RESERVED_RESULT_VISUAL_TOKENS,
        "max_retrieval_page_visual_tokens": PACKET_MAX_RETRIEVAL_PAGE_VISUAL_TOKENS,
        "reserved_retrieval_visual_tokens": PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS,
        "reserved_post_initial_visual_tokens": PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS,
    }
    require(caps == expected_caps,
            f"packet {game} caps differ from the closure-grade envelope")

    carrier_pages = manifest.get("carrier_pages")
    require(isinstance(carrier_pages, dict) and set(carrier_pages) == {"raw", "overlay"},
            f"packet {game} must have exactly raw and overlay page carriers")
    raw_pages, overlay_pages = carrier_pages["raw"], carrier_pages["overlay"]
    require(isinstance(raw_pages, list) and isinstance(overlay_pages, list)
            and raw_pages and len(raw_pages) == len(overlay_pages),
            f"packet {game} raw/overlay carriers must be non-empty and matched")
    page_count = len(raw_pages)
    require(manifest.get("page_count") == page_count,
            f"packet {game} page_count disagrees with its matched carriers")
    require(PACKET_TARGET_INITIAL_PAGES <= page_count <= PACKET_MAX_INITIAL_PAGES,
            f"packet {game} exceeds the frozen initial-page allocation")
    require(manifest.get("pages") == raw_pages,
            f"packet {game} v3 raw-page alias disagrees with carrier_pages.raw")

    selection = manifest.get("selection")
    require(isinstance(selection, dict), f"packet {game} selection must be an object")
    require(selection.get("algorithm_version") == PACKET_FORMAT_VERSION,
            f"packet {game} selection algorithm is not v3")
    require(selection.get("target_initial_pages") == PACKET_TARGET_INITIAL_PAGES
            and selection.get("actual_initial_pages") == page_count,
            f"packet {game} initial-page selection totals are inconsistent")
    require(type(selection.get("above_target_declared")) is bool
            and selection["above_target_declared"] == (page_count > PACKET_TARGET_INITIAL_PAGES),
            f"packet {game} does not declare above-target packet expansion exactly")
    require(selection.get("image_cap_headroom") == expected_caps["max_images"] - page_count,
            f"packet {game} image-cap headroom is inconsistent")
    require(selection.get("interactive_three_result_pages_fit") is True,
            f"packet {game} does not reserve three interactive result images")
    require(selection.get("three_retrieval_pages_fit") is True,
            f"packet {game} does not reserve three retrieval result images")
    require(selection.get("probe_and_retrieval_six_pages_fit") is True,
            f"packet {game} does not reserve all six post-initial result images")
    require(selection.get("interactive_three_minimal_result_pages_fit_token_cap") is True,
            f"packet {game} does not reserve three interactive result-page token budgets")
    require(selection.get("probe_and_retrieval_pages_fit_token_cap") is True,
            f"packet {game} does not reserve probe plus retrieval visual-token budgets")

    evidence_items = manifest.get("evidence_items")
    require(isinstance(evidence_items, list) and len(evidence_items) == page_count,
            f"packet {game} must have one matched text evidence item per page")
    page_names: list[str] = []
    page_refs_by_carrier: dict[str, list[str]] = {
        carrier: [f"page {index}" for index in range(1, page_count + 1)]
        for carrier in ("text", "raw", "overlay")
    }
    evidence_ids: set[str] = set()
    pages_dir = packet_dir / "pages"
    for carrier, pages in (("raw", raw_pages), ("overlay", overlay_pages)):
        for index, page in enumerate(pages, 1):
            require(isinstance(page, dict), f"packet {game} {carrier} page {index} metadata is invalid")
            require(page.get("page") == index,
                    f"packet {game} {carrier} page numbering is not contiguous")
            name = page.get("file")
            require(isinstance(name, str) and Path(name).name == name and bool(name),
                    f"packet {game} {carrier} page {index} has unsafe filename")
            page_path = pages_dir / name
            require(page_path.is_file(), f"packet {game} page is missing: {name}")
            digest = require_full_sha256(
                page.get("sha256"), f"packet {game} {carrier} page {index}.sha256"
            )
            require(sha256_file(page_path) == digest,
                    f"packet {game} {carrier} page {index} digest disagrees with bytes")
            require(page.get("bytes") == page_path.stat().st_size,
                    f"packet {game} {carrier} page {index} byte count is inconsistent")
            width, height = page.get("width"), page.get("height")
            require(type(width) is int and type(height) is int
                    and width >= 256 and height >= 256 and width % 32 == height % 32 == 0,
                    f"packet {game} {carrier} page {index} has invalid processor geometry")
            grid = page.get("image_grid_thw")
            require(isinstance(grid, list) and len(grid) == 3
                    and all(type(value) is int and value > 0 for value in grid)
                    and grid[0] == 1,
                    f"packet {game} {carrier} page {index} lacks processor-real image_grid_thw")
            require(page.get("processed_size") == [width, height]
                    and [grid[2] * 16, grid[1] * 16] == [width, height],
                    f"packet {game} {carrier} page {index} processor size is inconsistent")
            merged_grid = grid[0] * grid[1] * grid[2]
            require(merged_grid % 4 == 0
                    and page.get("visual_tokens") == merged_grid // 4,
                    f"packet {game} {carrier} page {index} visual-token count is inconsistent")
            require(page.get("measurement") == "processor-real",
                    f"packet {game} {carrier} page {index} is not processor-real measured")
            evidence_id = page.get("evidence_id")
            require(isinstance(evidence_id, str)
                    and re.fullmatch(r"E[0-9a-f]{12}", evidence_id) is not None,
                    f"packet {game} {carrier} page {index} has invalid evidence id")
            require(isinstance(page.get("kind"), str) and page["kind"],
                    f"packet {game} {carrier} page {index} lacks a kind")
            page_names.append(name)
            evidence_ids.add(evidence_id)
        require(len({page["file"] for page in pages}) == len(pages),
                f"packet {game} {carrier} repeats a page filename")

    require(len(set(page_names)) == len(page_names),
            f"packet {game} aliases a page file across carriers")
    for index, (raw_page, overlay_page, item) in enumerate(
        zip(raw_pages, overlay_pages, evidence_items), 1
    ):
        require(isinstance(item, dict),
                f"packet {game} evidence_items[{index - 1}] must be an object")
        require(raw_page["evidence_id"] == overlay_page["evidence_id"]
                == item.get("evidence_id"),
                f"packet {game} page {index} evidence ids are not carrier-matched")
        require(raw_page["kind"] == overlay_page["kind"] == item.get("kind"),
                f"packet {game} page {index} kinds are not carrier-matched")
        require(isinstance(item.get("text"), str) and item["text"].strip(),
                f"packet {game} evidence item {index} lacks its text carrier")
        require(isinstance(item.get("transition_refs"), list)
                and isinstance(item.get("episode_refs"), list)
                and isinstance(item.get("action_sequence"), list),
                f"packet {game} evidence item {index} has invalid provenance references")
        item_carriers = item.get("carriers")
        require(isinstance(item_carriers, dict)
                and set(item_carriers) == {"raw", "overlay", "text"},
                f"packet {game} evidence item {index} lacks matched text/raw/overlay carriers")
        for carrier, page in (("raw", raw_page), ("overlay", overlay_page)):
            binding = item_carriers[carrier]
            require(isinstance(binding, dict)
                    and binding.get("page") == index
                    and binding.get("file") == page["file"]
                    and binding.get("pages") == [page["file"]],
                    f"packet {game} evidence item {index} {carrier} binding is inconsistent")
        text_carrier = item_carriers["text"]
        require(isinstance(text_carrier, dict)
                and isinstance(text_carrier.get("boards"), list)
                and isinstance(text_carrier.get("actions"), list)
                and isinstance(text_carrier.get("derived"), list)
                and text_carrier["actions"] == item["action_sequence"],
                f"packet {game} evidence item {index} text carrier is invalid")
    require(len(evidence_ids) == page_count,
            f"packet {game} repeats an evidence id")

    actual_pages = {
        path.name for path in pages_dir.iterdir() if path.is_file()
    }
    require(actual_pages == set(page_names),
            f"packet {game} page set mismatch: missing={sorted(set(page_names)-actual_pages)}, "
            f"extra={sorted(actual_pages-set(page_names))}")

    ledger_bytes = ledger_path.read_bytes()
    ledger = ledger_bytes.decode("utf-8")
    ledger_digest = hashlib.sha256(ledger_bytes).hexdigest()
    require_full_sha256(manifest.get("ledger_sha256"), f"packet {game} ledger_sha256")
    require(manifest["ledger_sha256"] == ledger_digest,
            f"packet {game} ledger digest disagrees with manifest")
    require(manifest.get("ledger_bytes") == len(ledger_bytes),
            f"packet {game} ledger byte count is inconsistent")

    totals = manifest.get("carrier_totals")
    require(isinstance(totals, dict) and set(totals) == {"text", "raw", "overlay"},
            f"packet {game} carrier_totals must cover exactly text/raw/overlay")
    for carrier, pages in (("raw", raw_pages), ("overlay", overlay_pages)):
        total = totals[carrier]
        visual_tokens = sum(page["visual_tokens"] for page in pages)
        require(isinstance(total, dict)
                and total.get("page_count") == page_count
                and total.get("visual_tokens") == visual_tokens
                and visual_tokens <= expected_caps["max_visual_tokens"]
                and total.get("visual_token_headroom")
                == expected_caps["max_visual_tokens"] - visual_tokens
                and total.get("reserved_minimal_result_visual_tokens")
                == PACKET_RESERVED_RESULT_VISUAL_TOKENS
                and total.get("reserved_retrieval_visual_tokens")
                == PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS
                and total.get("reserved_post_initial_visual_tokens")
                == PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS
                and total.get("initial_visual_token_ceiling")
                == PACKET_MAX_INITIAL_VISUAL_TOKENS
                and total.get("processor_measurements") == "per-page image_grid_thw",
                f"packet {game} {carrier} carrier totals are inconsistent")
        require(visual_tokens <= PACKET_MAX_INITIAL_VISUAL_TOKENS
                and total["visual_token_headroom"]
                >= PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS,
                f"packet {game} {carrier} lacks probe/retrieval visual-token headroom")
    require(manifest.get("visual_tokens_total") == totals["raw"]["visual_tokens"],
            f"packet {game} legacy visual-token total disagrees with raw carrier")
    text_total = totals["text"]
    require(isinstance(text_total, dict)
            and type(text_total.get("text_tokens")) is int
            and 0 < text_total["text_tokens"] <= PACKET_MAX_TEXT_TOKENS
            and type(text_total.get("text_chars")) is int and text_total["text_chars"] > 0
            and text_total.get("measurement") == "checkpoint-tokenizer-real",
            f"packet {game} text carrier lacks a real <=12k-token total")

    inputs = manifest.get("inputs")
    require(isinstance(inputs, dict)
            and set(inputs) == {"normalized_export", "store", "recapture"},
            f"packet {game} lacks complete input provenance")
    require(isinstance(inputs["normalized_export"], dict)
            and isinstance(inputs["store"], dict) and inputs["store"]
            and isinstance(inputs["recapture"], dict),
            f"packet {game} input provenance has invalid sections")
    validate_sha256_fields(inputs, f"packet {game}.inputs")
    normalized = inputs["normalized_export"]
    require({
        "fleet_manifest_sha256", "exporter_sha256", "output_sha256", "source_sha256",
        "kept_rows", "dropped_analysis_rows", "superseded_abort",
    }.issubset(normalized), f"packet {game} lacks normalized-export provenance")
    for key in ("fleet_manifest_sha256", "exporter_sha256", "output_sha256", "source_sha256"):
        require_full_sha256(normalized.get(key), f"packet {game}.inputs.normalized_export.{key}")
    require(type(normalized.get("kept_rows")) is int and normalized["kept_rows"] > 0
            and type(normalized.get("dropped_analysis_rows")) is int
            and normalized["dropped_analysis_rows"] >= 0,
            f"packet {game} normalized-export row provenance is invalid")
    store = inputs["store"]
    require(set(store) == set(STORE_INPUT_SUFFIXES) | {"producer_lineage"},
            f"packet {game} store provenance inventory is incomplete")
    for name in STORE_INPUT_SUFFIXES:
        identity = store[name]
        require(isinstance(identity, dict)
                and set(identity) == {"sha256", "bytes"}
                and type(identity.get("bytes")) is int and identity["bytes"] >= 0,
                f"packet {game} store provenance for {name} is invalid")
        require_full_sha256(identity.get("sha256"),
                            f"packet {game}.inputs.store.{name}.sha256")
    performs = load_bound_jsonl(
        STORE_ROOT / f"{game}.{STORE_INPUT_SUFFIXES['performs']}", store["performs"],
        f"{game} performs store",
    )
    historical = load_bound_jsonl(
        STORE_ROOT / f"{game}.{STORE_INPUT_SUFFIXES['transitions']}",
        store["transitions"], f"{game} historical transitions",
    )
    require(store["producer_lineage"]
            == expected_e1_producer_lineage(game, performs, historical),
            f"packet {game} E1 producer lineage differs from the admitted live store")
    recapture = inputs["recapture"]
    require({"manifest_sha256", "manifest_bytes", "episodes", "engine_hashes", "versions"}
            .issubset(recapture), f"packet {game} lacks recapture provenance")
    require_full_sha256(recapture.get("manifest_sha256"),
                        f"packet {game}.inputs.recapture.manifest_sha256")
    require(type(recapture.get("manifest_bytes")) is int and recapture["manifest_bytes"] > 0,
            f"packet {game} recapture manifest byte count is invalid")
    episodes = recapture.get("episodes")
    require(isinstance(episodes, list) and episodes,
            f"packet {game} recapture provenance has no verified episodes")
    for index, episode in enumerate(episodes):
        require(isinstance(episode, dict) and episode.get("episode_index") == index
                and type(episode.get("bytes")) is int and episode["bytes"] > 0,
                f"packet {game} recapture episode {index} provenance is invalid")
        require_full_sha256(episode.get("sha256"),
                            f"packet {game}.inputs.recapture.episodes[{index}].sha256")
    engine_hashes = recapture.get("engine_hashes")
    require(isinstance(engine_hashes, dict)
            and {"game_source", "recapture_script"}.issubset(engine_hashes),
            f"packet {game} recapture engine/source provenance is incomplete")
    for name, digest in engine_hashes.items():
        require_full_sha256(digest,
                            f"packet {game}.inputs.recapture.engine_hashes.{name}")
    require(isinstance(recapture.get("versions"), dict),
            f"packet {game} recapture version provenance is invalid")
    require_full_sha256(manifest.get("input_bundle_sha256"),
                        f"packet {game}.input_bundle_sha256")
    require(manifest["input_bundle_sha256"] == sha256_json(inputs),
            f"packet {game} input provenance bundle digest is inconsistent")

    build = manifest.get("build_identity")
    require(isinstance(build, dict) and isinstance(build.get("packages"), dict)
            and isinstance(build.get("processor"), dict) and build["processor"],
            f"packet {game} lacks build/processor provenance")
    validate_sha256_fields(build, f"packet {game}.build_identity")
    builder_digest = require_full_sha256(
        build.get("packet_builder_sha256"), f"packet {game}.build_identity.packet_builder_sha256"
    )
    renderer_digest = require_full_sha256(
        build.get("renderer_sha256"), f"packet {game}.build_identity.renderer_sha256"
    )
    require(builder_digest == sha256_file(ROOT / "agent/harness/s4_packet.py")
            and renderer_digest == sha256_file(ROOT / "agent/harness/s4_render.py"),
            f"packet {game} was not built by the protocol scripts being frozen")
    processor = build["processor"]
    require(processor.get("implementation") == (
        "transformers.models.qwen2_vl.image_processing_pil_qwen2_vl."
        "Qwen2VLImageProcessorPil"
    ) and processor.get("patch_size") == 16 and processor.get("merge_size") == 2
            and isinstance(processor.get("tokenizer_class"), str)
            and processor["tokenizer_class"].strip()
            and isinstance(processor.get("pixel_limits"), dict),
            f"packet {game} lacks the frozen processor-real measurement identity")
    for key in (
        "preprocessor_config_sha256", "processor_config_sha256", "tokenizer_config_sha256",
    ):
        require_full_sha256(processor.get(key), f"packet {game}.build_identity.processor.{key}")
    serving_files = processor.get("serving_files")
    require(isinstance(serving_files, dict) and {
        "config.json", "tokenizer.json", "vocab.json", "merges.txt",
        "tokenizer_config.json", "chat_template.jinja", "preprocessor_config.json",
        "processor_config.json", "video_preprocessor_config.json",
        "model.safetensors.index.json",
    } == set(serving_files),
            f"packet {game} processor identity lacks serving-file provenance")
    require(processor.get("measurement_identity_sha256") == sha256_json(serving_files),
            f"packet {game} processor measurement identity digest is inconsistent")
    if certificate is not None:
        certified_files = certificate.get("checkpoint_model_files")
        require(isinstance(certified_files, dict) and certified_files,
                "serving certificate lacks checkpoint model-file identity")
        require(set(serving_files).issubset(certified_files),
                f"packet {game} used measurement files outside the certified checkpoint")
        for name, identity in serving_files.items():
            require(identity == certified_files[name],
                    f"packet {game} measurement identity drift for {name}")
        packet_transformers = (build.get("packages") or {}).get("transformers")
        certified_transformers = certificate.get("transformers_version")
        live_transformers = package_version("transformers")
        require(packet_transformers == certified_transformers == live_transformers,
                f"packet {game} tokenizer runtime differs from certified/live transformers")

    evidence_ids.update(
        match.group(0) for match in TID_PATTERN.finditer(ledger)
    )
    return {
        "game": game,
        "manifest_sha256": sha256_file(manifest_path),
        "ledger_sha256": ledger_digest,
        "pages": {name: sha256_file(pages_dir / name) for name in sorted(page_names)},
        "page_refs_by_carrier": page_refs_by_carrier,
        "evidence_ids": sorted(evidence_ids),
    }


def load_bound_jsonl(path: Path, identity: Any, label: str) -> list[dict[str, Any]]:
    require(path.is_file(), f"missing packet-bound {label}: {path}")
    require(isinstance(identity, dict), f"packet lacks {label} identity")
    expected = require_full_sha256(identity.get("sha256"), f"{label}.sha256")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected,
            f"packet-bound {label} bytes changed after packet construction")
    if "bytes" in identity:
        require(identity["bytes"] == len(raw), f"packet-bound {label} byte count drift")
    rows: list[dict[str, Any]] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"packet-bound {label} is not UTF-8") from exc
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid {label} {path}:{line_number}: {exc}") from exc
        require(isinstance(row, dict), f"invalid {label} object at {path}:{line_number}")
        rows.append(row)
    return rows


def store_completion_lengths(
    performs: list[dict[str, Any]], historical: list[dict[str, Any]], *, game: str,
) -> list[int]:
    """Completion lengths from the packet's admitted store, local to each episode/level."""
    history_by_step: dict[int, dict[str, Any]] = {}
    for index, row in enumerate(historical):
        step = row.get("step")
        require(type(step) is int and step not in history_by_step,
                f"packet-bound historical row {index} has a duplicate/invalid step for {game}")
        history_by_step[step] = row

    completions: list[int] = []
    expected_episode_step: int | None = None
    actions_since_completion = 0
    prior_levels = 0
    for index, row in enumerate(performs):
        episode_step = row.get("episode_step")
        levels = row.get("levels")
        action = row.get("action")
        step = row.get("step")
        require(type(episode_step) is int and episode_step >= 0
                and type(levels) is int and levels >= 0
                and type(step) is int and step > 0
                and isinstance(action, list) and len(action) == 3 and type(action[0]) is int,
                f"packet-bound performs row {index} is malformed for {game}")
        if episode_step == 0:
            expected_episode_step = 0
            actions_since_completion = 0
            prior_levels = 0
        require(expected_episode_step is not None and episode_step == expected_episode_step,
                f"packet-bound performs episode discontinuity for {game} at row {index}")
        expected_episode_step += 1

        # A0 is reset/initialization and never counts as a self-earned action.
        if action[0] != 0:
            actions_since_completion += 1
        historical_row = history_by_step.get(step) or {}
        if historical_row:
            for field in ("episode_step", "pre", "post"):
                require(historical_row.get(field) == row.get(field),
                        f"packet-bound historical/store disagreement for {game} step {step}")
        completed = historical_row.get("completed") is True or levels > prior_levels
        prior_levels = max(prior_levels, levels)
        if completed:
            require(actions_since_completion > 0,
                    f"packet-bound {game} reports a completion without a self-earned action")
            completions.append(actions_since_completion)
            actions_since_completion = 0
    return completions


def kaggle_completion_lengths(rows: list[dict[str, Any]], *, game: str) -> list[int]:
    """Completion lengths from normalized Kaggle history, local to reset-delimited episodes."""
    completions: list[int] = []
    actions_since_completion = 0
    in_episode = False
    previous_seq: int | None = None
    for index, row in enumerate(rows):
        action, row_type, seq = row.get("action"), row.get("type"), row.get("seq")
        require(isinstance(action, str) and (action == "RESET" or action.startswith("ACTION"))
                and row_type in {"initial", "action"}
                and type(seq) is int and seq >= 0
                and type(row.get("level_completed")) is bool,
                f"packet-bound normalized row {index} is malformed for {game}")
        if previous_seq is not None:
            require(seq == previous_seq + 1,
                    f"packet-bound normalized sequence discontinuity for {game} at row {index}")
        previous_seq = seq
        if row_type == "initial" or action == "RESET":
            in_episode = True
            actions_since_completion = 0
            continue
        require(in_episode, f"packet-bound normalized history for {game} lacks an initial boundary")
        actions_since_completion += 1
        if row["level_completed"] is True:
            completions.append(actions_since_completion)
            actions_since_completion = 0
        if row.get("state") in {"GAME_OVER", "WIN"} or row.get("game_over") is True:
            in_episode = False
            actions_since_completion = 0
    return completions


def autonomous_completion_length(game: str, blind_id: str) -> int | None:
    """Shortest packet-bound self-earned completion across store and normalized history."""
    manifest = load_object(
        PACKET_ROOT / blind_id / "packet_manifest.json", f"packet manifest for {game}"
    )
    require(manifest.get("format_version") == PACKET_FORMAT_VERSION
            and manifest.get("blind_id") == blind_id,
            f"cannot derive {game} completion stratum from a non-v3/unbound packet")
    inputs = manifest.get("inputs")
    require(isinstance(inputs, dict)
            and manifest.get("input_bundle_sha256") == sha256_json(inputs),
            f"packet {game} has invalid input provenance binding")
    normalized_identity = inputs.get("normalized_export") or {}
    store_identity = inputs.get("store") or {}
    kaggle_rows = load_bound_jsonl(
        KAGGLE_OBSERVATIONS / f"{game}.observations.jsonl",
        {"sha256": normalized_identity.get("output_sha256")},
        f"{game} normalized observations",
    )
    performs = load_bound_jsonl(
        STORE_ROOT / f"{game}.performs.jsonl", store_identity.get("performs"),
        f"{game} performs store",
    )
    historical = load_bound_jsonl(
        STORE_ROOT / f"{game}.transitions.jsonl", store_identity.get("transitions"),
        f"{game} historical transitions",
    )
    completions = (
        store_completion_lengths(performs, historical, game=game)
        + kaggle_completion_lengths(kaggle_rows, game=game)
    )
    return min(completions) if completions else None


def normalize_prior_exposure_registry(value: Any) -> dict[str, Any]:
    """Canonicalize the pre-selection disclosure of games already touched by development."""
    require(isinstance(value, dict),
            "Stage B requires a prior-development exposure registry object")
    require(set(value) == {
        "format_version", "registry_kind", "completeness_attestation", "entries",
    }, "prior-development exposure registry fields are incomplete or unexpected")
    require(value.get("format_version") == 1
            and value.get("registry_kind") == "prior_goal_inference_exposure",
            "unsupported prior-development exposure registry")
    require(value.get("completeness_attestation") == STAGE_B_EXPOSURE_ATTESTATION,
            "prior-development exposure registry lacks the required completeness attestation")
    entries = value.get("entries")
    require(isinstance(entries, list), "prior-development exposure entries must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        require(isinstance(entry, dict) and set(entry) == {"game", "reasons"},
                f"prior-development exposure entry {index} has an invalid schema")
        game, reasons = entry.get("game"), entry.get("reasons")
        require(isinstance(game, str) and game == game.strip() and bool(game)
                and re.fullmatch(r"[A-Za-z0-9_-]+", game) is not None,
                f"prior-development exposure entry {index} has an invalid game")
        require(game not in seen, f"duplicate prior-development exposure for {game}")
        seen.add(game)
        require(isinstance(reasons, list) and reasons
                and all(isinstance(reason, str) and reason == reason.strip() and bool(reason)
                        for reason in reasons),
                f"prior-development exposure for {game} requires non-empty reasons")
        require(len(reasons) == len(set(reasons)),
                f"prior-development exposure for {game} has duplicate reasons")
        normalized.append({"game": game, "reasons": sorted(reasons)})
    require(seen == KNOWN_PRIOR_EXPOSED_GAMES,
            "prior-development exposure registry game set must exactly equal the reviewed "
            f"known-prior cohort; missing={sorted(KNOWN_PRIOR_EXPOSED_GAMES - seen)}, "
            f"unexpected={sorted(seen - KNOWN_PRIOR_EXPOSED_GAMES)}")
    return {
        "format_version": 1,
        "registry_kind": "prior_goal_inference_exposure",
        "completeness_attestation": STAGE_B_EXPOSURE_ATTESTATION,
        "entries": sorted(normalized, key=lambda entry: entry["game"]),
    }


def _file_identity(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"missing {label}: {path}")
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def _validate_normalized_kaggle_rows(
    rows: list[dict[str, Any]], path: Path, *, expected_rows: int,
) -> None:
    require(len(rows) == expected_rows,
            f"normalized Kaggle row count {len(rows)} != manifest {expected_rows}: {path}")
    require(bool(rows) and rows[0].get("type") == "initial",
            f"normalized Kaggle history does not start at an initial boundary: {path}")
    for index, row in enumerate(rows):
        require(set(row) == NORMALIZED_KAGGLE_FIELDS,
                f"normalized Kaggle row {index} schema mismatch: {path}")
        require(row.get("type") in {"initial", "action"},
                f"normalized Kaggle row {index} has invalid type: {path}")
        action = row.get("action")
        require(isinstance(action, str)
                and re.fullmatch(r"RESET|ACTION[1-7]", action) is not None,
                f"normalized Kaggle row {index} has invalid action: {path}")
        require(row.get("seq") == index,
                f"normalized Kaggle row {index} has non-canonical sequence: {path}")
        board = row.get("board")
        require(isinstance(board, list) and len(board) == 64
                and all(isinstance(board_row, list) and len(board_row) == 64
                        and all(type(cell) is int and 0 <= cell <= 15 for cell in board_row)
                        for board_row in board),
                f"normalized Kaggle row {index} has an invalid 64x64 palette grid: {path}")
        click = row.get("click")
        require(click is None or (
            action == "ACTION6" and isinstance(click, list) and len(click) == 2
            and all(type(value) is int and 0 <= value < 64 for value in click)
        ), f"normalized Kaggle row {index} has an invalid click: {path}")
        require(type(row.get("action_num")) is int and row["action_num"] >= 0
                and type(row.get("level")) is int and 1 <= row["level"] <= 10
                and type(row.get("score")) is int
                and type(row.get("reward")) in {int, float}
                and row.get("state") in NORMALIZED_KAGGLE_STATES,
                f"normalized Kaggle row {index} has an invalid scalar value: {path}")
        require(all(type(row.get(flag)) is bool
                    for flag in ("done", "game_over", "level_completed")),
                f"normalized Kaggle row {index} has an invalid boolean: {path}")
        if row["type"] == "initial":
            require(action == "RESET" and click is None,
                    f"normalized Kaggle initial row {index} is not a reset: {path}")
    expected_text = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
    )
    require(path.read_text(encoding="utf-8") == expected_text,
            f"normalized Kaggle JSONL is not canonical exporter output: {path}")


def _stage_b_source_inventory() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Snapshot every game eligible at the fixed store/normalized-export cutoff."""
    fleet_path = KAGGLE_OBSERVATIONS / "manifest.json"
    fleet = load_object(fleet_path, "normalized Kaggle fleet manifest")
    fleet_identity = _file_identity(fleet_path, "normalized Kaggle fleet manifest")
    require(isinstance(fleet.get("games"), list),
            "normalized Kaggle fleet manifest has no game inventory")
    exporter_sha = require_full_sha256(
        fleet.get("exporter_sha256"), "normalized Kaggle exporter_sha256"
    )
    require(exporter_sha == sha256_file(HARNESS / "s4_export_kaggle.py"),
            "normalized Kaggle cutoff does not match the live leakage-gate exporter")

    fleet_entries: dict[str, dict[str, Any]] = {}
    fleet_totals: dict[str, int] = {}
    declared_outputs: set[str] = set()
    for index, entry in enumerate(fleet["games"]):
        require(isinstance(entry, dict),
                f"normalized Kaggle manifest game {index} is not an object")
        game = entry.get("game")
        require(isinstance(game, str) and game and game not in fleet_entries,
                f"normalized Kaggle manifest has a duplicate/invalid game at {index}")
        output = entry.get("output")
        require(output == f"{game}.observations.jsonl" and Path(output).name == output,
                f"normalized Kaggle output name is unsafe or mismatched for {game}")
        require(output not in declared_outputs,
                f"normalized Kaggle output is declared more than once: {output}")
        declared_outputs.add(output)
        require_full_sha256(entry.get("output_sha256"), f"{game} normalized output_sha256")
        require_full_sha256(entry.get("source_sha256"), f"{game} normalized source_sha256")
        rows = entry.get("rows")
        require(isinstance(rows, dict)
                and all(isinstance(kind, str) and type(count) is int and count >= 0
                        for kind, count in rows.items()),
                f"normalized Kaggle row counts are invalid for {game}")
        require(type(entry.get("kept_rows")) is int and entry["kept_rows"] >= 0
                and type(entry.get("completions")) is int and entry["completions"] >= 0,
                f"normalized Kaggle totals are invalid for {game}")
        for kind, count in rows.items():
            fleet_totals[kind] = fleet_totals.get(kind, 0) + count
        fleet_entries[game] = entry
    require(fleet.get("fleet_rows") == fleet_totals,
            "normalized Kaggle fleet totals disagree with its game entries")
    actual_outputs = {path.name for path in KAGGLE_OBSERVATIONS.glob("*.observations.jsonl")}
    require(actual_outputs == declared_outputs,
            "normalized Kaggle output inventory differs from its manifest; "
            f"missing={sorted(declared_outputs - actual_outputs)}, "
            f"extra={sorted(actual_outputs - declared_outputs)}")

    games_by_store_kind: dict[str, set[str]] = {}
    for kind, suffix in STORE_INPUT_SUFFIXES.items():
        marker = f".{suffix}"
        games_by_store_kind[kind] = {
            path.name[:-len(marker)] for path in STORE_ROOT.glob(f"*{marker}")
            if path.name.endswith(marker)
        }
    store_games = set().union(*games_by_store_kind.values())
    require(bool(store_games), "e1_store_v3 contains no games")
    for game in sorted(store_games):
        missing = [kind for kind, games in games_by_store_kind.items() if game not in games]
        require(not missing, f"e1_store_v3 game {game} lacks files: {missing}")
    missing_normalized = store_games - set(fleet_entries)
    require(not missing_normalized,
            "e1_store_v3 games are absent from the normalized Kaggle manifest: "
            f"{sorted(missing_normalized)}")

    aborted = KAGGLE_OBSERVATIONS / "ABORTED.txt"
    aborted_identity: dict[str, Any] | None = None
    if aborted.exists():
        require(aborted.stat().st_mtime_ns < fleet_path.stat().st_mtime_ns,
                "normalized export has an abort marker at or after its cutoff manifest")
        aborted_identity = {
            "present_but_superseded": True,
            "sha256": sha256_file(aborted),
        }

    inventory: list[dict[str, Any]] = []
    for game in sorted(store_games):
        fleet_entry = fleet_entries[game]
        normalized_path = KAGGLE_OBSERVATIONS / fleet_entry["output"]
        normalized_identity = {
            "fleet_manifest_sha256": fleet_identity["sha256"],
            "exporter_sha256": exporter_sha,
            "output_sha256": fleet_entry["output_sha256"],
            "source_sha256": fleet_entry["source_sha256"],
            "kept_rows": fleet_entry["kept_rows"],
            "dropped_analysis_rows": int((fleet_entry.get("rows") or {}).get("analysis", 0)),
            "superseded_abort": aborted_identity,
        }
        normalized_rows = load_bound_jsonl(
            normalized_path, {"sha256": fleet_entry["output_sha256"]},
            f"{game} normalized observations",
        )
        _validate_normalized_kaggle_rows(
            normalized_rows, normalized_path, expected_rows=fleet_entry["kept_rows"]
        )
        row_counts: dict[str, int] = {}
        for row in normalized_rows:
            row_type = row.get("type")
            row_counts[row_type] = row_counts.get(row_type, 0) + 1
        manifest_rows = fleet_entry.get("rows") or {}
        require(row_counts.get("initial", 0) == int(manifest_rows.get("initial", -1))
                and row_counts.get("action", 0) == int(manifest_rows.get("action", -1)),
                f"normalized Kaggle row-class counts drift for {game}")
        require(sum(row.get("level_completed") is True for row in normalized_rows)
                == fleet_entry["completions"],
                f"normalized Kaggle completion count drift for {game}")

        store = {
            kind: _file_identity(STORE_ROOT / f"{game}.{suffix}", f"{game} {kind} store")
            for kind, suffix in STORE_INPUT_SUFFIXES.items()
        }
        performs = load_bound_jsonl(
            STORE_ROOT / f"{game}.{STORE_INPUT_SUFFIXES['performs']}", store["performs"],
            f"{game} performs store",
        )
        transitions = load_bound_jsonl(
            STORE_ROOT / f"{game}.{STORE_INPUT_SUFFIXES['transitions']}",
            store["transitions"], f"{game} historical transitions",
        )
        store["producer_lineage"] = expected_e1_producer_lineage(
            game, performs, transitions
        )
        completions = (
            store_completion_lengths(performs, transitions, game=game)
            + kaggle_completion_lengths(normalized_rows, game=game)
        )
        completion_length = min(completions) if completions else None
        inventory.append({
            "game": game,
            "store": store,
            "normalized_export": normalized_identity,
            "autonomous_completion_length": completion_length,
            "completion_stratum": (
                "completion_exposed" if completion_length is not None
                else "completion_unexposed"
            ),
        })

    inventory_sha = sha256_json(inventory)
    source_cutoff = {
        "store_root": "logs/e1_store_v3",
        "normalized_root": "logs/s4_observation_log/kaggle_v4",
        "normalized_manifest": fleet_identity,
        "normalized_only_games": sorted(set(fleet_entries) - store_games),
        "eligible_inventory_sha256": inventory_sha,
    }
    return source_cutoff, inventory


def derive_stage_b_source_inventory_commitment() -> dict[str, Any]:
    """Create the source-only artifact that must be committed before any holdout draw."""
    source_cutoff, inventory = _stage_b_source_inventory()
    return {
        "format_version": 1,
        "artifact_type": "s4_stage_b_source_inventory_commitment",
        "protocol_constant": STAGE_B_SELECTION_PROTOCOL,
        "source_cutoff": source_cutoff,
        "source_cutoff_sha256": sha256_json(source_cutoff),
        "eligible_inventory": inventory,
        "eligible_inventory_sha256": sha256_json(inventory),
    }


def validate_stage_b_source_inventory_commitment(value: Any) -> dict[str, Any]:
    """Require an exact prior source commitment and reject any live-source drift."""
    require(isinstance(value, dict),
            "Stage B selection requires a prior immutable source-inventory commitment")
    require(set(value) == {
        "format_version", "artifact_type", "protocol_constant", "source_cutoff",
        "source_cutoff_sha256", "eligible_inventory", "eligible_inventory_sha256",
    }, "Stage B source-inventory commitment fields are incomplete or unexpected")
    require(value.get("format_version") == 1
            and value.get("artifact_type") == "s4_stage_b_source_inventory_commitment"
            and value.get("protocol_constant") == STAGE_B_SELECTION_PROTOCOL,
            "unsupported Stage B source-inventory commitment")
    expected = derive_stage_b_source_inventory_commitment()
    require(value == expected,
            "Stage B source-inventory commitment differs from the live frozen-source cutoff")
    return expected


def _verify_selected_packet_sources(
    selected_games: list[str], inventory: list[dict[str, Any]], mapping: dict[str, str],
) -> None:
    require(set(mapping) == set(selected_games) and len(mapping) == len(selected_games),
            "Stage B blind-map/preregistration games are not the exact rederived selection")
    by_game = {entry["game"]: entry for entry in inventory}
    for game in selected_games:
        blind_id = mapping[game]
        packet = load_object(
            PACKET_ROOT / blind_id / "packet_manifest.json", f"Stage B packet for {game}"
        )
        require(packet.get("format_version") == PACKET_FORMAT_VERSION
                and packet.get("blind_id") == blind_id,
                f"Stage B packet identity mismatch for {game}")
        inputs = packet.get("inputs")
        require(isinstance(inputs, dict)
                and packet.get("input_bundle_sha256") == sha256_json(inputs),
                f"Stage B packet input binding is invalid for {game}")
        require(inputs.get("store") == by_game[game]["store"],
                f"Stage B packet store sources differ from the selection cutoff for {game}")
        require(inputs.get("normalized_export") == by_game[game]["normalized_export"],
                f"Stage B packet normalized source differs from the selection cutoff for {game}")


def _preview_stage_b_selection_manifest(
    exposure_registry: Any, source_inventory_commitment: Any,
    selection_beacon_sha256: str,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Exercise ranking deterministically; this preview can never authorize closure."""
    registry = normalize_prior_exposure_registry(exposure_registry)
    commitment = validate_stage_b_source_inventory_commitment(
        source_inventory_commitment
    )
    source_cutoff = commitment["source_cutoff"]
    inventory = commitment["eligible_inventory"]
    inventory_sha = sha256_json(inventory)
    registry_sha = sha256_json(registry)
    beacon_sha = require_full_sha256(
        selection_beacon_sha256, "Stage B external selection beacon"
    )
    seed_sha = sha256_json({
        "protocol_constant": STAGE_B_SELECTION_PROTOCOL,
        "source_cutoff_sha256": sha256_json(source_cutoff),
        "eligible_inventory_sha256": inventory_sha,
        "external_selection_beacon_sha256": beacon_sha,
    })
    excluded = {entry["game"] for entry in registry["entries"]}
    ranked: dict[str, list[dict[str, Any]]] = {}
    selected_by_stratum: dict[str, list[str]] = {}
    for stratum in ("completion_exposed", "completion_unexposed"):
        candidates = [
            entry["game"] for entry in inventory
            if entry["completion_stratum"] == stratum
        ]
        ranking = sorted((
            {
                "game": game,
                "rank_sha256": hashlib.sha256(
                    f"{STAGE_B_SELECTION_PROTOCOL}|{seed_sha}|{stratum}|{game}".encode()
                ).hexdigest(),
                "excluded_prior_exposure": game in excluded,
            }
            for game in candidates
        ), key=lambda row: (row["rank_sha256"], row["game"]))
        selectable = [row for row in ranking if not row["excluded_prior_exposure"]]
        require(len(selectable) >= STAGE_B_SELECTION_PER_STRATUM,
                f"Stage B has fewer than {STAGE_B_SELECTION_PER_STRATUM} unused {stratum} "
                "games at the frozen cutoff")
        ranked[stratum] = ranking
        selected_by_stratum[stratum] = [
            row["game"] for row in selectable[:STAGE_B_SELECTION_PER_STRATUM]
        ]
    selected_games = (
        selected_by_stratum["completion_exposed"]
        + selected_by_stratum["completion_unexposed"]
    )
    manifest = {
        "format_version": 1,
        "artifact_type": "s4_stage_b_selection_manifest",
        "authorization_status": "non_authorizing_preview_pending_authenticated_beacon",
        "protocol_constant": STAGE_B_SELECTION_PROTOCOL,
        "algorithm": "sha256_rank_all_then_filter_known_exposure_first_3_per_stratum",
        "source_inventory_commitment": commitment,
        "source_inventory_commitment_sha256": sha256_json(commitment),
        "source_cutoff": source_cutoff,
        "source_cutoff_sha256": sha256_json(source_cutoff),
        "eligible_inventory": inventory,
        "eligible_inventory_sha256": inventory_sha,
        "prior_exposure_registry": registry,
        "prior_exposure_registry_sha256": registry_sha,
        "external_selection_beacon_sha256": beacon_sha,
        "selection_seed_sha256": seed_sha,
        "generation_seeds": stage_b_generation_seeds(),
        "ranking_by_stratum": ranked,
        "selected_by_stratum": selected_by_stratum,
        "selected_games": selected_games,
    }
    if mapping is not None:
        _verify_selected_packet_sources(selected_games, inventory, mapping)
    return manifest


def derive_stage_b_selection_manifest(
    exposure_registry: Any, source_inventory_commitment: Any,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fail closed until a protocol-pinned authenticated post-commitment beacon exists."""
    registry = normalize_prior_exposure_registry(exposure_registry)
    commitment = validate_stage_b_source_inventory_commitment(
        source_inventory_commitment
    )
    excluded = {entry["game"] for entry in registry["entries"]}
    for stratum in ("completion_exposed", "completion_unexposed"):
        unused = [
            entry["game"] for entry in commitment["eligible_inventory"]
            if entry["completion_stratum"] == stratum and entry["game"] not in excluded
        ]
        require(len(unused) >= STAGE_B_SELECTION_PER_STRATUM,
                f"Stage B has fewer than {STAGE_B_SELECTION_PER_STRATUM} unused {stratum} "
                "games at the frozen cutoff")
    raise RuntimeError(
        "Stage B selection is fail-closed pending a protocol-pinned, externally "
        "authenticated selection beacon released after the source-inventory commitment; "
        "the deterministic preview is non-authorizing"
    )


def logical_key(role: str, blind_id: str, arm: str, seed: int) -> str:
    return f"{role}|{blind_id}|{arm}|seed={seed}"


def _require_canonical_label(value: Any, label: str) -> str:
    require(isinstance(value, str) and value and value == value.strip(),
            f"{label} must be a non-empty, whitespace-normalized string")
    return value


def validate_ceiling_spec(value: Any) -> dict[str, Any]:
    """Validate the immutable identity and selection rule for a Stage-B ceiling."""
    require(isinstance(value, dict), "Stage B requires an immutable ceiling_spec object")
    kind = value.get("kind")
    require(kind in {"model", "blinded_human_cohort"},
            "ceiling_spec.kind must be model or blinded_human_cohort")
    identity_key = "model" if kind == "model" else "cohort"
    require(set(value) == {
        "kind", identity_key, "respondent_count", "aggregation", "familiarity_collection",
    }, f"ceiling_spec {kind} fields are incomplete or unexpected")

    count = value.get("respondent_count")
    require(type(count) is int and count == 1,
            "ceiling_spec.respondent_count must be exactly 1 for this artifact version")
    aggregation = value.get("aggregation")
    require(aggregation == {"rule": "single_respondent", "tie_rule": "not_applicable"},
            "ceiling_spec.aggregation must be single_respondent/not_applicable for this "
            "artifact version")

    expected_familiarity = (
        {
            "timing": "not_applicable",
            "scope": "model_training_exposure_unknown",
            "eligible_declarations": [],
        }
        if kind == "model" else
        {
            "timing": "before_evidence",
            "scope": "per_respondent",
            "eligible_declarations": list(CEILING_ELIGIBLE_FAMILIARITY),
        }
    )
    require(value.get("familiarity_collection") == expected_familiarity,
            "ceiling_spec familiarity policy is invalid for its ceiling kind")

    identity = value.get(identity_key)
    if kind == "model":
        require(isinstance(identity, dict)
                and set(identity) == {
                    "provider", "model_id", "checkpoint_sha256", "serving_config",
                },
                "model ceiling_spec must pin provider, model_id, checkpoint_sha256, and "
                "serving_config")
        _require_canonical_label(identity.get("provider"), "ceiling_spec.model.provider")
        _require_canonical_label(identity.get("model_id"), "ceiling_spec.model.model_id")
        require_full_sha256(
            identity.get("checkpoint_sha256"), "ceiling_spec.model.checkpoint_sha256"
        )
        require(isinstance(identity.get("serving_config"), dict)
                and bool(identity["serving_config"]),
                "ceiling_spec.model.serving_config must be a non-empty exact configuration")
    else:
        require(isinstance(identity, dict)
                and set(identity) == {
                    "cohort_id", "selection_rule", "respondent_id",
                    "roster_selection_commitment_sha256",
                },
                "human ceiling_spec must pin cohort_id, selection_rule, respondent_id, and "
                "roster/selection commitment")
        _require_canonical_label(identity.get("cohort_id"), "ceiling_spec.cohort.cohort_id")
        _require_canonical_label(
            identity.get("selection_rule"), "ceiling_spec.cohort.selection_rule"
        )
        _require_canonical_label(
            identity.get("respondent_id"), "ceiling_spec.cohort.respondent_id"
        )
        require_full_sha256(
            identity.get("roster_selection_commitment_sha256"),
            "ceiling_spec.cohort.roster_selection_commitment_sha256",
        )
    return value


def validate_adjudication_protocol(value: Any) -> dict[str, Any]:
    """Validate the frozen, role-blinded two-judge Stage-B adjudication contract."""
    require(isinstance(value, dict),
            "Stage B requires an immutable adjudication_protocol object")
    require(set(value) == {
        "format_version", "adjudicators", "blinding", "independence",
        "aggregation", "verdict_commitment",
    }, "adjudication_protocol fields are incomplete or unexpected")
    require(value.get("format_version") == ADJUDICATION_PROTOCOL_VERSION,
            "unsupported adjudication_protocol format_version")

    adjudicators = value.get("adjudicators")
    require(isinstance(adjudicators, list)
            and len(adjudicators) == ADJUDICATION_REQUIRED_JUDGES,
            f"adjudication_protocol requires exactly {ADJUDICATION_REQUIRED_JUDGES} "
            "independent adjudicators")
    ids: set[str] = set()
    commitments: set[str] = set()
    for index, adjudicator in enumerate(adjudicators):
        require(isinstance(adjudicator, dict)
                and set(adjudicator) == {
                    "adjudicator_id", "identity_commitment_sha256",
                    "ed25519_public_key_hex",
                }, f"adjudication_protocol adjudicator {index} has an invalid schema")
        adjudicator_id = _require_canonical_label(
            adjudicator.get("adjudicator_id"),
            f"adjudication_protocol.adjudicators[{index}].adjudicator_id",
        )
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", adjudicator_id) is not None,
                f"invalid adjudicator_id {adjudicator_id!r}")
        commitment = require_full_sha256(
            adjudicator.get("identity_commitment_sha256"),
            f"adjudication_protocol.adjudicators[{index}].identity_commitment_sha256",
        )
        require(adjudicator_id not in ids, "duplicate adjudicator_id in frozen protocol")
        require(commitment not in commitments,
                "adjudicator identity commitments must be distinct")
        public_key = adjudicator.get("ed25519_public_key_hex")
        require(isinstance(public_key, str)
                and re.fullmatch(r"[0-9a-f]{64}", public_key) is not None,
                f"adjudicator {adjudicator_id} requires a raw Ed25519 public key")
        require(public_key not in {
            item.get("ed25519_public_key_hex")
            for item in adjudicators[:index] if isinstance(item, dict)
        }, "adjudicator Ed25519 public keys must be distinct")
        ids.add(adjudicator_id)
        commitments.add(commitment)

    blinding = value.get("blinding")
    require(isinstance(blinding, dict)
            and set(blinding) == set(ADJUDICATION_BLINDING) | {
                "key_commitment_sha256",
            }, "adjudication_protocol.blinding has an invalid schema")
    require({key: blinding.get(key) for key in ADJUDICATION_BLINDING}
            == ADJUDICATION_BLINDING,
            "adjudication_protocol must freeze the HMAC role/cell blinding contract")
    require_full_sha256(
        blinding.get("key_commitment_sha256"),
        "adjudication_protocol.blinding.key_commitment_sha256",
    )
    require(value.get("independence") == {
        "judgments_per_primary": ADJUDICATION_REQUIRED_JUDGES,
        "other_verdicts_hidden_until_commitment": True,
        "role_and_cell_mapping_hidden_until_commitment": True,
        "rejoin_key_custodian_is_not_an_adjudicator": True,
        "separate_distribution_channels": True,
    }, "adjudication_protocol must require two judgments committed independently")
    require(value.get("aggregation") == ADJUDICATION_AGGREGATION,
            "adjudication_protocol must make every two-judge disagreement indeterminate")
    require(value.get("verdict_commitment") == {
        "algorithm": "sha256-canonical-json-v2",
        "signature_algorithm": "ed25519",
        "before_unblinding": True,
        "all_verdict_leaves_required": True,
        "commitment_receipt_required": True,
    }, "adjudication_protocol must authenticate complete opaque verdicts before unblinding")
    return value


def load_adjudication_key(
    path: Path | None, preregistration: dict[str, Any],
) -> bytes | None:
    """Load a committed HMAC key only for the grader's blinded Stage-B join."""
    if preregistration.get("stage") != "B":
        require(path is None,
                "--adjudication-key applies only to the role-blinded Stage-B workflow")
        return None
    require(path is not None and path.is_file(),
            "Stage B requires --adjudication-key with the precommitted private key file")
    raw = path.read_bytes()
    require(len(raw) >= 32, "adjudication blinding key must contain at least 32 bytes")
    expected = preregistration["adjudication_protocol"]["blinding"][
        "key_commitment_sha256"
    ]
    require(hashlib.sha256(raw).hexdigest() == expected,
            "adjudication blinding key does not match the frozen commitment")
    return raw


def normalize_preregistration(raw: Any, mapping: dict[str, str]) -> dict[str, Any]:
    require(isinstance(raw, dict), "preregistration must be a JSON object")
    config = json.loads(json.dumps(raw))
    config.setdefault("stage", "A")
    config.setdefault("games", list(mapping))
    config.setdefault("arms", list(ALL_ARMS))
    config.setdefault("seeds", [4])
    config.setdefault("roles", ["qwen"])
    config.setdefault("primary_arm", STAGE_B_PRIMARY_ARM)
    config.setdefault("budgets", dict(DEFAULT_BUDGETS))
    config.setdefault("missing_reruns", 1)
    config.setdefault("game_pass_min_seeds", 2 if len(config["seeds"]) >= 3 else 1)
    config.setdefault("closure", dict(STAGE_B_CLOSURE))
    config.setdefault("ceiling_familiarity_policy", {
        "eligible_declarations": list(CEILING_ELIGIBLE_FAMILIARITY),
    })

    stage = config["stage"]
    require(stage in {"A", "B"}, "preregistration.stage must be A or B")
    games, arms, seeds, roles = (
        config.get("games"), config.get("arms"), config.get("seeds"), config.get("roles")
    )
    require(isinstance(games, list) and games and all(isinstance(x, str) for x in games),
            "preregistration.games must be a non-empty string list")
    require(set(games) == set(mapping) and len(games) == len(mapping),
            "preregistered games must exactly equal the blind-map games")
    require(isinstance(arms, list) and arms and all(x in ALL_ARMS for x in arms),
            f"preregistration.arms must be a non-empty subset of {list(ALL_ARMS)}")
    require(isinstance(seeds, list) and seeds and all(type(x) is int and x >= 0 for x in seeds),
            "preregistration.seeds must be non-negative integers")
    require(isinstance(roles, list) and roles and all(x in {"qwen", "ceiling"} for x in roles),
            "preregistration.roles must contain qwen and/or ceiling")
    for label, values in (("games", games), ("arms", arms), ("seeds", seeds), ("roles", roles)):
        require(len(set(values)) == len(values), f"preregistration.{label} contains duplicates")
    primary_arm = config.get("primary_arm")
    require(primary_arm in arms, "preregistration.primary_arm must be one of the frozen arms")
    budgets = config.get("budgets")
    require(isinstance(budgets, dict) and set(budgets) == set(DEFAULT_BUDGETS),
            f"preregistration.budgets must contain exactly {sorted(DEFAULT_BUDGETS)}")
    require(all(type(budgets[key]) is int and budgets[key] > 0 for key in budgets),
            "all preregistered budgets must be positive integers")
    require(type(config.get("missing_reruns")) is int and config["missing_reruns"] == 1,
            "the frozen missing-output remedy must be exactly one rerun")
    require(type(config.get("game_pass_min_seeds")) is int
            and 1 <= config["game_pass_min_seeds"] <= len(seeds),
            "invalid game_pass_min_seeds")
    closure = config.get("closure")
    require(isinstance(closure, dict) and set(closure) == set(STAGE_B_CLOSURE),
            "invalid closure threshold object")
    require(all(type(value) is int and value >= 0 for value in closure.values()),
            "closure thresholds must be non-negative integers")
    familiarity_policy = config.get("ceiling_familiarity_policy")
    require(familiarity_policy == {
        "eligible_declarations": list(CEILING_ELIGIBLE_FAMILIARITY),
    }, "ceiling_familiarity_policy must freeze the exact unfamiliar/no-prior-exposure policy")
    ceiling_spec = config.get("ceiling_spec")
    supplied_ceiling_spec_sha = config.get("ceiling_spec_sha256")
    if ceiling_spec is None:
        require(stage != "B", "Stage B requires an immutable ceiling_spec object")
        require("ceiling" not in roles,
                "a preregistered ceiling role requires an immutable ceiling_spec")
        require(supplied_ceiling_spec_sha is None,
                "ceiling_spec_sha256 cannot be supplied without ceiling_spec")
    else:
        require("ceiling" in roles,
                "ceiling_spec cannot be frozen without a preregistered ceiling role")
        require("qwen" in roles,
                "a transcript-matched ceiling role requires the corresponding Qwen role")
        validate_ceiling_spec(ceiling_spec)
        ceiling_spec_sha = sha256_json(ceiling_spec)
        require(supplied_ceiling_spec_sha is None
                or supplied_ceiling_spec_sha == ceiling_spec_sha,
                "ceiling_spec_sha256 disagrees with the immutable ceiling_spec")
        config["ceiling_spec_sha256"] = ceiling_spec_sha
    adjudication_protocol = config.get("adjudication_protocol")
    supplied_adjudication_sha = config.get("adjudication_protocol_sha256")
    if stage == "B":
        validate_adjudication_protocol(adjudication_protocol)
        adjudication_sha = sha256_json(adjudication_protocol)
        require(supplied_adjudication_sha is None
                or supplied_adjudication_sha == adjudication_sha,
                "adjudication_protocol_sha256 disagrees with the immutable protocol")
        config["adjudication_protocol_sha256"] = adjudication_sha
    else:
        require(adjudication_protocol is None and supplied_adjudication_sha is None,
                "the closure-grade adjudication_protocol applies only to Stage B")
    source_inventory_commitment = config.get("stage_b_source_inventory_commitment")
    supplied_source_commitment_sha = config.get(
        "stage_b_source_inventory_commitment_sha256"
    )
    exposure_registry = config.get("stage_b_prior_exposure_registry")
    supplied_selection = config.get("stage_b_selection_manifest")
    supplied_selection_sha = config.get("stage_b_selection_manifest_sha256")
    if stage == "B":
        require(len(games) == 6 and len(seeds) == 3,
                "Stage B closure requires exactly 6 games and 3 seeds")
        require(seeds == stage_b_generation_seeds(),
                "Stage B seeds must exactly equal the ordered protocol-derived generation seeds")
        require(not (set(games) & PILOT_GAMES),
                f"Stage B games must be unused; pilot overlap={sorted(set(games) & PILOT_GAMES)}")
        require({"qwen", "ceiling"}.issubset(roles),
                "Stage B closure requires qwen and transcript-matched ceiling roles")
        require(primary_arm == STAGE_B_PRIMARY_ARM,
                f"Stage B primary_arm must be exactly {STAGE_B_PRIMARY_ARM!r}")
        require(config["game_pass_min_seeds"] == STAGE_B_GAME_PASS_MIN_SEEDS,
                "Stage B game pass threshold must be exactly 2 of 3 seeds")
        require(closure == STAGE_B_CLOSURE,
                "Stage B closure thresholds must be exactly 0 Qwen / 4 ceiling games / "
                "2 ceiling games per completion stratum")
        require(isinstance(source_inventory_commitment, dict),
                "Stage B requires a prior immutable source-inventory commitment")
        require(exposure_registry is not None,
                "Stage B requires a complete prior-development exposure registry")
        require(isinstance(supplied_selection, dict),
                "Stage B requires a frozen machine-verifiable selection manifest")
        derived_selection = derive_stage_b_selection_manifest(
            exposure_registry, source_inventory_commitment, mapping
        )
        canonical_source_commitment = derived_selection["source_inventory_commitment"]
        source_commitment_sha = sha256_json(canonical_source_commitment)
        require(supplied_source_commitment_sha is None
                or supplied_source_commitment_sha == source_commitment_sha,
                "stage_b_source_inventory_commitment_sha256 disagrees with the exact cutoff")
        require(supplied_selection == derived_selection,
                "Stage B selection manifest differs from the mechanically rederived holdout")
        selection_sha = sha256_json(derived_selection)
        require(supplied_selection_sha is None or supplied_selection_sha == selection_sha,
                "stage_b_selection_manifest_sha256 disagrees with the rederived manifest")
        require(games == derived_selection["selected_games"],
                "preregistration.games must exactly equal the mechanically selected Stage B games")
        config["stage_b_prior_exposure_registry"] = derived_selection[
            "prior_exposure_registry"
        ]
        config["stage_b_source_inventory_commitment"] = canonical_source_commitment
        config["stage_b_source_inventory_commitment_sha256"] = source_commitment_sha
        config["stage_b_selection_manifest"] = derived_selection
        config["stage_b_selection_manifest_sha256"] = selection_sha
    else:
        require(source_inventory_commitment is None and supplied_source_commitment_sha is None
                and exposure_registry is None and supplied_selection is None
                and supplied_selection_sha is None,
                "Stage-B selection artifacts cannot be attached to a Stage-A preregistration")

    derived_lengths = {
        game: autonomous_completion_length(game, mapping[game]) for game in games
    }
    supplied_lengths = config.get("autonomous_completion_lengths")
    require(supplied_lengths is None or supplied_lengths == derived_lengths,
            "supplied autonomous_completion_lengths drift from packet-bound observations")
    for game, value in derived_lengths.items():
        require(value is None or (type(value) is int and value > 0),
                f"invalid autonomous completion length for {game}")
    if stage == "B":
        cutoff_lengths = {
            entry["game"]: entry["autonomous_completion_length"]
            for entry in derived_selection["eligible_inventory"]
            if entry["game"] in mapping
        }
        require(derived_lengths == cutoff_lengths,
                "packet-bound completion strata differ from the frozen selection cutoff")
    config["autonomous_completion_lengths"] = derived_lengths
    if stage == "B":
        exposed = [game for game in games if derived_lengths[game] is not None]
        unexposed = [game for game in games if derived_lengths[game] is None]
        require(len(exposed) == 3 and len(unexposed) == 3,
                "Stage B must be stratified 3 completion-exposed / 3 unexposed; "
                f"got exposed={exposed}, unexposed={unexposed}")
    expected_budgets = {
        game: (
            2 * derived_lengths[game]
            if derived_lengths[game] is not None else PLAN_BUDGET_DEFAULT
        )
        for game in games
    }
    supplied_budgets = config.get("plan_action_budgets", expected_budgets)
    require(supplied_budgets == expected_budgets,
            f"plan_action_budgets must equal 2x completion length else {PLAN_BUDGET_DEFAULT}")
    config["plan_action_budgets"] = supplied_budgets

    required_cells = [
        {"role": role, "game_blind": mapping[game], "arm": arm, "seed": seed}
        for role in roles
        for game in games
        for arm in (arms if role == "qwen" else [primary_arm])
        for seed in seeds
    ]
    required_keys = {
        logical_key(cell["role"], cell["game_blind"], cell["arm"], cell["seed"])
        for cell in required_cells
    }
    expected_cells = config.get("expected_cells", required_cells)
    require(isinstance(expected_cells, list) and expected_cells,
            "preregistration.expected_cells must be non-empty")
    normalized_cells: list[dict[str, Any]] = []
    keys: set[str] = set()
    for index, cell in enumerate(expected_cells):
        require(isinstance(cell, dict), f"expected_cells[{index}] must be an object")
        require(set(cell) == {"role", "game_blind", "arm", "seed"},
                f"expected_cells[{index}] has unexpected/missing fields")
        role, blind_id, arm, seed = (
            cell["role"], cell["game_blind"], cell["arm"], cell["seed"]
        )
        require(role in roles and blind_id in mapping.values() and arm in arms and seed in seeds,
                f"expected_cells[{index}] is outside the declared factor levels")
        key = logical_key(role, blind_id, arm, seed)
        require(key not in keys, f"duplicate expected cell: {key}")
        keys.add(key)
        normalized_cells.append({"role": role, "game_blind": blind_id, "arm": arm, "seed": seed})
    require(keys == required_keys,
            "expected matrix must contain Qwen on every declared arm and ceiling only on "
            "the primary arm")
    config["expected_cells"] = normalized_cells
    config["expected_matrix_sha256"] = sha256_json(normalized_cells)
    return config


def default_preregistration(mapping: dict[str, str]) -> dict[str, Any]:
    return normalize_preregistration({}, mapping)


def snapshot_certificate() -> dict[str, Any]:
    certificate = load_object(CERTIFICATE, "serving certificate")
    require(certificate.get("status") == "done" and certificate.get("passed") is True,
            "serving certificate is not a completed PASS")
    require(certificate.get("verdict") == "PASS", "serving certificate is not PASS")
    gate_statuses = certificate.get("gate_statuses")
    require(isinstance(gate_statuses, dict) and set(gate_statuses) == EXPECTED_GATE_NAMES,
            "serving certificate has an incomplete or unknown gate inventory")
    require(all(status == "PASS" for status in gate_statuses.values()),
            "serving certificate contains a non-PASS gate")

    compatibility = certificate.get("serving_compatibility")
    require(isinstance(compatibility, dict),
            "serving certificate lacks serving compatibility")
    compatibility_digest = require_full_sha256(
        compatibility.get("sha256"), "serving certificate.serving_compatibility.sha256"
    )
    compatibility_payload = {
        key: value for key, value in compatibility.items() if key != "sha256"
    }
    require(compatibility_digest == sha256_json(compatibility_payload),
            "serving certificate serving-compatibility digest is invalid")

    checkpoint_identity = certificate.get("checkpoint_identity")
    require(isinstance(checkpoint_identity, dict),
            "serving certificate lacks checkpoint identity")
    checkpoint = require_full_sha256(
        compatibility.get("checkpoint_sha256"),
        "serving certificate.serving_compatibility.checkpoint_sha256",
    )
    identity_checkpoint = require_full_sha256(
        checkpoint_identity.get("checkpoint_sha256"),
        "serving certificate.checkpoint_identity.checkpoint_sha256",
    )
    model_files = checkpoint_identity.get("model_files")
    compatibility_versions = compatibility.get("versions")
    identity_versions = checkpoint_identity.get("versions")
    require(isinstance(model_files, dict) and model_files,
            "serving certificate lacks checkpoint model-file identity")
    validate_sha256_fields(model_files, "serving certificate.checkpoint_identity.model_files")

    probe_path = ROOT / "agent/harness/e2_probe_vlm.py"
    renderer_path = ROOT / "agent/harness/s4_render.py"
    require(probe_path.is_file(), f"missing live serving-gate script: {probe_path}")
    require(renderer_path.is_file(), f"missing live packet renderer: {renderer_path}")
    live_probe_sha = sha256_file(probe_path)
    live_renderer_sha = sha256_file(renderer_path)
    require(compatibility.get("script_sha") == live_probe_sha,
            "serving certificate gate script is stale")
    require(compatibility.get("renderer_sha") == live_renderer_sha,
            "serving certificate renderer is stale")

    live_versions = {
        package: package_version(package) for package in CERTIFICATE_RUNTIME_PACKAGES
    }
    require(compatibility_versions == live_versions,
            "serving certificate runtime versions differ from the live environment")
    for key, compatibility_value in (
        ("checkpoint_sha256", checkpoint),
        ("script_sha", live_probe_sha),
        ("renderer_sha", live_renderer_sha),
        ("versions", live_versions),
    ):
        require(checkpoint_identity.get(key) == compatibility_value,
                f"serving certificate checkpoint/compatibility drift for {key}")
    require(identity_checkpoint == checkpoint,
            "serving certificate checkpoint/compatibility drift for checkpoint_sha256")

    require(compatibility.get("wiring_sampler") == CERTIFICATE_WIRING_SAMPLER,
            "serving certificate wiring sampler differs from the pinned gate")
    require(compatibility.get("production_sampler") == CERTIFICATE_PRODUCTION_SAMPLER,
            "serving certificate production sampler differs from the runner")
    require(compatibility.get("reasoning_effort") == CERTIFICATE_REASONING_EFFORT,
            "serving certificate reasoning effort differs from the runner")
    experiment = compatibility.get("experiment_config")
    require(isinstance(experiment, dict),
            "serving certificate lacks experiment configuration")
    require(experiment.get("max_packet_images") == DEFAULT_BUDGETS["max_images"],
            "serving certificate image-count envelope differs from the runner")
    require(experiment.get("max_visual_tokens") == DEFAULT_BUDGETS["max_visual_tokens"],
            "serving certificate visual-token envelope differs from the runner")
    require(type(experiment.get("stability_replicates")) is int
            and experiment["stability_replicates"] >= 3
            and experiment.get("stability_required_passes")
            == experiment["stability_replicates"],
            "serving certificate production-sampler stability panel is insufficient")
    return {
        "path": str(CERTIFICATE.relative_to(ROOT)),
        "sha256": sha256_file(CERTIFICATE),
        "checkpoint_sha256": checkpoint,
        "checkpoint_model_files": model_files,
        "serving_compatibility_sha256": compatibility_digest,
        "gate_statuses": gate_statuses,
        "runtime_versions": live_versions,
        "transformers_version": identity_versions["transformers"],
    }


def freeze(preregistration_path: Path | None = None) -> int:
    require(not FROZEN.exists(), f"{FROZEN} already exists — the freeze is append-only")
    mapping = read_blind_map()
    raw_preregistration = (
        load_object(preregistration_path, "preregistration")
        if preregistration_path is not None else {}
    )
    preregistration = normalize_preregistration(raw_preregistration, mapping)
    git = current_git_state()
    require(not git["dirty"], f"refusing to freeze a dirty worktree: {git['status']}")
    scripts = {}
    for relative in SCRIPT_RELATIVE:
        path = ROOT / relative
        require(path.is_file(), f"missing protocol script: {path}")
        scripts[relative] = sha256_file(path)
    certificate = snapshot_certificate()
    payload = {
        "format_version": FORMAT_VERSION,
        "frozen_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "git_commit": git["commit"],
        "blind_map_sha256": sha256_file(SEALED / "blind_map.json"),
        "gold_files": snapshot_gold(mapping),
        "scripts": scripts,
        "certificate": certificate,
        "packets": {
            mapping[game]: snapshot_packet(game, mapping[game], certificate)
            for game in preregistration["games"]
        },
        "preregistration": preregistration,
        "preregistration_sha256": sha256_json(preregistration),
    }
    atomic_create(FROZEN, payload, mode=0o444)
    print(f"FROZEN {len(payload['gold_files'])} games at {git['commit'][:9]} "
          f"({sha256_file(FROZEN)[:12]})")
    return 0


def frozen_manifest_path() -> Path:
    """The active freeze: the versioned r4 artifact when it exists, else legacy.

    The legacy v2.2 freeze never ran in production; this dispatch keeps its code
    and tests inspectable while revision 4 owns the live protocol."""
    return FROZEN_R4 if FROZEN_R4.exists() else FROZEN


def verify_freeze() -> dict[str, Any]:
    if FROZEN_R4.exists():
        return verify_freeze_r4()
    frozen = load_object(FROZEN, "sealed freeze")
    require(frozen.get("format_version") == FORMAT_VERSION,
            f"unsupported sealed freeze version: {frozen.get('format_version')!r}")
    mapping = read_blind_map()
    require(sha256_file(SEALED / "blind_map.json") == frozen.get("blind_map_sha256"),
            "SEALED DRIFT: blind_map.json changed after freeze")
    require(snapshot_gold(mapping) == frozen.get("gold_files"),
            "SEALED DRIFT: exact gold set or digest changed after freeze")
    require(set(frozen.get("scripts") or {}) == set(SCRIPT_RELATIVE),
            "SEALED DRIFT: protocol script inventory changed")
    for relative, digest in frozen["scripts"].items():
        require(sha256_file(ROOT / relative) == digest,
                f"PROTOCOL DRIFT: {relative} changed after freeze")
    certificate = frozen.get("certificate")
    current_certificate = snapshot_certificate()
    require(isinstance(certificate, dict) and certificate == current_certificate,
            "SERVING DRIFT: certificate changed after freeze")
    preregistration = normalize_preregistration(frozen.get("preregistration"), mapping)
    require(preregistration == frozen.get("preregistration"),
            "invalid/non-canonical frozen preregistration")
    require(sha256_json(preregistration) == frozen.get("preregistration_sha256"),
            "SEALED DRIFT: preregistration digest mismatch")
    expected_packets = frozen.get("packets")
    require(isinstance(expected_packets, dict)
            and set(expected_packets) == {mapping[game] for game in preregistration["games"]},
            "SEALED DRIFT: packet inventory mismatch")
    for blind_id, expected in expected_packets.items():
        game = expected.get("game") if isinstance(expected, dict) else None
        require(isinstance(game, str) and mapping.get(game) == blind_id,
                f"invalid frozen packet binding for {blind_id}")
        require(snapshot_packet(game, blind_id, current_certificate) == expected,
                f"PACKET DRIFT: exact packet bytes changed for {blind_id}")
    git = current_git_state()
    require(not git["dirty"], f"refusing to grade a dirty worktree: {git['status']}")
    require(git["commit"] == frozen.get("git_commit"),
            f"git commit drift: {git['commit']} != {frozen.get('git_commit')}")
    return frozen


def blind_to_game(mapping: dict[str, str] | None = None) -> dict[str, str]:
    mapping = read_blind_map() if mapping is None else validate_blind_map(mapping)
    return {blind_id: game for game, blind_id in mapping.items()}


# --------------------------------------------------------------------- answer schema


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    require(isinstance(value, list), f"{label} must be a list")
    require(not nonempty or bool(value), f"{label} must be non-empty")
    require(all(isinstance(item, str) for item in value),
            f"{label} must contain strings")
    return value


def validate_answer(answer: Any) -> dict[str, Any]:
    require(isinstance(answer, dict), "final_answer must be a JSON object")
    required = {
        "hypotheses", "best_goal", "next_probe", "retrieval_requests",
        "goal_directed_plan",
    }
    require(set(answer) == required,
            f"final_answer keys must be exactly {sorted(required)}")
    hypotheses = answer.get("hypotheses")
    require(isinstance(hypotheses, list) and hypotheses, "hypotheses must be a non-empty list")
    probabilities: list[float] = []
    for index, hypothesis in enumerate(hypotheses):
        require(isinstance(hypothesis, dict), f"hypotheses[{index}] must be an object")
        hypothesis_keys = {
            "probability", "necessary_conditions", "sufficient_condition",
            "evidence_for", "evidence_against", "predicted_counterexample",
        }
        require(set(hypothesis) == hypothesis_keys,
                f"hypotheses[{index}] keys must be exactly {sorted(hypothesis_keys)}")
        probability = hypothesis.get("probability")
        require(type(probability) in {int, float} and math.isfinite(float(probability))
                and 0.0 <= float(probability) <= 1.0,
                f"hypotheses[{index}].probability must be finite and in [0,1]")
        probabilities.append(float(probability))
        _string_list(hypothesis.get("necessary_conditions"),
                     f"hypotheses[{index}].necessary_conditions")
        require(isinstance(hypothesis.get("sufficient_condition"), str)
                and hypothesis["sufficient_condition"].strip(),
                f"hypotheses[{index}].sufficient_condition must be non-empty")
        _string_list(hypothesis.get("evidence_for"), f"hypotheses[{index}].evidence_for")
        _string_list(hypothesis.get("evidence_against"),
                     f"hypotheses[{index}].evidence_against")
        require(isinstance(hypothesis.get("predicted_counterexample"), str)
                and hypothesis["predicted_counterexample"].strip(),
                f"hypotheses[{index}].predicted_counterexample must be non-empty")
    require(sum(probabilities) <= 1.0 + 1e-9, "hypothesis probabilities sum above 1")
    require(all(left >= right for left, right in zip(probabilities, probabilities[1:])),
            "hypotheses are not ranked by non-increasing probability")
    best_goal = answer.get("best_goal")
    require(isinstance(best_goal, dict)
            and set(best_goal) == {"plain_causal_condition", "structured_factors"},
            "best_goal has the wrong object schema")
    require(isinstance(best_goal.get("plain_causal_condition"), str)
            and best_goal["plain_causal_condition"].strip(),
            "best_goal.plain_causal_condition must be non-empty")
    _string_list(best_goal.get("structured_factors"), "best_goal.structured_factors")
    next_probe = answer.get("next_probe")
    require(isinstance(next_probe, dict) and set(next_probe) == {
        "start_state_id", "action", "predictions_by_hypothesis",
    }, "next_probe has the wrong object schema")
    start_state = next_probe.get("start_state_id")
    require(start_state is None or (isinstance(start_state, str) and start_state.strip()),
            "next_probe.start_state_id must be a non-empty string or null")
    probe_action = next_probe.get("action")
    require((start_state is None) == (probe_action is None),
            "next_probe start_state_id and action must both be null or both present")
    if probe_action is not None:
        require(isinstance(probe_action, dict) and set(probe_action) == {"id", "click"},
                "next_probe.action has the wrong object schema")
        # Value validity is deliberately left to the probe executor.  An invalid
        # requested id/click consumes budget and is evidence about probe use; it must
        # not erase an otherwise gradeable primary goal answer.
    predictions = next_probe.get("predictions_by_hypothesis")
    require(isinstance(predictions, dict)
            and all(isinstance(key, str) and isinstance(value, str)
                    for key, value in predictions.items()),
            "next_probe.predictions_by_hypothesis must map strings to strings")
    retrievals = answer.get("retrieval_requests")
    require(isinstance(retrievals, list), "retrieval_requests must be a list")
    for index, request in enumerate(retrievals):
        require(isinstance(request, dict) and set(request) == {"op", "args"}
                and isinstance(request.get("op"), str) and isinstance(request.get("args"), list),
                f"retrieval_requests[{index}] is malformed")
    plan = answer.get("goal_directed_plan")
    require(isinstance(plan, list), "goal_directed_plan must be a list")
    for index, step in enumerate(plan):
        require(isinstance(step, dict) and set(step) == {"action"}
                and isinstance(step.get("action"), dict)
                and set(step["action"]) == {"id", "click"},
                f"goal_directed_plan[{index}] has the wrong object schema")
    _, plan_error = validate_plan(plan)
    require(plan_error is None, plan_error or "invalid goal-directed plan")
    return answer


def answer_validation_error(answer: Any) -> str | None:
    try:
        validate_answer(answer)
    except RuntimeError as exc:
        return str(exc)
    return None


def classify_attempt(cell: dict[str, Any]) -> dict[str, Any]:
    outcome = cell.get("outcome")
    rounds = cell.get("rounds") or []
    truncated = any(
        isinstance(record, dict) and (
            record.get("finish_reason") == "length"
            or record.get("completeness") in {"truncated", "INDETERMINATE_BUDGET"}
        )
        for record in rounds
    )
    if truncated or "budget" in str(outcome).lower():
        return {"status": "missing", "missing_kind": "budget_indeterminate"}
    if outcome != "answered":
        text = str(outcome).lower()
        kind = (
            "instrument_error" if "instrument" in text
            else "refusal" if "refusal" in text
            else "malformed" if "malformed" in text
            else "missing_output"
        )
        return {"status": "missing", "missing_kind": kind}
    error = answer_validation_error(cell.get("final_answer"))
    if error is not None:
        return {"status": "missing", "missing_kind": "malformed", "schema_error": error}
    return {"status": "answered", "missing_kind": None}


# ----------------------------------------------------------------------------- axes


def valid_evidence_refs(packet: dict[str, Any], cell: dict[str, Any]) -> set[str]:
    by_carrier = packet.get("page_refs_by_carrier") or {}
    arm = cell.get("arm")
    if arm == "T":
        page_refs = by_carrier.get("text") or []
    elif arm == "V":
        page_refs = by_carrier.get("raw") or by_carrier.get("legacy") or []
    else:
        page_refs = by_carrier.get("overlay") or by_carrier.get("legacy") or []
    refs = {str(value).strip().lower() for value in page_refs}
    refs.update(str(value).strip().lower() for value in packet.get("evidence_ids", []))

    # A result log contains replay prefixes, generated asset paths, and other
    # instrument-only metadata.  It is therefore not itself a visibility record.
    # Pair successful results with the runner's successful delivery entries and
    # admit only identifiers present in delivered text, explicitly returned TID
    # lists, or the audit for an image page that was actually delivered.
    successful_results = [
        entry for entry in cell.get("probe_log") or []
        if isinstance(entry, dict) and entry.get("ok") is True
        and entry.get("kind") in {"probe", "retrieval"}
    ]
    successful_deliveries = [
        entry for entry in cell.get("delivery_log") or []
        if isinstance(entry, dict) and entry.get("result_ok") is True
    ]
    if len(successful_results) != len(successful_deliveries):
        # Missing or ambiguous delivery accounting cannot enlarge the citation
        # universe.  The frozen packet references above remain usable.
        return refs

    def add_tid(value: Any) -> None:
        if isinstance(value, str) and re.fullmatch(r"[SK]\d{5}", value, re.I):
            refs.add(value.lower())

    for result, delivery in zip(successful_results, successful_deliveries):
        text = result.get("text")
        if isinstance(text, str):
            refs.update(match.group(0).lower() for match in TID_PATTERN.finditer(text))
        for field in ("episode_tids", "history_tids"):
            values = result.get(field)
            if isinstance(values, list):
                for value in values:
                    add_tid(value)

        delivered_images = delivery.get("delivered_images")
        if (not isinstance(delivered_images, list)
                or not all(isinstance(path, str) for path in delivered_images)):
            continue
        delivered_paths = set(delivered_images)
        audits = result.get("image_audit")
        if not isinstance(audits, list):
            continue
        for audit in audits:
            if not isinstance(audit, dict) or audit.get("path") not in delivered_paths:
                continue
            for field in ("tid", "start_tid"):
                add_tid(audit.get(field))
            for field in ("tids", "episode_tids", "history_tids"):
                values = audit.get(field)
                if isinstance(values, list):
                    for value in values:
                        add_tid(value)
    return refs


def axis1_consistency(cell: dict[str, Any], allowed_refs: Iterable[str] | None = None) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    cited: list[str] = []
    for hypothesis in answer.get("hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        cited += [str(value) for value in (hypothesis.get("evidence_for") or [])]
        cited += [str(value) for value in (hypothesis.get("evidence_against") or [])]
    if allowed_refs is None:
        allowed = {f"page {index}" for index in range(1, int(cell.get("packet_pages") or 0) + 1)}
    else:
        allowed = {str(value).strip().lower() for value in allowed_refs}
    resolved = [citation for citation in cited if citation.strip().lower() in allowed]
    unresolved = [citation for citation in cited if citation.strip().lower() not in allowed]
    return {
        "cited": len(cited),
        "resolved": len(resolved),
        "unresolved": unresolved,
        "pass": bool(cited) and not unresolved,
        "note": "exact existence only; evidentiary support is adjudicated on axis 2",
    }


def axis2_worksheet(answer: dict[str, Any] | None, gold: dict[str, Any], *, terminal: bool) -> dict[str, Any]:
    answer = answer or {}
    hypotheses = answer.get("hypotheses") or []
    worksheet = {
        "model_best_goal": (answer.get("best_goal") or {}).get("plain_causal_condition"),
        "model_structured_factors": (answer.get("best_goal") or {}).get("structured_factors"),
        "model_hypotheses": [
            {
                "index": index,
                "probability": hypothesis.get("probability"),
                "necessary_conditions": hypothesis.get("necessary_conditions"),
                "sufficient_condition": hypothesis.get("sufficient_condition"),
                "evidence_for": hypothesis.get("evidence_for"),
                "evidence_against": hypothesis.get("evidence_against"),
            }
            for index, hypothesis in enumerate(hypotheses) if isinstance(hypothesis, dict)
        ],
        "sealed_paraphrase": gold["paraphrase"],
        "sealed_constraints": gold["constraints"],
        "sealed_axis_rubric": gold.get("axis_rubric"),
        "VERDICT_correct_in_kind": None,
        "VERDICT_constraints_by_item": [None] * len(gold["constraints"]),
        "VERDICT_constraints_present": None,
        "VERDICT_per_hypothesis_true": [None] * len(hypotheses),
    }
    if terminal:
        worksheet["VERDICT_terminal_evidence_present"] = None
    return worksheet


def axis3_worksheet(answer: dict[str, Any] | None, gold: dict[str, Any]) -> dict[str, Any]:
    answer = answer or {}
    hypotheses = answer.get("hypotheses") or []
    counterfactuals = gold["counterfactuals"]
    return {
        "model_conditions": [
            {
                "index": index,
                "necessary_conditions": hypothesis.get("necessary_conditions"),
                "sufficient_condition": hypothesis.get("sufficient_condition"),
                "predicted_counterexample": hypothesis.get("predicted_counterexample"),
            }
            for index, hypothesis in enumerate(hypotheses) if isinstance(hypothesis, dict)
        ],
        "sealed_counterfactuals": [
            {
                "index": index,
                "board": counterfactual["board"],
                "objective_holds": counterfactual["objective_holds"],
                "note": counterfactual["note"],
            }
            for index, counterfactual in enumerate(counterfactuals)
        ],
        "VERDICT_counterfactuals": [None] * len(counterfactuals),
        "VERDICT_survives_counterfactuals": None,
    }


def _optional_bool(value: Any, label: str) -> bool | None:
    if value is None:
        return None
    require(type(value) is bool, f"{label} must be true, false, or null")
    return value


def score_axis2(worksheet: dict[str, Any], *, terminal: bool) -> dict[str, Any]:
    correct = _optional_bool(worksheet.get("VERDICT_correct_in_kind"), "correct-in-kind verdict")
    constraint_items = worksheet.get("VERDICT_constraints_by_item")
    sealed_constraints = worksheet.get("sealed_constraints") or []
    require(isinstance(constraint_items, list) and len(constraint_items) == len(sealed_constraints),
            "per-constraint verdict count does not match sealed constraints")
    parsed_constraint_items = [
        _optional_bool(value, f"constraint verdict {index}")
        for index, value in enumerate(constraint_items)
    ]
    constraints_aggregate = _optional_bool(
        worksheet.get("VERDICT_constraints_present"), "constraint-completeness verdict"
    )
    constraints = (
        None if any(value is None for value in parsed_constraint_items)
        else all(parsed_constraint_items)
    )
    if constraints is not None and constraints_aggregate is not None:
        require(constraints_aggregate == constraints,
                "constraint aggregate verdict must equal conjunction of item verdicts")
    if constraints_aggregate is None:
        constraints = None
    verdicts = worksheet.get("VERDICT_per_hypothesis_true")
    hypotheses = worksheet.get("model_hypotheses") or []
    require(isinstance(verdicts, list) and len(verdicts) == len(hypotheses),
            "per-hypothesis verdict count does not match hypotheses")
    parsed_verdicts = [
        _optional_bool(value, f"per-hypothesis verdict {index}")
        for index, value in enumerate(verdicts)
    ]
    terminal_verdict = None
    if terminal:
        terminal_verdict = _optional_bool(
            worksheet.get("VERDICT_terminal_evidence_present"), "terminal-evidence verdict"
        )
    primary = None if correct is None or constraints is None else correct and constraints
    return {
        "status": "pending" if primary is None else "scored",
        "correct_in_kind": correct,
        "constraints_present": constraints,
        "constraints_by_item": parsed_constraint_items,
        "primary_pass": primary,
        "partial_components": sum(value is True for value in (correct, constraints)),
        "per_hypothesis_true": parsed_verdicts,
        "terminal_evidence_present": terminal_verdict,
    }


def axis4_calibration(worksheet2: dict[str, Any]) -> dict[str, Any]:
    axis2 = score_axis2(worksheet2, terminal="VERDICT_terminal_evidence_present" in worksheet2)
    verdicts = axis2["per_hypothesis_true"]
    hypotheses = worksheet2.get("model_hypotheses") or []
    if not hypotheses or any(value is None for value in verdicts):
        return {"status": "pending axis-2 per-hypothesis verdicts"}
    probabilities: list[float] = []
    for index, hypothesis in enumerate(hypotheses):
        probability = hypothesis.get("probability")
        require(type(probability) in {int, float} and math.isfinite(float(probability))
                and 0 <= float(probability) <= 1,
                f"invalid hypothesis probability at {index}")
        probabilities.append(float(probability))
    require(sum(probabilities) <= 1.0 + 1e-9, "hypothesis probabilities sum above 1")
    brier = sum(
        (probability - (1.0 if verdict else 0.0)) ** 2
        for probability, verdict in zip(probabilities, verdicts)
    ) / len(probabilities)
    top = max(range(len(probabilities)), key=probabilities.__getitem__)
    return {"status": "scored", "brier": round(brier, 4),
            "top_rank_correct": verdicts[top] is True}


def score_axis3(worksheet: dict[str, Any]) -> dict[str, Any]:
    verdicts = worksheet.get("VERDICT_counterfactuals")
    expected = worksheet.get("sealed_counterfactuals") or []
    require(isinstance(verdicts, list) and len(verdicts) == len(expected),
            "counterfactual verdict count does not match sealed counterfactuals")
    parsed = [_optional_bool(value, f"counterfactual verdict {index}")
              for index, value in enumerate(verdicts)]
    aggregate = _optional_bool(
        worksheet.get("VERDICT_survives_counterfactuals"), "counterfactual aggregate verdict"
    )
    if any(value is None for value in parsed) or aggregate is None:
        return {"status": "pending", "per_counterfactual": parsed, "pass": None}
    require(aggregate == all(parsed),
            "counterfactual aggregate verdict must equal conjunction of item verdicts")
    return {"status": "scored", "per_counterfactual": parsed, "pass": aggregate}


def validate_plan(plan: Any) -> tuple[list[tuple[int, int | None, int | None]], str | None]:
    if not isinstance(plan, list):
        return [], "goal_directed_plan is not a list"
    actions: list[tuple[int, int | None, int | None]] = []
    for index, step in enumerate(plan):
        if not isinstance(step, dict) or not isinstance(step.get("action"), dict):
            return actions, f"step {index} has no action object"
        action = step["action"]
        action_id = action.get("id")
        if type(action_id) is not int or not 0 <= action_id <= 7:
            return actions, f"step {index} action id is outside 0..7"
        click = action.get("click")
        if click is None:
            row = column = None
        elif (isinstance(click, (list, tuple)) and len(click) == 2
              and all(type(value) is int and 0 <= value < 64 for value in click)):
            row, column = click
        else:
            return actions, f"step {index} click must be null or two coordinates in 0..63"
        actions.append((action_id, row, column))
    return actions, None


def axis5_plan(cell: dict[str, Any], game: str, budget: int, execute: bool) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    plan = answer.get("goal_directed_plan")
    actions, error = validate_plan(plan)
    record: dict[str, Any] = {
        "plan_length": len(plan) if isinstance(plan, list) else None,
        "action_budget": budget,
    }
    if error is not None:
        record.update(status="invalid_plan", error=error, level_advanced=False)
        return record
    if not actions:
        record.update(status="no_plan", level_advanced=False)
        return record
    if not execute:
        record.update(status="not_executed", level_advanced=None)
        return record
    from s4_recapture import Engine  # engine is permitted only on the grading side

    try:
        engine = Engine(game)
        handle = engine.new()
        # Establish the same fixed reset state for every plan.  Reset is protocol
        # initialization, not one of the model's budgeted actions.
        initial = engine.perform(handle, (0, None, None))
        baseline = int(getattr(initial, "levels_completed", 0) or 0)
        completed = False
        steps = 0
        for action in actions[:budget]:
            response = engine.perform(handle, action)
            steps += 1
            levels_completed = int(getattr(response, "levels_completed", baseline) or 0)
            raw_state = getattr(response, "state", "")
            state = str(getattr(raw_state, "value", raw_state)).rsplit(".", 1)[-1]
            if levels_completed > baseline or state == "WIN":
                completed = True
                break
        record.update(
            status="executed",
            initialized_with_reset=True,
            steps_executed=steps,
            level_advanced=completed,
            truncated_to_budget=len(actions) > budget,
            budget_exhausted=not completed and len(actions) >= budget,
        )
    except Exception as exc:  # an engine/instrument error is not model failure
        record.update(status="instrument_error", error=f"{type(exc).__name__}: {exc}",
                      level_advanced=None)
    return record


# ------------------------------------------------------------ matrix + adjudication


def _document_role(document: dict[str, Any], preregistration: dict[str, Any]) -> str:
    role = document.get("role")
    if role is None and len(preregistration["roles"]) == 1:
        role = preregistration["roles"][0]
    require(role in preregistration["roles"],
            "answer document must declare a frozen role (qwen or ceiling)")
    return role


def _parse_utc(value: Any, label: str) -> _dt.datetime:
    require(isinstance(value, str), f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an ISO-8601 timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{label} must include a UTC offset")
    return parsed.astimezone(_dt.timezone.utc)


def _ceiling_document_cells(
    document: dict[str, Any], document_seeds: set[int],
) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for index, cell in enumerate(document["cells"]):
        require(isinstance(cell, dict), f"ceiling answer cell {index} must be an object")
        require(cell.get("role", "ceiling") == "ceiling",
                f"ceiling answer cell {index} declares a different role")
        seed = cell.get("seed")
        if seed is None and len(document_seeds) == 1:
            seed = next(iter(document_seeds))
        require(type(seed) is int and seed in document_seeds,
                f"ceiling answer cell {index} seed is absent from document metadata")
        blind_id, arm = cell.get("game_blind"), cell.get("arm")
        require(isinstance(blind_id, str) and isinstance(arm, str),
                f"ceiling answer cell {index} lacks game_blind/arm")
        cell_key = logical_key("ceiling", blind_id, arm, seed)
        require(cell_key not in expected, f"duplicate ceiling answer cell key: {cell_key}")
        expected[cell_key] = cell
    return expected


def _ceiling_input_cells(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cells = artifact.get("cells")
    require(isinstance(cells, list), "ceiling_input.cells must be a list")
    result: dict[str, dict[str, Any]] = {}
    for index, cell in enumerate(cells):
        require(isinstance(cell, dict), f"ceiling_input cell {index} must be an object")
        cell_key = _require_canonical_label(
            cell.get("ceiling_cell_key"), f"ceiling_input cell {index}.ceiling_cell_key"
        )
        require(cell_key not in result, f"duplicate ceiling_input cell key: {cell_key}")
        require_full_sha256(
            cell.get("evidence_sha256"), f"ceiling_input cell {index}.evidence_sha256"
        )
        evidence = cell.get("evidence")
        require(isinstance(evidence, dict),
                f"ceiling_input cell {index}.evidence must be an object")
        require(isinstance(evidence.get("user_messages"), list)
                and bool(evidence["user_messages"]),
                f"ceiling_input cell {index} lacks serialized user_messages")
        require(cell.get("evidence_sha256") == sha256_json(evidence),
                f"ceiling_input cell {index} evidence digest is invalid")
        result[cell_key] = cell
    return result


def validate_model_ceiling_execution_trace(
    document: dict[str, Any], preregistration: dict[str, Any], document_seeds: set[int],
    ceiling_artifact: dict[str, Any], ceiling_input_sha256: str,
) -> None:
    binding = document.get("ceiling_execution_trace")
    require(isinstance(binding, dict) and set(binding) == {"path", "sha256"},
            "model ceiling document must bind an immutable ceiling_execution_trace artifact")
    path = Path(binding.get("path", ""))
    digest = require_full_sha256(
        binding.get("sha256"), "ceiling_execution_trace.sha256"
    )
    require(path.is_file() and digest == sha256_file(path),
            "ceiling_execution_trace artifact is missing or its bytes changed")
    artifact = load_object(path, "ceiling execution trace")
    require(set(artifact) == {
        "format_version", "artifact_type", "ceiling_spec_sha256", "cells",
    } and artifact.get("format_version") == FORMAT_VERSION
            and artifact.get("artifact_type") == "s4_model_ceiling_execution_trace",
            "ceiling_execution_trace has an invalid schema or artifact type")
    spec_sha = preregistration["ceiling_spec_sha256"]
    require(artifact.get("ceiling_spec_sha256") == spec_sha,
            "ceiling_execution_trace is not bound to the frozen ceiling_spec")
    records = artifact.get("cells")
    require(isinstance(records, list), "ceiling_execution_trace.cells must be a list")
    record_by_key: dict[str, dict[str, Any]] = {}
    raw_by_key: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        require(isinstance(record, dict) and set(record) == {
            "ceiling_spec_sha256", "cell_key", "provider", "run_id", "model",
            "ceiling_input_sha256", "evidence_sha256", "prompt_messages_sha256",
            "raw_response_run_metadata", "final_answer_sha256",
        }, f"ceiling_execution_trace cell {index} has an invalid schema")
        cell_key = _require_canonical_label(
            record.get("cell_key"), f"ceiling_execution_trace cell {index}.cell_key"
        )
        require(cell_key not in record_by_key,
                f"duplicate ceiling_execution_trace cell key: {cell_key}")
        require(record.get("ceiling_spec_sha256") == spec_sha,
                f"ceiling_execution_trace cell {index} has ceiling_spec drift")
        model = preregistration["ceiling_spec"]["model"]
        require(record.get("provider") == model["provider"]
                and record.get("model") == model,
                f"ceiling_execution_trace cell {index} has model/provider drift")
        _require_canonical_label(
            record.get("run_id"), f"ceiling_execution_trace cell {index}.run_id"
        )
        require_full_sha256(
            record.get("final_answer_sha256"),
            f"ceiling_execution_trace cell {index}.final_answer_sha256",
        )
        require(record.get("ceiling_input_sha256") == ceiling_input_sha256,
                f"ceiling_execution_trace cell {index} has ceiling_input drift")
        require_full_sha256(
            record.get("evidence_sha256"),
            f"ceiling_execution_trace cell {index}.evidence_sha256",
        )
        require_full_sha256(
            record.get("prompt_messages_sha256"),
            f"ceiling_execution_trace cell {index}.prompt_messages_sha256",
        )
        raw_binding = record.get("raw_response_run_metadata")
        require(isinstance(raw_binding, dict) and set(raw_binding) == {"path", "sha256"},
                f"ceiling_execution_trace cell {index} lacks immutable raw response metadata")
        raw_path = Path(raw_binding.get("path", ""))
        raw_digest = require_full_sha256(
            raw_binding.get("sha256"),
            f"ceiling_execution_trace cell {index}.raw_response_run_metadata.sha256",
        )
        require(raw_path.is_file() and raw_digest == sha256_file(raw_path),
                f"ceiling_execution_trace cell {index} raw response metadata changed")
        raw_artifact = load_object(raw_path, "model ceiling raw execution transcript")
        require(isinstance(raw_artifact, dict) and set(raw_artifact) == {
            "format_version", "artifact_type", "ceiling_spec_sha256", "cell_key",
            "provider", "model", "run_id", "ceiling_input_sha256", "evidence_sha256",
            "prompt_messages", "raw_response", "run_metadata", "final_answer",
        } and raw_artifact.get("format_version") == FORMAT_VERSION
                and raw_artifact.get("artifact_type")
                == "s4_model_ceiling_raw_execution",
                f"ceiling_execution_trace cell {index} raw execution artifact has an "
                "invalid schema or type")
        require(raw_artifact.get("ceiling_spec_sha256") == spec_sha
                and raw_artifact.get("cell_key") == cell_key
                and raw_artifact.get("provider") == record.get("provider")
                and raw_artifact.get("model") == record.get("model")
                and raw_artifact.get("run_id") == record.get("run_id")
                and raw_artifact.get("ceiling_input_sha256") == ceiling_input_sha256
                and raw_artifact.get("evidence_sha256") == record.get("evidence_sha256"),
                f"ceiling_execution_trace cell {index} raw execution binding drift")
        require(isinstance(raw_artifact.get("prompt_messages"), list)
                and bool(raw_artifact["prompt_messages"]),
                f"ceiling_execution_trace cell {index} raw execution lacks prompt messages")
        require(isinstance(raw_artifact.get("run_metadata"), dict)
                and bool(raw_artifact["run_metadata"]),
                f"ceiling_execution_trace cell {index} raw execution lacks run metadata")
        require(raw_artifact.get("raw_response") is not None,
                f"ceiling_execution_trace cell {index} raw execution lacks raw response")
        require(record.get("prompt_messages_sha256")
                == sha256_json(raw_artifact["prompt_messages"]),
                f"ceiling_execution_trace cell {index} raw prompt/messages digest drift")
        require(record.get("final_answer_sha256")
                == sha256_json(raw_artifact.get("final_answer")),
                f"ceiling_execution_trace cell {index} raw parsed answer drift")
        record_by_key[cell_key] = record
        raw_by_key[cell_key] = raw_artifact

    expected = _ceiling_document_cells(document, document_seeds)
    input_cells = _ceiling_input_cells(ceiling_artifact)
    require(set(record_by_key) == set(expected),
            "ceiling_execution_trace cell inventory differs from the answer document")
    require(set(expected).issubset(input_cells),
            "model ceiling answer contains a cell absent from ceiling_input")
    for cell_key, cell in expected.items():
        record = record_by_key[cell_key]
        input_cell = input_cells[cell_key]
        require(record["evidence_sha256"] == input_cell["evidence_sha256"],
                f"ceiling_execution_trace evidence drift for {cell_key}")
        require(record["prompt_messages_sha256"]
                == sha256_json(input_cell["evidence"]["user_messages"]),
                f"ceiling_execution_trace prompt/messages drift for {cell_key}")
        require(raw_by_key[cell_key]["prompt_messages"]
                == input_cell["evidence"]["user_messages"],
                f"ceiling_execution_trace delivered extra or substituted messages for "
                f"{cell_key}")
        require(record["final_answer_sha256"] == sha256_json(cell.get("final_answer")),
                f"ceiling_execution_trace final_answer drift for {cell_key}")


def _primary_ceiling_cell_keys(preregistration: dict[str, Any]) -> list[str]:
    primary_arm = preregistration["primary_arm"]
    return sorted(
        logical_key("ceiling", row["game_blind"], row["arm"], row["seed"])
        for row in preregistration["expected_cells"]
        if row["role"] == "ceiling" and row["arm"] == primary_arm
    )


def _normalize_familiarity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"[\s-]+", "_", value.strip().casefold())


def build_familiarity_commitment_payload(
    draft: dict[str, Any], frozen: dict[str, Any], *, committed_utc: str | None = None,
) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    spec = preregistration.get("ceiling_spec") or {}
    require(preregistration.get("stage") == "B"
            and spec.get("kind") == "blinded_human_cohort",
            "pre-evidence familiarity commitments require a Stage-B blinded human ceiling")
    require(set(draft) == {"respondent_id", "declarations"},
            "familiarity commitment draft must contain respondent_id and declarations")
    respondent_id = spec["cohort"]["respondent_id"]
    require(draft.get("respondent_id") == respondent_id,
            "familiarity commitment respondent differs from the frozen blinded respondent")
    declarations = draft.get("declarations")
    require(isinstance(declarations, list),
            "familiarity commitment declarations must be a list")
    by_key: dict[str, str] = {}
    eligible = set(preregistration["ceiling_familiarity_policy"]["eligible_declarations"])
    for index, declaration in enumerate(declarations):
        require(isinstance(declaration, dict)
                and set(declaration) == {"cell_key", "familiarity"},
                f"familiarity declaration {index} has an invalid schema")
        cell_key = _require_canonical_label(
            declaration.get("cell_key"), f"familiarity declaration {index}.cell_key"
        )
        require(cell_key not in by_key, f"duplicate familiarity declaration: {cell_key}")
        familiarity = _normalize_familiarity(declaration.get("familiarity"))
        require(familiarity in eligible,
                f"familiarity declaration {index} is not closure-eligible before evidence")
        by_key[cell_key] = familiarity
    require(set(by_key) == set(_primary_ceiling_cell_keys(preregistration)),
            "familiarity commitment cell inventory differs from the frozen primary ceiling cells")
    timestamp = committed_utc or _dt.datetime.now(_dt.timezone.utc).isoformat()
    _parse_utc(timestamp, "familiarity commitment committed_utc")
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_pre_evidence_familiarity_commitment",
        "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
        "preregistration_sha256": frozen["preregistration_sha256"],
        "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
        "respondent_id": respondent_id,
        "committed_utc": timestamp,
        "declarations": [
            {"cell_key": cell_key, "familiarity": by_key[cell_key]}
            for cell_key in sorted(by_key)
        ],
    }


def prepare_familiarity_commitment(
    draft_path: Path, output_path: Path | None = None,
) -> Path:
    frozen = verify_freeze()
    draft = load_object(draft_path, "pre-evidence familiarity commitment draft")
    payload = build_familiarity_commitment_payload(draft, frozen)
    digest = sha256_json(payload)
    destination = output_path or draft_path.with_name(
        f"{draft_path.stem}.{digest[:12]}.familiarity_commitment.json"
    )
    atomic_create(destination, payload, mode=0o444)
    print(f"wrote append-only pre-evidence familiarity commitment {destination} "
          f"({sha256_file(destination)})")
    return destination


def validate_familiarity_commitment(
    binding: Any, frozen: dict[str, Any],
) -> tuple[dict[str, Any], _dt.datetime]:
    require(isinstance(binding, dict) and set(binding) == {"path", "sha256"},
            "human ceiling must bind a pre-evidence familiarity_commitment artifact")
    path = Path(binding.get("path", ""))
    digest = require_full_sha256(
        binding.get("sha256"), "familiarity_commitment.sha256"
    )
    require(path.is_file() and digest == sha256_file(path),
            "familiarity_commitment artifact is missing or its bytes changed")
    artifact = load_object(path, "pre-evidence familiarity commitment")
    require(set(artifact) == {
        "format_version", "artifact_type", "frozen_manifest_sha256",
        "preregistration_sha256", "ceiling_spec_sha256", "respondent_id",
        "committed_utc", "declarations",
    } and artifact.get("format_version") == FORMAT_VERSION
            and artifact.get("artifact_type") == "s4_pre_evidence_familiarity_commitment",
            "familiarity_commitment has an invalid schema or artifact type")
    preregistration = frozen["preregistration"]
    spec = preregistration["ceiling_spec"]
    require(spec["kind"] == "blinded_human_cohort",
            "model ceilings cannot supply a closure-eligible familiarity commitment")
    require(artifact.get("frozen_manifest_sha256") == sha256_file(frozen_manifest_path())
            and artifact.get("preregistration_sha256") == frozen["preregistration_sha256"]
            and artifact.get("ceiling_spec_sha256") == preregistration["ceiling_spec_sha256"],
            "familiarity_commitment is not bound to the frozen Stage-B protocol")
    require(artifact.get("respondent_id") == spec["cohort"]["respondent_id"],
            "familiarity_commitment respondent differs from the frozen blinded respondent")
    expected = build_familiarity_commitment_payload(
        {
            "respondent_id": artifact.get("respondent_id"),
            "declarations": artifact.get("declarations"),
        },
        frozen,
        committed_utc=artifact.get("committed_utc"),
    )
    require(artifact == expected,
            "familiarity_commitment content is non-canonical or incomplete")
    return artifact, _parse_utc(
        artifact["committed_utc"], "familiarity commitment committed_utc"
    )


def validate_human_ceiling_delivery_receipt(
    document: dict[str, Any], preregistration: dict[str, Any], document_seeds: set[int],
    ceiling_artifact: dict[str, Any], ceiling_input_sha256: str,
    familiarity_commitment_sha256: str,
) -> None:
    binding = document.get("ceiling_delivery_receipt")
    require(isinstance(binding, dict) and set(binding) == {"path", "sha256"},
            "human ceiling document must bind an immutable ceiling_delivery_receipt artifact")
    path = Path(binding.get("path", ""))
    digest = require_full_sha256(binding.get("sha256"), "ceiling_delivery_receipt.sha256")
    require(path.is_file() and digest == sha256_file(path),
            "ceiling_delivery_receipt artifact is missing or its bytes changed")
    artifact = load_object(path, "human ceiling delivery receipt")
    require(set(artifact) == {
        "format_version", "artifact_type", "ceiling_spec_sha256",
        "ceiling_input_sha256", "familiarity_commitment_sha256", "respondent_id", "cells",
    } and artifact.get("format_version") == FORMAT_VERSION
            and artifact.get("artifact_type") == "s4_human_ceiling_delivery_receipt",
            "ceiling_delivery_receipt has an invalid schema or artifact type")
    spec_sha = preregistration["ceiling_spec_sha256"]
    respondent_id = preregistration["ceiling_spec"]["cohort"]["respondent_id"]
    require(artifact.get("ceiling_spec_sha256") == spec_sha
            and artifact.get("ceiling_input_sha256") == ceiling_input_sha256
            and artifact.get("familiarity_commitment_sha256")
            == familiarity_commitment_sha256
            and artifact.get("respondent_id") == respondent_id,
            "ceiling_delivery_receipt protocol/respondent binding drift")
    records = artifact.get("cells")
    require(isinstance(records, list), "ceiling_delivery_receipt.cells must be a list")
    record_by_key: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        require(isinstance(record, dict) and set(record) == {
            "ceiling_spec_sha256", "familiarity_commitment_sha256", "cell_key",
            "respondent_id", "ceiling_input_sha256", "evidence_sha256", "familiarity",
            "no_extra_evidence", "final_answer_sha256",
        }, f"ceiling_delivery_receipt cell {index} has an invalid schema")
        cell_key = _require_canonical_label(
            record.get("cell_key"), f"ceiling_delivery_receipt cell {index}.cell_key"
        )
        require(cell_key not in record_by_key,
                f"duplicate ceiling_delivery_receipt cell key: {cell_key}")
        require(record.get("ceiling_spec_sha256") == spec_sha
                and record.get("familiarity_commitment_sha256")
                == familiarity_commitment_sha256
                and record.get("respondent_id") == respondent_id
                and record.get("ceiling_input_sha256") == ceiling_input_sha256,
                f"ceiling_delivery_receipt cell {index} binding drift")
        require(record.get("no_extra_evidence") is True,
                f"ceiling_delivery_receipt cell {index} does not attest no extra evidence")
        require_full_sha256(
            record.get("evidence_sha256"),
            f"ceiling_delivery_receipt cell {index}.evidence_sha256",
        )
        require_full_sha256(
            record.get("final_answer_sha256"),
            f"ceiling_delivery_receipt cell {index}.final_answer_sha256",
        )
        record_by_key[cell_key] = record
    expected = _ceiling_document_cells(document, document_seeds)
    input_cells = _ceiling_input_cells(ceiling_artifact)
    require(set(record_by_key) == set(expected),
            "ceiling_delivery_receipt cell inventory differs from the answer document")
    require(set(expected).issubset(input_cells),
            "human ceiling answer contains a cell absent from ceiling_input")
    for cell_key, cell in expected.items():
        record = record_by_key[cell_key]
        require(record["evidence_sha256"] == input_cells[cell_key]["evidence_sha256"],
                f"ceiling_delivery_receipt evidence drift for {cell_key}")
        require(_normalize_familiarity(record.get("familiarity"))
                == _normalize_familiarity(cell.get("familiarity")),
                f"ceiling_delivery_receipt familiarity drift for {cell_key}")
        require(record["final_answer_sha256"] == sha256_json(cell.get("final_answer")),
                f"ceiling_delivery_receipt final_answer drift for {cell_key}")


def validate_run_document(
    document: dict[str, Any], frozen: dict[str, Any]
) -> tuple[str, set[int], int]:
    preregistration = frozen["preregistration"]
    require(document.get("frozen_manifest_sha256") == sha256_file(frozen_manifest_path()),
            "answer document is not bound to this exact FROZEN.json")
    git = document.get("git") or {}
    require(git.get("commit") == frozen["git_commit"] and git.get("dirty") is False,
            "answer document was generated from a different or dirty git state")
    budgets = document.get("budgets")
    require(isinstance(budgets, dict) and set(budgets) == set(RUN_BUDGET_KEYS),
            f"answer document budgets must contain exactly {sorted(RUN_BUDGET_KEYS)}")
    for key in RUN_BUDGET_KEYS:
        require(budgets.get(key) == preregistration["budgets"][key],
                f"run budget drift for {key}")
    role = _document_role(document, preregistration)
    seeds = document.get("seeds")
    if seeds is None and document.get("seed_base") is not None:  # pre-v2 diagnostic compatibility
        seeds = [document["seed_base"]]
    require(isinstance(seeds, list) and seeds and len(set(seeds)) == len(seeds)
            and all(seed in preregistration["seeds"] for seed in seeds),
            "answer document seeds are invalid or not preregistered")
    attempt = document.get("attempt", 0)
    require(type(attempt) is int and 0 <= attempt <= preregistration["missing_reruns"],
            "answer document attempt is invalid")
    arms = document.get("arms")
    require(isinstance(arms, list) and len(set(arms)) == len(arms)
            and set(arms).issubset(preregistration["arms"]),
            "answer document arms are invalid or outside the preregistration")
    require(isinstance(document.get("cells"), list), "answer document cells must be a list")
    if role == "qwen":
        if "serving_snapshot" in frozen:  # revision 4: snapshot-bound identity
            snapshot = frozen["serving_snapshot"]
            identity = document.get("serving_identity") or {}
            require(identity.get("checkpoint_sha256")
                    == snapshot["checkpoint_fingerprint"]["checkpoint_sha256"],
                    "answer document checkpoint differs from the frozen serving "
                    "snapshot")
            require(identity.get("verified_shards") is True,
                    "answer run did not verify local checkpoint shards")
            require(identity.get("snapshot_sha256") == snapshot["snapshot_sha256"],
                    "answer document serving snapshot digest differs from the freeze")
        else:
            certificate = document.get("certificate") or {}
            require(certificate.get("checkpoint_sha256") == frozen["certificate"]["checkpoint_sha256"],
                    "answer document checkpoint does not match the frozen serving certificate")
            require(certificate.get("certificate_sha256") == frozen["certificate"]["sha256"],
                    "answer document serving certificate bytes do not match the freeze")
            require(certificate.get("certificate_verified_shards") is True,
                    "answer run did not verify local checkpoint shards")
    elif role == "ceiling":
        stage_label = f"Stage-{preregistration['stage']}"
        ceiling_spec = preregistration.get("ceiling_spec")
        require(isinstance(ceiling_spec, dict),
                f"{stage_label} ceiling document has no frozen ceiling_spec")
        require(preregistration["stage"] == "B" or ceiling_spec.get("kind") == "model",
                "Stage-A transcript-matched ceilings support only a descriptive model "
                "comparator")
        require(document.get("ceiling_spec") == preregistration["ceiling_spec"],
                f"{stage_label} ceiling document does not declare the frozen ceiling_spec")
        require(document.get("ceiling_spec_sha256")
                == preregistration["ceiling_spec_sha256"],
                f"{stage_label} ceiling document ceiling_spec digest mismatch")
        ceiling_input = document.get("ceiling_input")
        require(isinstance(ceiling_input, dict) and set(ceiling_input) == {"path", "sha256"},
                f"{stage_label} ceiling document must bind an immutable ceiling_input artifact")
        ceiling_path = Path(ceiling_input.get("path", ""))
        ceiling_input_sha = require_full_sha256(
            ceiling_input.get("sha256"), f"{stage_label} ceiling_input.sha256"
        )
        require(ceiling_path.is_file() and ceiling_input_sha == sha256_file(ceiling_path),
                f"{stage_label} ceiling_input artifact is missing or its bytes changed")
        ceiling_artifact = load_object(ceiling_path, "ceiling input artifact")
        require(set(ceiling_artifact) == {
            "format_version", "artifact_type", "frozen_manifest_sha256",
            "preregistration_sha256", "ceiling_spec", "ceiling_spec_sha256",
            "ceiling_familiarity_policy", "released_utc", "closure_eligibility",
            "respondent_id", "familiarity_commitment", "familiarity_declarations",
            "cells",
        } and ceiling_artifact.get("format_version") == FORMAT_VERSION
                and ceiling_artifact.get("artifact_type")
                == "s4_transcript_matched_ceiling_input"
                and ceiling_artifact.get("frozen_manifest_sha256") == sha256_file(frozen_manifest_path())
                and ceiling_artifact.get("preregistration_sha256")
                == frozen["preregistration_sha256"]
                and ceiling_artifact.get("ceiling_spec") == preregistration["ceiling_spec"]
                and ceiling_artifact.get("ceiling_spec_sha256")
                == preregistration["ceiling_spec_sha256"]
                and ceiling_artifact.get("ceiling_familiarity_policy")
                == preregistration["ceiling_familiarity_policy"],
                f"{stage_label} ceiling_input artifact does not match the frozen "
                "ceiling_spec or required schema")
        _parse_utc(ceiling_artifact.get("released_utc"), "ceiling_input released_utc")
        _ceiling_input_cells(ceiling_artifact)
        if ceiling_spec["kind"] == "model":
            require(ceiling_artifact.get("closure_eligibility")
                    == "descriptive_only_model"
                    and ceiling_artifact.get("respondent_id") is None
                    and ceiling_artifact.get("familiarity_commitment") is None
                    and ceiling_artifact.get("familiarity_declarations") is None,
                    "model ceiling_input must be explicitly descriptive-only")
            require(document.get("familiarity_commitment") is None,
                    "model ceiling cannot self-attest a closure-eligible familiarity commitment")
            validate_model_ceiling_execution_trace(
                document, preregistration, set(seeds), ceiling_artifact, ceiling_input_sha
            )
        else:
            respondent_id = ceiling_spec["cohort"]["respondent_id"]
            require(ceiling_artifact.get("closure_eligibility")
                    == "screened_blinded_human"
                    and ceiling_artifact.get("respondent_id") == respondent_id,
                    "human ceiling_input lacks its screened blinded respondent binding")
            require(document.get("respondent_id") == respondent_id,
                    "human ceiling document respondent_id differs from the frozen blinded "
                    "respondent")
            commitment_binding = document.get("familiarity_commitment")
            require(commitment_binding == ceiling_artifact.get("familiarity_commitment"),
                    "ceiling document familiarity commitment differs from ceiling_input")
            commitment, committed_utc = validate_familiarity_commitment(
                commitment_binding, frozen
            )
            released_utc = _parse_utc(
                ceiling_artifact.get("released_utc"), "ceiling_input released_utc"
            )
            require(committed_utc < released_utc,
                    "familiarity commitment was not frozen before ceiling evidence release")
            commitment_path = Path(commitment_binding["path"])
            require(commitment_path.stat().st_mtime_ns <= ceiling_path.stat().st_mtime_ns,
                    "familiarity commitment file postdates the ceiling_input artifact")
            require(ceiling_artifact.get("familiarity_declarations")
                    == commitment["declarations"],
                    "ceiling_input familiarity declarations differ from the commitment")
            declarations = {
                item["cell_key"]: item["familiarity"]
                for item in commitment["declarations"]
            }
            document_cells = _ceiling_document_cells(document, set(seeds))
            for cell_key, cell in document_cells.items():
                require(cell.get("respondent_id") == respondent_id,
                        f"ceiling answer cell {cell_key} respondent_id differs from the frozen "
                        "blinded respondent")
                require(_normalize_familiarity(cell.get("familiarity"))
                        == declarations.get(cell_key),
                        f"ceiling answer cell {cell_key} familiarity differs from its "
                        "pre-evidence commitment")
            validate_human_ceiling_delivery_receipt(
                document, preregistration, set(seeds), ceiling_artifact, ceiling_input_sha,
                commitment_binding["sha256"],
            )
    return role, set(seeds), attempt


def generation_seed(base_seed: int, blind_id: str, round_number: int) -> int:
    digest = hashlib.sha256(f"{base_seed}:{blind_id}_r{round_number}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def validate_cell_provenance(
    cell: dict[str, Any], frozen: dict[str, Any], *, seed: int, role: str,
) -> None:
    blind_id, arm = cell.get("game_blind"), cell.get("arm")
    packet = frozen["packets"].get(blind_id)
    require(isinstance(packet, dict), f"cell references an unfrozen packet: {blind_id!r}")
    if role == "qwen":
        require(cell.get("packet_manifest_sha256") == packet["manifest_sha256"],
                f"cell packet-manifest binding drift for {blind_id}/{arm}/seed={seed}")
        require(cell.get("packet_ledger_sha256") == packet["ledger_sha256"],
                f"cell packet-ledger binding drift for {blind_id}/{arm}/seed={seed}")
    rounds = cell.get("rounds") or []
    require(isinstance(rounds, list), "cell rounds must be a list")
    expected_rounds = frozen["preregistration"]["budgets"]["interaction_rounds"] + 1
    if role == "qwen" and cell.get("outcome") == "answered":
        require(len(rounds) == expected_rounds,
                f"answered Qwen cell must contain exactly {expected_rounds} matched "
                "generation rounds")
    require(len(rounds) <= expected_rounds,
            f"cell exceeds frozen interaction-round budget: {blind_id}/{arm}/seed={seed}")
    probes_spent = cell.get("probes_spent")
    if probes_spent is not None:
        require(type(probes_spent) is int
                and 0 <= probes_spent <= frozen["preregistration"]["budgets"]["active_probes"],
                f"cell exceeds frozen active-probe budget: {blind_id}/{arm}/seed={seed}")
    for round_number, record in enumerate(rounds):
        require(isinstance(record, dict), "round trace metadata must be an object")
        expected_tag = f"{blind_id}_{arm}_s{seed}_r{round_number}"
        require(record.get("tag") == expected_tag,
                f"round tag drift: {record.get('tag')!r} != {expected_tag!r}")
        require(record.get("seed") == generation_seed(seed, blind_id, round_number),
                f"effective generation seed drift in {expected_tag}")
        if role == "qwen" and cell.get("outcome") == "answered":
            require(record.get("max_tokens")
                    == frozen["preregistration"]["budgets"]["answer_tokens"],
                    f"matched answer-token budget missing/drifted in {expected_tag}")
        elif "max_tokens" in record:
            require(record["max_tokens"]
                    == frozen["preregistration"]["budgets"]["answer_tokens"],
                    f"answer-token budget drift in {expected_tag}")
        if "visual_tokens" in record:
            require(type(record["visual_tokens"]) is int
                    and record["visual_tokens"] <= frozen["preregistration"]["budgets"]["max_visual_tokens"],
                    f"visual-token budget drift in {expected_tag}")
        if "images" in record:
            require(isinstance(record["images"], list)
                    and len(record["images"]) <= frozen["preregistration"]["budgets"]["max_images"],
                    f"image-count budget drift in {expected_tag}")


def collect_attempts(
    answer_paths: list[Path], frozen: dict[str, Any]
) -> tuple[dict[str, dict[int, dict[str, Any]]], list[dict[str, str]]]:
    preregistration = frozen["preregistration"]
    expected = {
        logical_key(row["role"], row["game_blind"], row["arm"], row["seed"]): row
        for row in preregistration["expected_cells"]
    }
    attempts: dict[str, dict[int, dict[str, Any]]] = {key: {} for key in expected}
    bindings: list[dict[str, str]] = []
    for path in answer_paths:
        document = load_object(path, "answer document")
        role, document_seeds, document_attempt = validate_run_document(document, frozen)
        bindings.append({"path": str(path), "sha256": sha256_file(path)})
        observed_arms: set[str] = set()
        for cell_index, cell in enumerate(document["cells"]):
            require(isinstance(cell, dict), f"{path} cell {cell_index} must be an object")
            cell_role = cell.get("role", role)
            seed = cell.get("seed")
            if seed is None and len(document_seeds) == 1:
                seed = next(iter(document_seeds))
            blind_id, arm = cell.get("game_blind"), cell.get("arm")
            require(cell_role == role, f"{path} cell {cell_index} role differs from its document")
            require(type(seed) is int and seed in document_seeds,
                    f"{path} cell {cell_index} seed is absent from document metadata")
            key = logical_key(cell_role, blind_id, arm, seed)
            require(key in expected, f"unexpected cell outside frozen matrix: {key}")
            attempt = cell.get("attempt", document_attempt)
            require(type(attempt) is int and 0 <= attempt <= preregistration["missing_reruns"],
                    f"invalid attempt number for {key}: {attempt!r}")
            require(attempt not in attempts[key], f"duplicate cell attempt: {key} attempt {attempt}")
            validate_cell_provenance(cell, frozen, seed=seed, role=cell_role)
            attempts[key][attempt] = {
                "cell": cell,
                "source_path": str(path),
                "source_sha256": bindings[-1]["sha256"],
                "classification": classify_attempt(cell),
                "ceiling_input": document.get("ceiling_input"),
            }
            observed_arms.add(arm)
        require(observed_arms.issubset(set(document["arms"])),
                f"{path} contains a cell whose arm is absent from its arms metadata")
    return attempts, bindings


def resolve_attempts(
    attempts: dict[str, dict[int, dict[str, Any]]], frozen: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    remedy = frozen["preregistration"]["missing_reruns"]
    resolved: dict[str, dict[str, Any]] = {}
    for key, by_attempt in attempts.items():
        if not by_attempt:
            resolved[key] = {
                "status": "incomplete_run", "missing_kind": "absent_expected_cell",
                "rerun_required": False, "attempts": [], "selected": None,
            }
            continue
        require(0 in by_attempt, f"rerun exists without attempt 0 for {key}")
        require(set(by_attempt) == set(range(max(by_attempt) + 1)),
                f"non-contiguous attempts for {key}")
        selected = None
        history = []
        for attempt in sorted(by_attempt):
            record = by_attempt[attempt]
            classification = record["classification"]
            history.append({"attempt": attempt, **classification})
            if classification.get("missing_kind") == "instrument_error":
                require(attempt == max(by_attempt),
                        f"instrument-error cell {key} cannot use the missing-output remedy")
                break
            if classification["status"] == "answered":
                require(attempt == max(by_attempt), f"unnecessary rerun after answered cell {key}")
                selected = record
                break
        if any(item.get("missing_kind") == "instrument_error" for item in history):
            resolved[key] = {
                "status": "instrument_error", "missing_kind": "instrument_error",
                "rerun_required": False, "attempts": history, "selected": None,
            }
        elif selected is not None:
            resolved[key] = {
                "status": "answered", "missing_kind": None, "rerun_required": False,
                "attempts": history, "selected": selected,
            }
        else:
            final_attempt = max(by_attempt)
            resolved[key] = {
                "status": "rerun_required" if final_attempt < remedy else "missing_after_remedy",
                "missing_kind": by_attempt[final_attempt]["classification"]["missing_kind"],
                "rerun_required": final_attempt < remedy,
                "attempts": history, "selected": None,
            }
    return resolved


def ceiling_evidence_payload(cell: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Exact user-visible transcript, excluding Qwen's interim guesses and hidden assets."""
    rounds = cell.get("rounds") or []
    require(rounds and isinstance(rounds[-1], dict),
            "cannot prepare a ceiling input without final round trace metadata")
    messages = rounds[-1].get("messages")
    require(isinstance(messages, list),
            "final round trace does not retain the exact delivered messages")
    user_messages = [message for message in messages
                     if isinstance(message, dict) and message.get("role") == "user"]
    require(user_messages, "final round trace contains no user evidence messages")
    raw_images = rounds[-1].get("images") or []
    require(isinstance(raw_images, list), "final round image provenance must be a list")
    images = []
    for index, item in enumerate(raw_images):
        require(isinstance(item, dict), f"final round image {index} lacks provenance")
        path, digest = item.get("path"), item.get("sha256")
        require(isinstance(path, str) and isinstance(digest, str) and len(digest) == 64,
                f"final round image {index} lacks path/full SHA-256")
        image_path = Path(path)
        require(image_path.is_file() and sha256_file(image_path) == digest,
                f"delivered ceiling/Qwen image drift: {path}")
        images.append({
            key: item.get(key) for key in ("path", "sha256", "source_size", "processed_size")
            if key in item
        })
    delivery_log = []
    for entry in cell.get("delivery_log") or []:
        require(isinstance(entry, dict), "delivery_log entries must be objects")
        omitted = entry.get("omitted_images") or []
        require(isinstance(omitted, list), "delivery_log omitted_images must be a list")
        # Preserve the fact/cost of omissions without publishing filesystem paths to
        # result assets Qwen did not see (which would let a ceiling open them).
        delivery_log.append({
            key: entry.get(key) for key in (
                "label", "result_ok", "result_image_count", "all_images_delivered",
                "image_limit", "visual_token_limit", "context_images_after",
                "estimated_visual_tokens_after",
            ) if key in entry
        } | {
            "delivered_image_count": len(entry.get("delivered_images") or []),
            "omitted_image_count": len(omitted),
            "omitted_visual_tokens": sum(
                int(item.get("visual_tokens", 0)) for item in omitted if isinstance(item, dict)
            ),
        })
    return {
        "packet_sha256": sha256_json(packet),
        "user_messages": user_messages,
        "images": images,
        # This records explicit cap omissions as well as deliveries.  Hidden result
        # asset paths in probe_log are intentionally not exposed to the ceiling.
        "delivery_log": delivery_log,
    }


def evidence_digest(cell: dict[str, Any], packet: dict[str, Any]) -> str:
    return sha256_json(ceiling_evidence_payload(cell, packet))


def build_ceiling_input_payload(
    resolved: dict[str, dict[str, Any]], frozen: dict[str, Any], *,
    familiarity_commitment: dict[str, str] | None = None,
    released_utc: str | None = None,
) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    spec = preregistration.get("ceiling_spec")
    require(preregistration.get("stage") in {"A", "B"}
            and "ceiling" in preregistration.get("roles", [])
            and isinstance(spec, dict),
            "transcript-matched ceiling inputs require a frozen ceiling role and spec")
    require(preregistration["stage"] == "B" or spec.get("kind") == "model",
            "Stage-A transcript-matched ceilings support only a descriptive model comparator")
    primary_arm = preregistration["primary_arm"]
    expected_keys = {
        logical_key(row["role"], row["game_blind"], row["arm"], row["seed"])
        for row in preregistration["expected_cells"]
    }
    cells = []
    for row in preregistration["expected_cells"]:
        if row["role"] != "qwen" or row["arm"] != primary_arm:
            continue
        qwen_key = logical_key("qwen", row["game_blind"], row["arm"], row["seed"])
        ceiling_key = logical_key("ceiling", row["game_blind"], row["arm"], row["seed"])
        require(ceiling_key in expected_keys, f"frozen matrix lacks matched ceiling cell {ceiling_key}")
        resolution = resolved.get(qwen_key)
        require(resolution is not None and resolution.get("selected") is not None,
                f"cannot prepare ceiling input until Qwen primary cell is answered: {qwen_key}")
        qwen_cell = resolution["selected"]["cell"]
        evidence = ceiling_evidence_payload(qwen_cell, frozen["packets"][row["game_blind"]])
        cells.append({
            "ceiling_cell_key": ceiling_key,
            "qwen_cell_key": qwen_key,
            "game_blind": row["game_blind"],
            "arm": row["arm"],
            "seed": row["seed"],
            "evidence": evidence,
            "evidence_sha256": sha256_json(evidence),
        })
    cells.sort(key=lambda item: item["ceiling_cell_key"])
    release_timestamp = released_utc or _dt.datetime.now(_dt.timezone.utc).isoformat()
    released_at = _parse_utc(release_timestamp, "ceiling_input released_utc")
    familiarity_fields: dict[str, Any]
    if spec["kind"] == "blinded_human_cohort":
        commitment, committed_at = validate_familiarity_commitment(
            familiarity_commitment, frozen
        )
        require(committed_at < released_at,
                "familiarity commitment must be frozen before ceiling evidence release")
        familiarity_fields = {
            "closure_eligibility": "screened_blinded_human",
            "respondent_id": spec["cohort"]["respondent_id"],
            "familiarity_commitment": familiarity_commitment,
            "familiarity_declarations": commitment["declarations"],
        }
    else:
        require(familiarity_commitment is None,
                "model ceiling cannot use a human familiarity commitment")
        familiarity_fields = {
            "closure_eligibility": "descriptive_only_model",
            "respondent_id": None,
            "familiarity_commitment": None,
            "familiarity_declarations": None,
        }
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_transcript_matched_ceiling_input",
        "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
        "preregistration_sha256": frozen["preregistration_sha256"],
        "ceiling_spec": preregistration["ceiling_spec"],
        "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
        "ceiling_familiarity_policy": preregistration["ceiling_familiarity_policy"],
        "released_utc": release_timestamp,
        **familiarity_fields,
        "cells": cells,
    }


def prepare_ceiling_inputs(
    answer_paths: list[Path], output_path: Path | None = None, *,
    familiarity_commitment_path: Path | None = None,
) -> Path:
    frozen = verify_freeze()
    attempts, bindings = collect_attempts(answer_paths, frozen)
    del bindings
    resolved = resolve_attempts(attempts, frozen)
    spec = frozen["preregistration"]["ceiling_spec"]
    familiarity_binding = None
    if spec["kind"] == "blinded_human_cohort":
        require(familiarity_commitment_path is not None,
                "human --prepare-ceiling requires --familiarity-commitment")
        require(familiarity_commitment_path.is_file(),
                f"missing familiarity commitment: {familiarity_commitment_path}")
        familiarity_binding = {
            "path": str(familiarity_commitment_path),
            "sha256": sha256_file(familiarity_commitment_path),
        }
    else:
        require(familiarity_commitment_path is None,
                "model ceiling cannot use --familiarity-commitment")
    payload = build_ceiling_input_payload(
        resolved, frozen, familiarity_commitment=familiarity_binding
    )
    bundle = sha256_json(payload)
    destination = output_path or output_path_for(answer_paths, bundle, "ceiling_input")
    atomic_create(destination, payload, mode=0o444)
    if familiarity_binding is not None:
        require(Path(familiarity_binding["path"]).stat().st_mtime_ns
                <= destination.stat().st_mtime_ns,
                "familiarity commitment file postdates the released ceiling_input")
    print(f"wrote append-only transcript-matched ceiling input {destination} "
          f"({sha256_file(destination)})")
    return destination


def ceiling_familiarity_eligible(value: Any, preregistration: dict[str, Any]) -> bool:
    normalized = _normalize_familiarity(value)
    if normalized is None:
        return False
    policy = preregistration.get("ceiling_familiarity_policy") or {}
    eligible = policy.get("eligible_declarations")
    return isinstance(eligible, list) and normalized in eligible


def enforce_ceiling_matches(resolved: dict[str, dict[str, Any]], frozen: dict[str, Any]) -> None:
    preregistration = frozen["preregistration"]
    if "ceiling" not in preregistration["roles"]:
        return
    primary_arm = preregistration["primary_arm"]
    for row in preregistration["expected_cells"]:
        if row["role"] != "ceiling" or row["arm"] != primary_arm:
            continue
        ceiling_key = logical_key("ceiling", row["game_blind"], row["arm"], row["seed"])
        ceiling = resolved[ceiling_key]
        if ceiling["selected"] is None:
            continue
        ceiling_cell = ceiling["selected"]["cell"]
        binding = ceiling["selected"].get("ceiling_input") or {}
        path = Path(binding.get("path", "")) if isinstance(binding, dict) else Path("")
        matched = False
        supplied_artifact = None
        expected_cell = None
        if path.is_file() and binding.get("sha256") == sha256_file(path):
            try:
                supplied_artifact = load_object(path, "ceiling input artifact")
                expected_artifact = build_ceiling_input_payload(
                    resolved,
                    frozen,
                    familiarity_commitment=supplied_artifact.get("familiarity_commitment"),
                    released_utc=supplied_artifact.get("released_utc"),
                )
                expected_cell = next(
                    item for item in expected_artifact["cells"]
                    if item["ceiling_cell_key"] == ceiling_key
                )
            except RuntimeError:
                expected_artifact = None
            matched = (
                supplied_artifact == expected_artifact
                and expected_cell is not None
                and ceiling_cell.get("ceiling_input_cell_sha256") == expected_cell["evidence_sha256"]
            )
        if not matched:
            ceiling.update(
                status="missing_after_remedy", missing_kind="unmatched_ceiling",
                rerun_required=False, selected=None,
            )
        elif preregistration["ceiling_spec"]["kind"] == "model":
            if preregistration["stage"] == "B":
                ceiling.update(
                    status="missing_after_remedy",
                    missing_kind="model_ceiling_descriptive_only",
                    rerun_required=False,
                    selected=None,
                )
        elif (preregistration["ceiling_spec"]["kind"] == "blinded_human_cohort"
              and ceiling_cell.get("respondent_id")
              != preregistration["ceiling_spec"]["cohort"]["respondent_id"]):
            ceiling.update(
                status="missing_after_remedy", missing_kind="ceiling_identity_mismatch",
                rerun_required=False, selected=None,
            )
        elif _normalize_familiarity(ceiling_cell.get("familiarity")) != {
            item["cell_key"]: item["familiarity"]
            for item in supplied_artifact["familiarity_declarations"]
        }.get(ceiling_key):
            ceiling.update(
                status="missing_after_remedy", missing_kind="ceiling_familiarity_mismatch",
                rerun_required=False, selected=None,
            )
        elif not ceiling_familiarity_eligible(
            ceiling_cell.get("familiarity"), preregistration
        ):
            ceiling.update(
                status="missing_after_remedy",
                missing_kind="ceiling_familiarity_ineligible",
                rerun_required=False,
                selected=None,
            )


def _worksheet_cells(
    resolved: dict[str, dict[str, Any]], frozen: dict[str, Any], *, execute_plans: bool,
) -> list[dict[str, Any]]:
    """Build the grader-private logical cells; never serialize these in Stage B."""
    mapping = read_blind_map()
    reverse = blind_to_game(mapping)
    cells: list[dict[str, Any]] = []
    for expected in frozen["preregistration"]["expected_cells"]:
        key = logical_key(expected["role"], expected["game_blind"], expected["arm"], expected["seed"])
        resolution = resolved[key]
        game = reverse.get(expected["game_blind"])
        require(game is not None, f"unknown blind id in frozen matrix: {expected['game_blind']}")
        gold_path = GOLD / f"{game}.json"
        require(gold_path.is_file(), f"missing sealed gold for {game}")
        gold = validate_gold(game, load_object(gold_path, "gold file"))
        raw_cell = resolution["selected"]["cell"] if resolution["selected"] else {}
        answer = raw_cell.get("final_answer") if resolution["selected"] else None
        pre_answer = raw_cell.get("pre_probe_answer") if resolution["selected"] else None
        terminal = True  # preregistration requires the three-way class for every cell
        packet = frozen["packets"][expected["game_blind"]]
        cell = {
            "cell_key": key,
            **expected,
            "game": game,
            "observation": {name: value for name, value in resolution.items() if name != "selected"},
            "source_attempt": (
                resolution["selected"]["cell"].get("attempt", 0) if resolution["selected"] else None
            ),
            "answer_sha256": sha256_json(answer) if answer is not None else None,
            "axis1_consistency": axis1_consistency(
                raw_cell, valid_evidence_refs(packet, raw_cell)
            ) if answer is not None else {"status": "not observed"},
            "axis2_worksheet": axis2_worksheet(answer, gold, terminal=terminal),
            "pre_probe_axis2_worksheet": (
                axis2_worksheet(pre_answer, gold, terminal=True) if pre_answer else None
            ),
            "axis3_worksheet": axis3_worksheet(answer, gold),
            "axis5_plan": axis5_plan(
                raw_cell, game, frozen["preregistration"]["plan_action_budgets"][game],
                execute_plans,
            ) if answer is not None else {"status": "not observed"},
        }
        cells.append(cell)
    return cells


def _adjudication_hmac(key: bytes, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _opaque_item_id(
    key: bytes, *, adjudicator_id: str, cell_key: str, answers_bundle_sha256: str,
) -> str:
    return ADJUDICATION_ITEM_PREFIX + _adjudication_hmac(
        key, "item", adjudicator_id, answers_bundle_sha256, cell_key,
    )[:24]


def _opaque_answer_commitment(
    key: bytes, *, adjudicator_id: str, item_id: str, answer_sha256: str,
) -> str:
    return "A" + _adjudication_hmac(
        key, "answer", adjudicator_id, item_id, answer_sha256,
    )[:24]


def _opaque_answer_bundle_commitment(
    key: bytes, *, adjudicator_id: str, answers_bundle_sha256: str,
) -> str:
    return "B" + _adjudication_hmac(
        key, "answer-bundle", adjudicator_id, answers_bundle_sha256,
    )[:24]


def _redact_judge_facing_identifiers(value: Any, identifiers: Iterable[str]) -> Any:
    """Remove literal metadata leaks while preserving the answer/gold structure."""
    tokens = sorted(
        {token for token in identifiers if isinstance(token, str) and len(token) >= 3},
        key=len,
        reverse=True,
    )

    def redact(child: Any) -> Any:
        if isinstance(child, dict):
            return {name: redact(item) for name, item in child.items()}
        if isinstance(child, list):
            return [redact(item) for item in child]
        if isinstance(child, str):
            result = child
            for token in tokens:
                result = re.sub(
                    re.escape(token), "[BLINDED_METADATA]", result,
                    flags=re.IGNORECASE,
                )
            return result
        return child

    return redact(value)


def _blank_blinded_mutable_fields(value: Any) -> Any:
    """Retain the complete schema while blanking only adjudicator-writable fields."""
    def blank_verdict_shape(child: Any) -> Any:
        if isinstance(child, list):
            return [blank_verdict_shape(item) for item in child]
        if isinstance(child, dict):
            return {name: blank_verdict_shape(item) for name, item in child.items()}
        return None

    if isinstance(value, dict):
        result = {}
        for name, child in value.items():
            if name.startswith("VERDICT_"):
                # Length/key shape is immutable even though the verdict values are
                # writable. This catches dropped constraint/counterfactual verdicts
                # before any item is unblinded.
                result[name] = blank_verdict_shape(child)
            elif name in {
                "independence_declaration", "verdict_commitment_sha256",
                "adjudicator_signature_ed25519",
            }:
                result[name] = None
            elif name != "worksheet_sha256":
                result[name] = _blank_blinded_mutable_fields(child)
        return result
    if isinstance(value, list):
        return [_blank_blinded_mutable_fields(child) for child in value]
    return value


def _verdict_tree(value: Any) -> Any:
    """Extract opaque item IDs and verdict fields without consulting the rejoin key."""
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    if "item_id" in value:
        result["item_id"] = value["item_id"]
    for name, child in value.items():
        if name.startswith("VERDICT_"):
            result[name] = child
        elif isinstance(child, dict):
            nested = _verdict_tree(child)
            if isinstance(nested, dict) and nested:
                result[name] = nested
    return result


def _require_complete_verdict_tree(value: Any, label: str = "adjudication") -> None:
    """Every emitted verdict leaf is mandatory in the closure-grade workflow."""
    if isinstance(value, dict):
        for name, child in value.items():
            if name.startswith("VERDICT_"):
                _require_bool_verdict_value(child, f"{label}.{name}")
            else:
                _require_complete_verdict_tree(child, f"{label}.{name}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_complete_verdict_tree(child, f"{label}[{index}]")


def _require_bool_verdict_value(value: Any, label: str) -> None:
    if isinstance(value, list):
        for index, child in enumerate(value):
            _require_bool_verdict_value(child, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for name, child in value.items():
            _require_bool_verdict_value(child, f"{label}.{name}")
        return
    require(type(value) is bool, f"{label} must be completed with true or false")


def blinded_verdict_payload(document: dict[str, Any]) -> dict[str, Any]:
    """Canonical opaque payload signed independently by one frozen adjudicator."""
    return {
        "format_version": document.get("format_version"),
        "artifact_type": document.get("artifact_type"),
        "frozen_manifest_sha256": document.get("frozen_manifest_sha256"),
        "preregistration_sha256": document.get("preregistration_sha256"),
        "adjudication_protocol_sha256": document.get("adjudication_protocol_sha256"),
        "worksheet_sha256": document.get("worksheet_sha256"),
        "opaque_answer_bundle_commitment": document.get(
            "opaque_answer_bundle_commitment"
        ),
        "adjudicator": document.get("adjudicator"),
        "independence_declaration": document.get("independence_declaration"),
        "opaque_verdicts": [
            _verdict_tree(item) for item in document.get("items") or []
        ],
    }


def blinded_verdict_commitment(document: dict[str, Any]) -> str:
    """Digest judgments while item IDs are still opaque and roles remain unavailable."""
    items = document.get("items")
    require(isinstance(items, list), "blinded adjudication items must be a list")
    return sha256_json(blinded_verdict_payload(document))


def _load_ed25519_private_key(path: Path) -> Any:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    require(path.is_file(), f"missing adjudicator signing key: {path}")
    raw = path.read_bytes()
    stripped = raw.strip()
    if len(raw) == 32:
        key_bytes = raw
    elif re.fullmatch(rb"[0-9a-fA-F]{64}", stripped) is not None:
        key_bytes = bytes.fromhex(stripped.decode("ascii"))
    else:
        raise RuntimeError(
            "adjudicator signing key must be a raw 32-byte Ed25519 seed or 64 hex digits"
        )
    return Ed25519PrivateKey.from_private_bytes(key_bytes)


def _ed25519_public_key_hex(private_key: Any) -> str:
    from cryptography.hazmat.primitives import serialization

    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def _verify_adjudicator_signature(document: dict[str, Any]) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    adjudicator = document.get("adjudicator") or {}
    public_hex = adjudicator.get("ed25519_public_key_hex")
    signature_hex = document.get("adjudicator_signature_ed25519")
    require(isinstance(public_hex, str) and re.fullmatch(r"[0-9a-f]{64}", public_hex),
            "blinded adjudication lacks its frozen Ed25519 public key")
    require(isinstance(signature_hex, str)
            and re.fullmatch(r"[0-9a-f]{128}", signature_hex),
            "blinded adjudication lacks a complete Ed25519 signature")
    commitment = require_full_sha256(
        document.get("verdict_commitment_sha256"), "verdict_commitment_sha256"
    )
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(
            bytes.fromhex(signature_hex),
            ADJUDICATION_SIGNATURE_DOMAIN + bytes.fromhex(commitment),
        )
    except (InvalidSignature, ValueError) as exc:
        raise RuntimeError("adjudicator Ed25519 signature verification failed") from exc


def seal_blinded_adjudication(
    document: dict[str, Any], adjudicator_signing_key_path: Path,
) -> dict[str, Any]:
    """Seal one independently completed worksheet before the grader can unblind it."""
    require(document.get("artifact_type") == "s4_role_blinded_adjudication",
            "--seal-adjudication requires one role-blinded adjudicator worksheet")
    worksheet_sha = require_full_sha256(
        document.get("worksheet_sha256"), "worksheet_sha256"
    )
    require(sha256_json(_blank_blinded_mutable_fields(document)) == worksheet_sha,
            "worksheet immutable fields differ from its original blinded skeleton")
    _require_complete_verdict_tree(document)
    private_key = _load_ed25519_private_key(adjudicator_signing_key_path)
    expected_public_key = (document.get("adjudicator") or {}).get(
        "ed25519_public_key_hex"
    )
    require(_ed25519_public_key_hex(private_key) == expected_public_key,
            "adjudicator signing key does not match the frozen public key")
    sealed = json.loads(json.dumps(document))
    sealed["independence_declaration"] = ADJUDICATION_INDEPENDENCE_DECLARATION
    sealed["verdict_commitment_sha256"] = blinded_verdict_commitment(sealed)
    sealed["adjudicator_signature_ed25519"] = private_key.sign(
        ADJUDICATION_SIGNATURE_DOMAIN
        + bytes.fromhex(sealed["verdict_commitment_sha256"])
    ).hex()
    return sealed


def _build_blinded_adjudication_bundle(
    cells: list[dict[str, Any]], bindings: list[dict[str, str]],
    frozen: dict[str, Any], key: bytes,
) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    validate_adjudication_protocol(preregistration["adjudication_protocol"])
    expected_key_sha = preregistration["adjudication_protocol"]["blinding"][
        "key_commitment_sha256"
    ]
    require(hashlib.sha256(key).hexdigest() == expected_key_sha,
            "adjudication key differs from its frozen commitment")
    answer_artifacts = sorted(binding["sha256"] for binding in bindings)
    answers_bundle_sha256 = sha256_json(answer_artifacts)
    answered = [cell for cell in cells if cell["observation"]["status"] == "answered"]
    forbidden_identifiers = {
        # Qwen is a unique model identifier.  Do not blanket-redact the ordinary
        # English word "ceiling", which may itself be part of a game objective.
        "qwen",
        *(str(cell.get(field)) for cell in cells
          for field in ("cell_key", "game_blind", "game")),
    }
    worksheets = []
    for adjudicator in preregistration["adjudication_protocol"]["adjudicators"]:
        adjudicator_id = adjudicator["adjudicator_id"]
        sortable = []
        for cell in answered:
            item_id = _opaque_item_id(
                key, adjudicator_id=adjudicator_id, cell_key=cell["cell_key"],
                answers_bundle_sha256=answers_bundle_sha256,
            )
            item = {
                "item_id": item_id,
                "opaque_answer_commitment": _opaque_answer_commitment(
                    key, adjudicator_id=adjudicator_id, item_id=item_id,
                    answer_sha256=cell["answer_sha256"],
                ),
                "axis2_worksheet": _redact_judge_facing_identifiers(
                    cell["axis2_worksheet"], forbidden_identifiers
                ),
                "axis3_worksheet": _redact_judge_facing_identifiers(
                    cell["axis3_worksheet"], forbidden_identifiers
                ),
            }
            order = _adjudication_hmac(
                key, "order", adjudicator_id, answers_bundle_sha256, cell["cell_key"],
            )
            sortable.append((order, item_id, item))
        items = [item for _, _, item in sorted(sortable)]
        skeleton = {
            "format_version": FORMAT_VERSION,
            "artifact_type": "s4_role_blinded_adjudication",
            "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
            "preregistration_sha256": frozen["preregistration_sha256"],
            "opaque_answer_bundle_commitment": _opaque_answer_bundle_commitment(
                key, adjudicator_id=adjudicator_id,
                answers_bundle_sha256=answers_bundle_sha256,
            ),
            "expected_matrix_sha256": preregistration["expected_matrix_sha256"],
            "adjudication_protocol_sha256": preregistration[
                "adjudication_protocol_sha256"
            ],
            "adjudicator": dict(adjudicator),
            "instructions": (
                "Judge every response independently. Fill only VERDICT_* fields. Do not "
                "inspect another adjudicator's worksheet or any unblinding material. Seal "
                "this document with --seal-adjudication before it is returned to the grader. "
                "[BLINDED_METADATA] marks only literal protocol/game identifiers removed "
                "from otherwise unchanged answer or rubric text."
            ),
            "items": items,
            "independence_declaration": None,
            "verdict_commitment_sha256": None,
            "adjudicator_signature_ed25519": None,
        }
        worksheet = dict(skeleton)
        worksheet["worksheet_sha256"] = sha256_json(
            _blank_blinded_mutable_fields(skeleton)
        )
        worksheets.append(worksheet)
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_role_blinded_adjudication_bundle",
        "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
        "preregistration_sha256": frozen["preregistration_sha256"],
        "answers_bundle_sha256": answers_bundle_sha256,
        "answer_artifact_sha256s": answer_artifacts,
        "expected_matrix_sha256": preregistration["expected_matrix_sha256"],
        "adjudication_protocol_sha256": preregistration["adjudication_protocol_sha256"],
        "worksheet_count": len(worksheets),
        "worksheets": worksheets,
    }


def build_worksheet(
    answer_paths: list[Path], frozen: dict[str, Any], *, execute_plans: bool,
    adjudication_key: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    attempts, bindings = collect_attempts(answer_paths, frozen)
    resolved = resolve_attempts(attempts, frozen)
    enforce_ceiling_matches(resolved, frozen)
    cells = _worksheet_cells(resolved, frozen, execute_plans=execute_plans)
    if frozen["preregistration"]["stage"] == "B":
        require(adjudication_key is not None,
                "Stage B worksheet generation requires the committed adjudication key")
        return _build_blinded_adjudication_bundle(
            cells, bindings, frozen, adjudication_key,
        ), resolved
    require(adjudication_key is None,
            "Stage-A diagnostic worksheets do not use Stage-B blinding material")
    worksheet = {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_adjudication_worksheet",
        "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
        "preregistration_sha256": frozen["preregistration_sha256"],
        "answers": bindings,
        "answers_bundle_sha256": sha256_json(bindings),
        "expected_matrix_sha256": frozen["preregistration"]["expected_matrix_sha256"],
        "instructions": (
            "Stage-A diagnostic only: fill VERDICT_* fields and preserve all other fields."
        ),
        "cells": cells,
    }
    return worksheet, resolved


def strip_verdicts(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_verdicts(item) for key, item in value.items()
                if not key.startswith("VERDICT_") and key != "axis5_plan"}
    if isinstance(value, list):
        return [strip_verdicts(item) for item in value]
    return value


def validate_adjudications(template: dict[str, Any], adjudications: dict[str, Any]) -> None:
    for field in (
        "format_version", "frozen_manifest_sha256", "preregistration_sha256", "answers",
        "answers_bundle_sha256", "expected_matrix_sha256",
    ):
        require(adjudications.get(field) == template.get(field),
                f"adjudication binding drift in {field}")
    template_cells = {cell["cell_key"]: cell for cell in template["cells"]}
    supplied_cells = adjudications.get("cells")
    require(isinstance(supplied_cells, list), "adjudications.cells must be a list")
    require(len(supplied_cells) == len(template_cells), "adjudication cell count mismatch")
    require(all(isinstance(cell, dict) and isinstance(cell.get("cell_key"), str)
                for cell in supplied_cells), "adjudication cells require cell_key")
    supplied_by_key = {cell["cell_key"]: cell for cell in supplied_cells}
    require(len(supplied_by_key) == len(supplied_cells), "duplicate adjudication cell_key")
    require(set(supplied_by_key) == set(template_cells), "adjudication cell matrix mismatch")
    for key, expected in template_cells.items():
        require(strip_verdicts(supplied_by_key[key]) == strip_verdicts(expected),
                f"adjudication modified a sealed/model/binding field in {key}")


def prevalidate_signed_blinded_adjudications(
    adjudications: list[dict[str, Any]], preregistration: dict[str, Any], *,
    frozen_manifest_sha256: str | None = None,
    preregistration_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Authenticate both opaque documents without loading or consulting the rejoin key."""
    validate_adjudication_protocol(preregistration["adjudication_protocol"])
    require(isinstance(adjudications, list)
            and len(adjudications) == ADJUDICATION_REQUIRED_JUDGES,
            "Stage B requires exactly two independently signed adjudication files")
    expected_adjudicators = {
        item["adjudicator_id"]: item
        for item in preregistration["adjudication_protocol"]["adjudicators"]
    }
    expected_top_fields = {
        "format_version", "artifact_type", "frozen_manifest_sha256",
        "preregistration_sha256", "opaque_answer_bundle_commitment",
        "expected_matrix_sha256", "adjudication_protocol_sha256", "adjudicator",
        "instructions", "items", "independence_declaration",
        "verdict_commitment_sha256", "adjudicator_signature_ed25519",
        "worksheet_sha256",
    }
    expected_item_fields = {
        "item_id", "opaque_answer_commitment", "axis2_worksheet", "axis3_worksheet",
    }
    supplied_by_id: dict[str, dict[str, Any]] = {}
    for index, document in enumerate(adjudications):
        require(isinstance(document, dict) and set(document) == expected_top_fields,
                f"blinded adjudication {index} has an invalid signed-document schema")
        require(document.get("format_version") == FORMAT_VERSION
                and document.get("artifact_type") == "s4_role_blinded_adjudication",
                f"blinded adjudication {index} has an invalid artifact identity")
        require_full_sha256(
            document.get("frozen_manifest_sha256"),
            f"blinded adjudication {index}.frozen_manifest_sha256",
        )
        require_full_sha256(
            document.get("preregistration_sha256"),
            f"blinded adjudication {index}.preregistration_sha256",
        )
        if frozen_manifest_sha256 is not None:
            require(document["frozen_manifest_sha256"] == frozen_manifest_sha256,
                    f"blinded adjudication {index} targets a different frozen manifest")
        if preregistration_sha256 is not None:
            require(document["preregistration_sha256"] == preregistration_sha256,
                    f"blinded adjudication {index} targets a different preregistration")
        require(document.get("expected_matrix_sha256")
                == preregistration["expected_matrix_sha256"],
                f"blinded adjudication {index} targets a different expected matrix")
        require(document.get("adjudication_protocol_sha256")
                == preregistration["adjudication_protocol_sha256"],
                f"blinded adjudication {index} targets a different adjudication protocol")
        adjudicator = document.get("adjudicator")
        require(isinstance(adjudicator, dict),
                f"blinded adjudication {index} lacks a frozen adjudicator")
        adjudicator_id = adjudicator.get("adjudicator_id")
        require(adjudicator_id in expected_adjudicators
                and adjudicator == expected_adjudicators[adjudicator_id],
                f"unknown or drifted adjudicator in blinded document: {adjudicator_id!r}")
        require(adjudicator_id not in supplied_by_id,
                f"duplicate blinded adjudication for {adjudicator_id}")
        items = document.get("items")
        require(isinstance(items, list) and all(
            isinstance(item, dict) and set(item) == expected_item_fields
            for item in items
        ), f"adjudicator {adjudicator_id} has an invalid opaque item schema")
        item_ids = [item.get("item_id") for item in items]
        require(all(isinstance(item_id, str)
                    and re.fullmatch(r"J[0-9a-f]{24}", item_id) for item_id in item_ids)
                and len(set(item_ids)) == len(item_ids),
                f"adjudicator {adjudicator_id} has duplicate/malformed opaque item IDs")
        require(document.get("independence_declaration")
                == ADJUDICATION_INDEPENDENCE_DECLARATION,
                f"adjudicator {adjudicator_id} did not make the frozen independence declaration")
        worksheet_sha = require_full_sha256(
            document.get("worksheet_sha256"),
            f"adjudicator {adjudicator_id}.worksheet_sha256",
        )
        require(sha256_json(_blank_blinded_mutable_fields(document)) == worksheet_sha,
                f"worksheet immutable fields drift for adjudicator {adjudicator_id}")
        _require_complete_verdict_tree(document, f"adjudicator {adjudicator_id}")
        commitment = require_full_sha256(
            document.get("verdict_commitment_sha256"),
            f"adjudicator {adjudicator_id}.verdict_commitment_sha256",
        )
        require(commitment == blinded_verdict_commitment(document),
                f"opaque verdict commitment drift for adjudicator {adjudicator_id}")
        _verify_adjudicator_signature(document)
        supplied_by_id[adjudicator_id] = document
    require(set(supplied_by_id) == set(expected_adjudicators),
            "signed adjudicator inventory differs from the frozen protocol")
    return supplied_by_id


def build_adjudication_commitment_receipt(
    adjudications: list[dict[str, Any]], frozen: dict[str, Any], *,
    committed_utc: str | None = None,
) -> dict[str, Any]:
    """Create the no-key two-signature commit point required before rejoining roles."""
    preregistration = frozen["preregistration"]
    supplied = prevalidate_signed_blinded_adjudications(
        adjudications, preregistration,
        frozen_manifest_sha256=sha256_file(frozen_manifest_path()),
        preregistration_sha256=frozen["preregistration_sha256"],
    )
    rows = [
        {
            "adjudicator_id": adjudicator_id,
            "adjudication_artifact_sha256": sha256_json(supplied[adjudicator_id]),
            "verdict_commitment_sha256": supplied[adjudicator_id][
                "verdict_commitment_sha256"
            ],
            "adjudicator_signature_ed25519": supplied[adjudicator_id][
                "adjudicator_signature_ed25519"
            ],
        }
        for adjudicator_id in sorted(supplied)
    ]
    timestamp = committed_utc or _dt.datetime.now(_dt.timezone.utc).isoformat()
    _parse_utc(timestamp, "adjudication commitment receipt committed_utc")
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": ADJUDICATION_RECEIPT_TYPE,
        "frozen_manifest_sha256": sha256_file(frozen_manifest_path()),
        "preregistration_sha256": frozen["preregistration_sha256"],
        "adjudication_protocol_sha256": preregistration[
            "adjudication_protocol_sha256"
        ],
        "committed_utc": timestamp,
        "adjudications": rows,
        "commitment_set_sha256": sha256_json(rows),
        "phase": "both_signed_opaque_verdicts_committed_before_rejoin",
    }


def validate_adjudication_commitment_receipt(
    receipt: Any, adjudications: list[dict[str, Any]], frozen: dict[str, Any],
) -> None:
    require(isinstance(receipt, dict) and set(receipt) == {
        "format_version", "artifact_type", "frozen_manifest_sha256",
        "preregistration_sha256", "adjudication_protocol_sha256", "committed_utc",
        "adjudications", "commitment_set_sha256", "phase",
    }, "Stage-B adjudication commitment receipt has an invalid schema")
    expected = build_adjudication_commitment_receipt(
        adjudications, frozen, committed_utc=receipt.get("committed_utc")
    )
    require(receipt == expected,
            "Stage-B adjudication commitment receipt does not bind both signed artifacts")


def validate_blinded_adjudications(
    template: dict[str, Any], adjudications: list[dict[str, Any]],
    preregistration: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Verify both opaque verdict commitments before any HMAC rejoin is attempted."""
    require(template.get("artifact_type") == "s4_role_blinded_adjudication_bundle",
            "Stage-B adjudication template is not role-blinded")
    expected_worksheets = template.get("worksheets")
    require(isinstance(expected_worksheets, list)
            and len(expected_worksheets) == ADJUDICATION_REQUIRED_JUDGES,
            "role-blinded template lacks the two frozen worksheets")
    prevalidated = prevalidate_signed_blinded_adjudications(
        adjudications, preregistration
    )
    expected_by_id = {
        worksheet["adjudicator"]["adjudicator_id"]: worksheet
        for worksheet in expected_worksheets
    }
    require(set(expected_by_id) == {
        item["adjudicator_id"]
        for item in preregistration["adjudication_protocol"]["adjudicators"]
    }, "role-blinded worksheets differ from the frozen adjudicator inventory")

    supplied_by_id: dict[str, dict[str, Any]] = {}
    # This first pass deliberately has no key/cell mapping. It commits judgments
    # while every item is still an opaque HMAC identifier.
    for index, document in enumerate(adjudications):
        adjudicator = document["adjudicator"]
        adjudicator_id = adjudicator.get("adjudicator_id")
        require(adjudicator_id in expected_by_id,
                f"unknown adjudicator in blinded document: {adjudicator_id!r}")
        require(document is prevalidated[adjudicator_id],
                f"prevalidated adjudicator document drift for {adjudicator_id}")
        expected = expected_by_id[adjudicator_id]
        require(document.get("worksheet_sha256") == expected.get("worksheet_sha256"),
                f"worksheet binding drift for adjudicator {adjudicator_id}")
        require(_blank_blinded_mutable_fields(document)
                == _blank_blinded_mutable_fields(expected),
                f"adjudicator {adjudicator_id} modified a response/gold/binding field")
        supplied_by_id[adjudicator_id] = document
    require(set(supplied_by_id) == set(expected_by_id),
            "filled adjudicator inventory differs from the frozen protocol")
    return supplied_by_id


def _consensus_value(values: list[Any]) -> Any:
    require(len(values) == ADJUDICATION_REQUIRED_JUDGES,
            "consensus requires exactly two adjudicators")
    if all(isinstance(value, list) for value in values):
        lengths = {len(value) for value in values}
        if len(lengths) != 1:
            return None
        return [
            _consensus_value([value[index] for value in values])
            for index in range(next(iter(lengths)))
        ]
    return values[0] if values[0] == values[1] else None


def _consensus_worksheet(template: Any, supplied: list[Any]) -> Any:
    if isinstance(template, dict):
        result = {}
        for name, child in template.items():
            if name.startswith("VERDICT_"):
                result[name] = _consensus_value([value.get(name) for value in supplied])
            else:
                result[name] = _consensus_worksheet(
                    child, [value.get(name) for value in supplied]
                ) if isinstance(child, dict) else json.loads(json.dumps(child))
        return result
    return json.loads(json.dumps(template))


def _dual_score_axis2(
    template: dict[str, Any], supplied: list[dict[str, Any]], *, terminal: bool,
    adjudicator_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    individual = [score_axis2(value, terminal=terminal) for value in supplied]
    consensus_worksheet = _consensus_worksheet(template, supplied)
    consensus = score_axis2(consensus_worksheet, terminal=terminal)
    primary = [result["primary_pass"] for result in individual]
    verdict_trees = [_verdict_tree(value) for value in supplied]
    exact_agreement = verdict_trees[0] == verdict_trees[1]
    if not exact_agreement:
        consensus["status"] = "adjudicator_disagreement"
        consensus["primary_pass"] = None
    elif any(value is None for value in primary):
        consensus["status"] = "pending_adjudication"
        consensus["primary_pass"] = None
    else:
        consensus["status"] = "scored"
        consensus["primary_pass"] = primary[0]
    consensus["adjudicator_results"] = [
        {"adjudicator_id": adjudicator_id, **result}
        for adjudicator_id, result in zip(adjudicator_ids, individual)
    ]
    consensus["exact_verdict_agreement"] = exact_agreement
    consensus["unanimous_primary"] = exact_agreement and primary[0] is not None
    return consensus, consensus_worksheet


def _dual_score_axis3(
    template: dict[str, Any], supplied: list[dict[str, Any]],
    adjudicator_ids: list[str],
) -> dict[str, Any]:
    individual = [score_axis3(value) for value in supplied]
    consensus_worksheet = _consensus_worksheet(template, supplied)
    consensus = score_axis3(consensus_worksheet)
    passes = [result["pass"] for result in individual]
    verdict_trees = [_verdict_tree(value) for value in supplied]
    exact_agreement = verdict_trees[0] == verdict_trees[1]
    if not exact_agreement:
        consensus.update(status="adjudicator_disagreement", **{"pass": None})
    elif any(value is None for value in passes):
        consensus.update(status="pending_adjudication", **{"pass": None})
    else:
        consensus.update(status="scored", **{"pass": passes[0]})
    consensus["exact_verdict_agreement"] = exact_agreement
    consensus["adjudicator_results"] = [
        {"adjudicator_id": adjudicator_id, **result}
        for adjudicator_id, result in zip(adjudicator_ids, individual)
    ]
    return consensus


def terminal_evidence_classification(
    cell: dict[str, Any], final_axis2: dict[str, Any], pre_axis2: dict[str, Any] | None,
) -> dict[str, Any]:
    if pre_axis2 is None:
        return {"status": "pending", "classification": None, "reason": "no pre-probe adjudication"}
    initial = pre_axis2.get("terminal_evidence_present")
    final = final_axis2.get("terminal_evidence_present")
    if initial is None or final is None:
        return {"status": "pending", "classification": None}
    if initial:
        return {"status": "classified", "classification": "terminal-evidence-initially-present"}
    if not final:
        return {"status": "classified", "classification": "never-present"}
    if cell["arm"] not in INTERACTIVE_ARMS:
        return {
            "status": "indeterminate", "classification": None,
            "reason": "terminal evidence changed in a passive cell",
        }
    raw = cell.get("_raw_cell") or {}
    successful_interaction = any(
        isinstance(entry, dict) and entry.get("ok") is True
        and entry.get("kind") in {"probe", "retrieval"}
        for entry in raw.get("probe_log") or []
    )
    if successful_interaction:
        return {"status": "classified", "classification": "probe-acquired"}
    return {
        "status": "indeterminate", "classification": None,
        "reason": "terminal evidence appeared only after the pre-probe answer, but no successful "
                  "retrieval/probe is logged",
    }


def aggregate_primary(scored_cells: list[dict[str, Any]], frozen: dict[str, Any]) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    primary_arm = preregistration["primary_arm"]
    by_key = {cell["cell_key"]: cell for cell in scored_cells}
    mapping = read_blind_map()
    roles: dict[str, Any] = {}
    for role in preregistration["roles"]:
        games: dict[str, Any] = {}
        for game in preregistration["games"]:
            seed_rows = []
            for seed in preregistration["seeds"]:
                key = logical_key(role, mapping[game], primary_arm, seed)
                cell = by_key[key]
                observation = cell["observation"]
                if observation["status"] != "answered":
                    status, passed = "missing", None
                elif cell.get("closure_adjudication_ready", True) is not True:
                    status, passed = "pending", None
                else:
                    passed = cell["axis2"]["primary_pass"]
                    status = "pending" if passed is None else "observed"
                seed_rows.append({"seed": seed, "cell_key": key, "status": status, "pass": passed})
            complete = all(row["status"] == "observed" for row in seed_rows)
            passes = sum(row["pass"] is True for row in seed_rows)
            games[game] = {
                "status": "scored" if complete else "indeterminate",
                "seed_results": seed_rows,
                "passes": passes,
                "required_passes": preregistration["game_pass_min_seeds"],
                "pass": passes >= preregistration["game_pass_min_seeds"] if complete else None,
            }
        roles[role] = {
            "games": games,
            "games_passed": sum(result["pass"] is True for result in games.values()),
            "games_scored": sum(result["pass"] is not None for result in games.values()),
        }
        completion_lengths = preregistration.get("autonomous_completion_lengths")
        if preregistration.get("stage") == "B" and isinstance(completion_lengths, dict):
            roles[role]["completion_strata"] = {}
            for stratum, exposed in (
                ("completion_exposed", True), ("completion_unexposed", False),
            ):
                stratum_games = [
                    game for game in preregistration["games"]
                    if (completion_lengths.get(game) is not None) is exposed
                ]
                roles[role]["completion_strata"][stratum] = {
                    "games": stratum_games,
                    "games_passed": sum(games[game]["pass"] is True for game in stratum_games),
                    "games_scored": sum(games[game]["pass"] is not None for game in stratum_games),
                }
    return roles


def _closure_stratum_report(
    role_summary: dict[str, Any], preregistration: dict[str, Any],
) -> dict[str, Any]:
    lengths = preregistration.get("autonomous_completion_lengths")
    require(isinstance(lengths, dict) and set(lengths) == set(preregistration["games"]),
            "Stage B closure lacks frozen completion-stratum assignments")
    minimum = preregistration["closure"]["ceiling_min_pass_games_per_stratum"]
    report: dict[str, Any] = {}
    for stratum, exposed in (
        ("completion_exposed", True), ("completion_unexposed", False),
    ):
        games = [
            game for game in preregistration["games"]
            if (lengths[game] is not None) is exposed
        ]
        require(len(games) == STAGE_B_SELECTION_PER_STRATUM,
                f"Stage B closure stratum {stratum} does not contain exactly three games")
        row: dict[str, Any] = {
            "games": games,
            "ceiling_required_passes": minimum,
        }
        for role in ("qwen", "ceiling"):
            summary = role_summary[role]
            game_results = summary.get("games")
            require(isinstance(game_results, dict)
                    and all(isinstance(game_results.get(game), dict) for game in games),
                    f"Stage B {role} summary lacks per-game results for {stratum}")
            role_scored = sum(game_results[game].get("pass") is not None for game in games)
            role_passed = sum(game_results[game].get("pass") is True for game in games)
            row[role] = {
                "games_scored": role_scored,
                "games_passed": role_passed,
            }
        complete = all(row[role]["games_scored"] == len(games)
                       for role in ("qwen", "ceiling"))
        if not complete:
            verdict = "indeterminate_incomplete"
        elif row["qwen"]["games_passed"] > 0:
            verdict = "qwen_goal_inference_witnessed"
        elif row["ceiling"]["games_passed"] < minimum:
            verdict = "packet_adequacy_not_established"
        else:
            verdict = "closure_condition_met"
        row["verdict"] = verdict
        report[stratum] = row
    return report


def closure_decision(role_summary: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    if preregistration["stage"] != "B":
        return {"status": "descriptive_only", "decision": "NO_CLOSURE",
                "reason": "Stage A is an instrument pilot"}
    if (preregistration.get("ceiling_spec") or {}).get("kind") != "blinded_human_cohort":
        return {
            "status": "descriptive_only", "decision": "NO_CLOSURE",
            "reason": "model ceilings are upper-bound diagnostics; closure requires a "
                      "screened blinded human respondent",
        }
    if not {"qwen", "ceiling"}.issubset(role_summary):
        return {"status": "indeterminate", "decision": "NO_CLOSURE",
                "reason": "qwen and ceiling roles are both required"}
    strata = _closure_stratum_report(role_summary, preregistration)
    qwen_passes = sum(row["qwen"]["games_passed"] for row in strata.values())
    ceiling_passes = sum(row["ceiling"]["games_passed"] for row in strata.values())
    qwen_scored = sum(row["qwen"]["games_scored"] for row in strata.values())
    ceiling_scored = sum(row["ceiling"]["games_scored"] for row in strata.values())
    result = {
        "qwen_games_passed": qwen_passes,
        "ceiling_games_passed": ceiling_passes,
        "completion_strata": strata,
    }
    if qwen_scored != len(preregistration["games"]) \
            or ceiling_scored != len(preregistration["games"]):
        return {
            "status": "indeterminate", "decision": "NO_CLOSURE",
            "reason": "missing or pending primary game-seeds", **result,
        }
    thresholds = preregistration["closure"]
    if qwen_passes > thresholds["qwen_max_pass_games"]:
        return {"status": "decided", "decision": "KEEP_ROLE_OPEN", **result}
    ceiling_strata_adequate = all(
        row["ceiling"]["games_passed"]
        >= thresholds["ceiling_min_pass_games_per_stratum"]
        for row in strata.values()
    )
    if (ceiling_passes < thresholds["ceiling_min_pass_games"]
            or not ceiling_strata_adequate):
        return {
            "status": "indeterminate", "decision": "NO_CLOSURE_PACKET_INDICTED",
            "reason": "transcript-matched ceiling did not establish packet adequacy in both "
                      "completion strata",
            **result,
        }
    return {
        "status": "decided",
        "decision": "FAILS_REQUIRED_GOAL_INFERENCE_GATE",
        "scope": "exact_frozen_checkpoint_runtime_packet_and_interaction_interface",
        "interpretation": (
            "preregistered operational go/no-go only; not a population incapacity estimate"
        ),
        "zero_of_six_one_sided_95pct_upper_bound": round(
            1.0 - 0.05 ** (1.0 / 6.0), 6
        ),
        **result,
    }


def _score_legacy_adjudications(
    template: dict[str, Any], adjudications: dict[str, Any], frozen: dict[str, Any],
    resolved: dict[str, dict[str, Any]], *, execute_plans: bool,
) -> dict[str, Any]:
    validate_adjudications(template, adjudications)
    adjudicated = {cell["cell_key"]: cell for cell in adjudications["cells"]}
    reverse = blind_to_game()
    scored_cells = []
    for base in template["cells"]:
        supplied = adjudicated[base["cell_key"]]
        resolution = resolved[base["cell_key"]]
        if resolution["selected"] is None:
            scored_cells.append({
                "cell_key": base["cell_key"], "role": base["role"], "game_blind": base["game_blind"],
                "arm": base["arm"], "seed": base["seed"], "observation": base["observation"],
                "axis1_consistency": base["axis1_consistency"],
                "axis2": {"status": "not observed", "primary_pass": None},
                "axis3": {"status": "not observed", "pass": None},
                "axis4_calibration": {"status": "not observed"},
                "axis5_plan": {"status": "not observed"},
                "closure_adjudication_ready": False,
                "terminal_evidence": {"status": "not observed", "classification": None},
            })
            continue
        raw_cell = resolution["selected"]["cell"]
        axis2 = score_axis2(supplied["axis2_worksheet"], terminal=True)
        pre_axis2 = (
            score_axis2(supplied["pre_probe_axis2_worksheet"], terminal=True)
            if supplied.get("pre_probe_axis2_worksheet") is not None else None
        )
        axis3 = score_axis3(supplied["axis3_worksheet"])
        game = reverse.get(base["game_blind"])
        require(game is not None, f"unknown blind id during scoring: {base['game_blind']}")
        plan = axis5_plan(
            raw_cell, game, frozen["preregistration"]["plan_action_budgets"][game], execute_plans
        )
        terminal_cell = dict(base)
        terminal_cell["_raw_cell"] = raw_cell
        scored_cells.append({
            "cell_key": base["cell_key"], "role": base["role"], "game_blind": base["game_blind"],
            "arm": base["arm"], "seed": base["seed"], "observation": base["observation"],
            "axis1_consistency": base["axis1_consistency"],
            "axis2": axis2,
            "axis3": axis3,
            "axis4_calibration": axis4_calibration(supplied["axis2_worksheet"]),
            "axis5_plan": plan,
            "terminal_evidence": terminal_evidence_classification(terminal_cell, axis2, pre_axis2),
        })
    roles = aggregate_primary(scored_cells, frozen)
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_scored_adjudication",
        "frozen_manifest_sha256": template["frozen_manifest_sha256"],
        "preregistration_sha256": template["preregistration_sha256"],
        "answers": template["answers"],
        "answers_bundle_sha256": template["answers_bundle_sha256"],
        "adjudications_sha256": sha256_json(adjudications),
        "cells": scored_cells,
        "primary_by_role": roles,
        "closure": closure_decision(roles, frozen),
    }


def _score_blinded_adjudications(
    template: dict[str, Any], adjudications: list[dict[str, Any]],
    frozen: dict[str, Any], resolved: dict[str, dict[str, Any]], *,
    execute_plans: bool, adjudication_key: bytes,
    adjudication_commitment_receipt: dict[str, Any],
) -> dict[str, Any]:
    preregistration = frozen["preregistration"]
    validate_adjudication_commitment_receipt(
        adjudication_commitment_receipt, adjudications, frozen
    )
    # Important ordering invariant: authenticate both opaque verdict artifacts in
    # full before deriving even one item->logical-cell mapping with the private key.
    supplied_by_id = validate_blinded_adjudications(
        template, adjudications, preregistration,
    )
    expected_key_sha = preregistration["adjudication_protocol"]["blinding"][
        "key_commitment_sha256"
    ]
    require(hashlib.sha256(adjudication_key).hexdigest() == expected_key_sha,
            "adjudication key differs from its frozen commitment")

    cells = _worksheet_cells(resolved, frozen, execute_plans=execute_plans)
    adjudicator_ids = [
        item["adjudicator_id"]
        for item in preregistration["adjudication_protocol"]["adjudicators"]
    ]
    supplied_items: dict[str, dict[str, dict[str, Any]]] = {}
    for adjudicator_id in adjudicator_ids:
        require(
            supplied_by_id[adjudicator_id].get("opaque_answer_bundle_commitment")
            == _opaque_answer_bundle_commitment(
                adjudication_key, adjudicator_id=adjudicator_id,
                answers_bundle_sha256=template["answers_bundle_sha256"],
            ),
            f"opaque answer-bundle binding drift for adjudicator {adjudicator_id}",
        )
        items = supplied_by_id[adjudicator_id]["items"]
        item_map = {
            item["item_id"]: item for item in items if isinstance(item, dict)
        }
        require(len(item_map) == len(items),
                f"duplicate/malformed opaque item for adjudicator {adjudicator_id}")
        supplied_items[adjudicator_id] = item_map

    answers_bundle_sha256 = template["answers_bundle_sha256"]
    expected_ids: dict[str, set[str]] = {adjudicator_id: set() for adjudicator_id in adjudicator_ids}
    scored_cells: list[dict[str, Any]] = []
    reverse = blind_to_game()
    for base in cells:
        resolution = resolved[base["cell_key"]]
        if resolution["selected"] is None:
            scored_cells.append({
                "cell_key": base["cell_key"], "role": base["role"],
                "game_blind": base["game_blind"], "arm": base["arm"],
                "seed": base["seed"], "observation": base["observation"],
                "axis1_consistency": base["axis1_consistency"],
                "axis2": {"status": "not observed", "primary_pass": None},
                "axis3": {"status": "not observed", "pass": None},
                "axis4_calibration": {"status": "not observed"},
                "axis5_plan": {"status": "not observed"},
                "terminal_evidence": {"status": "not observed", "classification": None},
            })
            continue

        judge_items = []
        for adjudicator_id in adjudicator_ids:
            item_id = _opaque_item_id(
                adjudication_key, adjudicator_id=adjudicator_id,
                cell_key=base["cell_key"], answers_bundle_sha256=answers_bundle_sha256,
            )
            expected_ids[adjudicator_id].add(item_id)
            item = supplied_items[adjudicator_id].get(item_id)
            require(item is not None,
                    f"committed worksheet lacks opaque item {item_id} for {adjudicator_id}")
            expected_answer_commitment = _opaque_answer_commitment(
                adjudication_key, adjudicator_id=adjudicator_id, item_id=item_id,
                answer_sha256=base["answer_sha256"],
            )
            require(item.get("opaque_answer_commitment") == expected_answer_commitment,
                    f"opaque answer binding drift in item {item_id}")
            judge_items.append(item)

        axis2, consensus_axis2 = _dual_score_axis2(
            base["axis2_worksheet"],
            [item["axis2_worksheet"] for item in judge_items],
            terminal=True, adjudicator_ids=adjudicator_ids,
        )
        axis3 = _dual_score_axis3(
            base["axis3_worksheet"],
            [item["axis3_worksheet"] for item in judge_items],
            adjudicator_ids,
        )
        raw_cell = resolution["selected"]["cell"]
        game = reverse.get(base["game_blind"])
        require(game is not None, f"unknown blind id during scoring: {base['game_blind']}")
        plan = axis5_plan(
            raw_cell, game, preregistration["plan_action_budgets"][game], execute_plans
        )
        scored_cells.append({
            "cell_key": base["cell_key"], "role": base["role"],
            "game_blind": base["game_blind"], "arm": base["arm"], "seed": base["seed"],
            "observation": base["observation"],
            "axis1_consistency": base["axis1_consistency"],
            "axis2": axis2,
            "axis3": axis3,
            "axis4_calibration": axis4_calibration(consensus_axis2),
            "axis5_plan": plan,
            "closure_adjudication_ready": (
                axis2.get("status") == "scored"
                and axis3.get("status") == "scored"
                and axis2.get("exact_verdict_agreement") is True
                and axis3.get("exact_verdict_agreement") is True
            ),
            "terminal_evidence": {
                "status": "withheld_from_closure_adjudication",
                "classification": None,
                "reason": "pre-probe presence would reveal Qwen versus ceiling; "
                          "requires a separately frozen secondary protocol",
            },
        })

    for adjudicator_id in adjudicator_ids:
        require(set(supplied_items[adjudicator_id]) == expected_ids[adjudicator_id],
                f"opaque item inventory drift for adjudicator {adjudicator_id}")
    roles = aggregate_primary(scored_cells, frozen)
    adjudication_digests = [sha256_json(document) for document in adjudications]
    return {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_scored_adjudication",
        "frozen_manifest_sha256": template["frozen_manifest_sha256"],
        "preregistration_sha256": template["preregistration_sha256"],
        "answers_bundle_sha256": answers_bundle_sha256,
        "answer_artifact_sha256s": template["answer_artifact_sha256s"],
        "adjudication_protocol_sha256": preregistration["adjudication_protocol_sha256"],
        "opaque_verdict_commitments": {
            adjudicator_id: supplied_by_id[adjudicator_id]["verdict_commitment_sha256"]
            for adjudicator_id in adjudicator_ids
        },
        "adjudication_artifact_sha256s": adjudication_digests,
        "adjudications_sha256": sha256_json(adjudication_digests),
        "opaque_commitment_receipt_sha256": sha256_json(
            adjudication_commitment_receipt
        ),
        "both_signed_opaque_commitments_verified_before_rejoin": True,
        "cells": scored_cells,
        "primary_by_role": roles,
        "closure": closure_decision(roles, frozen),
    }


def score_adjudications(
    template: dict[str, Any], adjudications: dict[str, Any] | list[dict[str, Any]],
    frozen: dict[str, Any], resolved: dict[str, dict[str, Any]], *,
    execute_plans: bool, adjudication_key: bytes | None = None,
    adjudication_commitment_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if frozen["preregistration"]["stage"] == "B":
        require(adjudication_key is not None,
                "Stage-B scoring requires the committed adjudication key")
        require(isinstance(adjudications, list),
                "Stage B requires two separate blinded adjudication documents")
        require(isinstance(adjudication_commitment_receipt, dict),
                "Stage B requires the pre-rejoin two-signature commitment receipt")
        return _score_blinded_adjudications(
            template, adjudications, frozen, resolved,
            execute_plans=execute_plans, adjudication_key=adjudication_key,
            adjudication_commitment_receipt=adjudication_commitment_receipt,
        )
    require(adjudication_key is None,
            "Stage-A diagnostic scoring cannot use Stage-B unblinding material")
    require(adjudication_commitment_receipt is None,
            "Stage-A diagnostic scoring cannot use a Stage-B commitment receipt")
    require(isinstance(adjudications, dict),
            "Stage-A diagnostic scoring expects one filled worksheet")
    return _score_legacy_adjudications(
        template, adjudications, frozen, resolved, execute_plans=execute_plans,
    )


def output_path_for(answer_paths: list[Path], bundle_sha: str, suffix: str) -> Path:
    first = answer_paths[0]
    return first.with_name(f"{first.stem}.{bundle_sha[:12]}.{suffix}.json")


def grade(
    answers_paths: Path | list[Path], execute_plans: bool, tally: bool,
    *, adjudications_paths: Path | list[Path] | None = None,
    adjudication_key_path: Path | None = None,
    adjudication_receipt_path: Path | None = None,
    output_path: Path | None = None,
) -> int:
    frozen = verify_freeze()
    paths = [answers_paths] if isinstance(answers_paths, Path) else list(answers_paths)
    require(bool(paths), "at least one answers file is required")

    adjudication_paths: list[Path] | None = None
    adjudication_documents: list[dict[str, Any]] | None = None
    commitment_receipt: dict[str, Any] | None = None
    if adjudications_paths is not None:
        adjudication_paths = (
            [adjudications_paths]
            if isinstance(adjudications_paths, Path) else list(adjudications_paths)
        )
        adjudication_documents = [
            load_object(path, "signed adjudication") for path in adjudication_paths
        ]
        if frozen["preregistration"]["stage"] == "B":
            # This is deliberately before load_adjudication_key: the official
            # scoring path cannot acquire rejoin material until two frozen-key
            # signatures and their external opaque commit point both verify.
            prevalidate_signed_blinded_adjudications(
                adjudication_documents, frozen["preregistration"],
                frozen_manifest_sha256=sha256_file(frozen_manifest_path()),
                preregistration_sha256=frozen["preregistration_sha256"],
            )
            require(adjudication_receipt_path is not None
                    and adjudication_receipt_path.is_file(),
                    "Stage-B scoring requires --adjudication-receipt from the no-key "
                    "commit phase")
            commitment_receipt = load_object(
                adjudication_receipt_path, "opaque adjudication commitment receipt"
            )
            validate_adjudication_commitment_receipt(
                commitment_receipt, adjudication_documents, frozen
            )
        else:
            require(len(adjudication_documents) == 1,
                    "Stage-A diagnostic scoring accepts exactly one filled worksheet")
            require(adjudication_receipt_path is None,
                    "--adjudication-receipt applies only to Stage B")
    else:
        require(adjudication_receipt_path is None,
                "--adjudication-receipt requires both signed --adjudications")

    adjudication_key = load_adjudication_key(
        adjudication_key_path, frozen["preregistration"]
    )
    worksheet, resolved = build_worksheet(
        paths, frozen, execute_plans=execute_plans,
        adjudication_key=adjudication_key,
    )
    if adjudications_paths is None:
        destination = output_path or output_path_for(
            paths, worksheet["answers_bundle_sha256"], "worksheet"
        )
        if frozen["preregistration"]["stage"] == "B":
            worksheet_bindings = []
            for document in worksheet["worksheets"]:
                adjudicator_id = document["adjudicator"]["adjudicator_id"]
                child = destination.with_name(
                    f"{destination.stem}.{adjudicator_id}{destination.suffix}"
                )
                if child.exists():
                    require(load_object(child, "existing blinded worksheet") == document,
                            f"existing blinded worksheet bytes/content drift: {child}")
                else:
                    atomic_create(child, document, mode=0o600)
                worksheet_bindings.append({
                    "adjudicator_id": adjudicator_id,
                    "path": str(child),
                    "sha256": sha256_file(child),
                })
            index = {
                key: value for key, value in worksheet.items() if key != "worksheets"
            }
            index["artifact_type"] = "s4_role_blinded_adjudication_index"
            index["worksheets"] = worksheet_bindings
            if destination.exists():
                require(load_object(destination, "existing blinded worksheet index") == index,
                        f"existing blinded worksheet index drift: {destination}")
            else:
                atomic_create(destination, index, mode=0o444)
            print(f"wrote/verified two independent blinded worksheets; index {destination}")
        elif destination.exists():
            print(f"worksheet already exists; left untouched: {destination}")
        else:
            atomic_create(destination, worksheet, mode=0o644)
            print(f"wrote append-only worksheet {destination} "
                  f"({len(worksheet['cells'])} expected cells)")
        if tally:
            counts: dict[str, int] = {}
            for resolution in resolved.values():
                counts[resolution["status"]] = counts.get(resolution["status"], 0) + 1
            print("observations " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
            print("closure unavailable until --adjudications is supplied")
        return 0

    require(adjudication_paths is not None and adjudication_documents is not None,
            "internal adjudication loading invariant failed")
    adjudications: dict[str, Any] | list[dict[str, Any]] = (
        adjudication_documents
        if frozen["preregistration"]["stage"] == "B"
        else adjudication_documents[0]
    )
    scored = score_adjudications(
        worksheet, adjudications, frozen, resolved, execute_plans=execute_plans,
        adjudication_key=adjudication_key,
        adjudication_commitment_receipt=commitment_receipt,
    )
    scored["adjudication_files"] = [
        {"path": str(path), "sha256": sha256_file(path)}
        for path in adjudication_paths
    ]
    scored["adjudication_files_sha256"] = sha256_json(scored["adjudication_files"])
    if adjudication_receipt_path is not None:
        scored["adjudication_commitment_receipt_file"] = {
            "path": str(adjudication_receipt_path),
            "sha256": sha256_file(adjudication_receipt_path),
        }
    destination = output_path or output_path_for(
        paths, sha256_json({"answers": worksheet["answers_bundle_sha256"],
                            "adjudications": scored["adjudication_files_sha256"]}), "graded"
    )
    atomic_create(destination, scored, mode=0o444)
    print(f"wrote append-only scored artifact {destination}")
    if tally:
        for role, summary in scored["primary_by_role"].items():
            print(f"{role}: games passed {summary['games_passed']}/{len(summary['games'])}; "
                  f"scored {summary['games_scored']}/{len(summary['games'])}")
        print(f"closure: {scored['closure']['decision']} ({scored['closure']['status']})")
    return 0


# ==================================================================== revision 4
#
# Two-stage sealing (notes/qwen-3.8-slice4-refinement-plan.md): the versioned
# FROZEN.json is created BEFORE any confirmatory gate or sentinel answer exists
# and therefore binds ASSETS and thresholds, never results.  CONTINUE.json is
# created exactly once from the complete confirmatory outputs and says CONTINUE
# or STOP; it never rewrites the freeze.  The legacy v2.2 single-certificate
# freeze above is retained, un-runnable in production, as the inspectable record
# of the failed revision.

PROTOCOL_R4 = "r4"
SEALED_R4 = SEALED / PROTOCOL_R4
FROZEN_R4 = SEALED_R4 / "FROZEN.json"
CONTINUE_R4 = SEALED_R4 / "CONTINUE.json"
R4_FORMAT_VERSION = 4

R4_SCRIPT_RELATIVE = SCRIPT_RELATIVE + (
    "agent/harness/s4_delta.py",
    "agent/harness/s4_gates.py",
    "agent/harness/s4_sentinels.py",
    "agent/harness/s4_ledgers.py",
    "agent/harness/s4_ceiling.py",
    "agent/harness/e2_probe_vlm.py",
)

R4_STOPPING_RULES = (
    "G0 is mechanical and must pass 100%. Every model-dependent claim needs its "
    "full 6/6 (GX additionally 8/8 exact integer coordinates); no retry, "
    "majority vote, silent repair, or plus-minus-one conversion. If any claim in "
    "a SELECTED arm's requirement set fails, or any sentinel threshold fails, or "
    "the independent adequacy attestation is not 'adequate', CONTINUE.json says "
    "STOP and the frozen protocol version ends. A redesign is a new version with "
    "new sealed fixtures — never a rerun. On CONTINUE, all 16 Qwen cells run "
    "without inspecting outcomes or stopping early; then the four "
    "transcript-matched P comparator cells; then grading. GD_dense_4px_exact is "
    "reported as a diagnostic and can block nothing."
)


def serving_snapshot_r4(model: Path, *, full_shards: bool = True) -> dict[str, Any]:
    """Mechanical serving identity — file hashes, versions, pinned constants.

    No model generation and no gate verdicts: readability claims are certified
    post-freeze by the claim harness; this snapshot only pins WHAT would serve.
    """
    import importlib.metadata as md

    import e2_probe_vlm as probe
    import s4_packet as spk
    import s4_run as srun

    auditor = spk.ProcessorAuditor(model)
    snapshot: dict[str, Any] = {
        "model_path": str(model),
        "processor_identity": auditor.identity,
        "runtime_versions": {
            package: md.version(package)
            for package in ("mlx-vlm", "mlx", "mlx-lm", "transformers")
        },
        "production_sampler": dict(probe.PRODUCTION_SAMPLER),
        "reasoning_effort": probe.REASONING_EFFORT,
        "budgets": {
            "answer_tokens": srun.MAX_ANSWER_TOKENS,
            "interaction_rounds": srun.INTERACTION_ROUNDS,
            "retrievals_per_round": srun.RETRIEVALS_PER_ROUND,
            "active_probes": srun.ACTIVE_PROBES,
            "max_images": srun.MAX_IMAGES,
            "max_visual_tokens": srun.MAX_VISUAL_TOKENS,
        },
        "request_prompt_sha256": hashlib.sha256(srun.REQUEST.encode()).hexdigest(),
    }
    if full_shards:
        shards = probe.fingerprint(model)
        snapshot["checkpoint_fingerprint"] = {
            "checkpoint_sha256": shards.get("checkpoint_sha256"),
            "verified_shards": True,
        }
    snapshot["snapshot_sha256"] = sha256_json(
        {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    )
    return snapshot


def _r4_confirm_assets() -> dict[str, Any]:
    """The sealed confirmation fixtures and sentinel assets FROZEN binds."""
    import s4_gates as gates
    import s4_sentinels as sentinels

    fixtures_root = SEALED_R4 / "fixtures"
    gate_manifests = sorted(fixtures_root.glob("fixture_manifest_*.json"))
    require(gate_manifests,
            "freeze-r4 requires sealed confirm gate fixtures "
            "(s4_gates.py --build-fixtures-only --namespace confirm)")
    sentinel_manifest = fixtures_root / "sentinels/sentinel_manifest.json"
    require(sentinel_manifest.is_file(),
            "freeze-r4 requires sealed sentinel assets "
            "(s4_sentinels.py --generate --namespace confirm)")
    gold_dir = fixtures_root / "sentinels/gold"
    sentinel_gold = {
        path.name: sha256_file(path) for path in sorted(gold_dir.glob("*.json"))
    }
    require(sentinel_gold, "sentinel gold is missing from the sealed fixtures")
    return {
        "gate_fixture_manifests": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in gate_manifests
        },
        "sentinel_manifest_sha256": sha256_file(sentinel_manifest),
        "sentinel_gold_files": sentinel_gold,
        "arm_requirements": {
            arm: list(claims) for arm, claims in gates.ARM_REQUIREMENTS.items()
        },
        "gate_thresholds": dict(gates.THRESHOLDS),
        "sentinel_thresholds": {
            "passive_variants": sentinels.PASSIVE_VARIANTS,
            "active_variants": sentinels.ACTIVE_VARIANTS,
            "pass_threshold": sentinels.PASS_THRESHOLD,
            "total_generations": sentinels.TOTAL_GENERATIONS,
        },
        "precision_profile": gates.PRECISION_PROFILE,
    }


def freeze_r4(preregistration_path: Path | None, model: Path) -> int:
    import s4_ledgers as ledgers

    ledgers.enforce_offline_scientific_run("s4_grade --freeze-r4", [])
    require(not FROZEN_R4.exists(), f"{FROZEN_R4} already exists — append-only")
    require(not CONTINUE_R4.exists(),
            "a continuation certificate exists without its freeze — sealed dir corrupt")
    for stray in ("claims.json", "sentinel_results.json"):
        require(not (SEALED_R4 / stray).exists(),
                f"confirmatory output {stray} predates the freeze — refusing")
    mapping = read_blind_map()
    raw = (load_object(preregistration_path, "preregistration")
           if preregistration_path is not None else {})
    preregistration = normalize_preregistration(raw, mapping)
    git = current_git_state()
    require(not git["dirty"], f"refusing to freeze a dirty worktree: {git['status']}")
    scripts = {}
    for relative in R4_SCRIPT_RELATIVE:
        path = ROOT / relative
        require(path.is_file(), f"missing protocol script: {path}")
        scripts[relative] = sha256_file(path)
    recaptures = {}
    for game in preregistration["games"]:
        manifest_path = (ROOT / "logs/s4_observation_log/recapture" / game
                         / "manifest.json")
        require(manifest_path.is_file(), f"missing recapture manifest for {game}")
        recaptures[game] = sha256_file(manifest_path)
    snapshot = serving_snapshot_r4(model)
    payload = {
        "format_version": R4_FORMAT_VERSION,
        "protocol_version": PROTOCOL_R4,
        "frozen_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "git_commit": git["commit"],
        "blind_map_sha256": sha256_file(SEALED / "blind_map.json"),
        "gold_files": snapshot_gold(mapping),
        "scripts": scripts,
        "recapture_manifests": recaptures,
        "serving_snapshot": snapshot,
        "packets": {
            mapping[game]: snapshot_packet(game, mapping[game], None)
            for game in preregistration["games"]
        },
        "confirm_assets": _r4_confirm_assets(),
        "stopping_rules": R4_STOPPING_RULES,
        "kaggle_eval_budget": ledgers.KAGGLE_EVAL_BUDGET,
        "submission_guard": (
            "KAGGLE_EVAL_BUDGET=0 through final grading; every slice-4 command "
            "path fails closed on submission capability; neither FROZEN nor "
            "CONTINUE grants submission authority"
        ),
        "preregistration": preregistration,
        "preregistration_sha256": sha256_json(preregistration),
    }
    atomic_create(FROZEN_R4, payload, mode=0o444)
    print(f"FROZEN[r4] {len(payload['gold_files'])} games at {git['commit'][:9]} "
          f"({sha256_file(FROZEN_R4)[:12]})")
    return 0


def verify_freeze_r4() -> dict[str, Any]:
    frozen = load_object(FROZEN_R4, "sealed r4 freeze")
    require(frozen.get("format_version") == R4_FORMAT_VERSION
            and frozen.get("protocol_version") == PROTOCOL_R4,
            "unsupported r4 freeze")
    mapping = read_blind_map()
    require(sha256_file(SEALED / "blind_map.json") == frozen.get("blind_map_sha256"),
            "SEALED DRIFT: blind_map.json changed after freeze")
    require(snapshot_gold(mapping) == frozen.get("gold_files"),
            "SEALED DRIFT: exact gold set or digest changed after freeze")
    require(set(frozen.get("scripts") or {}) == set(R4_SCRIPT_RELATIVE),
            "SEALED DRIFT: r4 protocol script inventory changed")
    for relative, digest in (frozen.get("scripts") or {}).items():
        path = ROOT / relative
        require(path.is_file() and sha256_file(path) == digest,
                f"PROTOCOL DRIFT: {relative} changed after freeze")
    preregistration = normalize_preregistration(frozen.get("preregistration"), mapping)
    require(preregistration == frozen.get("preregistration"),
            "invalid/non-canonical frozen preregistration")
    require(frozen.get("preregistration_sha256") == sha256_json(preregistration),
            "SEALED DRIFT: preregistration digest mismatch")
    expected_packets = frozen.get("packets")
    require(isinstance(expected_packets, dict)
            and set(expected_packets)
            == {mapping[game] for game in preregistration["games"]},
            "SEALED DRIFT: packet inventory mismatch")
    for blind_id, expected in expected_packets.items():
        game = expected.get("game") if isinstance(expected, dict) else None
        require(isinstance(game, str) and mapping.get(game) == blind_id,
                f"invalid frozen packet binding for {blind_id}")
        require(snapshot_packet(game, blind_id, None) == expected,
                f"PACKET DRIFT: exact packet bytes changed for {blind_id}")
    for game, digest in (frozen.get("recapture_manifests") or {}).items():
        manifest_path = (ROOT / "logs/s4_observation_log/recapture" / game
                         / "manifest.json")
        require(manifest_path.is_file() and sha256_file(manifest_path) == digest,
                f"RECAPTURE DRIFT: {game} manifest changed after freeze")
    git = current_git_state()
    require(not git["dirty"], f"refusing to proceed on a dirty worktree: {git['status']}")
    require(git["commit"] == frozen.get("git_commit"),
            f"git commit drift: {git['commit']} != {frozen.get('git_commit')}")
    require(frozen.get("kaggle_eval_budget") == 0,
            "r4 freeze must pin KAGGLE_EVAL_BUDGET=0")
    return frozen


def continue_r4(claims_path: Path, sentinel_results_path: Path,
                adequacy_path: Path) -> int:
    """One-shot continuation: bind the complete confirmatory outputs, aggregate
    mechanically, and write CONTINUE or STOP.  Never rewrites the freeze."""
    import s4_gates as gates
    import s4_sentinels as sentinels

    require(not CONTINUE_R4.exists(), f"{CONTINUE_R4} already exists — one-shot")
    frozen = verify_freeze_r4()
    frozen_sha = sha256_file(FROZEN_R4)

    claims_doc = load_object(claims_path, "confirmatory gate claims")
    require(claims_doc.get("namespace") == "confirm",
            "continuation requires CONFIRM-namespace gate claims")
    require(claims_doc.get("frozen_manifest_sha256") == frozen_sha,
            "gate claims are not bound to this exact FROZEN.json")
    claim_results = claims_doc.get("results") or {}
    selected_arms = frozen["preregistration"]["arms"]
    eligibility = gates.derive_arm_eligibility(claim_results, selected_arms)
    g0 = (claim_results.get("G0_protocol_serving") or {})
    require(g0.get("kind") == "mechanical", "G0 claim record is malformed")

    sentinel_doc = load_object(sentinel_results_path, "sentinel results")
    require(sentinel_doc.get("namespace") == "confirm"
            and sentinel_doc.get("frozen_manifest_sha256") == frozen_sha,
            "sentinel results are not bound to this exact FROZEN.json")
    passive_summary = sentinels.aggregate_passive(sentinel_doc["passive_worksheets"])
    active_summary = sentinels.aggregate_active(sentinel_doc["active_records"])
    adequacy = sentinels.validate_adequacy_attestation(
        load_object(adequacy_path, "independent adequacy attestation")
    )

    passive_pass = all(
        summary["pass"] for arm, summary in passive_summary.items()
        if arm in {"T", "V", "O"} and arm in selected_arms
    )
    sentinel_pass = passive_pass and (
        active_summary["pass"] if "P" in selected_arms else True
    )
    verdict = "CONTINUE" if (
        g0.get("pass") is True
        and eligibility["all_selected_arms_eligible"]
        and sentinel_pass
        and adequacy["verdict"] == "adequate"
    ) else "STOP"
    payload = {
        "format_version": R4_FORMAT_VERSION,
        "protocol_version": PROTOCOL_R4,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "frozen_manifest_sha256": frozen_sha,
        "gate_claims": {"path": str(claims_path), "sha256": sha256_file(claims_path)},
        "sentinel_results": {"path": str(sentinel_results_path),
                             "sha256": sha256_file(sentinel_results_path)},
        "adequacy_attestation": {"path": str(adequacy_path),
                                 "sha256": sha256_file(adequacy_path)},
        "eligibility": eligibility,
        "sentinel_summary": {"passive": passive_summary, "active": active_summary},
        "adequacy_verdict": adequacy["verdict"],
        "verdict": verdict,
        "rule": ("the pilot runner requires the exact verdict CONTINUE and "
                 "verifies every bound hash; a STOP ends this frozen version"),
    }
    atomic_create(CONTINUE_R4, payload, mode=0o444)
    print(f"CONTINUE[r4] verdict={verdict} ({sha256_file(CONTINUE_R4)[:12]})")
    return 0 if verdict == "CONTINUE" else 3


def verify_continue_r4(frozen_sha: str) -> dict[str, Any]:
    """Runner-side verification: exact verdict, exact bindings, live artifacts."""
    continuation = load_object(CONTINUE_R4, "continuation certificate")
    require(continuation.get("format_version") == R4_FORMAT_VERSION,
            "unsupported continuation certificate")
    require(continuation.get("frozen_manifest_sha256") == frozen_sha,
            "continuation certificate is bound to a different freeze")
    for binding_name in ("gate_claims", "sentinel_results", "adequacy_attestation"):
        binding = continuation.get(binding_name) or {}
        path = Path(binding.get("path", ""))
        require(path.is_file() and sha256_file(path) == binding.get("sha256"),
                f"continuation binding drift: {binding_name}")
    require(continuation.get("verdict") == "CONTINUE",
            f"continuation verdict is {continuation.get('verdict')!r}; "
            "the frozen run has ended")
    return continuation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--preregistration", type=Path,
                        help="JSON protocol/config; defaults to the explicit Stage-A pilot")
    parser.add_argument("--answers", type=Path, nargs="+")
    parser.add_argument("--adjudications", type=Path, nargs="+",
                        help="one Stage-A worksheet or both independently sealed Stage-B files")
    parser.add_argument("--adjudication-key", type=Path,
                        help="private Stage-B HMAC key matching the frozen commitment")
    parser.add_argument("--adjudication-receipt", type=Path,
                        help="no-key two-signature commit receipt required before Stage-B rejoin")
    parser.add_argument("--seal-adjudication", type=Path,
                        help="seal one completed blinded worksheet before unblinding")
    parser.add_argument("--adjudicator-signing-key", type=Path,
                        help="raw Ed25519 private key for the worksheet's frozen adjudicator")
    parser.add_argument("--commit-adjudications", type=Path, nargs=2,
                        metavar=("SIGNED_A", "SIGNED_B"),
                        help="verify both signatures and create the pre-rejoin opaque receipt")
    parser.add_argument("--prepare-ceiling", action="store_true",
                        help="write immutable Stage-B inputs containing exactly Qwen-delivered evidence")
    parser.add_argument("--prepare-familiarity", type=Path, metavar="DRAFT",
                        help="freeze blinded-human familiarity declarations before evidence release")
    parser.add_argument("--familiarity-commitment", type=Path,
                        help="pre-evidence commitment required by human --prepare-ceiling")
    parser.add_argument("--derive-stage-b-selection", type=Path, metavar="EXPOSURE_REGISTRY",
                        help="derive the deterministic Stage-B selection manifest without a model")
    parser.add_argument("--commit-stage-b-inventory", action="store_true",
                        help="write the immutable source inventory before any Stage-B ranking")
    parser.add_argument("--source-inventory-commitment", type=Path,
                        help="prior source-inventory artifact required by Stage-B selection")
    parser.add_argument("--out", type=Path, help="new output path (must not exist)")
    parser.add_argument("--execute-plans", action="store_true")
    parser.add_argument("--tally", action="store_true")
    parser.add_argument("--freeze-r4", action="store_true",
                        help="create the versioned r4 FROZEN.json (before any "
                             "confirmatory gate/sentinel answer exists)")
    parser.add_argument("--continue-r4", action="store_true",
                        help="one-shot continuation certificate from confirmatory "
                             "outputs; writes CONTINUE or STOP")
    parser.add_argument("--gate-claims", type=Path)
    parser.add_argument("--sentinel-results", type=Path)
    parser.add_argument("--adequacy", type=Path)
    parser.add_argument("--model", type=Path,
                        default=Path.home() / "models/mlx/Qwen3.8-27B-8bit")
    args = parser.parse_args()
    import s4_ledgers
    s4_ledgers.enforce_offline_scientific_run("s4_grade", [])
    if args.freeze_r4:
        require(not args.freeze and not args.continue_r4,
                "--freeze-r4 stands alone")
        return freeze_r4(args.preregistration, args.model)
    if args.continue_r4:
        require(args.gate_claims is not None and args.sentinel_results is not None
                and args.adequacy is not None,
                "--continue-r4 requires --gate-claims, --sentinel-results and "
                "--adequacy")
        return continue_r4(args.gate_claims, args.sentinel_results, args.adequacy)
    if args.seal_adjudication is not None:
        require(args.out is not None and not args.freeze and args.preregistration is None
                and args.answers is None and args.adjudications is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is not None
                and args.commit_adjudications is None and not args.prepare_ceiling
                and args.prepare_familiarity is None
                and args.familiarity_commitment is None
                and args.derive_stage_b_selection is None
                and not args.commit_stage_b_inventory
                and args.source_inventory_commitment is None
                and not args.execute_plans and not args.tally,
                "--seal-adjudication requires only one input and a new --out path")
        document = load_object(args.seal_adjudication, "completed blinded worksheet")
        atomic_create(
            args.out,
            seal_blinded_adjudication(document, args.adjudicator_signing_key),
            mode=0o444,
        )
        print(f"sealed opaque adjudicator verdicts {args.out} "
              f"({sha256_file(args.out)[:12]})")
        return 0
    if args.commit_adjudications is not None:
        require(args.out is not None and not args.freeze and args.preregistration is None
                and args.answers is None and args.adjudications is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is None
                and args.seal_adjudication is None and not args.prepare_ceiling
                and args.prepare_familiarity is None
                and args.familiarity_commitment is None
                and args.derive_stage_b_selection is None
                and not args.commit_stage_b_inventory
                and args.source_inventory_commitment is None
                and not args.execute_plans and not args.tally,
                "--commit-adjudications requires only two signed inputs and a new --out")
        frozen = verify_freeze()
        documents = [
            load_object(path, "signed adjudication")
            for path in args.commit_adjudications
        ]
        receipt = build_adjudication_commitment_receipt(documents, frozen)
        atomic_create(args.out, receipt, mode=0o444)
        print(f"committed two signed opaque adjudications {args.out} "
              f"({sha256_file(args.out)[:12]})")
        return 0
    if args.prepare_familiarity is not None:
        require(not args.freeze and args.preregistration is None and args.answers is None
                and args.adjudications is None and not args.prepare_ceiling
                and args.derive_stage_b_selection is None
                and not args.commit_stage_b_inventory
                and args.source_inventory_commitment is None
                and args.familiarity_commitment is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is None
                and args.commit_adjudications is None
                and args.seal_adjudication is None
                and not args.execute_plans and not args.tally,
                "--prepare-familiarity cannot be combined with freeze/grading options")
        prepare_familiarity_commitment(args.prepare_familiarity, args.out)
        return 0
    if args.commit_stage_b_inventory:
        require(args.out is not None and not args.freeze and args.preregistration is None
                and args.answers is None and args.adjudications is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is None
                and args.commit_adjudications is None
                and args.seal_adjudication is None
                and not args.prepare_ceiling and args.prepare_familiarity is None
                and args.familiarity_commitment is None
                and args.derive_stage_b_selection is None
                and args.source_inventory_commitment is None
                and not args.execute_plans and not args.tally,
                "--commit-stage-b-inventory requires only a new --out path")
        commitment = derive_stage_b_source_inventory_commitment()
        atomic_create(args.out, commitment, mode=0o444)
        print(f"wrote Stage-B source-inventory commitment {args.out} "
              f"({sha256_file(args.out)[:12]})")
        return 0
    if args.derive_stage_b_selection is not None:
        require(not args.freeze and args.preregistration is None and args.answers is None
                and args.adjudications is None and not args.prepare_ceiling
                and args.prepare_familiarity is None and args.familiarity_commitment is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is None
                and args.commit_adjudications is None
                and args.seal_adjudication is None
                and not args.commit_stage_b_inventory
                and args.source_inventory_commitment is not None
                and not args.execute_plans and not args.tally,
                "--derive-stage-b-selection requires only --source-inventory-commitment "
                "and optional --out")
        registry = load_object(
            args.derive_stage_b_selection, "prior-development exposure registry"
        )
        source_commitment = load_object(
            args.source_inventory_commitment, "Stage-B source-inventory commitment"
        )
        selection = derive_stage_b_selection_manifest(registry, source_commitment)
        if args.out is None:
            print(json.dumps(selection, indent=1, ensure_ascii=False))
        else:
            atomic_create(args.out, selection, mode=0o444)
            print(f"wrote Stage-B selection manifest {args.out} "
                  f"({sha256_file(args.out)[:12]})")
        return 0
    if args.freeze:
        require(args.answers is None and args.adjudications is None and not args.prepare_ceiling
                and args.prepare_familiarity is None and args.familiarity_commitment is None
                and args.adjudication_key is None
                and args.adjudication_receipt is None
                and args.adjudicator_signing_key is None
                and args.commit_adjudications is None
                and args.seal_adjudication is None
                and not args.commit_stage_b_inventory
                and args.source_inventory_commitment is None,
                "--freeze cannot be combined with grading inputs")
        return freeze(args.preregistration)
    if args.answers:
        require(not args.commit_stage_b_inventory
                and args.source_inventory_commitment is None
                and args.adjudicator_signing_key is None
                and args.commit_adjudications is None,
                "Stage-B inventory options cannot be combined with answer processing")
        if args.prepare_ceiling:
            require(args.adjudications is None and args.adjudication_key is None
                    and args.adjudication_receipt is None
                    and not args.execute_plans,
                    "--prepare-ceiling cannot be combined with adjudication or plan execution")
            prepare_ceiling_inputs(
                args.answers, args.out,
                familiarity_commitment_path=args.familiarity_commitment,
            )
            return 0
        require(args.familiarity_commitment is None,
                "--familiarity-commitment applies only to --prepare-ceiling")
        return grade(
            args.answers, args.execute_plans, args.tally,
            adjudications_paths=args.adjudications,
            adjudication_key_path=args.adjudication_key,
            adjudication_receipt_path=args.adjudication_receipt,
            output_path=args.out,
        )
    parser.error("pass --commit-stage-b-inventory, --derive-stage-b-selection, "
                 "--prepare-familiarity, "
                 "--seal-adjudication, --commit-adjudications, --freeze, or "
                 "--answers <cells.json> [...] ")
    return 2


if __name__ == "__main__":
    sys.exit(main())
