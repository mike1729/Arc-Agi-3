#!/usr/bin/env python3
"""Slice-4 vision bring-up probe v2.2 — production-regime gates, direct mlx_vlm path.

`notes/qwen-3.8-slice4-design.md` → Gates + REVIEW ROUND 1 (probe findings, all
adopted). v1 tested an easier token regime than production (16x16 boards at 512^2 =
one merged visual token per cell; production is 64x64 at 1024^2 = one token per 2x2
cells) and its PASS was neither reproducible nor bound to the tested configuration.
v2.2:

  - every board rendered by the SHARED production renderer (`s4_render`);
  - fixtures: 64x64 boards, one-cell objects, all 16 palette ids, similar greys,
    exact coordinates via marker plates, 16-page binding under two permutations;
  - deterministic wiring gates (temperature 0) separated from a production-sampler
    stability panel (1.0/0.95/20), with `mx.random.seed` immediately before EVERY
    generation on a recorded schedule — mlx-vlm 0.6.8 with top_k=20 uses the global
    MLX RNG, so nothing else is a seed;
  - hard template invariants inside `ask` (assistant marker present, open-think tail,
    whitespace-tolerant prefill scan, placeholder count == images, serialized
    text->placeholder binding);
  - full per-call traces on disk, truncation classified apart from formatting and
    visual-semantic failures, expanded-token cross-check against the generator;
  - gate-4 chance control (left / right / none, swapped + blank variants);
  - PASS bound to full local hashes + serving identity; per-call atomic checkpointing;
    one global run lock; overwrite refused without --force; pre-load manifests.

NEVER constrain the first decoded token: think free-form; JSON arrives after
`</think>`.

Run:
  .venv/bin/python agent/harness/e2_probe_vlm.py --out logs/e2_probe_vlm_38_8bit.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, Callable

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_render as sr  # noqa: E402  (shared production renderer — the point)

ROOT = Path(__file__).resolve().parents[2]
MODEL = Path.home() / "models/mlx/Qwen3.8-27B-8bit"

WIRING_SAMPLER = {"temperature": 0.0, "top_p": 1.0}          # deterministic gates
# Qwen3.8's official thinking-mode sampler.  No-op penalty/min-p fields are
# explicit so an MLX default change cannot silently alter the experiment.
PRODUCTION_SAMPLER = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "repetition_penalty": 1.0,
}
REASONING_EFFORT = "xhigh"
PRESERVE_THINKING = True
NATIVE_CONTEXT_TOKENS = 262_144
VISION_PAD = "<|image_pad|>"
MAX_PACKET_IMAGES = 16
MAX_VISUAL_TOKENS = 16_384
EXPECTED_MODEL_REVISION = "815b83c0df8ffd1d1b5244cf75fd6ef14fca9ef9"
EXPECTED_MODEL_TYPE = "qwen3_5"
EXPECTED_ARCHITECTURE = "Qwen3_5ForConditionalGeneration"
PINNED_VERSIONS = {
    "mlx-vlm": "0.6.8",
    "mlx": "0.32.0",
    "mlx-lm": "0.31.3",
    "transformers": "5.14.1",
}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """Hash a local file using Git's canonical ``blob <size>\0<bytes>`` identity."""
    h = hashlib.sha1()
    h.update(f"blob {path.stat().st_size}\0".encode())
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    """Experiment-critical invariant that remains active under ``python -O``."""
    if not condition:
        raise RuntimeError(message)


class IndeterminateBudget(RuntimeError):
    """The model exhausted its output budget, so no capability verdict is valid."""


def capture_git_state() -> dict[str, Any]:
    git: dict[str, Any] = {}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True,
            check=True,
        ).stdout.splitlines()
        git.update({"commit": commit, "dirty": bool(status), "status": status})
    except Exception as exc:
        git["error"] = repr(exc)
    return git


def fingerprint(model: Path, git_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind PASS to the exact local checkpoint and serving configuration."""
    named = [
        ".gitattributes", "README.md",
        "config.json", "generation_config.json", "tokenizer.json", "vocab.json",
        "merges.txt",
        "tokenizer_config.json", "chat_template.jinja", "preprocessor_config.json",
        "processor_config.json", "video_preprocessor_config.json",
        "model.safetensors.index.json",
    ]
    missing = [name for name in named if not (model / name).is_file()]
    require(not missing, f"missing required checkpoint files: {missing}")
    files = {
        n: {"bytes": (model / n).stat().st_size, "sha256": sha256_file(model / n)}
        for n in named
    }

    # Hugging Face stores the immutable source revision and expected LFS digests in
    # this local tree manifest. Full local hashes below additionally detect local
    # corruption or replacement; byte sizes alone are not checkpoint identity.
    index_path = model / "model.safetensors.index.json"
    require(index_path.exists(), f"missing weight index: {index_path}")
    index = json.loads(index_path.read_text())
    indexed_shards = sorted(set(index.get("weight_map", {}).values()))
    actual_shards = sorted(p.name for p in model.glob("model*.safetensors"))
    require(indexed_shards == actual_shards, (
        f"indexed/actual weight shard mismatch: indexed={indexed_shards}, "
        f"actual={actual_shards}"
    ))

    expected_root_files = sorted(named + indexed_shards)
    actual_root_files = sorted(path.name for path in model.iterdir() if path.is_file())
    require(actual_root_files == expected_root_files, (
        f"unexpected local checkpoint overlays: expected={expected_root_files}, "
        f"actual={actual_root_files}"
    ))

    download_dir = model / ".cache/huggingface/download"
    shard_metadata: dict[str, list[str]] = {}
    for name in indexed_shards:
        metadata_path = download_dir / f"{name}.metadata"
        require(metadata_path.exists(), f"missing Hugging Face metadata: {metadata_path}")
        lines = metadata_path.read_text().splitlines()
        require(len(lines) >= 2, f"malformed Hugging Face metadata: {metadata_path}")
        shard_metadata[name] = lines
    revisions = {lines[0] for lines in shard_metadata.values()}
    require(len(revisions) == 1, f"mixed Hugging Face shard revisions: {sorted(revisions)}")
    revision = next(iter(revisions))
    require(revision == EXPECTED_MODEL_REVISION, (
        f"checkpoint revision drift: {revision} != {EXPECTED_MODEL_REVISION}"
    ))
    tree_path = model / ".cache/huggingface/trees" / f"{revision}.json"
    require(tree_path.is_file(), f"missing Hugging Face tree manifest: {tree_path}")
    tree = json.loads(tree_path.read_text())
    tree_files = tree.get("files", {})
    for name, actual in files.items():
        expected = tree_files.get(name, {})
        require(bool(expected), f"serving file missing from Hugging Face tree: {name}")
        require(expected.get("size") == actual["bytes"], f"serving file size mismatch: {name}")
        if expected.get("lfs_sha256"):
            require(expected["lfs_sha256"] == actual["sha256"], (
                f"serving file LFS digest mismatch: {name}"
            ))
        else:
            require(expected.get("blob_id") == git_blob_sha1(model / name), (
                f"serving file Git blob mismatch: {name}"
            ))
    shards: dict[str, dict[str, Any]] = {}
    for name in indexed_shards:
        path = model / name
        digest = sha256_file(path)
        expected = tree_files.get(path.name, {})
        require(bool(expected), f"weight missing from Hugging Face tree manifest: {path.name}")
        require(expected.get("size") == path.stat().st_size, f"weight size mismatch: {path.name}")
        require(bool(expected.get("lfs_sha256")), f"weight lacks an LFS digest: {path.name}")
        entry: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": digest}
        entry["expected_lfs_sha256"] = expected["lfs_sha256"]
        entry["matches_hf_manifest"] = digest == expected["lfs_sha256"]
        require(entry["matches_hf_manifest"], f"weight digest mismatch: {path.name}")
        metadata_lines = shard_metadata[path.name]
        require(metadata_lines[0] == tree_path.stem, (
            f"mixed Hugging Face revision for {path.name}: {metadata_lines[0]}"
        ))
        require(metadata_lines[1] == expected["lfs_sha256"], (
            f"metadata/tree LFS mismatch for {path.name}"
        ))
        shards[path.name] = entry
    require(bool(shards), f"no model weight shards found under {model}")

    versions = {p: pkg_version(p) for p in PINNED_VERSIONS}
    require(versions == PINNED_VERSIONS, f"runtime version drift: {versions} != {PINNED_VERSIONS}")
    config = json.loads((model / "config.json").read_text())
    require(config.get("model_type") == EXPECTED_MODEL_TYPE, (
        f"model type drift: {config.get('model_type')} != {EXPECTED_MODEL_TYPE}"
    ))
    require(config.get("architectures") == [EXPECTED_ARCHITECTURE], (
        f"model architecture drift: {config.get('architectures')}"
    ))
    quant = config.get("quantization", config.get("quantization_config", {}))
    require(quant == {"group_size": 64, "bits": 8, "mode": "affine"}, (
        f"unexpected quantization config: {quant}"
    ))
    vision = config.get("vision_config", {})
    require(
        {key: vision.get(key) for key in ("patch_size", "spatial_merge_size",
                                           "temporal_patch_size")}
        == {"patch_size": 16, "spatial_merge_size": 2, "temporal_patch_size": 2},
        f"vision geometry drift: {vision}",
    )
    preprocessor = json.loads((model / "preprocessor_config.json").read_text())
    require(preprocessor.get("processor_class") == "Qwen3VLProcessor", (
        f"processor class drift: {preprocessor.get('processor_class')}"
    ))
    require(preprocessor.get("size") == {
        "longest_edge": 16_777_216, "shortest_edge": 65_536,
    }, f"processor pixel limits drift: {preprocessor.get('size')}")

    checkpoint_payload = {
        "revision": tree_path.stem,
        "model_files": files,
        "weight_shards": shards,
    }
    checkpoint_sha256 = hashlib.sha256(
        json.dumps(checkpoint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "model_path": str(model),
        "checkpoint_sha256": checkpoint_sha256,
        "model_files": files,
        "weight_shards": shards,
        "huggingface_tree": {
            "revision": tree_path.stem,
            "manifest_sha256": sha256_file(tree_path),
        },
        "script_sha": sha256_file(Path(__file__)),
        "renderer_sha": sha256_file(HARNESS / "s4_render.py"),
        "versions": versions,
        "git": capture_git_state() if git_state is None else git_state,
        "command": shlex.join(sys.argv),
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }


def extract_json(answer: str) -> dict[str, Any] | None:
    for candidate in reversed(re.findall(r"\{[^{}]*\}", answer, re.S)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def classify_completion(
    finish_reason: str | None,
    generation_tokens: int | None,
    max_tokens: int,
    think_closed: bool,
    payload: dict[str, Any] | None,
) -> str:
    """Classify protocol completion without guessing termination from token count."""
    if finish_reason not in {"stop", "length"}:
        return "instrument_error"
    if generation_tokens is None or not 0 <= generation_tokens <= max_tokens:
        return "instrument_error"
    if finish_reason == "length" and generation_tokens != max_tokens:
        return "instrument_error"
    if finish_reason == "length":
        return "truncated"
    if not think_closed:
        return "unclosed"
    if payload is None:
        return "no_json"
    return "complete"


def classify_gate(passed: bool, calls: list[dict[str, Any]]) -> str:
    """Keep input/protocol/budget failures distinct from semantic failures."""
    if passed:
        return "PASS"
    completions = {call.get("completeness") for call in calls}
    if "truncated" in completions:
        return "INDETERMINATE_BUDGET"
    if any(completion != "complete" for completion in completions):
        return "PROTOCOL_FAIL"
    return "SEMANTIC_FAIL"


def is_page_number(value: Any) -> bool:
    """JSON booleans are Python ints; reject them as malformed page numbers."""
    return type(value) is int and 1 <= value <= MAX_PACKET_IMAGES


def seed_for(base_seed: int, tag: str) -> int:
    """Stable uint64 seed: adding or reordering another gate cannot change this call."""
    digest = hashlib.sha256(f"{base_seed}:{tag}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def stability_count(raw: str) -> int:
    value = positive_int(raw)
    if value < 3:
        raise argparse.ArgumentTypeError("must be at least 3")
    return value


def uint64_seed(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 0 <= value < 2 ** 64:
        raise argparse.ArgumentTypeError("must be in [0, 2**64)")
    return value


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def acquire_run_lock(path: Path):
    """Hold a process-scoped nonblocking lock across hashing, load, and all gates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another e2_probe_vlm process holds the global run lock") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({
        "pid": os.getpid(),
        "acquired_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }))
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp.replace(path)


class Vlm:
    def __init__(self, path: Path):
        from mlx_vlm import load

        self.path = path
        self.model, self.processor = load(str(path), strict=True, lazy=False)
        require(type(self.model).__name__ == "Model", (
            f"unexpected loaded model class: {type(self.model)!r}"
        ))
        require(type(self.model).__module__ == "mlx_vlm.models.qwen3_5.qwen3_5", (
            f"unexpected loaded model module: {type(self.model).__module__}"
        ))
        require(hasattr(self.model, "vision_tower"), "loaded model has no vision_tower")
        require(type(self.processor).__name__ == "Qwen3VLProcessor", (
            f"unexpected loaded processor class: {type(self.processor)!r}"
        ))
        self.calls = 0

    def ask(
        self,
        items: list[dict[str, str]],
        images: list[Path],
        *,
        seed: int,
        sampler: dict[str, Any],
        max_tokens: int,
        run_dir: Path,
        tag: str,
    ) -> dict[str, Any]:
        """One user turn of interleaved text/image items. Hard invariants raise —
        a wiring defect must kill the probe, not lower a score."""
        import mlx.core as mx
        from PIL import Image
        from mlx_vlm import generate

        self.calls += 1
        messages = [{"role": "user", "content": items}]
        prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True,
            reasoning_effort=REASONING_EFFORT,
            preserve_thinking=PRESERVE_THINKING,
        )
        # --- invariants (review probe-finding 3) ---
        marker = prompt.rfind("<|im_start|>assistant")
        require(marker != -1, "assistant marker missing from serialized prompt")
        generation_region = prompt[marker:]
        require(prompt.rstrip().endswith("<think>"), "generation tail does not open <think>")
        require(not re.search(r"<think>\s*</think>", generation_region), (
            "pre-filled (whitespace-equivalent) empty think block in generation region"
        ))
        image_items = [i for i in items if i.get("type") == "image"]
        require(len(image_items) == len(images), "image items != images supplied")
        require(0 < len(images) <= MAX_PACKET_IMAGES, (
            f"image count {len(images)} outside 1..{MAX_PACKET_IMAGES}"
        ))
        # one pad RUN per image; count contiguous runs, not tokens
        pad_runs = len(re.findall(rf"(?:{re.escape(VISION_PAD)})+", prompt))
        require(pad_runs == len(images), f"placeholder runs {pad_runs} != images {len(images)}")
        # serialized binding: each text item that precedes an image item must appear
        # before that image's pad run in the rendered prompt.
        cursor = 0
        pad_iter = [
            match.start()
            for match in re.finditer(rf"(?:{re.escape(VISION_PAD)})+", prompt)
        ]
        seen_images = 0
        for item in items:
            if item.get("type") == "text":
                idx = prompt.find(item["text"], cursor)
                require(idx != -1, f"text item lost from serialized prompt: {item['text'][:40]!r}")
                cursor = idx + len(item["text"])
                if seen_images < len(pad_iter):
                    require(idx < pad_iter[seen_images] or seen_images == len(images), (
                        "text/image interleaving order broken in serialized prompt"
                    ))
            else:
                require(seen_images < len(pad_iter), "more image items than serialized pads")
                require(pad_iter[seen_images] >= cursor, "image pad precedes its label")
                cursor = pad_iter[seen_images]
                seen_images += 1

        pil = []
        image_meta = []
        for path in images:
            with Image.open(path) as opened:
                image = opened.convert("RGB").copy()
            require(image.width % 32 == 0 and image.height % 32 == 0, (
                f"{path.name}: dimensions are not multiples of 32"
            ))
            require(image.width * image.height >= 65_536, (
                f"{path.name}: below processor pixel minimum"
            ))
            pil.append(image)
            image_meta.append({
                "path": str(path), "sha256": sha256_file(path),
                "source_size": [image.width, image.height],
            })
        inputs = self.processor(text=prompt, images=pil or None, return_tensors="np")
        grid_thw = inputs.get("image_grid_thw")
        require(grid_thw is not None, "processor omitted image_grid_thw")
        grid = np.asarray(grid_thw)
        require(grid.shape == (len(images), 3), (
            f"image_grid_thw shape {grid.shape} != {(len(images), 3)}"
        ))
        image_processor = self.processor.image_processor
        patch_size = int(getattr(image_processor, "patch_size", 0))
        merge_size = int(getattr(image_processor, "merge_size", 0))
        require((patch_size, merge_size) == (16, 2), (
            f"processor geometry drift: patch={patch_size}, merge={merge_size}"
        ))
        visual_tokens = 0
        for meta, (grid_t, grid_h, grid_w) in zip(image_meta, grid.tolist()):
            require(int(grid_t) == 1, f"unexpected temporal image grid: {grid_t}")
            processed_size = [int(grid_w) * patch_size, int(grid_h) * patch_size]
            meta["processed_size"] = processed_size
            require(processed_size == meta["source_size"], (
                f"processor resized {Path(meta['path']).name}: "
                f"source={meta['source_size']} processed={processed_size}"
            ))
            merged = int(grid_t) * int(grid_h) * int(grid_w)
            require(merged % (merge_size ** 2) == 0, "non-integral merged visual-token count")
            visual_tokens += merged // (merge_size ** 2)
        require(visual_tokens <= MAX_VISUAL_TOKENS, (
            f"visual-token budget {visual_tokens} exceeds {MAX_VISUAL_TOKENS}"
        ))
        expanded = int(np.asarray(inputs["input_ids"]).shape[-1])

        mx.random.seed(seed)  # the ONLY effective seed under top_k sampling
        start = time.monotonic()
        out = generate(
            self.model,
            self.processor,
            prompt,
            image=[str(p) for p in images],
            max_tokens=max_tokens,
            verbose=False,
            **sampler,
        )
        text = out.text if hasattr(out, "text") else str(out)
        stats = {
            k: getattr(out, k, None)
            for k in ("prompt_tokens", "generation_tokens", "prompt_tps",
                      "generation_tps", "peak_memory", "total_tokens",
                      "cached_tokens", "finish_reason")
        }
        full = "<think>" + text
        closed = "</think>" in full
        think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        payload = extract_json(answer) if closed else None
        completeness = classify_completion(
            stats.get("finish_reason"), stats.get("generation_tokens"), max_tokens,
            closed, payload,
        )
        prompt_tokens_match = stats.get("prompt_tokens") == expanded
        token_accounting_match = (
            stats.get("total_tokens")
            == stats.get("prompt_tokens") + stats.get("generation_tokens")
            if isinstance(stats.get("prompt_tokens"), int)
            and isinstance(stats.get("generation_tokens"), int)
            else False
        )
        record = {
            "tag": tag,
            "seed": seed,
            "sampler": sampler,
            "reasoning_effort": REASONING_EFFORT,
            "preserve_thinking": PRESERVE_THINKING,
            "max_tokens": max_tokens,
            "items": items,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "images": image_meta,
            "image_grid_thw": grid.tolist(),
            "visual_tokens": visual_tokens,
            "expanded_prompt_tokens": expanded,
            "generator_prompt_tokens": stats.get("prompt_tokens"),
            "prompt_tokens_match": prompt_tokens_match,
            "token_accounting_match": token_accounting_match,
            "stats": stats,
            "completion_contains_close": closed,   # generated evidence
            "prompt_opened_think": True,           # asserted above, by construction
            "think_chars": len(think.strip()),
            "completeness": completeness,
            "payload": payload,
            "wall_seconds": round(time.monotonic() - start, 1),
        }
        trace = dict(record)
        trace["prompt"] = prompt
        trace["raw_completion"] = text
        trace["think"] = think
        trace["answer"] = answer
        atomic_write(run_dir / f"call_{self.calls:02d}_{tag}.json", trace)
        require(completeness != "instrument_error", (
            f"{tag}: invalid generation termination metadata: {stats}"
        ))
        require(prompt_tokens_match, (
            f"{tag}: generator prompt tokens {stats.get('prompt_tokens')} != expanded {expanded}"
        ))
        require(token_accounting_match, f"{tag}: total-token accounting mismatch: {stats}")
        if completeness == "truncated":
            raise IndeterminateBudget(
                f"{tag}: generation exhausted max_tokens={max_tokens}; rerun at a "
                "preregistered larger budget instead of scoring this as a failure"
            )
        return record


# ---------------------------------------------------------------------------------
# Fixtures — 64x64 production boards through s4_render only.
# ---------------------------------------------------------------------------------


def fixture_palette() -> tuple[np.ndarray, dict[str, Any]]:
    """One-cell objects of every palette id on a white board; known counts for three
    nameable colours; a yellow singleton alone in row 0; a purple singleton to mark."""
    g = np.zeros((64, 64), dtype=np.uint8)
    singles = {
        1: (12, 5), 2: (20, 50), 3: (33, 14), 4: (47, 8), 5: (5, 27), 6: (52, 44),
        7: (26, 37), 10: (39, 58), 12: (58, 21), 13: (9, 47), 15: (7, 55),
    }
    for value, (r, c) in singles.items():
        g[r, c] = value
    g[0, 41] = 11                                   # the only non-white cell in row 0
    for r, c in ((15, 15), (44, 30), (61, 3)):      # red x3
        g[r, c] = 8
    for r, c in ((28, 6), (36, 49)):                # blue x2
        g[r, c] = 9
    for r, c in ((3, 3), (17, 60), (50, 55), (62, 40)):  # green x4
        g[r, c] = 14
    truth = {"red_count": 3, "blue_count": 2, "green_count": 4,
             "marked_cell_colour": "purple", "top_row_colour": "yellow",
             "marked_cell": singles[15]}
    return g, truth


def fixture_fill_pair(
    a_id: int, b_id: int,
) -> tuple[np.ndarray, tuple[int, int], tuple[int, int]]:
    """Counterbalance grey identity independently of position and marker label."""
    g = np.zeros((64, 64), dtype=np.uint8)
    a, b = (18, 14), (42, 46)
    g[16:21, 12:17] = a_id
    g[40:45, 44:49] = b_id
    return g, a, b


def fixture_block(
    colour: int,
    bbox: tuple[int, int, int, int] = (24, 24, 27, 27),
) -> np.ndarray:
    g = np.zeros((64, 64), dtype=np.uint8)
    r0, c0, r1, c1 = bbox
    g[r0:r1 + 1, c0:c1 + 1] = colour
    return g


def fixture_relation(red_left: bool) -> np.ndarray:
    g = np.zeros((64, 64), dtype=np.uint8)
    left, right = (slice(30, 33), slice(10, 13)), (slice(30, 33), slice(50, 53))
    g[left if red_left else right] = 8
    g[right if red_left else left] = 9
    return g


PALETTE_REQUEST = (
    "Image 1 is a 64x64 board. Image 2 is the SAME board with one cell ringed by a "
    "magenta marker. Think first, carefully. Then answer with ONLY a JSON object on "
    'the last line: {"red_count": <int>, "blue_count": <int>, "green_count": <int>, '
    '"marked_cell_colour": "<colour word>", "top_row_colour": "<colour word>"} — '
    "counts of pure-red, pure-blue and pure-green cells on the board, the colour of "
    "the ringed cell, and the colour of the only non-white cell in the top row."
)


def run_gates(
    vlm: Vlm,
    work: Path,
    run_dir: Path,
    args,
    doc: dict[str, Any],
    persist: Callable[[], None] | None = None,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    gate_statuses: dict[str, str] = {}
    doc["gate_statuses"] = gate_statuses
    checkpoint = persist or (lambda: None)

    def record_result(name: str, passed: bool, calls: list[dict[str, Any]]) -> None:
        results[name] = passed
        gate_statuses[name] = classify_gate(passed, calls)

    def save(grid, name):
        return sr.render_board(grid).save(work / name)

    # Gate 1 — production palette/coordinates (deterministic wiring).
    grid, truth = fixture_palette()
    board_png = save(grid, "g1_board.png")
    marker_png = sr.render_marker(grid, truth["marked_cell"], "MARKED CELL").save(
        work / "g1_marker.png"
    )
    call = vlm.ask(
        [{"type": "text", "text": "Image 1:"}, {"type": "image"},
         {"type": "text", "text": "Image 2:"}, {"type": "image"},
         {"type": "text", "text": PALETTE_REQUEST}],
        [board_png, marker_png],
        seed=seed_for(args.seed, "g1_palette"), sampler=WIRING_SAMPLER,
        max_tokens=args.max_tokens,
        run_dir=run_dir, tag="g1_palette",
    )
    p = call["payload"] or {}
    checks = {
        "complete": call["completeness"] == "complete",
        "tokens_match": call["prompt_tokens_match"],
        "red": p.get("red_count") == truth["red_count"],
        "blue": p.get("blue_count") == truth["blue_count"],
        "green": p.get("green_count") == truth["green_count"],
        "marked": str(p.get("marked_cell_colour", "")).strip().lower() == "purple",
        "top_row": str(p.get("top_row_colour", "")).strip().lower() == "yellow",
    }
    doc["gate1_palette"] = {
        "call": call,
        "checks": checks,
        "truth": {key: value for key, value in truth.items() if key != "marked_cell"},
    }
    record_result("gate1_palette_production", all(checks.values()), [call])
    checkpoint()

    # Gate 2 — similar greys, marked pair. Review round 1 rerun fix: the first wording
    # ("same or different") was semantically ambiguous — the model correctly read both
    # marker positions and answered that the CELLS were different (different positions),
    # which was true. The question is now about fill colour only, boolean.
    grey_checks = {}
    doc["gate2_greys"] = grey_checks
    grey_cases = (
        ("same_light", 2, 2, True),
        ("same_dark", 3, 3, True),
        ("diff_ab", 2, 3, False),
        ("diff_ba", 3, 2, False),
    )
    for tag, a_id, b_id, same in grey_cases:
        grid, a, b = fixture_fill_pair(a_id, b_id)
        board = save(grid, f"g2_board_{tag}.png")
        ma = sr.render_marker(grid, a, "SAMPLE A").save(work / f"g2_a_{tag}.png")
        mb = sr.render_marker(grid, b, "SAMPLE B").save(work / f"g2_b_{tag}.png")
        call = vlm.ask(
            [{"type": "text", "text": "Image 1 (board):"}, {"type": "image"},
             {"type": "text", "text": "Image 2 (mark A):"}, {"type": "image"},
             {"type": "text", "text": "Image 3 (mark B):"}, {"type": "image"},
             {"type": "text", "text": (
                 "All three images show the same board. Image 2 marks sample A and "
                 "Image 3 marks sample B. The magenta rings and labels are annotations, "
                 "not object colours. Compare only the uniform interior fill of each "
                 "5x5 square containing the marked centre cell. Ignore position, ring "
                 "colour, and labels. Palette ID 2 is RGB(153,153,153); palette ID 3 "
                 "is RGB(102,102,102). Think first. Then answer with ONLY a JSON "
                 'object: {"a_fill_id": 2 or 3, "b_fill_id": 2 or 3, '
                 '"same_fill_colour": true or false}.'
             )}],
            [board, ma, mb],
            seed=seed_for(args.seed, f"g2_{tag}"), sampler=WIRING_SAMPLER,
            max_tokens=args.max_tokens, run_dir=run_dir, tag=f"g2_{tag}",
        )
        p = call["payload"] or {}
        got_a, got_b = p.get("a_fill_id"), p.get("b_fill_id")
        got_same = p.get("same_fill_colour")
        checks = {
            "complete": call["completeness"] == "complete",
            "a_fill": got_a == a_id,
            "b_fill": got_b == b_id,
            "same_fill": got_same is same,
            "internally_consistent": (
                isinstance(got_same, bool) and got_same == (got_a == got_b)
            ),
        }
        grey_checks[tag] = {
            "call": call, "truth": {"a_fill_id": a_id, "b_fill_id": b_id,
                                      "same_fill_colour": same},
            "checks": checks, "correct": all(checks.values()),
        }
        checkpoint()
    record_result(
        "gate2_grey_fill_colour",
        all(v["correct"] for v in grey_checks.values()),
        [value["call"] for value in grey_checks.values()],
    )
    checkpoint()

    # Gate 3 — a production-scale 16-page mixed packet. Targets span early, middle,
    # and final pages and cover every plate type. Palette IDs 14/15/12 are each
    # mechanically absent from every non-target page, so the scorer has one truth.
    green = fixture_block(14, (40, 8, 43, 11))
    grey_light = fixture_block(2, (7, 45, 10, 51))
    cyan = fixture_block(10, (51, 10, 51, 18))
    purple = fixture_block(15, (24, 24, 27, 27))
    grey_dark = fixture_block(3, (10, 10, 14, 14))
    blue = fixture_block(9, (44, 50, 50, 51))
    orange = fixture_block(12, (32, 17, 36, 21))
    yellow = fixture_block(11, (55, 12, 55, 12))
    pink = fixture_block(7, (13, 39, 16, 42))

    diff_pre = np.zeros((64, 64), dtype=np.uint8)
    diff_three = diff_pre.copy()
    for r, c in ((8, 9), (31, 45), (54, 20)):
        diff_three[r, c] = 1
    diff_one = diff_pre.copy(); diff_one[18, 18] = 1
    diff_five = diff_pre.copy()
    for r, c in ((5, 55), (16, 40), (29, 29), (43, 12), (58, 48)):
        diff_five[r, c] = 1

    sb_grey_a = fixture_block(1, (8, 8, 11, 11))
    sb_grey_b = fixture_block(4, (45, 45, 48, 48))
    sb_black = fixture_block(5, (20, 50, 25, 53))
    sb_red = fixture_block(8, (30, 5, 33, 8))
    sb_yellow = fixture_block(11, (4, 30, 7, 33))
    # Match the densest observed live intervention: 28 exact 64x64 frames at four
    # pixels/cell on one page.  One unique one-cell event tests that this compact
    # representation is model-readable, not merely byte-exact.
    animation_target_frame = 23
    animation_target_row = 37
    animation_target_col = 11
    animation_frames = []
    for frame_index in range(28):
        frame = fixture_block(2, (8 + frame_index % 8, 44, 10 + frame_index % 8, 46))
        if frame_index == animation_target_frame:
            frame[animation_target_row, animation_target_col] = 11
        animation_frames.append(frame)

    pages: list[Path] = []
    page_sources: list[list[np.ndarray]] = []

    def add_page(plate: sr.Plate, sources: list[np.ndarray]) -> None:
        page_no = len(pages) + 1
        pages.append(plate.save(work / f"g3_p{page_no:02d}.png"))
        page_sources.append(sources)

    add_page(sr.render_board(green), [green])                         # 1 target board
    add_page(sr.render_board(grey_light), [grey_light])               # 2
    add_page(sr.render_board(cyan), [cyan])                            # 3
    add_page(sr.render_crop(purple, (24, 24, 27, 27)), [purple])      # 4 target crop
    add_page(sr.render_crop(grey_dark, (10, 10, 14, 14)), [grey_dark])  # 5
    add_page(sr.render_crop(blue, (44, 50, 50, 51)), [blue])          # 6
    add_page(sr.render_marker(orange, (34, 19), "ACTION7(19,34)"), [orange])  # 7 target marker
    add_page(sr.render_marker(yellow, (55, 12), "ACTION2(12,55)"), [yellow])  # 8
    add_page(sr.render_marker(pink, (14, 40), "ACTION6(40,14)"), [pink])      # 9
    add_page(sr.render_diff_mask(diff_pre, diff_three), [diff_pre, diff_three])  # 10 target diff
    add_page(sr.render_diff_mask(diff_pre, diff_one), [diff_pre, diff_one])       # 11
    add_page(sr.render_diff_mask(diff_pre, diff_five), [diff_pre, diff_five])     # 12
    add_page(sr.storyboard([sb_grey_a, sb_grey_b], cols=2), [sb_grey_a, sb_grey_b])  # 13
    add_page(sr.storyboard([sb_grey_a, sb_black, sb_grey_b], cols=3),
             [sb_grey_a, sb_black, sb_grey_b])                            # 14
    add_page(sr.storyboard([sb_red, sb_grey_a, sb_yellow, sb_black], cols=2),
             [sb_red, sb_grey_a, sb_yellow, sb_black])                    # 15
    add_page(sr.storyboard(animation_frames, cols=7, cell_px=4), animation_frames)  # 16

    require(len(pages) == MAX_PACKET_IMAGES, f"Gate 3 built {len(pages)} pages")
    page_colours = [
        set(int(v) for source in sources for v in np.unique(source))
        for sources in page_sources
    ]
    for colour, expected_page in ((14, 1), (15, 4), (12, 7)):
        actual_pages = [i + 1 for i, colours in enumerate(page_colours) if colour in colours]
        require(actual_pages == [expected_page], (
            f"Gate 3 colour {colour} is not unique: pages={actual_pages}"
        ))
    request = (
        "These are distinct outer pages. They include raw full boards, magnified "
        "crops, annotated boards with magenta rings, black-and-white changed-cell "
        "masks, and multi-frame storyboards. Report OUTER PAGE numbers for every "
        "page field; only animation_frame_index uses the index printed inside its "
        "storyboard. Think first. Then answer with ONLY "
        "a JSON object: "
        '{"animation_storyboard_page": <int>, "animation_frame_index": <int>, '
        '"animation_yellow_row": <int>, "animation_yellow_col": <int>, '
        '"orange_marker_page": <int>, '
        '"green_board_page": <int>, "three_change_diff_page": <int>, '
        '"purple_crop_page": <int>}. Rows and columns are 0-indexed from the '
        "top-left of the 64x64 board, so each runs 0-63; the frame index is the "
        "frame's printed label. The requested pages are: the storyboard with "
        "exactly 28 indexed frames, plus the internal frame index and 64x64 board "
        "row/column of its unique one-cell yellow event; the annotated board whose orange square is "
        "ringed; the raw full board whose only non-white object is green; the diff "
        "mask with exactly three white changed cells; and the magnified crop of a "
        "purple square."
    )
    target_original_indexes = {
        "green_board_page": 0,
        "purple_crop_page": 3,
        "orange_marker_page": 6,
        "three_change_diff_page": 9,
        "animation_storyboard_page": 15,
    }
    permutations = {
        "a": [10, 0, 14, 5, 8, 3, 12, 1, 6, 4, 13, 2, 9, 7, 11, 15],
        "b": [3, 11, 1, 14, 15, 8, 0, 13, 5, 2, 10, 6, 7, 4, 12, 9],
    }
    binding_runs = {}
    doc["gate3_binding"] = binding_runs
    previous_expected: dict[str, int] | None = None
    for variant, permutation in permutations.items():
        require(sorted(permutation) == list(range(MAX_PACKET_IMAGES)), (
            f"Gate 3 permutation {variant} is invalid: {permutation}"
        ))
        expected = {
            key: permutation.index(original_index) + 1
            for key, original_index in target_original_indexes.items()
        }
        if previous_expected is not None:
            require(all(expected[key] != previous_expected[key] for key in expected), (
                "Gate 3 counter-permutation must move every queried target"
            ))
        previous_expected = expected
        ordered_pages = [pages[index] for index in permutation]
        items: list[dict[str, str]] = []
        for i in range(MAX_PACKET_IMAGES):
            items.append({"type": "text", "text": f"Page {i + 1} of {MAX_PACKET_IMAGES}:"})
            items.append({"type": "image"})
        items.append({"type": "text", "text": request})
        tag = f"g3_binding_{variant}"
        call = vlm.ask(
            items, ordered_pages, seed=seed_for(args.seed, tag),
            sampler=WIRING_SAMPLER, max_tokens=args.packet_max_tokens,
            run_dir=run_dir, tag=tag,
        )
        p = call["payload"] or {}
        typed_pages = all(is_page_number(p.get(key)) for key in expected)
        animation_checks = {
            "animation_frame_index": p.get("animation_frame_index") == animation_target_frame,
            "animation_yellow_row": p.get("animation_yellow_row") == animation_target_row,
            "animation_yellow_col": p.get("animation_yellow_col") == animation_target_col,
        }
        checks = {
            "complete": call["completeness"] == "complete",
            "sixteen_images": len(call["image_grid_thw"]) == MAX_PACKET_IMAGES,
            "within_visual_budget": call["visual_tokens"] <= MAX_VISUAL_TOKENS,
            "typed_page_numbers": typed_pages,
            **{key: is_page_number(p.get(key)) and p[key] == value
               for key, value in expected.items()},
            **animation_checks,
            "distinct_pages": typed_pages and len({p[key] for key in expected}) == len(expected),
        }
        binding_runs[variant] = {
            "permutation_zero_based": permutation,
            "expected": expected,
            "animation_truth": {
                "frame_index": animation_target_frame,
                "row": animation_target_row,
                "col": animation_target_col,
                "cell_px": 4,
                "frame_count": len(animation_frames),
            },
            "call": call,
            "checks": checks,
        }
        checkpoint()
    record_result(
        "gate3_packet_binding",
        all(all(run["checks"].values()) for run in binding_runs.values()),
        [run["call"] for run in binding_runs.values()],
    )
    checkpoint()

    # Gate 4 — CONTROLLED SPATIAL GROUNDING: left / right(swapped) / none(blank).
    # What a pass proves is that the relation answer tracks the pixels under swap and
    # ablation — not "substantive thinking"; think length is diagnostic only.
    rel_request = (
        "Think first. Then answer with ONLY a JSON object: "
        '{"relation": "left" or "right" or "none"} — is the red square to the left '
        "or to the right of the blue square? If there is no red or blue square, "
        'answer "none".'
    )
    rel_checks = {}
    doc["gate4_spatial_grounding"] = rel_checks
    for tag, grid, want in (
        ("left", fixture_relation(True), "left"),
        ("right", fixture_relation(False), "right"),
        ("blank", np.zeros((64, 64), dtype=np.uint8), "none"),
    ):
        img = save(grid, f"g4_{tag}.png")
        call = vlm.ask(
            [{"type": "image"}, {"type": "text", "text": rel_request}], [img],
            seed=seed_for(args.seed, f"g4_{tag}"), sampler=WIRING_SAMPLER,
            max_tokens=args.max_tokens,
            run_dir=run_dir, tag=f"g4_{tag}",
        )
        got = str((call["payload"] or {}).get("relation", "")).strip().lower()
        rel_checks[tag] = {"call": call,
                          "complete": call["completeness"] == "complete",
                          "correct": call["completeness"] == "complete" and got == want,
                          "think_chars_diagnostic": call["think_chars"]}
        checkpoint()
    record_result(
        "gate4_spatial_grounding",
        all(v["correct"] for v in rel_checks.values()),
        [value["call"] for value in rel_checks.values()],
    )
    checkpoint()

    # Gate 5 — production-sampler stability panel on the complete Gate-1 item.
    # Every replicate must pass. At the preregistered p<=0.5 null, the maximum
    # false-pass probability is 0.5**n (12.5% at the minimum n=3), not 50% as
    # under the old 2-of-3 rule.
    stability = []
    doc["gate5_stability"] = stability
    for rep in range(args.stability):
        call = vlm.ask(
            [{"type": "text", "text": "Image 1:"}, {"type": "image"},
             {"type": "text", "text": "Image 2:"}, {"type": "image"},
             {"type": "text", "text": PALETTE_REQUEST}],
            [board_png, marker_png],
            seed=seed_for(args.seed, f"g5_stability_{rep}"),
            sampler=PRODUCTION_SAMPLER, max_tokens=args.max_tokens,
            run_dir=run_dir, tag=f"g5_stability_{rep}",
        )
        p = call["payload"] or {}
        ok = (
            call["completeness"] == "complete"
            and p.get("red_count") == 3 and p.get("blue_count") == 2
            and p.get("green_count") == 4
            and str(p.get("marked_cell_colour", "")).strip().lower() == "purple"
            and str(p.get("top_row_colour", "")).strip().lower() == "yellow"
        )
        stability.append({"call": call, "correct": ok})
        checkpoint()
    passes = sum(1 for s in stability if s["correct"])
    doc["gate5_pass_fraction"] = f"{passes}/{args.stability}"
    doc["gate5_null_false_pass_upper_bound"] = 0.5 ** args.stability
    record_result(
        "gate5_sampler_stability", passes == args.stability,
        [value["call"] for value in stability],
    )
    checkpoint()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--seed", type=uint64_seed, default=4,
                        help="uint64 base for stable tag-derived seeds")
    parser.add_argument("--stability", type=stability_count, default=3,
                        help="production-sampler replicates; >=3 and all must pass")
    parser.add_argument("--max-tokens", type=positive_int, default=4000)
    parser.add_argument("--packet-max-tokens", type=positive_int, default=8000,
                        help="generation budget for the 16-page Gate-3 call")
    parser.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    args = parser.parse_args()
    if args.packet_max_tokens < args.max_tokens:
        parser.error("--packet-max-tokens must be >= --max-tokens")

    args.model = args.model.expanduser().resolve()
    if not args.model.is_dir():
        parser.error(f"--model is not a directory: {args.model}")

    out_path = args.out or ROOT / f"logs/e2_probe_vlm_{args.model.name}.json"
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not os.access(out_path.parent, os.W_OK):
        parser.error(f"output directory is not writable: {out_path.parent}")

    try:
        _run_lock = acquire_run_lock(ROOT / "logs/.e2_probe_vlm.lock")
    except RuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    # --force may replace only a completed artifact. It must never clobber an active
    # canonical run, including an older probe version that predates the flock above.
    canonical_out = (ROOT / f"logs/e2_probe_vlm_{args.model.name}.json").resolve()
    active_statuses = {"fingerprinting", "loading", "loaded"}
    for candidate in {out_path, canonical_out}:
        if not candidate.exists():
            continue
        try:
            existing = json.loads(candidate.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}
        if existing.get("status") in active_statuses:
            print(
                f"REFUSED: active probe status={existing['status']} at {candidate} "
                f"(run_dir={existing.get('run_dir', 'unknown')})",
                file=sys.stderr,
            )
            _run_lock.close()
            return 2
    if out_path.exists() and not args.force:
        print(f"REFUSED: {out_path} exists (pass --force to overwrite)", file=sys.stderr)
        _run_lock.close()
        return 2

    # Capture repository state before this run writes a potentially tracked output.
    git_state = capture_git_state()
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = ROOT / f"logs/e2_probe_vlm_runs/{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    work = run_dir / "boards"
    work.mkdir()
    manifest_path = run_dir / "run_manifest.json"

    experiment_config = {
        "seed_base": args.seed,
        "stability_replicates": args.stability,
        "stability_required_passes": args.stability,
        "max_tokens": args.max_tokens,
        "packet_max_tokens": args.packet_max_tokens,
        "max_packet_images": MAX_PACKET_IMAGES,
        "max_visual_tokens": MAX_VISUAL_TOKENS,
        "native_context_tokens": NATIVE_CONTEXT_TOKENS,
    }
    resolved_config = {
        "model": str(args.model),
        "out": str(out_path),
        **experiment_config,
    }
    doc: dict[str, Any] = {
        "note": "notes/qwen-3.8-slice4-design.md -> Gates + REVIEW ROUND 1; probe v2.2",
        "resolved_config": resolved_config,
        "run_provenance": {
            "argv": list(sys.argv),
            "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "model_path": str(args.model),
            "output_path": str(out_path),
            "run_dir": str(run_dir),
        },
        "wiring_sampler": WIRING_SAMPLER,
        "production_sampler": PRODUCTION_SAMPLER,
        "reasoning_effort": REASONING_EFFORT,
        "preserve_thinking": PRESERVE_THINKING,
        "seed_base": args.seed,
        "run_dir": str(run_dir),
        "status": "fingerprinting",
    }

    def persist() -> None:
        atomic_write(out_path, doc)
        atomic_write(manifest_path, doc)

    # Destination and immutable in-run manifest are checkpointed before hashing or
    # model loading. Every later state transition updates both atomically.
    persist()

    try:
        print(f"fingerprinting {args.model.name} (full shard verification) ...", flush=True)
        checkpoint = fingerprint(args.model, git_state=git_state)
        serving_payload = {
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "versions": checkpoint["versions"],
            "script_sha": checkpoint["script_sha"],
            "renderer_sha": checkpoint["renderer_sha"],
            "wiring_sampler": WIRING_SAMPLER,
            "production_sampler": PRODUCTION_SAMPLER,
            "reasoning_effort": REASONING_EFFORT,
            "preserve_thinking": PRESERVE_THINKING,
            "native_context_tokens": NATIVE_CONTEXT_TOKENS,
            "experiment_config": experiment_config,
        }
        doc["checkpoint_identity"] = checkpoint
        doc["serving_compatibility"] = {
            **serving_payload,
            "sha256": canonical_sha256(serving_payload),
        }
        doc["status"] = "loading"
        persist()
        print(f"loading {args.model.name} ...", flush=True)
        vlm = Vlm(args.model)
        doc["status"] = "loaded"
        persist()
        results = run_gates(vlm, work, run_dir, args, doc, persist=persist)
    except IndeterminateBudget as exc:
        doc["status"] = "indeterminate_budget"
        doc["verdict"] = "INDETERMINATE_BUDGET"
        doc["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        persist()
        print(f"INDETERMINATE_BUDGET: {exc}", file=sys.stderr)
        _run_lock.close()
        return 3
    except BaseException as exc:
        doc["status"] = "aborted"
        doc["verdict"] = "ABORTED_INSTRUMENT"
        doc["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        persist()
        _run_lock.close()
        raise

    doc["results"] = results
    doc["passed"] = all(results.values())
    statuses = set(doc["gate_statuses"].values())
    doc["verdict"] = (
        "PASS" if doc["passed"]
        else "INDETERMINATE_BUDGET" if "INDETERMINATE_BUDGET" in statuses
        else "PROTOCOL_FAIL" if "PROTOCOL_FAIL" in statuses
        else "SEMANTIC_FAIL"
    )
    doc["status"] = "done"
    persist()
    for name in results:
        print(f"{name}: {doc['gate_statuses'][name]}", flush=True)
    print(f"ALL GATES: {doc['verdict']}")
    print(f"wrote {out_path}  (traces: {run_dir})")
    _run_lock.close()
    return 0 if doc["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
