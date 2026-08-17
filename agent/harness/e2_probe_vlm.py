#!/usr/bin/env python3
"""Slice-4 vision bring-up probe v2 — production-regime gates, direct mlx_vlm path.

`notes/qwen-3.8-slice4-design.md` → Gates + REVIEW ROUND 1 (probe findings, all
adopted). v1 tested an easier token regime than production (16x16 boards at 512^2 =
one merged visual token per cell; production is 64x64 at 1024^2 = one token per 2x2
cells) and its PASS was neither reproducible nor bound to the tested configuration.
v2:

  - every board rendered by the SHARED production renderer (`s4_render`);
  - fixtures: 64x64 boards, one-cell objects, all 16 palette ids, similar greys,
    exact coordinates via marker plates, packet-scale multi-image binding;
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
  - PASS bound to the full serving fingerprint; per-call atomic checkpointing;
    overwrite refused without --force; destination preflighted before model load.

NEVER constrain the first decoded token: think free-form; JSON arrives after
`</think>`.

Run:
  .venv/bin/python agent/harness/e2_probe_vlm.py --out logs/e2_probe_vlm_38_8bit.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_render as sr  # noqa: E402  (shared production renderer — the point)

ROOT = Path(__file__).resolve().parents[2]
MODEL = Path.home() / "models/mlx/Qwen3.8-27B-8bit"

WIRING_SAMPLER = {"temperature": 0.0, "top_p": 1.0}          # deterministic gates
PRODUCTION_SAMPLER = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
REASONING_EFFORT = "xhigh"
VISION_PAD = "<|image_pad|>"

# Colour words the checks accept, for maximally nameable palette entries.
WORDS = {8: "red", 9: "blue", 11: "yellow", 14: "green", 15: "purple", 12: "orange"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def fingerprint(model: Path) -> dict[str, Any]:
    """Bind PASS to the exact serving configuration (review finding 6)."""
    named = [
        "config.json", "generation_config.json", "tokenizer.json",
        "tokenizer_config.json", "chat_template.jinja", "preprocessor_config.json",
        "processor_config.json", "model.safetensors.index.json",
    ]
    files = {n: sha256_file(model / n) for n in named if (model / n).exists()}
    shards = {
        p.name: p.stat().st_size for p in sorted(model.glob("model*.safetensors"))
    }
    git = {}
    try:
        git["commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        git["dirty"] = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
            ).stdout.strip()
        )
    except Exception as exc:  # fingerprint must never abort the probe
        git["error"] = repr(exc)
    return {
        "model_path": str(model),
        "model_files": files,
        "weight_shards_bytes": shards,
        "script_sha": sha256_file(Path(__file__)),
        "renderer_sha": sha256_file(HARNESS / "s4_render.py"),
        "versions": {
            p: pkg_version(p) for p in ("mlx-vlm", "mlx", "mlx-lm", "transformers")
        },
        "git": git,
        "command": " ".join(sys.argv),
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }


def extract_json(answer: str) -> dict[str, Any] | None:
    for candidate in reversed(re.findall(r"\{[^{}]*\}", answer, re.S)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    tmp.replace(path)


class Vlm:
    def __init__(self, path: Path):
        from mlx_vlm import load

        self.path = path
        self.model, self.processor = load(str(path))
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
        )
        # --- invariants (review probe-finding 3) ---
        marker = prompt.rfind("<|im_start|>assistant")
        assert marker != -1, "assistant marker missing from serialized prompt"
        generation_region = prompt[marker:]
        assert prompt.rstrip().endswith("<think>"), "generation tail does not open <think>"
        assert not re.search(r"<think>\s*</think>", generation_region), (
            "pre-filled (whitespace-equivalent) empty think block in generation region"
        )
        pads = prompt.count(VISION_PAD)
        image_items = [i for i in items if i.get("type") == "image"]
        assert len(image_items) == len(images), "image items != images supplied"
        # one pad RUN per image; count contiguous runs, not tokens
        pad_runs = len(re.findall(rf"(?:{re.escape(VISION_PAD)})+", prompt))
        assert pad_runs == len(images), f"placeholder runs {pad_runs} != images {len(images)}"
        # serialized binding: each text item that precedes an image item must appear
        # before that image's pad run in the rendered prompt.
        cursor, pad_iter = 0, [m.start() for m in re.finditer(rf"(?:{re.escape(VISION_PAD)})+", prompt)]
        seen_images = 0
        for item in items:
            if item.get("type") == "text":
                idx = prompt.find(item["text"], cursor)
                assert idx != -1, f"text item lost from serialized prompt: {item['text'][:40]!r}"
                cursor = idx + len(item["text"])
                if seen_images < len(pad_iter):
                    assert idx < pad_iter[seen_images] or seen_images == len(images), (
                        "text/image interleaving order broken in serialized prompt"
                    )
            else:
                assert pad_iter[seen_images] >= cursor, "image pad precedes its label"
                cursor = pad_iter[seen_images]
                seen_images += 1

        pil = [Image.open(p) for p in images]
        for p, im in zip(images, pil):
            assert im.width % 32 == 0 and im.height % 32 == 0, f"{p.name}: dims not %32"
            assert im.width * im.height >= 65536, f"{p.name}: below processor pixel minimum"
        inputs = self.processor(text=prompt, images=pil or None, return_tensors="np")
        grid_thw = inputs.get("image_grid_thw")
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
                      "generation_tps", "peak_memory")
        }
        full = "<think>" + text
        closed = "</think>" in full
        think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        payload = extract_json(answer) if closed else None
        gen_tokens = stats.get("generation_tokens")
        truncated = (not closed) and (gen_tokens is None or gen_tokens >= max_tokens - 1)
        completeness = (
            "complete" if closed and payload is not None
            else "truncated" if truncated
            else "no_json" if closed
            else "unclosed"
        )
        record = {
            "tag": tag,
            "seed": seed,
            "sampler": sampler,
            "images": [
                {"path": str(p), "sha256_16": sha256_file(p),
                 "size": list(Image.open(p).size)}
                for p in images
            ],
            "image_grid_thw": None if grid_thw is None else np.asarray(grid_thw).tolist(),
            "expanded_prompt_tokens": expanded,
            "generator_prompt_tokens": stats.get("prompt_tokens"),
            "prompt_tokens_match": stats.get("prompt_tokens") in (None, expanded),
            "stats": stats,
            "completion_contains_close": closed,   # generated evidence
            "prompt_opened_think": True,           # asserted above, by construction
            "think_chars": len(think.strip()),
            "completeness": completeness,
            "payload": payload,
            "wall_seconds": round(time.monotonic() - start, 1),
        }
        trace = dict(record)
        trace["raw_completion"] = text
        trace["think"] = think
        trace["answer"] = answer
        atomic_write(run_dir / f"call_{self.calls:02d}_{tag}.json", trace)
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


def fixture_greys(same: bool) -> tuple[np.ndarray, tuple[int, int], tuple[int, int]]:
    g = np.zeros((64, 64), dtype=np.uint8)
    a, b = (18, 14), (18, 46)
    g[16:21, 12:17] = 2
    g[16:21, 44:49] = 2 if same else 3
    return g, a, b


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


def run_gates(vlm: Vlm, work: Path, run_dir: Path, args, doc: dict[str, Any]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    call_no = iter(range(1, 100))
    seed_for = lambda: args.seed * 1000 + next(call_no)

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
        seed=seed_for(), sampler=WIRING_SAMPLER, max_tokens=args.max_tokens,
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
    doc["gate1_palette"] = {"call": call, "checks": checks, "truth": {k: v for k, v in truth.items() if k != "marked_cell"}}
    results["gate1_palette_production"] = all(checks.values())

    # Gate 2 — similar greys, marked pair. Review round 1 rerun fix: the first wording
    # ("same or different") was semantically ambiguous — the model correctly read both
    # marker positions and answered that the CELLS were different (different positions),
    # which was true. The question is now about fill colour only, boolean.
    grey_checks = {}
    for same in (False, True):
        grid, a, b = fixture_greys(same)
        board = save(grid, f"g2_board_{same}.png")
        ma = sr.render_marker(grid, a, "MARK A").save(work / f"g2_a_{same}.png")
        mb = sr.render_marker(grid, b, "MARK B").save(work / f"g2_b_{same}.png")
        call = vlm.ask(
            [{"type": "text", "text": "Image 1 (board):"}, {"type": "image"},
             {"type": "text", "text": "Image 2 (mark A):"}, {"type": "image"},
             {"type": "text", "text": "Image 3 (mark B):"}, {"type": "image"},
             {"type": "text", "text": (
                 "Compare the FILL COLOUR of the cell inside the magenta ring in "
                 "Image 2 with the fill colour of the cell inside the magenta ring "
                 "in Image 3. Ignore the rings themselves and ignore where the "
                 "cells are on the board. Think first. Then answer with ONLY a "
                 'JSON object: {"same_fill_colour": true or false}.'
             )}],
            [board, ma, mb],
            seed=seed_for(), sampler=WIRING_SAMPLER, max_tokens=args.max_tokens,
            run_dir=run_dir, tag=f"g2_greys_{'same' if same else 'diff'}",
        )
        got = (call["payload"] or {}).get("same_fill_colour")
        grey_checks["same" if same else "diff"] = {"call": call, "correct": got is same}
    doc["gate2_greys"] = grey_checks
    results["gate2_grey_fill_colour"] = all(v["correct"] for v in grey_checks.values())

    # Gate 3 — packet-scale multi-image binding (6 pages). Review round 1 rerun fix:
    # the first fixture repeated the green board across pages 3/4/6, making the
    # queried targets non-unique — the model detected the ill-posedness in its think
    # and truncated deliberating it. Pages are now built from DISJOINT boards: each
    # queried object exists on exactly one page by construction.
    g_green = np.zeros((64, 64), dtype=np.uint8); g_green[40:44, 8:12] = 14
    g_orange = np.zeros((64, 64), dtype=np.uint8); g_orange[10:14, 30:34] = 12
    g_purple = np.zeros((64, 64), dtype=np.uint8); g_purple[24:28, 24:28] = 15
    g_yellow = np.zeros((64, 64), dtype=np.uint8); g_yellow[55, 12] = 11
    g_blue_pre = np.zeros((64, 64), dtype=np.uint8)
    g_blue_post = g_blue_pre.copy(); g_blue_post[20, 20] = 9
    g_grey1 = np.zeros((64, 64), dtype=np.uint8); g_grey1[5:9, 5:9] = 2
    g_grey2 = np.zeros((64, 64), dtype=np.uint8); g_grey2[50:54, 50:54] = 3
    pages = [
        save(g_green, "g3_p1.png"),
        save(g_orange, "g3_p2.png"),
        sr.render_crop(g_purple, (24, 24, 27, 27)).save(work / "g3_p3.png"),
        sr.render_marker(g_yellow, (55, 12), "ACTION6(12,55)").save(work / "g3_p4.png"),
        sr.render_diff_mask(g_blue_pre, g_blue_post).save(work / "g3_p5.png"),
        sr.storyboard([g_grey1, g_grey2, g_grey1], cols=3).save(work / "g3_p6.png"),
    ]
    items: list[dict[str, str]] = []
    for i in range(6):
        items.append({"type": "text", "text": f"Page {i + 1}:"})
        items.append({"type": "image"})
    items.append({"type": "text", "text": (
        "Think first. Then answer with ONLY a JSON object: "
        '{"green_square_page": <int>, "orange_square_page": <int>, '
        '"diff_mask_page": <int>} — the diff mask is the black image with white '
        "marks."
    )})
    call = vlm.ask(items, pages, seed=seed_for(), sampler=WIRING_SAMPLER,
                   max_tokens=max(args.max_tokens, 8000), run_dir=run_dir,
                   tag="g3_binding")
    p = call["payload"] or {}
    checks = {
        "complete": call["completeness"] == "complete",
        "green": p.get("green_square_page") == 1,
        "orange": p.get("orange_square_page") == 2,
        "diff": p.get("diff_mask_page") == 5,
    }
    doc["gate3_binding"] = {"call": call, "checks": checks}
    results["gate3_packet_binding"] = all(checks.values())

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
    for tag, grid, want in (
        ("left", fixture_relation(True), "left"),
        ("right", fixture_relation(False), "right"),
        ("blank", np.zeros((64, 64), dtype=np.uint8), "none"),
    ):
        img = save(grid, f"g4_{tag}.png")
        call = vlm.ask(
            [{"type": "image"}, {"type": "text", "text": rel_request}], [img],
            seed=seed_for(), sampler=WIRING_SAMPLER, max_tokens=args.max_tokens,
            run_dir=run_dir, tag=f"g4_{tag}",
        )
        got = str((call["payload"] or {}).get("relation", "")).strip().lower()
        rel_checks[tag] = {"call": call, "correct": got == want,
                          "think_chars_diagnostic": call["think_chars"]}
    doc["gate4_spatial_grounding"] = rel_checks
    results["gate4_spatial_grounding"] = all(v["correct"] for v in rel_checks.values())

    # Gate 5 — production-sampler stability panel on the gate-1 item.
    stability = []
    for rep in range(args.stability):
        call = vlm.ask(
            [{"type": "text", "text": "Image 1:"}, {"type": "image"},
             {"type": "text", "text": "Image 2:"}, {"type": "image"},
             {"type": "text", "text": PALETTE_REQUEST}],
            [board_png, marker_png],
            seed=seed_for(), sampler=PRODUCTION_SAMPLER, max_tokens=args.max_tokens,
            run_dir=run_dir, tag=f"g5_stability_{rep}",
        )
        p = call["payload"] or {}
        ok = (
            call["completeness"] == "complete"
            and p.get("red_count") == 3 and p.get("blue_count") == 2
            and p.get("green_count") == 4
            and str(p.get("marked_cell_colour", "")).strip().lower() == "purple"
        )
        stability.append({"call": call, "correct": ok})
    doc["gate5_stability"] = stability
    passes = sum(1 for s in stability if s["correct"])
    doc["gate5_pass_fraction"] = f"{passes}/{args.stability}"
    results["gate5_sampler_stability"] = passes * 3 >= args.stability * 2  # >= 2/3 (w)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=4, help="base of the recorded seed schedule")
    parser.add_argument("--stability", type=int, default=3, help="production-sampler replicates")
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--force", action="store_true", help="allow overwriting an existing --out")
    args = parser.parse_args()

    out_path = args.out or ROOT / f"logs/e2_probe_vlm_{args.model.name}.json"
    if out_path.exists() and not args.force:
        print(f"REFUSED: {out_path} exists (pass --force to overwrite)", file=sys.stderr)
        return 2
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / f"logs/e2_probe_vlm_runs/{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    work = run_dir / "boards"
    work.mkdir()
    # preflight the destination BEFORE the model eats 30 GB of memory
    atomic_write(out_path, {"status": "preflight", "run_dir": str(run_dir)})

    doc: dict[str, Any] = {
        "note": "notes/qwen-3.8-slice4-design.md -> Gates + REVIEW ROUND 1; probe v2",
        "fingerprint": fingerprint(args.model),
        "wiring_sampler": WIRING_SAMPLER,
        "production_sampler": PRODUCTION_SAMPLER,
        "reasoning_effort": REASONING_EFFORT,
        "seed_base": args.seed,
        "run_dir": str(run_dir),
        "status": "loading",
    }
    atomic_write(out_path, doc)

    print(f"loading {args.model.name} ...", flush=True)
    vlm = Vlm(args.model)
    doc["status"] = "loaded"
    atomic_write(out_path, doc)

    try:
        results = run_gates(vlm, work, run_dir, args, doc)
    finally:
        doc["status"] = "finished_or_aborted"
        atomic_write(out_path, doc)

    doc["results"] = results
    doc["passed"] = all(results.values())
    doc["status"] = "done"
    atomic_write(out_path, doc)
    for name, ok in results.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}", flush=True)
    print(f"ALL GATES: {'PASS' if doc['passed'] else 'FAIL'}")
    print(f"wrote {out_path}  (traces: {run_dir})")
    return 0 if doc["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
