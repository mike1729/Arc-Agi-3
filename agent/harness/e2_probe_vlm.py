#!/usr/bin/env python3
"""Slice-4 vision bring-up probe — the four gates, direct mlx_vlm path.

`notes/qwen-3.8-slice4-design.md` → Gates. No slice-4 number is trusted before all four
PASS on the serving configuration that will run the night:

  1. synthetic palette board — exact colours, counts, locations;
  2. two-image ordering — reverse the images, the answer must reverse;
  3. blank/substituted image — the answer must track the pixels, not priors;
  4. image-conditioned thinking — substantive open/closed think + a correct relation.

Serving pins (operator, rev 2): direct `mlx_vlm.load`/`generate` — never the server,
never `mlx_lm` (it discards the vision weights). The checkpoint processor's chat
template is called DIRECTLY with interleaved image/text items — the mlx-vlm helper
prepends anonymous images. `enable_thinking=True` explicitly on every call (0.6.x
defaults to the pre-filled non-thinking path — the July mechanism); the generation
region is asserted prefill-free every call. Sampler: temperature 1.0, top-p 0.95,
top-k 20. Effort xhigh (capability upper bound). NEVER constrain the first decoded
token: the model thinks free-form; the JSON asked for arrives after `</think>`.

Run:
  .venv/bin/python agent/harness/e2_probe_vlm.py --out logs/e2_probe_vlm_38_8bit.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MODEL = Path.home() / "models/mlx/Qwen3.8-27B-8bit"

# Canonical ARC palette, copied by value from the reference vision harness
# (agent/reference/taaf/src/ARC3-Inference/inference/agent/vision_context.py:14,
# ARC_COLOR_MAP). The slightly different gi2_observation.render_crop palette is NOT
# used — rev 2 pins this one for every slice-4 render, and the probe must see the same
# colours the packets will use.
ARC_COLOR_MAP: dict[int, tuple[int, int, int]] = {
    0: (255, 255, 255),
    1: (204, 204, 204),
    2: (153, 153, 153),
    3: (102, 102, 102),
    4: (51, 51, 51),
    5: (0, 0, 0),
    6: (229, 58, 163),
    7: (255, 123, 204),
    8: (249, 60, 49),
    9: (30, 147, 255),
    10: (136, 216, 241),
    11: (255, 220, 0),
    12: (255, 133, 27),
    13: (146, 18, 49),
    14: (79, 204, 48),
    15: (163, 86, 214),
}
# Names the checks accept in answers, for the four maximally-nameable colours + white.
COLOR_WORDS = {8: "red", 9: "blue", 11: "yellow", 14: "green", 0: "white"}

SAMPLER = {"temperature": 1.0, "top_p": 0.95, "top_k": 20}
REASONING_EFFORT = "xhigh"
CELL_PX = 32  # gate boards are 16x16 cells -> 512x512, a multiple of 32


def render(cells: np.ndarray, path: Path) -> Path:
    rgb = np.zeros((*cells.shape, 3), dtype=np.uint8)
    for value, colour in ARC_COLOR_MAP.items():
        rgb[cells == value] = colour
    img = Image.fromarray(np.kron(rgb, np.ones((CELL_PX, CELL_PX, 1), dtype=np.uint8)))
    assert img.size[0] % 32 == 0 and img.size[1] % 32 == 0
    img.save(path)
    return path


def board(spec: dict[int, list[tuple[int, int]]], size: int = 16) -> np.ndarray:
    cells = np.zeros((size, size), dtype=np.uint8)
    for value, positions in spec.items():
        for r, c in positions:
            cells[r, c] = value
    return cells


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def extract_json(answer: str) -> dict[str, Any] | None:
    """Last {...} block in the post-think answer; fences tolerated. Free text first,
    JSON after — the first decoded token is never constrained."""
    matches = re.findall(r"\{[^{}]*\}", answer, re.S)
    for candidate in reversed(matches):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


class Vlm:
    def __init__(self, path: Path):
        from mlx_vlm import load

        self.path = path
        self.model, self.processor = load(str(path))

    def ask(
        self, items: list[dict[str, str]], images: list[Path], max_tokens: int
    ) -> dict[str, Any]:
        """items: interleaved [{"type": "text"|"image", ...}] for ONE user turn.
        Image order in `images` must match the image items' order — that alignment is
        the point of calling the processor template directly."""
        from mlx_vlm import generate

        messages = [{"role": "user", "content": items}]
        prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True,
            reasoning_effort=REASONING_EFFORT,
        )
        generation_region = prompt[prompt.rfind("<|im_start|>assistant") :]
        opens = prompt.rstrip().endswith("<think>")
        prefilled = "<think>\n\n</think>" in generation_region
        pil = [Image.open(p) for p in images]
        inputs = self.processor(text=prompt, images=pil or None, return_tensors="np")
        grid_thw = inputs.get("image_grid_thw")
        start = time.monotonic()
        out = generate(
            self.model,
            self.processor,
            prompt,
            image=[str(p) for p in images],
            max_tokens=max_tokens,
            verbose=False,
            **SAMPLER,
        )
        text = out.text if hasattr(out, "text") else str(out)
        full = ("<think>" + text) if opens else text
        closed = "</think>" in full
        think = full.split("<think>", 1)[-1].split("</think>", 1)[0] if "<think>" in full else ""
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        return {
            "images": [
                {"path": str(p), "sha256_16": sha256(p), "size": Image.open(p).size}
                for p in images
            ],
            "image_grid_thw": None if grid_thw is None else np.asarray(grid_thw).tolist(),
            "expanded_prompt_tokens": int(np.asarray(inputs["input_ids"]).shape[-1]),
            "prompt_opens_think": opens,
            "prefilled_empty_think": prefilled,
            "think_opened": "<think>" in full,
            "think_closed": closed,
            "think_chars": len(think.strip()),
            "answer": answer,
            "payload": extract_json(answer),
            "wall_seconds": round(time.monotonic() - start, 1),
        }


COUNT_REQUEST = (
    "Think first, carefully. Then answer with ONLY a JSON object on the last line: "
    '{"red_count": <int>, "blue_count": <int>, "centre_colour": "<colour word>"} — '
    "the number of pure red cells, the number of pure blue cells, and the colour of "
    "the cell at the exact centre of the grid (row 8, column 8 of 16, 0-indexed)."
)


def gate1_palette(vlm: Vlm, work: Path, out: dict[str, Any]) -> bool:
    """Exact colours, counts, locations on a canonical-palette board."""
    spec = {8: [(1, 2), (4, 12), (13, 3)], 9: [(2, 9), (6, 6), (9, 1), (11, 13), (14, 8)], 11: [(8, 8)]}
    img = render(board(spec), work / "gate1_board.png")
    call = vlm.ask(
        [{"type": "image"}, {"type": "text", "text": COUNT_REQUEST}], [img], 4000
    )
    p = call["payload"] or {}
    checks = {
        "no_prefill": not call["prefilled_empty_think"],
        "red_count": p.get("red_count") == 3,
        "blue_count": p.get("blue_count") == 5,
        "centre_colour": str(p.get("centre_colour", "")).strip().lower() == "yellow",
    }
    out["gate1_palette"] = {"call": call, "checks": checks, "expected": {"red": 3, "blue": 5, "centre": "yellow"}}
    return all(checks.values())


def gate2_ordering(vlm: Vlm, work: Path, out: dict[str, Any]) -> bool:
    """Reverse the images; the answer must reverse."""
    a = render(board({8: [(0, 0)]}), work / "gate2_a.png")  # red top-left
    b = render(board({14: [(0, 0)]}), work / "gate2_b.png")  # green top-left
    request = (
        "Think first. Then answer with ONLY a JSON object on the last line: "
        '{"image1_top_left": "<colour word>", "image2_top_left": "<colour word>"}.'
    )
    items = [
        {"type": "text", "text": "Image 1:"},
        {"type": "image"},
        {"type": "text", "text": "Image 2:"},
        {"type": "image"},
        {"type": "text", "text": request},
    ]
    first = vlm.ask(items, [a, b], 4000)
    second = vlm.ask(items, [b, a], 4000)
    p1, p2 = first["payload"] or {}, second["payload"] or {}
    norm = lambda d, k: str(d.get(k, "")).strip().lower()
    checks = {
        "forward": norm(p1, "image1_top_left") == "red" and norm(p1, "image2_top_left") == "green",
        "reversed": norm(p2, "image1_top_left") == "green" and norm(p2, "image2_top_left") == "red",
    }
    out["gate2_ordering"] = {"first": first, "second": second, "checks": checks}
    return all(checks.values())


def gate3_substitution(vlm: Vlm, work: Path, out: dict[str, Any]) -> bool:
    """Blank and substituted boards under gate 1's question — track the pixels."""
    blank = render(board({}), work / "gate3_blank.png")
    substituted = render(
        board({8: [(0, 5), (3, 3), (7, 10), (12, 2)], 9: [(5, 5), (10, 10)], 11: [(8, 8)]}),
        work / "gate3_substituted.png",
    )
    call_blank = vlm.ask([{"type": "image"}, {"type": "text", "text": COUNT_REQUEST}], [blank], 4000)
    call_sub = vlm.ask([{"type": "image"}, {"type": "text", "text": COUNT_REQUEST}], [substituted], 4000)
    pb, ps = call_blank["payload"] or {}, call_sub["payload"] or {}
    checks = {
        "blank_red": pb.get("red_count") == 0,
        "blank_blue": pb.get("blue_count") == 0,
        "blank_centre": str(pb.get("centre_colour", "")).strip().lower() == "white",
        "substituted_red": ps.get("red_count") == 4,
        "substituted_blue": ps.get("blue_count") == 2,
    }
    out["gate3_substitution"] = {"blank": call_blank, "substituted": call_sub, "checks": checks}
    return all(checks.values())


def gate4_thinking(vlm: Vlm, work: Path, out: dict[str, Any]) -> bool:
    """Substantive image-conditioned thinking + a correct simple relation."""
    cells = board({})
    cells[6:9, 2:5] = 8   # red 3x3, left
    cells[6:9, 11:14] = 9  # blue 3x3, right
    img = render(cells, work / "gate4_relation.png")
    call = vlm.ask(
        [
            {"type": "image"},
            {
                "type": "text",
                "text": (
                    "Think first. Then answer with ONLY a JSON object on the last "
                    'line: {"relation": "left" or "right"} — is the red square to '
                    "the left or to the right of the blue square?"
                ),
            },
        ],
        [img],
        4000,
    )
    p = call["payload"] or {}
    checks = {
        "no_prefill": not call["prefilled_empty_think"],
        "think_opened": call["think_opened"],
        "think_closed": call["think_closed"],
        "think_substantive": call["think_chars"] >= 200,
        "relation": str(p.get("relation", "")).strip().lower() == "left",
    }
    out["gate4_thinking"] = {"call": call, "checks": checks}
    return all(checks.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out_path = args.out or ROOT / f"logs/e2_probe_vlm_{args.model.name}.json"

    work = ROOT / "logs/e2_probe_vlm_boards"
    work.mkdir(parents=True, exist_ok=True)

    config_fingerprint = hashlib.sha256(
        (args.model / "config.json").read_bytes()
    ).hexdigest()[:16]

    print(f"loading {args.model.name} ...", flush=True)
    vlm = Vlm(args.model)

    document: dict[str, Any] = {
        "note": "notes/qwen-3.8-slice4-design.md -> Gates; four gates, direct mlx_vlm path",
        "model": str(args.model),
        "config_sha256_16": config_fingerprint,
        "versions": {p: pkg_version(p) for p in ("mlx-vlm", "mlx", "mlx-lm", "transformers")},
        "sampler": SAMPLER,
        "reasoning_effort": REASONING_EFFORT,
        "cell_px": CELL_PX,
    }
    results: dict[str, bool] = {}
    for name, gate in (
        ("gate1_palette", gate1_palette),
        ("gate2_ordering", gate2_ordering),
        ("gate3_substitution", gate3_substitution),
        ("gate4_thinking", gate4_thinking),
    ):
        passed = gate(vlm, work, document)
        results[name] = passed
        print(f"{name}: {'PASS' if passed else 'FAIL'}", flush=True)

    document["results"] = results
    document["passed"] = all(results.values())
    out_path.write_text(json.dumps(document, indent=1))
    print(f"ALL GATES: {'PASS' if document['passed'] else 'FAIL'}")
    print(f"wrote {out_path}")
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
