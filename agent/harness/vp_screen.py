#!/usr/bin/env python3
"""Freeze, run, resume, score, and verify VP Freeze-1 measurements."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gi2_traces import ROOT, _sha256  # noqa: E402
from vp_questions import (  # noqa: E402
    ARMS,
    COLOR_NAMES,
    GAMES,
    OUTPUT as QUESTIONS,
    SCALES,
    build_corpus_index,
    initialize_renderer,
    render_semantic,
    render_vp1,
    render_vp2,
)
from vp_regions import GoldRegion, score_region_boxes  # noqa: E402

FREEZE = ROOT / "logs/vp_freeze.json"
RAW = ROOT / "logs/vp_raw.jsonl"
RESULTS = ROOT / "logs/vp_results.json"
FORMAT_VERSION = 1
GOVERNING_COMMIT = "b3836e5"
MODEL_BASENAME = "Qwen3.6-27B-8bit"
FROZEN_FILES = (
    "agent/harness/vp_inventory.py",
    "agent/harness/vp_regions.py",
    "agent/harness/vp_questions.py",
    "agent/harness/vp_screen.py",
    "notes/vp-perception-screen.md",
    "tests/test_vp_regions.py",
    "tests/test_vp_questions.py",
)
GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "seed": 20260802,
    "chat_template_kwargs": {"enable_thinking": False},
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_freeze() -> dict[str, Any]:
    questions = json.loads(QUESTIONS.read_text())
    files = {}
    for relative in FROZEN_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"frozen file missing: {relative}")
        files[relative] = _sha256(path)
    contract = {
        "governing_commit": GOVERNING_COMMIT,
        "files": files,
        "questions": {
            "path": str(QUESTIONS.relative_to(ROOT)),
            "sha256": _sha256(QUESTIONS),
            "question_fingerprint": questions["question_fingerprint"],
            "inputs": questions["inputs"],
        },
        "model_basename": MODEL_BASENAME,
        "generation": GENERATION,
        "arms": list(ARMS),
        "games": list(GAMES),
    }
    return {
        "format_version": FORMAT_VERSION,
        "status": "frozen",
        "scope": "vp_freeze_1_measurement",
        "contract": contract,
        "contract_fingerprint": _fingerprint(contract),
    }


def verify_freeze() -> list[str]:
    try:
        existing = json.loads(FREEZE.read_text())
        expected = build_freeze()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if existing == expected:
        return []
    problems = []
    if existing.get("contract_fingerprint") != expected["contract_fingerprint"]:
        problems.append("contract fingerprint drift")
    actual_contract = existing.get("contract", {})
    expected_contract = expected["contract"]
    for relative, digest in expected_contract["files"].items():
        if actual_contract.get("files", {}).get(relative) != digest:
            problems.append(f"frozen file drift: {relative}")
    for key in ("governing_commit", "questions", "model_basename", "generation", "arms", "games"):
        if actual_contract.get(key) != expected_contract[key]:
            problems.append(f"contract drift: {key}")
    return problems or ["freeze differs"]


def require_freeze() -> dict[str, Any]:
    problems = verify_freeze()
    if problems:
        raise ValueError("VP implementation is not frozen: " + "; ".join(problems))
    return json.loads(FREEZE.read_text())


def _strict_json(text: Any) -> dict[str, Any]:
    if not isinstance(text, str) or not text or text[0] != "{" or text[-1] != "}":
        raise ValueError("response must be a bare JSON object")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("response must decode to an object")
    return value


def parse_vp1(text: Any) -> dict[str, Any]:
    value = _strict_json(text)
    expected = {"marked_cells", "patch_P", "pixel_count_band", "component_count_band", "lookups"}
    if set(value) != expected:
        raise ValueError("VP1 keys differ from schema")
    marked = value["marked_cells"]
    lookups = value["lookups"]
    patch = value["patch_P"]
    if not isinstance(marked, dict) or set(marked) != set("ABCDE"):
        raise ValueError("marked_cells must contain A-E")
    if not isinstance(lookups, dict) or set(lookups) != {"U1", "U2"}:
        raise ValueError("lookups must contain U1/U2")
    if not isinstance(patch, list) or len(patch) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in patch):
        raise ValueError("patch_P must be 3x3")
    if any(not isinstance(item, str) for item in list(marked.values()) + list(lookups.values())
           + [cell for row in patch for cell in row]
           + [value["pixel_count_band"], value["component_count_band"]]):
        raise ValueError("VP1 answers must be strings")
    colors = {"white", "light_gray", "gray", "dark_gray", "charcoal", "black", "magenta",
              "pink", "red", "blue", "light_blue", "yellow", "orange", "maroon", "green", "purple"}
    if any(item not in colors for item in list(marked.values()) + list(lookups.values())
           + [cell for row in patch for cell in row]):
        raise ValueError("unknown color name")
    if value["pixel_count_band"] not in {"0", "1-4", "5-16", "17-64", "65-256", "257-1024", "1025-4096"}:
        raise ValueError("unknown pixel-count band")
    if value["component_count_band"] not in {"0", "1", "2", "3-4", "5-8", "9-16", "17-32", "33+"}:
        raise ValueError("unknown component-count band")
    return value


def parse_vp2(text: Any) -> dict[str, Any]:
    value = _strict_json(text)
    if set(value) != {"changed_count_band", "regions", "no_op", "change_kind"}:
        raise ValueError("VP2 keys differ from schema")
    if not isinstance(value["changed_count_band"], str) or not isinstance(value["regions"], list):
        raise ValueError("invalid VP2 count/regions")
    if not isinstance(value["no_op"], bool) or value["change_kind"] not in {
        "appear", "disappear", "move", "recolor", "mixed", "none"
    }:
        raise ValueError("invalid VP2 no_op/change_kind")
    boxes = []
    for box in value["regions"]:
        if not isinstance(box, list) or len(box) != 4 or any(isinstance(x, bool) or not isinstance(x, int) for x in box):
            raise ValueError("invalid region box")
        if not (0 <= box[0] <= box[2] < 64 and 0 <= box[1] <= box[3] < 64):
            raise ValueError("region box is outside the board or reversed")
        boxes.append(box)
    if len(boxes) > 12 or len({tuple(box) for box in boxes}) != len(boxes) or boxes != sorted(boxes):
        raise ValueError("region boxes must be distinct, row-major, and at most 12")
    if value["changed_count_band"] not in {"0", "1-4", "5-16", "17-64", "65-256", "257-1024", "1025-4096"}:
        raise ValueError("unknown changed-count band")
    if value["no_op"] and not (value["changed_count_band"] == "0" and boxes == [] and value["change_kind"] == "none"):
        raise ValueError("inconsistent no-op fields")
    if not value["no_op"] and value["changed_count_band"] == "0":
        raise ValueError("changed response cannot use band 0")
    return value


def parse_semantic(text: Any, family: str) -> dict[str, Any]:
    value = _strict_json(text)
    if family == "identity":
        if set(value) != {"identity"} or value["identity"] not in "ABCD" or len(value["identity"]) != 1:
            raise ValueError("invalid identity response")
    elif set(value) != {"transition"} or value["transition"] not in {
        "became_true", "became_false", "stayed_true", "stayed_false"
    }:
        raise ValueError("invalid relation response")
    return value


def score_vp1(question: dict[str, Any], parsed: dict[str, Any] | None) -> dict[str, Any]:
    if parsed is None:
        return {"marked_correct": 0, "marked_total": 5, "patch_cells_correct": 0,
                "patch_cells_total": 9, "patch_exact": False, "pixel_band": False,
                "component_band": False, "lookups_correct": 0, "lookups_total": 2}
    marked_gold = {item["label"]: item["gold"] for item in question["markers"]}
    marked_correct = sum(parsed["marked_cells"].get(label) == gold for label, gold in marked_gold.items())
    patch_gold = question["patch"]["gold"]
    patch_cells = sum(parsed["patch_P"][r][c] == patch_gold[r][c] for r in range(3) for c in range(3))
    lookup_gold = {item["label"]: item["gold"] for item in question["lookups"]}
    return {
        "marked_correct": marked_correct, "marked_total": 5,
        "patch_cells_correct": patch_cells, "patch_cells_total": 9,
        "patch_exact": patch_cells == 9,
        "pixel_band": parsed["pixel_count_band"] == question["pixel_target"]["gold"],
        "component_band": parsed["component_count_band"] == question["component_target"]["gold"],
        "lookups_correct": sum(parsed["lookups"].get(label) == gold for label, gold in lookup_gold.items()),
        "lookups_total": 2,
    }


def score_vp2(question: dict[str, Any], parsed: dict[str, Any] | None) -> dict[str, Any]:
    gold = question["gold"]
    if parsed is None:
        return {"count_band": False, "no_op_correct": False, "change_kind": False, "matched": 0,
                "predicted_regions": 0, "gold_regions": len(gold["regions"]), "region_f1": 0.0}
    if question["changed"]:
        regions = [GoldRegion(tuple(item["box"]), item["cell_count"]) for item in gold["regions"]]
        try:
            region_score = score_region_boxes(parsed["regions"], regions)
        except ValueError:
            region_score = score_region_boxes([], regions)
    else:
        region_score = score_region_boxes([], [])
    return {
        "count_band": parsed["changed_count_band"] == gold["changed_count_band"],
        "no_op_correct": parsed["no_op"] == gold["no_op"],
        "change_kind": parsed["change_kind"] == gold["change_kind"],
        "matched": region_score.matched, "predicted_regions": region_score.predicted,
        "gold_regions": region_score.gold, "region_f1": region_score.f1,
    }


class JsonlLog:
    def __init__(self, path: Path):
        self.path = path; self.lock = threading.Lock()

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def append(self, row: dict[str, Any]) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n"); handle.flush()


def call_chat(base_url: str, payload: dict[str, Any], timeout: float) -> tuple[dict, float]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions",
                                     data=_canonical(payload),
                                     headers={"Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"model request failed: {exc}") from exc
    elapsed = time.monotonic() - started
    value = json.loads(raw)
    if not isinstance(value, dict): raise RuntimeError("response is not an object")
    return value, elapsed


def _assistant_text(response: dict[str, Any]) -> Any:
    try: return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError): return None


def _usage(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    return usage if isinstance(usage, dict) else {}


def _question_maps(document: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    questions, games = {}, {}
    for game in document["games"]:
        games[game["env"]] = game
        for family in ("vp1", "vp2", "semantic"):
            for question in game[family]: questions[question["question_id"]] = question
    return questions, games


def _permuted_vp1_question(question: dict[str, Any], palette_map: dict[int, int]) -> dict[str, Any]:
    inverse_names = {name: value for value, name in COLOR_NAMES.items()}
    recolor = lambda name: COLOR_NAMES[palette_map[inverse_names[name]]]
    result = json.loads(json.dumps(question))
    for marker in result["markers"]:
        marker["gold"] = recolor(marker["gold"])
    result["patch"]["gold"] = [[recolor(cell) for cell in row] for row in result["patch"]["gold"]]
    for lookup in result["lookups"]:
        lookup["gold"] = recolor(lookup["gold"])
    for target in ("pixel_target", "component_target"):
        result[target]["value"] = palette_map[result[target]["value"]]
        result[target]["color"] = COLOR_NAMES[result[target]["value"]]
    return result


def _execute(row: dict[str, Any], *, question: dict[str, Any], index, model: str,
             base_url: str, timeout: float, chat=call_chat) -> dict[str, Any]:
    family = row["family"]
    palette_map = row.get("palette_map")
    scoring_question = (_permuted_vp1_question(question, palette_map)
                        if family == "vp1" and palette_map else question)
    if family == "vp1": messages, packet_meta = render_vp1(scoring_question, index, row["arm"], palette_map); max_tokens = 512
    elif family == "vp2": messages, packet_meta = render_vp2(question, index, row["arm"], row["packaging"], palette_map); max_tokens = 320
    else: messages, packet_meta = render_semantic(question, index, row["arm"], row["packaging"]); max_tokens = 96
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, **GENERATION}
    response, elapsed = chat(base_url, payload, timeout)
    raw_text = _assistant_text(response)
    parsed = None; parse_error = None
    try:
        parsed = parse_vp1(raw_text) if family == "vp1" else parse_vp2(raw_text) if family == "vp2" else parse_semantic(raw_text, question["family"])
    except (ValueError, json.JSONDecodeError) as exc:
        parse_error = str(exc)
    if family == "vp1": score = score_vp1(scoring_question, parsed)
    elif family == "vp2": score = score_vp2(scoring_question, parsed)
    else:
        key = "identity" if question["family"] == "identity" else "transition"
        score = {"correct": parsed is not None and parsed[key] == question["gold"]}
    return {
        **row, "status": "complete", "recorded_at": _now(), "model": model,
        "freeze_fingerprint": require_freeze()["contract_fingerprint"],
        "request_sha256": _fingerprint(payload), "packet_meta": packet_meta,
        "elapsed_seconds": elapsed, "usage": _usage(response), "raw_response": response,
        "raw_output": raw_text, "parse_valid": parsed is not None, "parse_error": parse_error,
        "parsed": parsed, "score": score,
    }


def run_rows(rows: list[dict[str, Any]], *, questions: dict[str, dict], index, model: str,
             base_url: str, timeout: float, concurrency: int, continue_on_error: bool = False) -> dict[str, int]:
    if Path(model).name != MODEL_BASENAME:
        raise ValueError(f"measurement model must end with {MODEL_BASENAME}")
    freeze = require_freeze(); logger = JsonlLog(RAW); existing = logger.records()
    for record in existing:
        if record.get("freeze_fingerprint") != freeze["contract_fingerprint"]:
            raise ValueError("raw log contains a different freeze")
    terminal = {record["row_id"] for record in existing if record.get("status") == "complete"}
    pending = [row for row in rows if row["row_id"] not in terminal]
    summary = {"planned": len(rows), "already_complete": len(rows) - len(pending), "complete": 0, "error": 0}

    def one(row):
        try:
            return _execute(row, question=questions[row["question_id"]], index=index, model=model,
                            base_url=base_url, timeout=timeout)
        except Exception as exc:
            return {**row, "status": "error", "recorded_at": _now(), "model": model,
                    "freeze_fingerprint": freeze["contract_fingerprint"],
                    "error_type": type(exc).__name__, "error": str(exc)}

    fatal = None
    pool = ThreadPoolExecutor(max_workers=concurrency)
    futures = {}
    iterator = iter(pending)
    try:
        for row in iterator:
            futures[pool.submit(one, row)] = row
            if len(futures) == concurrency:
                break
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future, None)
                if future.cancelled():
                    continue
                result = future.result(); logger.append(result); summary[result["status"]] += 1
                if result["status"] == "error" and not continue_on_error and fatal is None:
                    fatal = result
            if fatal:
                for future in futures:
                    future.cancel()
                break
            for row in iterator:
                futures[pool.submit(one, row)] = row
                if len(futures) == concurrency:
                    break
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if fatal:
        raise RuntimeError(f"{fatal['row_id']}: {fatal['error']}")
    return summary


def _complete_records() -> list[dict[str, Any]]:
    latest = {}
    for row in JsonlLog(RAW).records():
        if row.get("status") == "complete": latest[row["row_id"]] = row
    return list(latest.values())


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _paired_cluster_se(left: list[dict], right: list[dict], value: Callable[[dict], float]) -> float:
    """Standard error of paired board/pair-cluster differences."""
    left_map = {row["question_id"]: row for row in left}
    right_map = {row["question_id"]: row for row in right}
    common = sorted(set(left_map) & set(right_map))
    differences = [value(left_map[qid]) - value(right_map[qid]) for qid in common]
    if len(differences) < 2:
        return 0.0
    return statistics.stdev(differences) / math.sqrt(len(differences))


def _hierarchical_ci(rows: list[dict], statistic: Callable[[list[dict]], float], *,
                     seed: str, replicates: int = 2000) -> list[float]:
    """Deterministic 90% games→sessions→questions cluster bootstrap."""
    if not rows:
        return [0.0, 0.0]
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    by_game: dict[str, dict[int, list[dict]]] = {}
    for row in rows:
        by_game.setdefault(row["env"], {}).setdefault(int(row["session_index"]), []).append(row)
    games = sorted(by_game)
    estimates = []
    for _ in range(replicates):
        sample = []
        for boot_game in range(len(games)):
            env = rng.choice(games)
            sessions = sorted(by_game[env])
            for _boot_session in range(len(sessions)):
                session = rng.choice(sessions)
                cluster = by_game[env][session]
                for _ in range(len(cluster)):
                    cloned = dict(rng.choice(cluster))
                    cloned["_bootstrap_game"] = boot_game
                    sample.append(cloned)
        estimates.append(float(statistic(sample)))
    estimates.sort()
    low = estimates[math.floor(.05 * (replicates - 1))]
    high = estimates[math.ceil(.95 * (replicates - 1))]
    return [low, high]


def _game_macro(rows: list[dict], value: Callable[[list[dict]], float]) -> float:
    grouped: dict[Any, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("_bootstrap_game", row["env"]), []).append(row)
    return _mean([value(group) for group in grouped.values()])


def _vp1_board_margin(row: dict) -> float:
    score = row["score"]
    return min(
        (score["marked_correct"] / score["marked_total"]) / .90,
        float(score["patch_exact"]) / .70,
        float(score["pixel_band"]) / .75,
        float(score["component_band"]) / .70,
    )


def _vp1_arm_summary(records: list[dict], arm: str) -> dict[str, Any]:
    rows = [r for r in records if r["family"] == "vp1" and r["arm"] == arm]
    per_game = {}
    for env in GAMES:
        game = [r for r in rows if r["env"] == env]
        per_game[env] = {
            "marked_accuracy": sum(r["score"]["marked_correct"] for r in game) / max(1, sum(r["score"]["marked_total"] for r in game)),
            "patch_cell_accuracy": sum(r["score"]["patch_cells_correct"] for r in game) / max(1, sum(r["score"]["patch_cells_total"] for r in game)),
            "patch_exact_accuracy": _mean([float(r["score"]["patch_exact"]) for r in game]),
            "pixel_band_accuracy": _mean([float(r["score"]["pixel_band"]) for r in game]),
            "component_band_accuracy": _mean([float(r["score"]["component_band"]) for r in game]),
            "lookup_accuracy": sum(r["score"]["lookups_correct"] for r in game) / max(1, sum(r["score"]["lookups_total"] for r in game)),
            "first_pass_validity": _mean([float(r["parse_valid"]) for r in game]),
        }
    macro = {key: _mean([per_game[env][key] for env in GAMES]) for key in next(iter(per_game.values()))}
    passes = (macro["marked_accuracy"] >= .90 and sum(per_game[e]["marked_accuracy"] >= .80 for e in GAMES) >= 5
              and min(per_game[e]["marked_accuracy"] for e in GAMES) >= .60
              and macro["patch_cell_accuracy"] >= .97 and macro["patch_exact_accuracy"] >= .70
              and macro["pixel_band_accuracy"] >= .75 and macro["component_band_accuracy"] >= .70)
    margin = min(macro["marked_accuracy"]/.90, macro["patch_exact_accuracy"]/.70,
                 macro["pixel_band_accuracy"]/.75, macro["component_band_accuracy"]/.70)
    intervals = {
        "marked_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: sum(r["score"]["marked_correct"] for r in group) / sum(r["score"]["marked_total"] for r in group)), seed=f"vp1:{arm}:marked"),
        "patch_cell_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: sum(r["score"]["patch_cells_correct"] for r in group) / sum(r["score"]["patch_cells_total"] for r in group)), seed=f"vp1:{arm}:patch-cell"),
        "patch_exact_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["patch_exact"]) for r in group])), seed=f"vp1:{arm}:patch-exact"),
        "pixel_band_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["pixel_band"]) for r in group])), seed=f"vp1:{arm}:pixel"),
        "component_band_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["component_band"]) for r in group])), seed=f"vp1:{arm}:component"),
    }
    return {"arm": arm, "n": len(rows), "per_game": per_game, "macro": macro,
            "interval_90": intervals,
            "passes": passes, "normalized_margin": margin,
            "mean_input_tokens": _mean([float(r.get("usage", {}).get("prompt_tokens", 0)) for r in rows]),
            "mean_encoded_chars": _mean([float(r["packet_meta"]["encoded_chars"]) for r in rows])}


def select_champion(records: list[dict]) -> tuple[str, dict[str, Any]]:
    summaries = {arm: _vp1_arm_summary(records, arm) for arm in ARMS}
    candidates = [summaries[arm] for arm in ("I-4", "I-8", "I-16")]
    candidates.sort(key=lambda item: -item["normalized_margin"])
    best = candidates[0]
    best_rows = [r for r in records if r["family"] == "vp1" and r["arm"] == best["arm"]]
    tied = []
    tie_diagnostics = {}
    for candidate in candidates:
        rows = [r for r in records if r["family"] == "vp1" and r["arm"] == candidate["arm"]]
        standard_error = _paired_cluster_se(best_rows, rows, _vp1_board_margin)
        gap = best["normalized_margin"] - candidate["normalized_margin"]
        tie_diagnostics[candidate["arm"]] = {"gap_from_best": gap, "paired_board_se": standard_error}
        if gap <= standard_error + 1e-12:
            tied.append(candidate)
    tied.sort(key=lambda item: (item["mean_input_tokens"], item["mean_encoded_chars"], SCALES[item["arm"]]))
    champion = tied[0]["arm"]
    return champion, {"arms": summaries, "champion": champion,
                      "tie_diagnostics": tie_diagnostics,
                      "visual_route_pass": summaries[champion]["passes"]}


def _micro_region(rows: list[dict]) -> float:
    matched = sum(r["score"]["matched"] for r in rows)
    predicted = sum(r["score"]["predicted_regions"] for r in rows)
    gold = sum(r["score"]["gold_regions"] for r in rows)
    precision = matched / predicted if predicted else 0.0
    recall = matched / gold if gold else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _balanced_accuracy(rows: list[dict]) -> float:
    positives = [r for r in rows if not r["question_changed"]]
    negatives = [r for r in rows if r["question_changed"]]
    return (_mean([float(r["score"]["no_op_correct"]) for r in positives])
            + _mean([float(r["score"]["no_op_correct"]) for r in negatives])) / 2


def _vp2_pair_margin(row: dict) -> float:
    if row["question_changed"]:
        return min(float(row["score"]["count_band"]) / .80,
                   float(row["score"]["region_f1"]) / .70)
    if row["env"] in {"tu93", "ls20"}:
        return float(row["score"]["count_band"]) / .80
    return min(float(row["score"]["count_band"]) / .80,
               float(row["score"]["no_op_correct"]) / .85)


def packaging_summary(records: list[dict], champion: str) -> dict[str, Any]:
    out = {}
    for packaging in ("separate", "contact"):
        rows = [r for r in records if r["phase"] == "vp2-selector" and r["arm"] == champion and r["packaging"] == packaging]
        per_game = {}
        for env in GAMES:
            game = [r for r in rows if r["env"] == env]
            changed = [r for r in game if r["question_changed"]]
            count_acc = _mean([float(r["score"]["count_band"]) for r in changed])
            f1 = _micro_region(changed)
            terms = [count_acc/.80, f1/.70]
            ba = None
            if env not in {"tu93", "ls20"}:
                ba = _balanced_accuracy(game); terms.append(ba/.85)
            per_game[env] = {"changed_count_accuracy": count_acc, "region_f1": f1,
                             "no_op_balanced_accuracy": ba, "normalized_margin": min(terms)}
        out[packaging] = {"per_game": per_game,
                          "score": _mean([per_game[e]["normalized_margin"] for e in GAMES]),
                          "mean_input_tokens": _mean([float(r.get("usage", {}).get("prompt_tokens", 0)) for r in rows]),
                          "mean_encoded_chars": _mean([float(r["packet_meta"]["encoded_chars"]) for r in rows])}
    best = max(out, key=lambda p: out[p]["score"])
    best_rows = [r for r in records if r["phase"] == "vp2-selector" and r["packaging"] == best]
    tied = []
    tie_diagnostics = {}
    for packaging in ("separate", "contact"):
        rows = [r for r in records if r["phase"] == "vp2-selector" and r["packaging"] == packaging]
        standard_error = _paired_cluster_se(best_rows, rows, _vp2_pair_margin)
        gap = out[best]["score"] - out[packaging]["score"]
        tie_diagnostics[packaging] = {"gap_from_best": gap, "paired_pair_se": standard_error}
        if gap <= standard_error + 1e-12:
            tied.append(packaging)
    winner = min(tied, key=lambda p: (out[p]["mean_input_tokens"], out[p]["mean_encoded_chars"],
                                      0 if p == "contact" else 1))
    return {"packagings": out, "selected": winner, "tie_diagnostics": tie_diagnostics}


def vp2_summary(records: list[dict], champion: str, packaging: str,
                phases: set[str] | None = None) -> dict[str, Any]:
    phases = phases or {"vp2-selector", "vp2-main"}
    rows = [r for r in records if r["family"] == "vp2" and r["arm"] == champion
            and r["packaging"] == packaging and r["phase"] in phases]
    per_game = {}
    for env in GAMES:
        game = [r for r in rows if r["env"] == env]
        changed = [r for r in game if r["question_changed"]]
        count = _mean([float(r["score"]["count_band"]) for r in game])
        f1 = _micro_region(changed)
        ba = _balanced_accuracy(game) if env not in {"tu93", "ls20"} else None
        per_game[env] = {"changed_count_accuracy": count, "region_f1": f1,
                         "no_op_balanced_accuracy": ba,
                         "change_kind_accuracy": _mean([float(r["score"]["change_kind"]) for r in game]),
                         "first_pass_validity": _mean([float(r["parse_valid"]) for r in game])}
    count_macro = _mean([per_game[e]["changed_count_accuracy"] for e in GAMES])
    f1_macro = _mean([per_game[e]["region_f1"] for e in GAMES])
    eligible_ba = [per_game[e]["no_op_balanced_accuracy"] for e in GAMES if per_game[e]["no_op_balanced_accuracy"] is not None]
    passes = (count_macro >= .80 and f1_macro >= .70
              and sum(per_game[e]["changed_count_accuracy"] >= .60 and per_game[e]["region_f1"] >= .60 for e in GAMES) >= 5
              and _mean(eligible_ba) >= .85
              and sum(value >= .70 for value in eligible_ba) >= 3)
    intervals = {
        "changed_count_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["count_band"]) for r in group])), seed=f"vp2:{champion}:{packaging}:count"),
        "region_f1": _hierarchical_ci(
            [r for r in rows if r["question_changed"]], lambda sample: _game_macro(sample, _micro_region), seed=f"vp2:{champion}:{packaging}:regions"),
        "change_kind_accuracy": _hierarchical_ci(
            rows, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["change_kind"]) for r in group])), seed=f"vp2:{champion}:{packaging}:kind"),
    }
    eligible_rows = [r for r in rows if r["env"] not in {"tu93", "ls20"}]
    intervals["no_op_balanced_accuracy"] = _hierarchical_ci(
        eligible_rows, lambda sample: _game_macro(sample, _balanced_accuracy), seed=f"vp2:{champion}:{packaging}:noop")
    return {"n": len(rows), "per_game": per_game,
            "macro": {"changed_count_accuracy": count_macro, "region_f1": f1_macro,
                      "no_op_balanced_accuracy": _mean(eligible_ba),
                      "change_kind_accuracy": _mean([per_game[e]["change_kind_accuracy"] for e in GAMES])},
            "interval_90": intervals, "passes_pixel": passes}


def semantic_summary(records: list[dict], champion: str, packaging: str) -> dict[str, Any]:
    rows = [r for r in records if r["family"] == "semantic" and r["arm"] == champion and r["packaging"] == packaging]
    per_game = {}
    for env in GAMES:
        per_game[env] = {}
        for family in ("identity", "relation"):
            subset = [r for r in rows if r["env"] == env and r["semantic_family"] == family]
            per_game[env][family] = _mean([float(r["score"]["correct"]) for r in subset])
    identity = _mean([per_game[e]["identity"] for e in GAMES])
    relation = _mean([per_game[e]["relation"] for e in GAMES])
    passes = (identity >= .75 and relation >= .70
              and sum(per_game[e]["identity"] >= 4/6 and per_game[e]["relation"] >= 4/6 for e in GAMES) >= 4
              and min(per_game[e][f] for e in GAMES for f in ("identity", "relation")) >= 2/6)
    intervals = {}
    for family in ("identity", "relation"):
        subset = [r for r in rows if r["semantic_family"] == family]
        intervals[f"{family}_accuracy"] = _hierarchical_ci(
            subset, lambda sample: _game_macro(sample, lambda group: _mean([float(r["score"]["correct"]) for r in group])),
            seed=f"semantic:{champion}:{packaging}:{family}")
    return {"n": len(rows), "per_game": per_game,
            "macro": {"identity_accuracy": identity, "relation_accuracy": relation},
            "interval_90": intervals,
            "passes_semantic": passes}


def palette_summary(records: list[dict], champion: str, packaging: str) -> dict[str, Any]:
    rows = [r for r in records if r["phase"] == "palette" and r["arm"] == champion]
    out = {"n": len(rows), "permutation": {}}
    for permutation in ("perm-1", "perm-2"):
        subset = [r for r in rows if r["permutation"] == permutation]
        vp1 = [r for r in subset if r["family"] == "vp1"]
        vp2 = [r for r in subset if r["family"] == "vp2"]
        out["permutation"][permutation] = {
            "n": len(subset),
            "vp1_marked_accuracy": sum(r["score"]["marked_correct"] for r in vp1) / max(1, sum(r["score"]["marked_total"] for r in vp1)),
            "vp1_patch_cell_accuracy": sum(r["score"]["patch_cells_correct"] for r in vp1) / max(1, sum(r["score"]["patch_cells_total"] for r in vp1)),
            "vp1_pixel_band_accuracy": _mean([float(r["score"]["pixel_band"]) for r in vp1]),
            "vp1_component_band_accuracy": _mean([float(r["score"]["component_band"]) for r in vp1]),
            "vp2_changed_count_accuracy": _mean([float(r["score"]["count_band"]) for r in vp2]),
            "vp2_region_f1": _micro_region([r for r in vp2 if r["question_changed"]]),
            "first_pass_validity": _mean([float(r["parse_valid"]) for r in subset]),
        }
    return out


def write_results(document: dict[str, Any]) -> dict[str, Any]:
    records = _complete_records(); result: dict[str, Any] = {
        "format_version": 1, "status": "in_progress", "scope": "vp_freeze_1_iteration",
        "freeze_fingerprint": require_freeze()["contract_fingerprint"],
        "question_fingerprint": document["question_fingerprint"], "n_complete": len(records),
    }
    vp1_records = [r for r in records if r["family"] == "vp1"]
    if vp1_records:
        champion, vp1 = select_champion(records); result["vp1"] = vp1
        if all(vp1["arms"][arm]["n"] == 48 for arm in ARMS):
            result["champion"] = champion
    if "champion" in result:
        selector = packaging_summary(records, result["champion"])
        if all(len([r for r in records if r.get("phase") == "vp2-selector" and r.get("packaging") == p]) == 48 for p in ("separate", "contact")):
            result["packaging"] = selector
    if "packaging" in result:
        champion, packaging = result["champion"], result["packaging"]["selected"]
        vp2 = vp2_summary(records, champion, packaging); semantic = semantic_summary(records, champion, packaging)
        result["vp2"] = vp2; result["vp2_semantic"] = semantic
        controls = {"I-A": vp2_summary(records, "I-A", "ascii", {"vp2-control"})}
        if champion != "I-4":
            controls["I-4"] = vp2_summary(records, "I-4", packaging, {"vp2-control"})
        result["vp2_controls"] = controls
        result["palette_permutation"] = palette_summary(records, champion, packaging)
        if vp2["n"] == 144 and semantic["n"] == 72:
            result["vp2_pass"] = bool(vp2["passes_pixel"] and semantic["passes_semantic"])
            if result["palette_permutation"]["n"] == 48:
                result["status"] = "complete"
    RESULTS.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return result


def _vp1_rows(document: dict) -> list[dict]:
    return [{"row_id": f"vp1|{arm}|{q['question_id']}", "phase": "vp1", "family": "vp1",
             "arm": arm, "question_id": q["question_id"], "env": q["env"],
             "session_index": q["session_index"]}
            for game in document["games"] for q in game["vp1"] for arm in ARMS]


def _selector_rows(document: dict, champion: str) -> list[dict]:
    qmap, _ = _question_maps(document)
    ids = [qid for game in document["games"] for qid in game["vp2_selector"]]
    return [{"row_id": f"vp2-selector|{champion}|{packaging}|{qid}", "phase": "vp2-selector",
             "family": "vp2", "arm": champion, "packaging": packaging, "question_id": qid,
             "env": qmap[qid]["env"], "session_index": qmap[qid]["session_index"],
             "question_changed": qmap[qid]["changed"]}
            for qid in ids for packaging in ("separate", "contact")]


def _vp2_main_rows(document: dict, champion: str, packaging: str) -> list[dict]:
    rows = []
    for game in document["games"]:
        selector = set(game["vp2_selector"])
        for q in game["vp2"]:
            if q["question_id"] not in selector:
                rows.append({"row_id": f"vp2-main|{champion}|{packaging}|{q['question_id']}",
                             "phase": "vp2-main", "family": "vp2", "arm": champion,
                             "packaging": packaging, "question_id": q["question_id"],
                             "env": q["env"], "session_index": q["session_index"],
                             "question_changed": q["changed"]})
            rows.append({"row_id": f"vp2-control|I-A|ascii|{q['question_id']}",
                         "phase": "vp2-control", "family": "vp2", "arm": "I-A",
                         "packaging": "ascii", "question_id": q["question_id"],
                         "env": q["env"], "session_index": q["session_index"],
                         "question_changed": q["changed"]})
            if champion != "I-4":
                rows.append({"row_id": f"vp2-control|I-4|{packaging}|{q['question_id']}",
                             "phase": "vp2-control", "family": "vp2", "arm": "I-4",
                             "packaging": packaging, "question_id": q["question_id"],
                             "env": q["env"], "session_index": q["session_index"],
                             "question_changed": q["changed"]})
    return rows


def _semantic_rows(document: dict, champion: str, packaging: str) -> list[dict]:
    return [{"row_id": f"semantic|{champion}|{packaging}|{q['question_id']}", "phase": "semantic",
             "family": "semantic", "semantic_family": q["family"], "arm": champion,
             "packaging": packaging, "question_id": q["question_id"], "env": q["env"],
             "session_index": q["session_index"]}
            for game in document["games"] for q in game["semantic"]]


def _palette_rows(document: dict, champion: str, packaging: str) -> list[dict]:
    qmap, _ = _question_maps(document)
    rows = []
    for game in document["games"]:
        for item in game["palette"]:
            question = qmap[item["question_id"]]
            permutation = item["permutation"]
            rows.append({
                "row_id": f"palette|{permutation}|{item['family']}|{champion}|{item['question_id']}",
                "phase": "palette", "family": item["family"], "arm": champion,
                "packaging": packaging if item["family"] == "vp2" else None,
                "permutation": permutation,
                "palette_map": {int(k): int(v) for k, v in document["palette_permutations"][permutation].items()},
                "question_id": item["question_id"], "env": question["env"],
                "session_index": question["session_index"],
                "question_changed": question.get("changed"),
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-freeze", action="store_true")
    parser.add_argument("--verify-freeze", action="store_true")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--model", default="/Users/michal/models/mlx/Qwen3.6-27B-8bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    if args.write_freeze:
        manifest = build_freeze(); FREEZE.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        print("vp_screen: wrote freeze", manifest["contract_fingerprint"][:16]); return 0
    if args.verify_freeze:
        problems = verify_freeze()
        if problems:
            print("vp_screen: freeze FAILED", *problems, sep="\n- "); return 1
        print("vp_screen: freeze verified"); return 0
    document = json.loads(QUESTIONS.read_text()); require_freeze()
    if args.summarize:
        print(json.dumps(write_results(document), indent=2)); return 0
    if not args.run_all:
        parser.error("choose --write-freeze, --verify-freeze, --run-all, or --summarize")
    index = build_corpus_index(); initialize_renderer(); questions, _ = _question_maps(document)
    print("VP1", run_rows(_vp1_rows(document), questions=questions, index=index, model=args.model,
                          base_url=args.base_url, timeout=args.timeout, concurrency=args.concurrency), flush=True)
    result = write_results(document); champion = result["champion"]
    if not result["vp1"]["visual_route_pass"]:
        print("VP1 visual route failed; frozen routing stops before VP2"); return 2
    print("VP2 selector", run_rows(_selector_rows(document, champion), questions=questions, index=index,
                                   model=args.model, base_url=args.base_url, timeout=args.timeout,
                                   concurrency=args.concurrency), flush=True)
    result = write_results(document); packaging = result["packaging"]["selected"]
    print("VP2 main", run_rows(_vp2_main_rows(document, champion, packaging), questions=questions,
                               index=index, model=args.model, base_url=args.base_url,
                               timeout=args.timeout, concurrency=args.concurrency), flush=True)
    print("VP2-S", run_rows(_semantic_rows(document, champion, packaging), questions=questions,
                            index=index, model=args.model, base_url=args.base_url,
                            timeout=args.timeout, concurrency=args.concurrency), flush=True)
    print("Palette", run_rows(_palette_rows(document, champion, packaging), questions=questions,
                              index=index, model=args.model, base_url=args.base_url,
                              timeout=args.timeout, concurrency=args.concurrency), flush=True)
    print(json.dumps(write_results(document), indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
