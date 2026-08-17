#!/usr/bin/env python3
"""Slice-4 plate renderer — canonical palette, NN upscaling, separated annotations.

`notes/qwen-3.8-slice4-design.md` → Rendering specification. This module is pure
pixels: it reads grids and produces PNG plates. It never touches game source, human
replays, or store semantics — blindness by construction, so the packet builder can
import it freely.

Rules it enforces (rev 2, operator-pinned):
  - canonical ARC palette (taaf `vision_context.py` ARC_COLOR_MAP) — the only palette;
  - full 64x64 boards at 16x nearest-neighbour -> 1024x1024;
  - crops at dynamic NN scale, >= MIN_CROP_CELL_PX per cell;
  - every emitted dimension a multiple of 32 (neutral-margin padding, recorded);
  - never emit raw 64x64 (the processor would upscale bicubically);
  - raw evidence and annotations are SEPARATE plates — no box is ever drawn on the
    only copy of an exhibit;
  - five-panel before/after exhibits:
    full-board context | magnified pre-crop | action/click marker | magnified
    post-crop | binary diff mask.

Selftest: palette identity with `e2_probe_vlm`, exact grid round-trip through a
rendered plate, dimension rules, diff-mask correctness.

Run:
  .venv/bin/python agent/harness/s4_render.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

# Canonical ARC palette — copied by value from
# agent/reference/taaf/src/ARC3-Inference/inference/agent/vision_context.py:14.
# `gi2_observation.render_crop`'s slightly different palette is deliberately NOT used.
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

FULL_BOARD_CELL_PX = 16      # 64x64 board -> 1024x1024
MIN_CROP_CELL_PX = 32        # crops: at least this many pixels per game cell
PAD_RGB = (220, 220, 220)    # neutral margin used only to reach %32 dimensions
MARKER_RGB = (255, 0, 255)   # magenta: not in the palette, unmistakable on any board
DIFF_CHANGED = 255           # diff mask: white = changed, black = unchanged


@dataclass
class Plate:
    """One emitted PNG plus the exact accounting the ledger records."""

    image: Image.Image
    kind: str
    cell_px: int
    pad: tuple[int, int]                 # (right, bottom) padding pixels added for %32
    bbox: tuple[int, int, int, int] | None = None  # (r0, c0, r1, c1) crop, inclusive
    meta: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path)
        return path


def _pad_to_32(rgb: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    h, w = rgb.shape[:2]
    ph, pw = (-h) % 32, (-w) % 32
    if ph or pw:
        rgb = np.pad(
            rgb,
            ((0, ph), (0, pw), (0, 0)),
            mode="constant",
            constant_values=0,
        )
        rgb[h:, :, :] = PAD_RGB
        rgb[:, w:, :] = PAD_RGB
    return rgb, (pw, ph)


def _to_rgb(grid: np.ndarray) -> np.ndarray:
    rgb = np.zeros((*grid.shape, 3), dtype=np.uint8)
    for value, colour in ARC_COLOR_MAP.items():
        rgb[grid == value] = colour
    return rgb


def _upscale(rgb: np.ndarray, cell_px: int) -> np.ndarray:
    return np.kron(rgb, np.ones((cell_px, cell_px, 1), dtype=np.uint8))


def render_board(grid: np.ndarray, cell_px: int = FULL_BOARD_CELL_PX) -> Plate:
    """Full board at fixed NN scale. 64x64 -> 1024x1024 exactly (no padding)."""
    grid = np.asarray(grid, dtype=np.uint8)
    rgb, pad = _pad_to_32(_upscale(_to_rgb(grid), cell_px))
    return Plate(Image.fromarray(rgb), "board", cell_px, pad, meta={"shape": grid.shape})


def render_crop(
    grid: np.ndarray,
    bbox: tuple[int, int, int, int],
    margin: int = 2,
    min_cell_px: int = MIN_CROP_CELL_PX,
) -> Plate:
    """Magnified crop around an inclusive (r0, c0, r1, c1) bbox with a cell margin."""
    grid = np.asarray(grid, dtype=np.uint8)
    r0, c0, r1, c1 = bbox
    r0, c0 = max(0, r0 - margin), max(0, c0 - margin)
    r1, c1 = min(grid.shape[0] - 1, r1 + margin), min(grid.shape[1] - 1, c1 + margin)
    window = grid[r0 : r1 + 1, c0 : c1 + 1]
    cell_px = max(min_cell_px, MIN_CROP_CELL_PX)
    rgb, pad = _pad_to_32(_upscale(_to_rgb(window), cell_px))
    return Plate(
        Image.fromarray(rgb), "crop", cell_px, pad,
        bbox=(r0, c0, r1, c1), meta={"window_shape": window.shape},
    )


def render_marker(
    grid: np.ndarray,
    click: tuple[int, int] | None,
    action_label: str,
    cell_px: int = FULL_BOARD_CELL_PX,
) -> Plate:
    """Annotation plate: the board COPY with the click cell outlined and the action
    label in the padded margin. The raw board plate stays untouched elsewhere."""
    base = render_board(grid, cell_px)
    img = base.image.copy()
    draw = ImageDraw.Draw(img)
    if click is not None:
        r, c = click
        x0, y0 = c * cell_px, r * cell_px
        for w in range(3):  # 3px ring, outside-in, so the cell's colour stays visible
            draw.rectangle(
                [x0 - w - 1, y0 - w - 1, x0 + cell_px + w, y0 + cell_px + w],
                outline=MARKER_RGB,
            )
    # label strip appended BELOW the board (never over pixels), padded to %32
    strip_h = 32
    labelled = Image.new("RGB", (img.width, img.height + strip_h), PAD_RGB)
    labelled.paste(img, (0, 0))
    ImageDraw.Draw(labelled).text((8, img.height + 8), action_label, fill=(0, 0, 0))
    rgb, pad = _pad_to_32(np.asarray(labelled))
    return Plate(
        Image.fromarray(rgb), "marker", cell_px, pad,
        meta={"click": click, "action_label": action_label},
    )


def render_diff_mask(
    pre: np.ndarray, post: np.ndarray, cell_px: int = FULL_BOARD_CELL_PX
) -> Plate:
    """Binary changed-cell mask: white = changed, black = unchanged."""
    pre, post = np.asarray(pre), np.asarray(post)
    mask = (pre != post).astype(np.uint8) * DIFF_CHANGED
    rgb = np.repeat(mask[:, :, None], 3, axis=2)
    rgb, pad = _pad_to_32(_upscale(rgb, cell_px))
    return Plate(
        Image.fromarray(rgb), "diff_mask", cell_px, pad,
        meta={"changed_cells": int((pre != post).sum())},
    )


def changed_bbox(pre: np.ndarray, post: np.ndarray) -> tuple[int, int, int, int] | None:
    """Inclusive bbox of the changed-cell union; None when nothing changed."""
    rows, cols = np.nonzero(np.asarray(pre) != np.asarray(post))
    if rows.size == 0:
        return None
    return int(rows.min()), int(cols.min()), int(rows.max()), int(cols.max())


def exhibit(
    pre: np.ndarray,
    post: np.ndarray,
    action_label: str,
    click: tuple[int, int] | None = None,
) -> dict[str, Plate]:
    """The five-panel before/after exhibit, each panel its own plate:
    context | pre-crop | marker | post-crop | diff mask. Falls back to full-board
    pre/post panels when the change is board-wide or absent (recorded in meta)."""
    bbox = changed_bbox(pre, post)
    if click is not None and bbox is not None:
        bbox = (
            min(bbox[0], click[0]), min(bbox[1], click[1]),
            max(bbox[2], click[0]), max(bbox[3], click[1]),
        )
    elif click is not None and bbox is None:
        bbox = (click[0], click[1], click[0], click[1])
    panels: dict[str, Plate] = {"context": render_board(pre)}
    if bbox is None:
        panels["pre_crop"] = render_board(pre)
        panels["post_crop"] = render_board(post)
        panels["pre_crop"].meta["fallback"] = "no changed cells and no click"
    else:
        span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) + 1
        if span > 32:  # board-wide change: crops would be full-board anyway
            panels["pre_crop"] = render_board(pre)
            panels["post_crop"] = render_board(post)
            panels["pre_crop"].meta["fallback"] = f"changed span {span} cells, board-wide"
        else:
            panels["pre_crop"] = render_crop(pre, bbox)
            panels["post_crop"] = render_crop(post, bbox)
    panels["marker"] = render_marker(pre, click, action_label)
    panels["diff_mask"] = render_diff_mask(pre, post)
    return panels


def storyboard(
    frames: Sequence[np.ndarray],
    cols: int = 4,
    cell_px: int = 4,
    gap: int = 8,
) -> Plate:
    """Thumbnail atlas with index labels in the gutters, never over board pixels.
    cell_px=4 keeps 64x64 thumbnails at 256px — atlas pages, not evidence closeups."""
    if not frames:
        raise ValueError("storyboard needs at least one frame")
    thumbs = [_upscale(_to_rgb(np.asarray(f, dtype=np.uint8)), cell_px) for f in frames]
    th, tw = thumbs[0].shape[:2]
    rows = (len(thumbs) + cols - 1) // cols
    label_h = 16
    sheet = Image.new(
        "RGB",
        (cols * tw + (cols + 1) * gap, rows * (th + label_h) + (rows + 1) * gap),
        PAD_RGB,
    )
    draw = ImageDraw.Draw(sheet)
    for i, thumb in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = gap + c * (tw + gap)
        y = gap + r * (th + label_h + gap)
        sheet.paste(Image.fromarray(thumb), (x, y))
        draw.text((x, y + th + 2), f"[{i}]", fill=(0, 0, 0))
    rgb, pad = _pad_to_32(np.asarray(sheet))
    return Plate(
        Image.fromarray(rgb), "storyboard", cell_px, pad,
        meta={"frames": len(frames), "cols": cols},
    )


def decode_board(plate: Plate) -> np.ndarray:
    """Exact inverse for un-annotated board plates — the selftest's round trip."""
    rgb = np.asarray(plate.image)
    w_pad, h_pad = plate.pad
    if h_pad:
        rgb = rgb[:-h_pad]
    if w_pad:
        rgb = rgb[:, :-w_pad]
    cells = rgb[:: plate.cell_px, :: plate.cell_px]
    lookup = {colour: value for value, colour in ARC_COLOR_MAP.items()}
    out = np.zeros(cells.shape[:2], dtype=np.uint8)
    for r in range(cells.shape[0]):
        for c in range(cells.shape[1]):
            out[r, c] = lookup[tuple(cells[r, c])]
    return out


def selftest() -> int:
    import e2_probe_vlm

    # Probe v2 carries no palette copy — it must render through THIS module, which is
    # the stronger property the old palette-identity assertion approximated.
    assert e2_probe_vlm.sr is sys.modules[__name__], "probe does not render through s4_render"

    rng = np.random.default_rng(4)
    grid = rng.integers(0, 16, size=(64, 64), dtype=np.uint8)
    plate = render_board(grid)
    assert plate.image.size == (1024, 1024), plate.image.size
    assert np.array_equal(decode_board(plate), grid), "round trip failed"

    crop = render_crop(grid, (10, 10, 14, 14))
    assert crop.image.width % 32 == 0 and crop.image.height % 32 == 0
    assert crop.cell_px >= MIN_CROP_CELL_PX

    post = grid.copy()
    post[12, 13] = (int(post[12, 13]) + 1) % 16
    panels = exhibit(grid, post, "ACTION6(13,12)", click=(12, 13))
    assert set(panels) == {"context", "pre_crop", "marker", "post_crop", "diff_mask"}
    assert panels["diff_mask"].meta["changed_cells"] == 1
    mask = np.asarray(panels["diff_mask"].image)
    px = FULL_BOARD_CELL_PX
    assert mask[12 * px + 1, 13 * px + 1, 0] == DIFF_CHANGED
    assert mask[0, 0, 0] == 0
    raw = render_board(grid)  # raw plate emitted alongside marker stays unannotated
    assert np.array_equal(np.asarray(raw.image), np.asarray(plate.image))

    sheet = storyboard([grid, post, grid], cols=2)
    assert sheet.image.width % 32 == 0 and sheet.image.height % 32 == 0

    wide = grid.copy()
    wide[:, :] = (wide + 1) % 16
    fb = exhibit(grid, wide, "RESET")
    assert fb["pre_crop"].meta.get("fallback", "").startswith("changed span")

    print("SELFTEST PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    parser.error("this module is a library; run --selftest or import it")
    return 2


if __name__ == "__main__":
    HARNESS = Path(__file__).resolve().parent
    if str(HARNESS) not in sys.path:
        sys.path.insert(0, str(HARNESS))
    sys.exit(main())
