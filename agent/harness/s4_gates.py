"""Claim-scoped gates and mechanical arm eligibility (slice-4 protocol revision 4).

Replaces the v2.2 single-certificate monolith: each certified CLAIM is its own
record with its own fixtures, calls, and mechanical checks, and an arm is
eligible only when every claim in its frozen requirement set passed.  A failed
claim can never veto an arm that does not consume it, and the runner refuses
the whole declared matrix if any selected arm is ineligible — silently falling
back to a subset would change the experiment after seeing results.

Claims
  G0_protocol_serving                 mechanical, must pass 100%      (T V O P)
  GT_text_exact                       model, 6/6                      (T)
  GV_raw_readout                      model, 6/6                      (V O P)
  GO_overlay_readout                  model, 6/6                      (O P)
  GP_interaction                      model, 6/6                      (P)
  GX_precision_action:<profile>       model, 6/6 plus 8/8 coordinates (P)
  GD_dense_4px_exact                  model diagnostic; blocks nothing

Model-dependent claims run under the PRODUCTION sampler, pinned effort, real
prompt schema, image history, and token envelope; a temperature-0 result is a
wiring diagnostic and cannot authorize an inferential arm.  Stability bar per
claim: two counter-permutations over three fresh source-blind fixtures, 6/6
complete call-level passes — an operational bar (rejects p<=0.5 at 1/64), not
a reliability claim.  GX additionally requires eight fresh sealed coordinates
covering all row/column patch phases, decoded mechanically from the final PNG,
8/8 exact, with strict `type(value) is int` coordinates.

Fixtures are procedural and seeded.  `dev` and `confirm` namespaces derive
disjoint content; development calibration may only ever consume `dev`;
confirmation fixtures are generated at seal time, sealed under the versioned
directory, and consumed exactly once after FROZEN.json exists.  Truth is
generated procedurally AND independently re-decoded from the produced PNGs —
a fixture whose decode disagrees with its intent aborts fixture generation.

This module performs no model generation unless explicitly invoked with --run,
which additionally requires the sealed FROZEN.json for the confirm namespace.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_delta as sd  # noqa: E402
import s4_ledgers as sl  # noqa: E402
import s4_render as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "r4"
FORMAT_VERSION = 1
DEV_FIXTURES = ROOT / "logs/s4_gate_dev"
SEALED_R4 = ROOT / "logs/s4_sealed" / PROTOCOL_VERSION
CONFIRM_FIXTURES = SEALED_R4 / "fixtures"

PRECISION_PROFILE = sr.RULER_CROP_PROFILE
GX_CLAIM = f"GX_precision_action:{PRECISION_PROFILE}"

MODEL_CLAIMS = ("GT_text_exact", "GV_raw_readout", "GO_overlay_readout",
                "GP_interaction", GX_CLAIM)
DIAGNOSTIC_CLAIMS = ("GD_dense_4px_exact",)
ALL_CLAIMS = ("G0_protocol_serving",) + MODEL_CLAIMS + DIAGNOSTIC_CLAIMS

ARM_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "T": ("G0_protocol_serving", "GT_text_exact"),
    "V": ("G0_protocol_serving", "GV_raw_readout"),
    "O": ("G0_protocol_serving", "GV_raw_readout", "GO_overlay_readout"),
    "P": ("G0_protocol_serving", "GV_raw_readout", "GO_overlay_readout",
          "GP_interaction", GX_CLAIM),
}

MODEL_CLAIM_FIXTURES = 3
MODEL_CLAIM_PERMUTATIONS = 2
MODEL_CLAIM_REQUIRED_PASSES = MODEL_CLAIM_FIXTURES * MODEL_CLAIM_PERMUTATIONS  # 6/6
GX_STABILITY_FIXTURES = MODEL_CLAIM_FIXTURES
GX_STABILITY_CALLS = MODEL_CLAIM_REQUIRED_PASSES
GX_COORDINATE_FIXTURES = 8          # fresh 8/8 exact, all patch phases covered
GX_TOTAL_FIXTURES = GX_STABILITY_FIXTURES + GX_COORDINATE_FIXTURES
GX_TOTAL_CALLS = GX_STABILITY_CALLS + GX_COORDINATE_FIXTURES
PATCH_PHASE_GRIDS = (16, 32)        # phases verified on the FINAL rendered bbox
GX_EXPECTED_PHASES = {
    "mod16": [0, 8],
    "mod32": [0, 8, 16, 24],
}
PRODUCTION_CONTEXT_PAGES = 10
PRODUCTION_MAX_IMAGES = 16
CONFIRM_RESERVATION = SEALED_R4 / "gate_confirm_reservation.json"
CONFIRM_RESULTS = SEALED_R4 / "claims.json"
CONFIRM_RUN_DIR = SEALED_R4 / "gate_run"

THRESHOLDS = {
    "model_claim_calls": MODEL_CLAIM_REQUIRED_PASSES,
    "model_claim_required_passes": MODEL_CLAIM_REQUIRED_PASSES,
    "gx_coordinate_fixtures": GX_COORDINATE_FIXTURES,
    "gx_required_exact": GX_COORDINATE_FIXTURES,
    "gx_stability_calls": GX_STABILITY_CALLS,
    "gx_stability_required_passes": GX_STABILITY_CALLS,
    "g0_required": "100% mechanical",
    "no_retry_no_majority_no_silent_repair": True,
    "plus_minus_one_is_a_fail": True,
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_sha256(value: Any) -> str:
    return sd.canonical_sha256(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_seed(namespace: str, claim: str, index: int, base_seed: int) -> int:
    """Disjoint deterministic derivation; dev and confirm can never collide."""
    require(namespace in {"dev", "confirm"}, f"unknown fixture namespace {namespace!r}")
    import hashlib

    digest = hashlib.sha256(
        f"{PROTOCOL_VERSION}:{namespace}:{claim}:{index}:{base_seed}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _rng(namespace: str, claim: str, index: int, base_seed: int) -> np.random.Generator:
    return np.random.default_rng(fixture_seed(namespace, claim, index, base_seed))


def _int_field(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if type(value) is not int:  # floats that compare equal are invalid by design
        errors.append(f"{key} must be a JSON integer, got {value!r}")


def make_validator(int_keys: Sequence[str], str_keys: Sequence[str] = ()) -> Callable:
    keys = list(int_keys) + list(str_keys)

    def _validate(payload: Any) -> list[str]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return ["final answer must be a JSON object"]
        for key in keys:
            if key not in payload:
                errors.append(f"missing key {key}")
        for key in int_keys:
            if key in payload:
                _int_field(payload, key, errors)
        for key in str_keys:
            if key in payload and not isinstance(payload[key], str):
                errors.append(f"{key} must be a string")
        return errors

    return _validate


# --------------------------------------------------------------------- fixtures


def _sparse_board(rng: np.random.Generator, *, objects: int) -> np.ndarray:
    grid = np.zeros((64, 64), dtype=np.uint8)
    for _ in range(objects):
        h, w = int(rng.integers(2, 6)), int(rng.integers(2, 6))
        r = int(rng.integers(0, 64 - h))
        c = int(rng.integers(0, 64 - w))
        colour = int(rng.integers(1, 16))
        grid[r : r + h, c : c + w] = colour
    return grid


def _unique_cell_colour(grid: np.ndarray, rng: np.random.Generator) -> int:
    present = set(int(v) for v in np.unique(grid))
    candidates = [value for value in range(1, 16) if value not in present]
    require(candidates, "fixture board left no unused palette colour")
    return int(rng.choice(candidates))


def build_gx_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """One sealed precision-action coordinate fixture on the frozen profile.

    The ruler window is deterministically OFF-CENTRE around the target so the
    answer is never derivable from window geometry, and the target's final
    rendered pixel bbox covers a scheduled (row, col) patch phase for both
    processor grids.  Truth is verified by decoding the produced PNG.
    """
    rng = _rng(namespace, GX_CLAIM, index, base_seed)
    require(0 <= index < GX_TOTAL_FIXTURES,
            f"GX fixture index outside 0..{GX_TOTAL_FIXTURES - 1}")
    # Indices 0..2 are the ordinary 3x2 stability holdouts.  Indices 3..10 are
    # a fresh, disjoint eight-coordinate phase/nuisance suite.
    schedule_index = (
        index if index < GX_STABILITY_FIXTURES
        else index - GX_STABILITY_FIXTURES
    )
    cluttered = schedule_index % 2 == 1
    grid = _sparse_board(rng, objects=14 if cluttered else 4)

    # Eight distinct, counterbalanced target colours.  Clearing an accidentally
    # generated occurrence before placing the target makes uniqueness an actual
    # fixture invariant instead of a probabilistic hope.
    target_colour = schedule_index + 1
    grid[grid == target_colour] = 0

    # Two fixtures per quadrant, all four near-edge combinations, and every
    # r0/c0 residue needed by the production v2 carrier's deterministic neutral
    # phase offset.  Patch phase is still measured below from FINAL pixels.
    positions = (
        (8, 8), (8, 55), (24, 8), (24, 55),
        (40, 8), (40, 55), (55, 8), (55, 55),
    )
    row, col = positions[schedule_index]
    # Namespace separation is visible in the actual requested coordinate, not
    # merely in unrelated clutter or RNG state.
    if namespace == "confirm":
        row += 2 if row < 32 else -2
        col += 2 if col < 32 else -2
    grid[row, col] = target_colour

    desired_r0_mod4 = schedule_index % 4
    desired_c0_mod4 = (schedule_index * 3) % 4

    def _window_start(target: int, residue: int) -> int:
        candidates = [value for value in range(max(0, target - 7), target + 1)
                      if value % 4 == residue]
        require(candidates, "GX could not schedule the requested crop-origin phase")
        # Off-centre and deterministic: never disclose the target as crop centre.
        return min(candidates, key=lambda value: (abs((target - value) - 3), value))

    window_r0 = _window_start(row, desired_r0_mod4)
    window_c0 = _window_start(col, desired_c0_mod4)
    height = 9 + (schedule_index % 4)
    width = 10 + ((schedule_index * 3) % 4)
    window = (window_r0, window_c0,
              min(63, max(row + 2, window_r0 + height - 1)),
              min(63, max(col + 2, window_c0 + width - 1)))
    require(window[0] <= row <= window[2] and window[1] <= col <= window[3],
            "GX fixture window does not contain its target")
    plate = sr.render_ruler_crop(grid, window, margin=0, cell_px=32)
    decoded = sr.decode_ruler_view(plate)
    r0, c0, _r1, _c1 = plate.bbox
    hits = np.argwhere(decoded == target_colour)
    require(hits.shape[0] == 1, "GX fixture target is not unique in the rendered window")
    decoded_row, decoded_col = int(hits[0][0]) + r0, int(hits[0][1]) + c0
    require((decoded_row, decoded_col) == (row, col),
            "GX fixture PNG decode disagrees with generator intent")
    # Patch phase measured from the FINAL rendered target bbox, never board coords.
    # `origin_px` includes the production profile's neutral top/left phase offset.
    origin_y, origin_x = plate.meta.get(
        "origin_px", [sr.RULER_GUTTER_PX, sr.RULER_GUTTER_PX]
    )
    y0 = int(origin_y) + (row - r0) * plate.cell_px
    x0 = int(origin_x) + (col - c0) * plate.cell_px
    phases = {f"mod{g}": [int(y0 % g), int(x0 % g)] for g in PATCH_PHASE_GRIDS}

    # A real mixed visual context, not an isolated crop.  The precision page
    # occupies both outer and inner positions across the eight holdouts.
    precision_positions = (0, 9, 1, 8, 2, 7, 3, 6)
    precision_position = precision_positions[schedule_index]
    context_pages: list[tuple[str, sr.Plate]] = []
    for page_index in range(PRODUCTION_CONTEXT_PAGES):
        if page_index == precision_position:
            context_pages.append(("precision_ruler_target", plate))
        else:
            distractor = _sparse_board(
                rng, objects=2 + (page_index + schedule_index) % 7
            )
            context_pages.append((f"context_{page_index + 1:02d}",
                                  sr.render_board(distractor, cell_px=4)))
    question = (
        f"Exactly one page is a magnified window with explicit rulers; the other "
        f"pages are irrelevant full-context boards. In the ruler page, "
        f"the left gutter prints 0-based ABSOLUTE row indices and the top gutter "
        f"prints 0-based ABSOLUTE column indices. Exactly one cell has colour id "
        f"{target_colour}. Think first. Then answer with ONLY a JSON object: "
        '{"target_row": <int>, "target_col": <int>}'
    )
    return {
        "claim": GX_CLAIM,
        "namespace": namespace,
        "index": index,
        "profile": PRECISION_PROFILE,
        "grid": grid.tolist(),
        "window": list(plate.bbox),
        "pages": context_pages,
        "precision_page": precision_position + 1,
        "question": question,
        "truth": {"target_row": row, "target_col": col},
        "target_pixel_origin": [int(y0), int(x0)],
        "patch_phases": phases,
        "nuisance": {
            "density": "cluttered" if cluttered else "sparse",
            "quadrant": ("top_left", "top_right", "top_left", "top_right",
                         "bottom_left", "bottom_right", "bottom_left",
                         "bottom_right")[schedule_index],
            "edge_rows": "near_top" if row <= 10 else "near_bottom" if row >= 53 else "interior",
            "edge_cols": "near_left" if col <= 10 else "near_right",
            "target_colour": target_colour,
            "precision_page": precision_position + 1,
            "crop_origin_mod4": [window_r0 % 4, window_c0 % 4],
        },
        "int_keys": ["target_row", "target_col"],
    }


def gx_phase_coverage(fixtures: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Mechanically enforce the frozen phase and nuisance schedule.

    Phase values come from final rendered target pixel origins.  Board
    coordinates and renderer intent are deliberately not accepted as proxies.
    """
    require(len(fixtures) == GX_COORDINATE_FIXTURES,
            f"GX requires exactly {GX_COORDINATE_FIXTURES} distinct fixtures")
    seen: dict[str, set[Any]] = {
        "row_mod16": set(), "col_mod16": set(),
        "row_mod32": set(), "col_mod32": set(),
        "density": set(), "quadrant": set(), "edge_rows": set(),
        "edge_cols": set(), "target_colour": set(), "precision_page": set(),
    }
    for fixture in fixtures:
        for grid in PATCH_PHASE_GRIDS:
            y_mod, x_mod = fixture["patch_phases"][f"mod{grid}"]
            seen[f"row_mod{grid}"].add(y_mod)
            seen[f"col_mod{grid}"].add(x_mod)
        for key in ("density", "quadrant", "edge_rows", "edge_cols",
                    "target_colour", "precision_page"):
            seen[key].add(fixture["nuisance"][key])
    coverage = {key: sorted(values) for key, values in seen.items()}
    expected = {
        "row_mod16": GX_EXPECTED_PHASES["mod16"],
        "col_mod16": GX_EXPECTED_PHASES["mod16"],
        "row_mod32": GX_EXPECTED_PHASES["mod32"],
        "col_mod32": GX_EXPECTED_PHASES["mod32"],
    }
    phase_ok = all(coverage[key] == values for key, values in expected.items())
    nuisance_ok = (
        coverage["density"] == ["cluttered", "sparse"]
        and len(coverage["quadrant"]) == 4
        and {"near_top", "near_bottom"}.issubset(seen["edge_rows"])
        and {"near_left", "near_right"}.issubset(seen["edge_cols"])
        and len(coverage["target_colour"]) == GX_COORDINATE_FIXTURES
        and {1, PRODUCTION_CONTEXT_PAGES}.issubset(seen["precision_page"])
    )
    return {**coverage, "expected_phases": expected,
            "phase_coverage_pass": phase_ok,
            "nuisance_coverage_pass": nuisance_ok,
            "pass": phase_ok and nuisance_ok}


def build_gt_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Text-carrier exactness fixture using the REAL text encoders."""
    import s4_packet as spk

    rng = _rng(namespace, "GT_text_exact", index, base_seed)
    boards = [_sparse_board(rng, objects=3 + i) for i in range(3)]
    # a no-effect action: identical pre/post
    frames = [f"F{index}{chr(97 + i)}" for i in range(3)]
    text_boards = [
        f"frame {fid} [OBSERVED]\n{spk._grid_rle(board)}"
        for fid, board in zip(frames, boards)
    ]
    effect_record = sd.sequence_record(
        frames[:2], [boards[0].tolist(), boards[1].tolist()],
        binding={"tid": f"T{index}01", "action": "A3"},
    )
    no_effect_record = sd.sequence_record(
        [frames[1], frames[1] + "x"], [boards[1].tolist(), boards[1].tolist()],
        binding={"tid": f"T{index}02", "action": "A5"},
    )
    probes: list[tuple[int, int, int]] = []
    board = boards[2]
    for _ in range(3):
        r, c = int(rng.integers(0, 64)), int(rng.integers(0, 64))
        probes.append((r, c, int(board[r, c])))
    records = text_boards + [
        sd.render_text_block(effect_record), sd.render_text_block(no_effect_record)
    ]
    ledger = "\n\n".join(records)
    question = (
        f"Using ONLY the exact records above: report the colour ids of frame "
        f"{frames[2]} at (row,col) {tuple(probes[0][:2])}, {tuple(probes[1][:2])} and "
        f"{tuple(probes[2][:2])} (0-based), and the tid of the action record whose "
        "frames are identical (a no-effect observation). Think first. Then answer "
        'with ONLY a JSON object: {"cell_0": <int>, "cell_1": <int>, '
        '"cell_2": <int>, "no_effect_tid": "<string>"}'
    )
    truth = {
        "cell_0": probes[0][2], "cell_1": probes[1][2], "cell_2": probes[2][2],
        "no_effect_tid": f"T{index}02",
    }
    # independent decode: the RLE text must reproduce the exact grid
    decoded = spk.decode_text_grid(spk._grid_rle(board), {})
    require(decoded == board.tolist(), "GT fixture text carrier decode mismatch")
    return {
        "claim": "GT_text_exact", "namespace": namespace, "index": index,
        "records": records, "ledger": ledger, "question": question, "truth": truth,
        "int_keys": ["cell_0", "cell_1", "cell_2"], "str_keys": ["no_effect_tid"],
    }


def _storyboard_with_event(rng: np.random.Generator, frames: int, cell_px: int
                           ) -> tuple[list[np.ndarray], int]:
    base = _sparse_board(rng, objects=3)
    sequence = []
    event_frame = int(rng.integers(2, frames - 2))
    for i in range(frames):
        frame = base.copy()
        marcher = 4 + (i % 8)
        frame[marcher : marcher + 2, 44:47] = 2
        if i == event_frame:
            colour = _unique_cell_colour(frame, rng)
            frame[int(rng.integers(20, 44)), int(rng.integers(8, 40))] = colour
        sequence.append(frame)
    return sequence, event_frame


def build_gv_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Raw-carrier readout at the carrier's ACTUAL resolutions — structural claims
    only (binding, order, event frame, coarse change), never cell-exact."""
    rng = _rng(namespace, "GV_raw_readout", index, base_seed)
    opening = _sparse_board(rng, objects=5)
    pre = _sparse_board(rng, objects=4)
    post = pre.copy()
    r, c = int(rng.integers(8, 56)), int(rng.integers(8, 56))
    post[r : r + 3, c : c + 3] = _unique_cell_colour(pre, rng)
    frames, event_frame = _storyboard_with_event(rng, 12, 4)
    green = np.zeros((64, 64), dtype=np.uint8)
    green[10:20, 10:20] = 3
    pages = [
        ("opening_8px", sr.render_board(opening, cell_px=8)),
        ("green_board", sr.render_board(green, cell_px=8)),
        ("causal_pre_4px", sr.render_board(pre, cell_px=4)),
        ("causal_post_4px", sr.render_board(post, cell_px=4)),
        ("diff_mask", sr.render_diff_mask(pre, post)),
        ("storyboard_4px", sr.storyboard(list(frames), cols=4, cell_px=4)),
        ("distractor_raw_8px", sr.render_board(
            _sparse_board(rng, objects=7), cell_px=8)),
        ("distractor_raw_4px", sr.render_board(
            _sparse_board(rng, objects=11), cell_px=4)),
        ("no_effect_mask", sr.render_diff_mask(opening, opening)),
        ("distractor_storyboard_4px", sr.storyboard(
            list(_storyboard_with_event(rng, 8, 4)[0]), cols=4, cell_px=4)),
    ]
    require(len(pages) == PRODUCTION_CONTEXT_PAGES,
            "GV must exercise the actual ten-page visual context")
    question = (
        "Pages are numbered in delivery order. Report: the page showing the board "
        "whose only non-background object is green; the page showing the binary "
        "changed-cell mask; the printed frame index of the storyboard frame that "
        "contains the single one-cell event; and whether the pre->post pair ADDED "
        "or REMOVED cells (structural, from the mask). Think first. Then answer "
        'with ONLY a JSON object: {"green_page": <int>, "mask_page": <int>, '
        '"event_frame": <int>, "change_kind": "added"|"removed"}'
    )
    return {
        "claim": "GV_raw_readout", "namespace": namespace, "index": index,
        "pages": pages, "question": question,
        "queried_pages": {"green_page": 1, "mask_page": 4},
        "truth_static": {"event_frame": event_frame, "change_kind": "added"},
        "int_keys": ["green_page", "mask_page", "event_frame"],
        "str_keys": ["change_kind"],
    }


def build_go_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Overlay readout: annotation-versus-state, alignment, component binding."""
    rng = _rng(namespace, "GO_overlay_readout", index, base_seed)
    board = _sparse_board(rng, objects=5)
    click = (int(rng.integers(4, 60)), int(rng.integers(4, 60)))
    under = int(board[click[0], click[1]])
    marked = sr.render_marker(board, click, f"A6({click[1]},{click[0]})")
    raw = sr.render_board(board)
    comp_r, comp_c = int(rng.integers(8, 50)), int(rng.integers(8, 50))
    comp_colour = _unique_cell_colour(board, rng)
    comp_board = board.copy()
    comp_board[comp_r : comp_r + 4, comp_c : comp_c + 4] = comp_colour
    comp_id = f"C{index}07"
    trans_pre = _sparse_board(rng, objects=6)
    trans_post = trans_pre.copy()
    tr, tc = int(rng.integers(10, 50)), int(rng.integers(10, 50))
    trans_post[tr : tr + 3, tc : tc + 3] = _unique_cell_colour(trans_pre, rng)
    decoy = _sparse_board(rng, objects=8)
    decoy_click = (int(rng.integers(4, 60)), int(rng.integers(4, 60)))
    pages = [
        ("raw", raw),
        ("marked", marked),
        ("component_board", sr.render_board(comp_board)),
        ("transition_pre", sr.render_board(trans_pre, cell_px=4)),
        ("transition_pre_marked", sr.render_marker(
            trans_pre, (tr, tc), f"A6({tc},{tr})", cell_px=4)),
        ("transition_post", sr.render_board(trans_post, cell_px=4)),
        ("transition_diff", sr.render_diff_mask(trans_pre, trans_post)),
        ("decoy_raw", sr.render_board(decoy, cell_px=8)),
        ("decoy_marked", sr.render_marker(
            decoy, decoy_click, f"A6({decoy_click[1]},{decoy_click[0]})", cell_px=8)),
        ("decoy_no_effect_diff", sr.render_diff_mask(decoy, decoy)),
    ]
    require(len(pages) == PRODUCTION_CONTEXT_PAGES,
            "GO must exercise the actual ten-page visual context")
    ledger = (
        f"component {comp_id}: bbox=({comp_r},{comp_c},{comp_r + 3},{comp_c + 3}) "
        f"[DERIVED-EXACT]"
    )
    question = (
        f"{ledger}\nThe magenta ring on the marked page is drawn by the recorder. "
        "Report: whether the ring is part of the game state or an annotation; the "
        "colour id of the CELL the ring surrounds; which page number shows the raw "
        f"unannotated copy of the same board; the page numbers of that marked copy "
        f"and component board; the aligned transition post and changed-cell mask; "
        f"and the colour id of component {comp_id} per its ledger bbox. Think first. "
        "Then answer with ONLY a JSON "
        'object: {"ring_is": "annotation"|"game_state", "ringed_cell_colour": <int>, '
        '"raw_page": <int>, "marked_page": <int>, "component_page": <int>, '
        '"transition_post_page": <int>, "transition_diff_page": <int>, '
        '"component_colour": <int>}'
    )
    return {
        "claim": "GO_overlay_readout", "namespace": namespace, "index": index,
        "pages": pages, "question": question,
        "queried_pages": {
            "raw_page": 0, "marked_page": 1, "component_page": 2,
            "transition_post_page": 5, "transition_diff_page": 6,
        },
        "truth_static": {
            "ring_is": "annotation", "ringed_cell_colour": under,
            "component_colour": comp_colour,
        },
        "int_keys": [
            "ringed_cell_colour", "raw_page", "marked_page", "component_page",
            "transition_post_page", "transition_diff_page", "component_colour",
        ],
        "str_keys": ["ring_is"],
    }


def build_gp_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Interaction chronology: 10 initial pages growing to 16 across staged
    rounds, result binding, settled-outcome reading, and a failed request that
    must be reported as failed (no silent repair)."""
    rng = _rng(namespace, "GP_interaction", index, base_seed)
    initial_pages = []
    for i in range(10):
        initial_pages.append((f"page_{i + 1}", sr.render_board(
            _sparse_board(rng, objects=2 + i % 4), cell_px=8)))
    pre = _sparse_board(rng, objects=3)
    mid = pre.copy()
    mid[30:33, 30:33] = _unique_cell_colour(pre, rng)
    settled = mid.copy()
    settled[10:12, 50:53] = _unique_cell_colour(mid, rng)
    result_frames = [pre, mid, settled]
    probe_tag = f"S{1000 + index}"
    rounds = [
        {"label": probe_tag,
         "pages": [
             (f"{probe_tag}_result_storyboard",
              sr.storyboard(result_frames, cols=3, cell_px=8)),
             (f"{probe_tag}_pre", sr.render_board(pre, cell_px=4)),
             (f"{probe_tag}_settled_diff", sr.render_diff_mask(pre, settled)),
         ],
         "text": (f"probe {probe_tag} result: replayed prefix, performed the "
                  "requested action, all response frames in order; the LAST frame "
                  "is the settled state [OBSERVED]")},
        {"label": f"K{2000 + index}",
         "pages": [],
         "text": (f"retrieval K{2000 + index} failed: request is invalid or absent "
                  "from the frozen observation store; it was not rewritten")},
        {"label": f"K{2001 + index}",
         "pages": [
             (f"K{2001 + index}_result_ruler", sr.render_ruler_frame(settled)),
             (f"K{2001 + index}_result_raw", sr.render_board(settled, cell_px=4)),
             (f"K{2001 + index}_result_context", sr.render_board(mid, cell_px=4)),
         ],
         "text": f"retrieval K{2001 + index} result: settled board, full frame "
                 "with rulers [OBSERVED]"},
    ]
    question = (
        "Report: how many images the FIRST evidence message contained; the total "
        "number of images delivered across the whole conversation; the 1-based "
        "index (within its own result storyboard) of the settled frame of probe "
        f"{probe_tag}; and the exact outcome of retrieval K{2000 + index} "
        '("returned_result" or "failed_no_result"). Think first. Then answer with '
        'ONLY a JSON object: {"initial_images": <int>, "total_images": <int>, '
        '"settled_frame": <int>, "k_outcome": "returned_result"|"failed_no_result"}'
    )
    total_images = len(initial_pages) + sum(len(r["pages"]) for r in rounds)
    require(total_images == PRODUCTION_MAX_IMAGES,
            "GP fixture must exercise exact 10-to-16-image growth")
    return {
        "claim": "GP_interaction", "namespace": namespace, "index": index,
        "initial_pages": initial_pages, "rounds": rounds, "question": question,
        "truth_static": {
            "initial_images": 10, "total_images": total_images,
            "settled_frame": 3, "k_outcome": "failed_no_result",
        },
        "int_keys": ["initial_images", "total_images", "settled_frame"],
        "str_keys": ["k_outcome"],
    }


def build_gd_fixture(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Diagnostic: the refuted dense 4px exact-localization profile, retained so
    later checkpoints report progress against the same bar.  Blocks nothing."""
    rng = _rng(namespace, "GD_dense_4px_exact", index, base_seed)
    frames, event_frame = _storyboard_with_event(rng, 28, 4)
    target = None
    for r in range(64):
        for c in range(64):
            if frames[event_frame][r, c] != 0 and all(
                frames[i][r, c] == 0 for i in range(len(frames)) if i != event_frame
            ):
                target = (r, c)
    require(target is not None, "GD fixture lost its unique event cell")
    question = (
        "The storyboard shows 28 indexed frames of one 64x64 board. Rows and "
        "columns are 0-indexed from the top-left, so each runs 0-63; the frame "
        "index is the frame's printed label. Exactly one frame contains a "
        "single one-cell event. Think first. Then answer with ONLY a JSON object: "
        '{"event_frame": <int>, "event_row": <int>, "event_col": <int>}'
    )
    return {
        "claim": "GD_dense_4px_exact", "namespace": namespace, "index": index,
        "pages": [("storyboard_4px", sr.storyboard(list(frames), cols=7, cell_px=4))],
        "question": question,
        "truth_static": {"event_frame": event_frame,
                         "event_row": target[0], "event_col": target[1]},
        "int_keys": ["event_frame", "event_row", "event_col"],
    }


FIXTURE_BUILDERS: dict[str, Callable[[str, int, int], dict[str, Any]]] = {
    "GT_text_exact": build_gt_fixture,
    "GV_raw_readout": build_gv_fixture,
    "GO_overlay_readout": build_go_fixture,
    "GP_interaction": build_gp_fixture,
    GX_CLAIM: build_gx_fixture,
    "GD_dense_4px_exact": build_gd_fixture,
}


def _reload_plate(path: Path, source: sr.Plate) -> sr.Plate:
    """Reload emitted PNG bytes while retaining non-truth renderer metadata."""
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert("RGB").copy()
    return sr.Plate(
        image=image, kind=source.kind, cell_px=source.cell_px,
        pad=source.pad, bbox=source.bbox, meta=dict(source.meta),
    )


def _materialize_fixture(
    claim: str, fixture: dict[str, Any], directory: Path, tag: str,
    *, namespace: str, base_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Emit every plate, reload final PNG bytes, verify truth, and describe it.

    The returned descriptor is path-independent: the sealed fixture and the
    regenerated one-shot run must have the same metadata and PNG byte hashes.
    """
    emitted: list[dict[str, Any]] = []

    def _emit(pages: Sequence[tuple[str, sr.Plate]], group: str
              ) -> list[tuple[str, sr.Plate]]:
        final: list[tuple[str, sr.Plate]] = []
        for page_index, (name, plate) in enumerate(pages):
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
            path = directory / f"{tag}_{group}_{page_index + 1:02d}_{safe}.png"
            plate.save(path)
            reloaded = _reload_plate(path, plate)
            emitted.append({
                "logical_name": f"{group}/{page_index + 1:02d}/{name}",
                "sha256": sha256_file(path),
                "size": [reloaded.image.width, reloaded.image.height],
                "kind": plate.kind,
                "cell_px": plate.cell_px,
                "pad": list(plate.pad),
                "bbox": list(plate.bbox) if plate.bbox is not None else None,
                "meta": plate.meta,
                "path": str(path),
            })
            final.append((name, reloaded))
        return final

    final_fixture = dict(fixture)
    if "pages" in fixture:
        final_fixture["pages"] = _emit(fixture["pages"], "pages")
    if "initial_pages" in fixture:
        final_fixture["initial_pages"] = _emit(fixture["initial_pages"], "initial")
    if "rounds" in fixture:
        rounds = []
        for round_index, round_entry in enumerate(fixture["rounds"], start=1):
            rounds.append({
                **round_entry,
                "pages": _emit(round_entry["pages"], f"round{round_index}"),
            })
        final_fixture["rounds"] = rounds

    verify_fixture_decode(claim, final_fixture)
    metadata = {
        key: value for key, value in final_fixture.items()
        if key not in {"pages", "initial_pages", "rounds"}
    }
    if "pages" in final_fixture:
        metadata["page_names"] = [name for name, _plate in final_fixture["pages"]]
    if "initial_pages" in final_fixture:
        metadata["initial_page_names"] = [
            name for name, _plate in final_fixture["initial_pages"]
        ]
    if "rounds" in final_fixture:
        metadata["rounds"] = [
            {
                "label": entry["label"], "text": entry["text"],
                "page_names": [name for name, _plate in entry["pages"]],
            }
            for entry in final_fixture["rounds"]
        ]
    portable_assets = [
        {key: value for key, value in asset.items() if key != "path"}
        for asset in emitted
    ]
    body = {
        "claim": claim,
        "namespace": namespace,
        "index": fixture["index"],
        "base_seed": base_seed,
        "fixture_seed": fixture_seed(namespace, claim, fixture["index"], base_seed),
        "metadata": metadata,
        "assets": portable_assets,
    }
    descriptor = {**body, "descriptor_sha256": canonical_sha256(body)}
    descriptor["asset_paths"] = [asset["path"] for asset in emitted]
    return final_fixture, descriptor


def _portable_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    portable = {key: value for key, value in descriptor.items()
                if key != "asset_paths"}
    return json.loads(json.dumps(portable, sort_keys=True))


def _descriptor_paths(descriptor: dict[str, Any], group: str) -> list[Path]:
    pairs = zip(descriptor["assets"], descriptor.get("asset_paths", ()))
    return [Path(path) for asset, path in pairs
            if asset["logical_name"].startswith(group + "/")]


def _decode_storyboard(plate: sr.Plate) -> list[np.ndarray]:
    """Decode every board thumbnail from final storyboard pixels."""
    rgb = np.asarray(plate.image)
    frames = int(plate.meta["frames"])
    cols = int(plate.meta["cols"])
    gap, label_h = 8, 16
    thumb = 64 * plate.cell_px
    lookup = {colour: value for value, colour in sr.ARC_COLOR_MAP.items()}
    decoded: list[np.ndarray] = []
    for frame_index in range(frames):
        panel_r, panel_c = divmod(frame_index, cols)
        y0 = gap + panel_r * (thumb + label_h + gap)
        x0 = gap + panel_c * (thumb + gap)
        cells = rgb[
            y0 : y0 + thumb : plate.cell_px,
            x0 : x0 + thumb : plate.cell_px,
        ]
        require(cells.shape[:2] == (64, 64),
                "storyboard final PNG has an invalid thumbnail geometry")
        board = np.zeros((64, 64), dtype=np.uint8)
        for r in range(64):
            for c in range(64):
                colour = tuple(int(v) for v in cells[r, c])
                require(colour in lookup,
                        "storyboard final PNG contains a non-palette board pixel")
                board[r, c] = lookup[colour]
        decoded.append(board)
    return decoded


def _decode_diff_mask(plate: sr.Plate) -> np.ndarray:
    rgb = np.asarray(plate.image)
    cells = rgb[::plate.cell_px, ::plate.cell_px][:64, :64]
    white = np.all(cells == 255, axis=2)
    black = np.all(cells == 0, axis=2)
    require(np.all(white | black), "final diff-mask PNG contains non-binary cells")
    return white


def verify_fixture_decode(claim: str, fixture: dict[str, Any]) -> None:
    """Independently re-decode produced plates; truth must match construction.

    GX and GT verify inside their builders (ruler decode / RLE decode).  The
    page claims verify here: rendered pixels, not renderer intent, carry truth.
    """
    if claim == GX_CLAIM:
        by_name = {name: plate for name, plate in fixture["pages"]}
        precision = by_name["precision_ruler_target"]
        decoded = sr.decode_ruler_view(precision)
        r0, c0, _r1, _c1 = precision.bbox
        truth = fixture["truth"]
        target_colour = fixture["nuisance"]["target_colour"]
        hits = np.argwhere(decoded == target_colour)
        require(hits.shape == (1, 2),
                "GX final PNG does not contain exactly one target cell")
        recovered = (int(hits[0][0]) + r0, int(hits[0][1]) + c0)
        require(recovered == (truth["target_row"], truth["target_col"]),
                "GX final PNG truth does not match generated coordinate")
        origin_y, origin_x = precision.meta.get(
            "origin_px", [sr.RULER_GUTTER_PX, sr.RULER_GUTTER_PX]
        )
        y0 = int(origin_y) + int(hits[0][0]) * precision.cell_px
        x0 = int(origin_x) + int(hits[0][1]) * precision.cell_px
        require([y0, x0] == fixture["target_pixel_origin"],
                "GX stored target pixel origin does not match final PNG geometry")
        for grid in PATCH_PHASE_GRIDS:
            require([y0 % grid, x0 % grid] == fixture["patch_phases"][f"mod{grid}"],
                    f"GX mod{grid} phase does not match final PNG target bbox")
    elif claim == "GV_raw_readout":
        by_name = {name: plate for name, plate in fixture["pages"]}
        pre = sr.decode_board(by_name["causal_pre_4px"])
        post = sr.decode_board(by_name["causal_post_4px"])
        changed = np.argwhere(pre != post)
        require(changed.size > 0, "GV fixture pre/post decode shows no change")
        require(np.array_equal(_decode_diff_mask(by_name["diff_mask"]), pre != post),
                "GV final diff-mask PNG is not aligned with final pre/post PNGs")
        added = all(pre[r, c] == 0 for r, c in changed)
        require(added == (fixture["truth_static"]["change_kind"] == "added"),
                "GV fixture change-kind truth does not match decoded plates")
        green = sr.decode_board(by_name["green_board"])
        colours = set(int(v) for v in np.unique(green)) - {0}
        require(colours == {3}, "GV green-board fixture decode mismatch")
        story = _decode_storyboard(by_name["storyboard_4px"])
        candidates = []
        for frame_index, board in enumerate(story):
            other_colours = set(int(v) for i, other in enumerate(story)
                                if i != frame_index for v in np.unique(other))
            for colour in set(int(v) for v in np.unique(board)) - other_colours - {0}:
                if int(np.count_nonzero(board == colour)) == 1:
                    candidates.append(frame_index)
        require(candidates == [fixture["truth_static"]["event_frame"]],
                "GV event-frame truth is not recoverable from final storyboard PNG")
    elif claim == "GO_overlay_readout":
        by_name = {name: plate for name, plate in fixture["pages"]}
        raw = sr.decode_board(by_name["raw"])
        marked_meta = by_name["marked"].meta
        r, c = marked_meta["click"]
        require(int(raw[r, c]) == fixture["truth_static"]["ringed_cell_colour"],
                "GO ringed-cell truth does not match decoded raw plate")
        marker_rgb = np.asarray(by_name["marked"].image)
        raw_rgb = np.asarray(by_name["raw"].image)
        require(np.any(np.all(marker_rgb == sr.MARKER_RGB, axis=2))
                and not np.any(np.all(raw_rgb == sr.MARKER_RGB, axis=2)),
                "GO final marked/raw PNGs do not preserve annotation separation")
        comp = sr.decode_board(by_name["component_board"])
        colours = set(int(v) for v in np.unique(comp)) - set(
            int(v) for v in np.unique(raw))
        require(colours == {fixture["truth_static"]["component_colour"]},
                "GO component colour does not match decoded component plate")
        trans_pre = sr.decode_board(by_name["transition_pre"])
        trans_post = sr.decode_board(by_name["transition_post"])
        require(np.array_equal(
            _decode_diff_mask(by_name["transition_diff"]),
            trans_pre != trans_post,
        ), "GO final transition diff is not aligned with final pre/post PNGs")
    elif claim == "GP_interaction":
        first_round = fixture["rounds"][0]
        story_by_name = {name: plate for name, plate in first_round["pages"]}
        story = _decode_storyboard(story_by_name[
            next(name for name in story_by_name if name.endswith("_result_storyboard"))
        ])
        last_round = fixture["rounds"][-1]
        _name, plate = last_round["pages"][0]
        require(plate.meta.get("profile") == sr.RULER_FRAME_PROFILE,
                "GP settled retrieval is not the certified ruler frame")
        settled = sr.decode_ruler_view(plate)  # must decode exactly (raises otherwise)
        require(np.array_equal(story[-1], settled),
                "GP settled-frame truth disagrees across final storyboard/ruler PNGs")
        raw_settled = sr.decode_board(last_round["pages"][1][1])
        require(np.array_equal(raw_settled, settled),
                "GP final raw/ruler settled-result PNGs disagree")


# ------------------------------------------------------------ permutation logic


def counter_permutations(n_pages: int, seed: int) -> list[list[int]]:
    """Two permutations; the second moves EVERY position of the first."""
    rng = np.random.default_rng(seed)
    first = list(rng.permutation(n_pages))
    for _ in range(64):
        second = list(rng.permutation(n_pages))
        if all(a != b for a, b in zip(first, second)):
            return [[int(v) for v in first], [int(v) for v in second]]
    raise RuntimeError("could not derive a full counter-permutation")


def permuted_truth(fixture: dict[str, Any], permutation: list[int]) -> dict[str, Any]:
    """Static truths plus page-number truths recomputed under the permutation."""
    truth = dict(fixture.get("truth_static") or fixture.get("truth") or {})
    for key, original_index in (fixture.get("queried_pages") or {}).items():
        truth[key] = permutation.index(original_index) + 1
    return truth


# ------------------------------------------------------------------ evaluation


def score_call(payload: dict[str, Any] | None, truth: dict[str, Any],
               int_keys: Sequence[str]) -> dict[str, Any]:
    """Mechanical exact scoring; a missing/invalid payload is a failed call.
    No retry, no majority vote, no ±1 conversion."""
    checks: dict[str, bool] = {}
    if payload is None:
        return {"pass": False, "checks": {}, "reason": "no schema-valid payload"}
    for key, expected in truth.items():
        value = payload.get(key)
        if key in int_keys and type(value) is not int:
            checks[key] = False
        else:
            checks[key] = value == expected
    ok = all(checks.values()) and bool(checks)
    return {"pass": ok, "checks": checks}


def score_completed_call(payload: dict[str, Any] | None, truth: dict[str, Any],
                         int_keys: Sequence[str], record: dict[str, Any]
                         ) -> dict[str, Any]:
    score = score_call(payload, truth, int_keys)
    score["completion_complete"] = record.get("completeness") == "complete"
    score["pass"] = score["pass"] and score["completion_complete"]
    return score


def validate_claim_result(
    claim: str, result: dict[str, Any], *, namespace: str, base_seed: int,
) -> dict[str, Any]:
    """Re-derive one native claim verdict; never trust its summary booleans."""
    import e2_probe_vlm as probe

    errors: list[str] = []
    if not isinstance(result, dict):
        return {"pass": False, "errors": ["claim result is not an object"]}
    if result.get("claim") != claim:
        errors.append("claim name mismatch")
    if claim == "G0_protocol_serving":
        if result.get("kind") != "mechanical":
            errors.append("G0 kind is not mechanical")
        checks = result.get("checks") or {}
        required_checks = (
            "sampler_agreement", "template_opens_think", "no_prefilled_think",
            "template_preserves_thinking", "allowlist_excludes_source",
            "frozen_serving_match",
        )
        missing_checks = [key for key in required_checks if key not in checks]
        if missing_checks:
            errors.append(f"G0 missing checks: {missing_checks}")
        blind = checks.get("packet_source_blind") or {}
        if set(blind) != {"s4_packet", "s4_probes"}:
            errors.append("G0 source-blind inventory is malformed")
        recomputed = (
            not missing_checks
            and all(checks.get(key) is True for key in required_checks)
            and set(blind) == {"s4_packet", "s4_probes"}
            and all(blind.values())
        )
        if result.get("pass") is not recomputed:
            errors.append("G0 summary pass does not match mechanical checks")
        return {"pass": not errors and recomputed, "errors": errors,
                "failure_reasons": [] if recomputed else ["mechanical check failed"]}

    if result.get("namespace") != namespace or result.get("base_seed") != base_seed:
        errors.append("namespace/base-seed mismatch")
    expected_kind = "model_diagnostic" if claim in DIAGNOSTIC_CLAIMS else "model"
    if result.get("kind") != expected_kind:
        errors.append("claim kind mismatch")
    calls = result.get("calls")
    if not isinstance(calls, list):
        return {"pass": False, "errors": errors + ["calls is not a list"]}
    expected_calls = (GX_TOTAL_CALLS if claim == GX_CLAIM
                      else 2 if claim in DIAGNOSTIC_CLAIMS
                      else MODEL_CLAIM_REQUIRED_PASSES)
    if len(calls) != expected_calls:
        errors.append(f"call inventory is {len(calls)}, expected {expected_calls}")
    if len({call.get("tag") for call in calls}) != len(calls):
        errors.append("call tags are not unique")

    passed = 0
    keys_seen: set[tuple[int, int]] = set()
    for call in calls:
        if not isinstance(call, dict):
            errors.append("call record is not an object")
            continue
        fixture_index = call.get("fixture_index")
        permutation_index = call.get("permutation_index", 0)
        if type(fixture_index) is not int or type(permutation_index) is not int:
            errors.append("call lacks strict integer fixture/permutation index")
            continue
        key = (fixture_index, permutation_index)
        if key in keys_seen:
            errors.append(f"duplicate fixture/permutation {key}")
        keys_seen.add(key)
        truth, payload = call.get("truth"), call.get("payload")
        if not isinstance(truth, dict):
            errors.append(f"{key}: truth is malformed")
            continue
        int_keys = [name for name, value in truth.items() if type(value) is int]
        recomputed = score_call(payload, truth, int_keys)
        call_pass = recomputed["pass"]

        round_records = call.get("rounds") if claim == "GP_interaction" else [
            {"record": call.get("round"), "seed": call.get("seed")}
        ]
        if claim == "GP_interaction":
            checks = (call.get("score") or {}).get("interaction_checks") or {}
            required_checks = {
                "four_generation_calls", "exact_image_growth",
                "assistant_user_interleaving", "intermediate_complete",
                "final_complete",
            }
            if set(checks) != required_checks or not all(checks.values()):
                call_pass = False
                if set(checks) != required_checks:
                    errors.append(f"{key}: GP chronology check inventory is malformed")
            if not isinstance(round_records, list) or len(round_records) != 4:
                call_pass = False
                errors.append(f"{key}: GP does not contain four generation records")
                round_records = []
        for round_position, round_entry in enumerate(round_records):
            record = (round_entry or {}).get("record")
            if not isinstance(record, dict):
                call_pass = False
                errors.append(f"{key}: missing generation record")
                continue
            if record.get("sampler") != probe.PRODUCTION_SAMPLER:
                call_pass = False
                errors.append(f"{key}: sampler drift")
            if record.get("reasoning_effort") != probe.REASONING_EFFORT:
                call_pass = False
                errors.append(f"{key}: reasoning-effort drift")
            if record.get("seed") != round_entry.get("seed"):
                call_pass = False
                errors.append(f"{key}: generation seed binding mismatch")
            if claim == "GP_interaction":
                expected_seed = fixture_seed(
                    namespace,
                    f"{claim}:{permutation_index}:r{round_position}",
                    fixture_index,
                    base_seed,
                ) % 2**64
            elif claim == GX_CLAIM:
                suite = call.get("suite")
                expected_seed = fixture_seed(
                    namespace, f"{claim}:{suite}:{permutation_index}",
                    fixture_index, base_seed,
                ) % 2**64
            else:
                expected_seed = fixture_seed(
                    namespace, f"{claim}:{permutation_index}", fixture_index,
                    base_seed,
                ) % 2**64
            if record.get("seed") != expected_seed:
                call_pass = False
                errors.append(f"{key}: generation seed differs from frozen derivation")
            if record.get("completeness") != "complete":
                call_pass = False
        if bool((call.get("score") or {}).get("pass")) != call_pass:
            errors.append(f"{key}: stored score differs from mechanical score")
        passed += bool(call_pass)

    claim_extra_pass = True
    if claim == GX_CLAIM:
        expected_keys = {
            (fixture_index, permutation_index)
            for fixture_index in range(GX_STABILITY_FIXTURES)
            for permutation_index in range(MODEL_CLAIM_PERMUTATIONS)
        } | {
            (fixture_index, 0)
            for fixture_index in range(GX_STABILITY_FIXTURES, GX_TOTAL_FIXTURES)
        }
        coverage = result.get("patch_phase_coverage") or {}
        claim_extra_pass = coverage.get("pass") is True
        if not isinstance(coverage.get("phase_coverage_pass"), bool) \
                or not isinstance(coverage.get("nuisance_coverage_pass"), bool):
            errors.append("GX phase/nuisance coverage record is malformed")
        stability_calls = [call for call in calls if call.get("suite") == "stability"]
        coordinate_calls = [call for call in calls if call.get("suite") == "coordinate"]
        if len(stability_calls) != GX_STABILITY_CALLS:
            errors.append("GX stability call inventory mismatch")
        if len(coordinate_calls) != GX_COORDINATE_FIXTURES:
            errors.append("GX coordinate call inventory mismatch")
        for call in calls:
            fixture_index = call.get("fixture_index")
            expected_suite = (
                "stability" if type(fixture_index) is int
                and fixture_index < GX_STABILITY_FIXTURES else "coordinate"
            )
            if call.get("suite") != expected_suite:
                errors.append(f"GX fixture {fixture_index}: wrong suite binding")
        for call in coordinate_calls:
            if (call.get("permutation_index") != 0
                    or call.get("permutation")
                    != list(range(PRODUCTION_CONTEXT_PAGES))):
                errors.append("GX coordinate holdout was reordered or duplicated")
        stored_stability_passes = sum(
            bool((call.get("score") or {}).get("pass")) for call in stability_calls
        )
        stored_coordinate_passes = sum(
            bool((call.get("score") or {}).get("pass")) for call in coordinate_calls
        )
        if (result.get("stability_passes") != stored_stability_passes
                or result.get("stability_required") != GX_STABILITY_CALLS):
            errors.append("GX stability summary mismatch")
        if (result.get("coordinate_exact") != stored_coordinate_passes
                or result.get("coordinate_required") != GX_COORDINATE_FIXTURES):
            errors.append("GX coordinate summary mismatch")
        for fixture_index in range(GX_STABILITY_FIXTURES):
            by_perm = {
                call.get("permutation_index"): call.get("permutation")
                for call in stability_calls
                if call.get("fixture_index") == fixture_index
            }
            first, second = by_perm.get(0), by_perm.get(1)
            if (not isinstance(first, list) or not isinstance(second, list)
                    or sorted(first) != list(range(PRODUCTION_CONTEXT_PAGES))
                    or sorted(second) != list(range(PRODUCTION_CONTEXT_PAGES))
                    or not all(a != b for a, b in zip(first, second))):
                errors.append(
                    f"GX fixture {fixture_index}: invalid stability permutations"
                )
    elif claim in DIAGNOSTIC_CLAIMS:
        expected_keys = {(0, 0), (0, 1)}
        if result.get("blocking") is not False:
            errors.append("GD diagnostic is not explicitly non-blocking")
    else:
        expected_keys = {
            (fixture_index, permutation_index)
            for fixture_index in range(MODEL_CLAIM_FIXTURES)
            for permutation_index in range(MODEL_CLAIM_PERMUTATIONS)
        }
        for fixture_index in range(MODEL_CLAIM_FIXTURES):
            by_permutation = {
                call.get("permutation_index"): call.get("permutation")
                for call in calls if call.get("fixture_index") == fixture_index
            }
            first, second = by_permutation.get(0), by_permutation.get(1)
            if (not isinstance(first, list) or not isinstance(second, list)
                    or len(first) != len(second) or not first
                    or sorted(first) != list(range(len(first)))
                    or sorted(second) != list(range(len(second)))
                    or not all(a != b for a, b in zip(first, second))):
                errors.append(
                    f"fixture {fixture_index}: counter-permutations are not full derangements"
                )
    if keys_seen != expected_keys:
        errors.append("fixture/permutation inventory mismatch")
    if result.get("passes") != passed or result.get("required") != expected_calls:
        errors.append("summary counts differ from re-derived counts")
    expected_pass = passed == expected_calls and claim_extra_pass
    if result.get("pass") is not expected_pass:
        errors.append("summary verdict differs from re-derived verdict")
    return {"pass": not errors and expected_pass, "errors": errors,
            "failure_reasons": [] if expected_pass else ["claim threshold not met"],
            "passes": passed, "required": expected_calls}


def derive_arm_eligibility(
    claim_results: dict[str, dict[str, Any]], selected_arms: Sequence[str],
    *, strict: bool = True, namespace: str = "confirm", base_seed: int = 4,
) -> dict[str, Any]:
    """Mechanical: an arm is eligible iff every claim in its requirement set
    passed.  GD never appears in any requirement set."""
    arms: dict[str, Any] = {}
    for arm in selected_arms:
        require(arm in ARM_REQUIREMENTS, f"unknown arm {arm!r}")
        validations = {
            claim: (validate_claim_result(
                claim, claim_results.get(claim) or {}, namespace=namespace,
                base_seed=base_seed,
            ) if strict else {"pass": bool(
                (claim_results.get(claim) or {}).get("pass")
            ), "errors": []})
            for claim in ARM_REQUIREMENTS[arm]
        }
        blocking = [claim for claim, validation in validations.items()
                    if not validation["pass"]]
        arms[arm] = {"eligible": not blocking, "blocking_claims": blocking,
                     "requirement_set": list(ARM_REQUIREMENTS[arm]),
                     "claim_validations": validations}
    all_eligible = all(entry["eligible"] for entry in arms.values())
    return {
        "arms": arms,
        "all_selected_arms_eligible": all_eligible,
        "matrix_rule": (
            "if any selected arm is ineligible the runner refuses the ENTIRE "
            "declared matrix; silent fallback would change the experiment"
        ),
    }


# --------------------------------------------------------------- G0 mechanical


def g0_protocol_serving(
    model_path: Path, frozen_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mechanical serving/protocol claim — no model generation.

    Verifies runtime identity, checkpoint serving files, sampler/effort/budget
    constants agreement across modules, chat-template thinking invariants on a
    fixture conversation, and packet-builder source blindness.
    """
    import e2_probe_vlm as probe
    import s4_packet as spk
    import s4_run as srun

    checks: dict[str, Any] = {}
    auditor = spk.ProcessorAuditor(model_path)
    checks["processor_identity"] = auditor.identity["measurement_identity_sha256"]
    import importlib.metadata as md
    runtime_versions = {
        package: md.version(package)
        for package in ("mlx-vlm", "mlx", "mlx-lm", "transformers")
    }
    checks["runtime_versions"] = runtime_versions
    checks["sampler_agreement"] = (
        probe.PRODUCTION_SAMPLER == srun.probe.PRODUCTION_SAMPLER
    )
    checks["effort"] = probe.REASONING_EFFORT
    checks["budget_agreement"] = {
        "answer_tokens": srun.MAX_ANSWER_TOKENS,
        "max_images": srun.MAX_IMAGES,
        "max_visual_tokens": srun.MAX_VISUAL_TOKENS,
        "max_context_text_tokens": srun.MAX_CONTEXT_TEXT_TOKENS,
        "native_context_tokens": srun.NATIVE_CONTEXT_TOKENS,
        "interaction_rounds": srun.INTERACTION_ROUNDS,
    }
    checks["precision_profile"] = PRECISION_PROFILE
    # Template invariants on a fixture conversation (tokenizer-level, no weights).
    rendered = auditor.tokenizer.apply_chat_template(
        [{"role": "user", "content": "fixture"}],
        tokenize=False, add_generation_prompt=True,
        enable_thinking=True, reasoning_effort=probe.REASONING_EFFORT,
        preserve_thinking=probe.PRESERVE_THINKING,
    )
    checks["template_opens_think"] = rendered.rstrip().endswith("<think>")
    import re
    marker = rendered.rfind("<|im_start|>assistant")
    checks["no_prefilled_think"] = (
        marker != -1 and not re.search(r"<think>\s*</think>", rendered[marker:])
    )
    history_rendered = auditor.tokenizer.apply_chat_template(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer",
             "reasoning_content": "retained reasoning"},
            {"role": "user", "content": "second"},
        ],
        tokenize=False, add_generation_prompt=True,
        enable_thinking=True, reasoning_effort=probe.REASONING_EFFORT,
        preserve_thinking=probe.PRESERVE_THINKING,
    )
    checks["template_preserves_thinking"] = (
        "<think>\nretained reasoning\n</think>" in history_rendered
        and "<think>\n\n</think>" not in history_rendered
    )
    # Source blindness: the packet/probe builders must not reference source or
    # human-material roots, and their allowlists must exclude them.
    forbidden = ("environment_files", "human_replays", "e1_completions", "sealed/gold")
    blind = {}
    for module_name in ("s4_packet", "s4_probes"):
        text = (HARNESS / f"{module_name}.py").read_text()
        blind[module_name] = not any(token in text for token in forbidden)
    checks["packet_source_blind"] = blind
    allowed = tuple(str(p) for p in spk.ALLOWED_ROOTS)
    checks["allowlist_excludes_source"] = not any(
        any(token in root for token in forbidden) for root in allowed
    )
    if frozen_snapshot is None:
        checks["frozen_serving_match"] = None
    else:
        import hashlib as _hashlib

        checkpoint = probe.fingerprint(model_path).get("checkpoint_sha256")
        frozen_checkpoint = (
            frozen_snapshot.get("checkpoint_fingerprint") or {}
        ).get("checkpoint_sha256")
        current_request_sha = _hashlib.sha256(srun.REQUEST.encode()).hexdigest()
        serving_checks = {
            "model_path": Path(frozen_snapshot.get("model_path", "")).resolve()
                          == model_path.resolve(),
            "processor_identity": frozen_snapshot.get("processor_identity")
                                  == auditor.identity,
            "runtime_versions": frozen_snapshot.get("runtime_versions")
                                == runtime_versions,
            "production_sampler": frozen_snapshot.get("production_sampler")
                                  == probe.PRODUCTION_SAMPLER,
            "reasoning_effort": frozen_snapshot.get("reasoning_effort")
                                == probe.REASONING_EFFORT,
            "preserve_thinking": frozen_snapshot.get("preserve_thinking")
                                 is probe.PRESERVE_THINKING,
            "budgets": frozen_snapshot.get("budgets") == {
                "answer_tokens": srun.MAX_ANSWER_TOKENS,
                "interaction_rounds": srun.INTERACTION_ROUNDS,
                "retrievals_per_round": srun.RETRIEVALS_PER_ROUND,
                "active_probes": srun.ACTIVE_PROBES,
                "max_images": srun.MAX_IMAGES,
                "max_visual_tokens": srun.MAX_VISUAL_TOKENS,
                "max_context_text_tokens": srun.MAX_CONTEXT_TEXT_TOKENS,
                "native_context_tokens": srun.NATIVE_CONTEXT_TOKENS,
            },
            "request_prompt_sha256": frozen_snapshot.get("request_prompt_sha256")
                                     == current_request_sha,
            "checkpoint_sha256": frozen_checkpoint is not None
                                 and checkpoint == frozen_checkpoint,
        }
        checks["frozen_serving_checks"] = serving_checks
        checks["frozen_serving_match"] = all(serving_checks.values())
    mechanical_pass = all([
        checks["sampler_agreement"], checks["template_opens_think"],
        checks["no_prefilled_think"], checks["template_preserves_thinking"],
        all(blind.values()),
        checks["allowlist_excludes_source"],
        checks["frozen_serving_match"] is not False,
    ])
    return {
        "claim": "G0_protocol_serving", "kind": "mechanical",
        "pass": mechanical_pass, "checks": checks,
        "rule": "mechanical, must pass 100%; a temp-0 model call may diagnose "
                "wiring but cannot authorize an inferential arm",
    }


# ----------------------------------------------------------------- claim runs


def _ask_gate(srun, vlm, messages, images, *, seed: int, max_tokens: int,
              run_dir: Path, tag: str, payload_validator,
              serving_identity: dict[str, Any],
              max_input_text_tokens: int | None = None,
              round_index: int = 0, round_kind: str = "gate_single"):
    """One production generation, recorded exactly once in the local ledger."""
    record, payload, answer = srun.ask_chat(
        vlm, messages, images, seed=seed, max_tokens=max_tokens,
        max_input_text_tokens=(
            srun.MAX_INITIAL_PROMPT_TEXT_TOKENS
            if max_input_text_tokens is None else max_input_text_tokens
        ),
        run_dir=run_dir, tag=tag, payload_validator=payload_validator,
        ledger_module="s4_gates", ledger_purpose="confirmatory_readability_gate",
        serving_identity=serving_identity,
        round_index=round_index, round_kind=round_kind,
    )
    trace_path = run_dir / f"{tag}.trace.json"
    require(trace_path.is_file(), f"gate serving trace was not written for {tag}")
    record = {
        **record,
        "trace": {"path": str(trace_path), "sha256": sha256_file(trace_path)},
    }
    return record, payload, answer


def run_model_claim(
    vlm, claim: str, namespace: str, base_seed: int, run_dir: Path,
    *, answer_tokens: int, serving_identity: dict[str, Any],
    sealed_claim: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Six production-sampler calls (3 fixtures x 2 counter-permutations); 6/6.

    GX runs the ordinary 3x2 stability suite plus eight fresh coordinate
    holdouts (6/6 and 8/8 exact).
    GD runs one fixture x 2 permutations, reported without blocking anything.
    """
    import s4_run as srun

    sl.enforce_offline_scientific_run(f"s4_gates:{claim}", [])
    if namespace == "confirm":
        require(sealed_claim is not None,
                f"confirm gate claim {claim} lacks its sealed fixture binding")
        _authorize_confirm_claim(
            claim=claim, base_seed=base_seed, run_dir=run_dir,
            answer_tokens=answer_tokens, serving_identity=serving_identity,
        )
    builder = FIXTURE_BUILDERS[claim]
    work = run_dir / "boards"
    work.mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, Any]] = []
    passes = 0

    def _build_final(index: int) -> tuple[dict[str, Any], dict[str, Any]]:
        fixture = builder(namespace, index, base_seed)
        safe_claim = "".join(ch if ch.isalnum() else "_" for ch in claim)
        final, descriptor = _materialize_fixture(
            claim, fixture, work, f"{safe_claim}_{namespace}_{index}",
            namespace=namespace, base_seed=base_seed,
        )
        if sealed_claim is not None:
            records = sealed_claim.get("fixture_records")
            require(isinstance(records, list) and len(records) > index,
                    f"sealed manifest lacks {claim} fixture {index}")
            require(_portable_descriptor(descriptor) == records[index],
                    f"{claim} fixture {index} differs from the sealed manifest")
        return final, descriptor

    if claim == GX_CLAIM:
        built = [_build_final(i) for i in range(GX_TOTAL_FIXTURES)]
        stability_built = built[:GX_STABILITY_FIXTURES]
        coordinate_built = built[GX_STABILITY_FIXTURES:]
        coverage = gx_phase_coverage([item[0] for item in coordinate_built])
        require(coverage["pass"],
                f"GX sealed holdouts do not cover frozen phase/nuisance strata: {coverage}")

        def _run_gx(fixture: dict[str, Any], descriptor: dict[str, Any],
                    *, suite: str, permutation_index: int,
                    permutation: list[int]) -> None:
            nonlocal passes
            tag = (f"gx_{suite}_{namespace}_{fixture['index']}_"
                   f"{permutation_index}")
            paths = _descriptor_paths(descriptor, "pages")
            require(len(paths) == PRODUCTION_CONTEXT_PAGES,
                    "GX must run in a ten-page mixed production context")
            paths = [paths[i] for i in permutation]
            items: list[dict[str, str]] = []
            for page_no in range(1, len(paths) + 1):
                items.extend((
                    {"type": "text", "text": f"Page {page_no} of {len(paths)}:"},
                    {"type": "image"},
                ))
            items.append({"type": "text", "text": fixture["question"]})
            validator = make_validator(fixture["int_keys"])
            call_seed = fixture_seed(
                namespace, f"{claim}:{suite}:{permutation_index}",
                fixture["index"], base_seed,
            ) % 2**64
            record, payload, _ = _ask_gate(
                srun, vlm, [{"role": "user", "content": items}], paths,
                seed=call_seed, max_tokens=answer_tokens, run_dir=run_dir,
                tag=tag, payload_validator=validator,
                serving_identity=serving_identity,
            )
            score = score_completed_call(
                payload, fixture["truth"], fixture["int_keys"], record
            )
            passes += bool(score["pass"])
            calls.append({"tag": tag, "fixture_index": fixture["index"],
                          "suite": suite,
                          "permutation_index": permutation_index,
                          "permutation": permutation,
                          "fixture_descriptor_sha256": descriptor["descriptor_sha256"],
                          "seed": call_seed,
                          "truth": fixture["truth"], "payload": payload,
                          "score": score, "round": record})

        for fixture, descriptor in stability_built:
            permutations = counter_permutations(
                PRODUCTION_CONTEXT_PAGES,
                fixture_seed(
                    namespace, f"{claim}:stability:perm",
                    fixture["index"], base_seed,
                ),
            )
            for permutation_index, permutation in enumerate(permutations):
                _run_gx(
                    fixture, descriptor, suite="stability",
                    permutation_index=permutation_index, permutation=permutation,
                )
        stability_passes = passes
        for fixture, descriptor in coordinate_built:
            _run_gx(
                fixture, descriptor, suite="coordinate", permutation_index=0,
                permutation=list(range(PRODUCTION_CONTEXT_PAGES)),
            )
        coordinate_exact = passes - stability_passes
        result_pass = (
            stability_passes == GX_STABILITY_CALLS
            and coordinate_exact == GX_COORDINATE_FIXTURES
            and coverage["pass"]
        )
        return {"claim": claim, "kind": "model", "namespace": namespace,
                "base_seed": base_seed,
                "profile": PRECISION_PROFILE, "calls": calls,
                "passes": passes, "required": GX_TOTAL_CALLS,
                "stability_passes": stability_passes,
                "stability_required": GX_STABILITY_CALLS,
                "coordinate_exact": coordinate_exact,
                "coordinate_required": GX_COORDINATE_FIXTURES,
                "patch_phase_coverage": coverage, "pass": result_pass}

    n_fixtures = 1 if claim in DIAGNOSTIC_CLAIMS else MODEL_CLAIM_FIXTURES
    required = (2 if claim in DIAGNOSTIC_CLAIMS
                else MODEL_CLAIM_REQUIRED_PASSES)
    for index in range(n_fixtures):
        fixture, descriptor = _build_final(index)
        if claim == "GT_text_exact":
            permutations = counter_permutations(
                len(fixture["records"]),
                fixture_seed(namespace, f"{claim}:perm", index, base_seed),
            )
            for perm_index, permutation in enumerate(permutations):
                tag = f"gt_{namespace}_{index}_{perm_index}"
                ledger = "\n\n".join(fixture["records"][i] for i in permutation)
                items = [{"type": "text",
                          "text": ledger + "\n\n" + fixture["question"]}]
                validator = make_validator(fixture["int_keys"],
                                           fixture.get("str_keys", ()))
                call_seed = fixture_seed(
                    namespace, f"{claim}:{perm_index}", index, base_seed
                ) % 2**64
                record, payload, _ = _ask_gate(
                    srun, vlm, [{"role": "user", "content": items}], [],
                    seed=call_seed, max_tokens=answer_tokens, run_dir=run_dir,
                    tag=tag, payload_validator=validator,
                    serving_identity=serving_identity,
                )
                score = score_completed_call(
                    payload, fixture["truth"], fixture["int_keys"], record
                )
                passes += bool(score["pass"])
                calls.append({"tag": tag, "fixture_index": index,
                              "permutation_index": perm_index,
                              "permutation": permutation, "seed": call_seed,
                              "fixture_descriptor_sha256": descriptor["descriptor_sha256"],
                              "score": score, "payload": payload,
                              "truth": fixture["truth"], "round": record})
            continue
        if claim == "GP_interaction":
            permutations = counter_permutations(
                len(fixture["initial_pages"]),
                fixture_seed(namespace, f"{claim}:perm", index, base_seed),
            )
            initial_all_paths = _descriptor_paths(descriptor, "initial")
            round_path_sets = [
                _descriptor_paths(descriptor, f"round{round_index}")
                for round_index in range(1, len(fixture["rounds"]) + 1)
            ]
            for perm_index, permutation in enumerate(permutations):
                tag = f"gp_{namespace}_{index}_{perm_index}"
                initial_paths = [initial_all_paths[i] for i in permutation]
                messages: list[dict[str, Any]] = []
                items: list[dict[str, str]] = []
                for page_no in range(1, len(initial_paths) + 1):
                    items.append({"type": "text", "text": f"Page {page_no} of 10:"})
                    items.append({"type": "image"})
                items.append({
                    "type": "text",
                    "text": ('Inspect this initial evidence. Do not answer the final '
                             'chronology question yet. Answer ONLY {"ack":"continue"}.'),
                })
                images = list(initial_paths)
                messages.append({"role": "user", "content": items})
                interaction_rounds: list[dict[str, Any]] = []
                ack_validator = make_validator((), ("ack",))
                seed0 = fixture_seed(
                    namespace, f"{claim}:{perm_index}:r0", index, base_seed
                ) % 2**64
                record, interim_payload, answer = _ask_gate(
                    srun, vlm, messages, images, seed=seed0,
                    max_tokens=answer_tokens, run_dir=run_dir,
                    tag=tag + "_r0", payload_validator=ack_validator,
                    serving_identity=serving_identity,
                    round_index=0, round_kind="gate_interaction_initial",
                )
                interaction_rounds.append({"round": 0, "seed": seed0,
                                           "payload": interim_payload,
                                           "record": record})
                prior_record = record
                interim_ok = (
                    interim_payload == {"ack": "continue"}
                    and record.get("completeness") == "complete"
                )
                payload = None
                final_record = None
                for round_index, round_entry in enumerate(fixture["rounds"], start=1):
                    round_items = [{"type": "text", "text": round_entry["text"]}]
                    round_paths = round_path_sets[round_index - 1]
                    for name, _plate in round_entry["pages"]:
                        round_items.append({"type": "text", "text": f"{name}:"})
                        round_items.append({"type": "image"})
                    if round_index == len(fixture["rounds"]):
                        round_items.append({"type": "text", "text": fixture["question"]})
                        validator = make_validator(
                            fixture["int_keys"], fixture.get("str_keys", ())
                        )
                    else:
                        round_items.append({
                            "type": "text",
                            "text": ('Retain this exact result. Do not answer the final '
                                     'question yet. Answer ONLY {"ack":"continue"}.'),
                        })
                        validator = ack_validator
                    prior_trace_path = Path(prior_record["trace"]["path"])
                    require(sha256_file(prior_trace_path)
                            == prior_record["trace"]["sha256"],
                            "GP prior serving trace changed before history reuse")
                    prior_trace = json.loads(prior_trace_path.read_text())
                    require(prior_trace.get("answer") == answer
                            and isinstance(prior_trace.get("think"), str),
                            "GP prior answer/reasoning differs from its trace")
                    messages.append({
                        "role": "assistant",
                        "content": answer,
                        "reasoning_content": prior_trace["think"],
                    })
                    messages.append({"role": "user", "content": round_items})
                    images.extend(round_paths)
                    round_seed = fixture_seed(
                        namespace, f"{claim}:{perm_index}:r{round_index}",
                        index, base_seed,
                    ) % 2**64
                    final_record, payload, answer = _ask_gate(
                        srun, vlm, messages, images, seed=round_seed,
                        max_tokens=answer_tokens, run_dir=run_dir,
                        tag=f"{tag}_r{round_index}", payload_validator=validator,
                        serving_identity=serving_identity,
                        max_input_text_tokens=srun.MAX_CONTEXT_TEXT_TOKENS,
                        round_index=round_index,
                        round_kind="gate_interaction_update",
                    )
                    interaction_rounds.append({
                        "round": round_index, "seed": round_seed,
                        "payload": payload, "record": final_record,
                        "cumulative_images": len(images),
                    })
                    prior_record = final_record
                    if round_index < len(fixture["rounds"]):
                        interim_ok = interim_ok and (
                            payload == {"ack": "continue"}
                            and final_record.get("completeness") == "complete"
                        )
                require(final_record is not None, "GP omitted its final interaction round")
                score = score_completed_call(
                    payload, fixture["truth_static"], fixture["int_keys"],
                    final_record,
                )
                image_growth = [10] + [entry["cumulative_images"]
                                       for entry in interaction_rounds[1:]]
                roles = [message["role"] for message in messages]
                interaction_checks = {
                    "four_generation_calls": len(interaction_rounds) == 4,
                    "exact_image_growth": image_growth == [10, 13, 13, 16],
                    "assistant_user_interleaving": roles
                        == ["user", "assistant", "user", "assistant", "user",
                            "assistant", "user"],
                    "intermediate_complete": interim_ok,
                    "final_complete": final_record.get("completeness") == "complete",
                }
                score["interaction_checks"] = interaction_checks
                score["pass"] = score["pass"] and all(interaction_checks.values())
                passes += bool(score["pass"])
                calls.append({"tag": tag, "fixture_index": index,
                              "permutation_index": perm_index,
                              "permutation": permutation,
                              "fixture_descriptor_sha256": descriptor["descriptor_sha256"],
                              "score": score, "payload": payload,
                              "truth": fixture["truth_static"],
                              "rounds": interaction_rounds})
            continue
        # page-permutation claims: GV, GO, GD
        n_pages = len(fixture["pages"])
        permutations = (
            [[0], [0]] if claim in DIAGNOSTIC_CLAIMS and n_pages == 1
            else counter_permutations(
                n_pages, fixture_seed(namespace, f"{claim}:perm", index, base_seed)
            )
        )
        all_paths = _descriptor_paths(descriptor, "pages")
        for perm_index, permutation in enumerate(permutations):
            tag = f"{claim.split('_')[0].lower()}_{namespace}_{index}_{perm_index}"
            paths = [all_paths[i] for i in permutation]
            items = []
            for page_no in range(1, len(paths) + 1):
                items.append({"type": "text", "text": f"Page {page_no} of {len(paths)}:"})
                items.append({"type": "image"})
            items.append({"type": "text", "text": fixture["question"]})
            truth = permuted_truth(fixture, permutation)
            validator = make_validator(fixture["int_keys"], fixture.get("str_keys", ()))
            call_seed = fixture_seed(
                namespace, f"{claim}:{perm_index}", index, base_seed
            ) % 2**64
            record, payload, _ = _ask_gate(
                srun, vlm, [{"role": "user", "content": items}], paths,
                seed=call_seed, max_tokens=answer_tokens, run_dir=run_dir,
                tag=tag, payload_validator=validator,
                serving_identity=serving_identity,
            )
            score = score_completed_call(payload, truth, fixture["int_keys"], record)
            passes += bool(score["pass"])
            calls.append({"tag": tag, "fixture_index": index,
                          "permutation_index": perm_index,
                          "permutation": permutation, "seed": call_seed,
                          "fixture_descriptor_sha256": descriptor["descriptor_sha256"],
                          "score": score,
                          "payload": payload, "truth": truth, "round": record})

    result = {
        "claim": claim,
        "kind": "model_diagnostic" if claim in DIAGNOSTIC_CLAIMS else "model",
        "namespace": namespace, "base_seed": base_seed,
        "calls": calls, "passes": passes,
        "required": required, "pass": passes == required,
    }
    if claim in DIAGNOSTIC_CLAIMS:
        result["blocking"] = False
        result["note"] = "reported diagnostic; consumed by no arm requirement set"
    return result


def _atomic_create_json(path: Path, payload: dict[str, Any], *, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
    except FileExistsError as exc:
        raise RuntimeError(f"{path} already exists — append-only/one-shot") from exc
    path.chmod(mode)


def _load_confirm_binding(base_seed: int) -> tuple[dict[str, Any], str,
                                                    dict[str, Any], str, str]:
    """Verify FROZEN and resolve the one exact sealed gate manifest by seed."""
    import s4_grade as grade

    frozen = grade.verify_freeze_r4()
    frozen_path = SEALED_R4 / "FROZEN.json"
    frozen_sha = sha256_file(frozen_path)
    manifests = ((frozen.get("confirm_assets") or {})
                 .get("gate_fixture_manifests") or {})
    require(isinstance(manifests, dict) and manifests,
            "FROZEN does not bind any confirm gate fixture manifest")
    matches: list[tuple[str, str, dict[str, Any]]] = []
    for relative, expected_sha in manifests.items():
        path = ROOT / relative
        require(path.is_file() and sha256_file(path) == expected_sha,
                f"sealed gate fixture manifest drift: {relative}")
        document = json.loads(path.read_text())
        if (document.get("namespace") == "confirm"
                and document.get("base_seed") == base_seed):
            matches.append((relative, expected_sha, document))
    require(len(matches) == 1,
            f"expected exactly one frozen confirm fixture manifest for seed "
            f"{base_seed}, found {len(matches)}")
    relative, manifest_sha, manifest = matches[0]
    require(manifest.get("protocol_version") == PROTOCOL_VERSION,
            "sealed gate fixture manifest has wrong protocol version")
    require(manifest.get("generator_sha256") == sha256_file(Path(__file__)),
            "sealed gate manifest was generated by different gate code")
    expected_fixture_claims = set(MODEL_CLAIMS) | set(DIAGNOSTIC_CLAIMS)
    require(set(manifest.get("claims") or {}) == expected_fixture_claims,
            "sealed confirm manifest must contain the complete claim inventory")
    return frozen, frozen_sha, manifest, relative, manifest_sha


def _confirm_reservation_errors(
    reservation: Any, *, frozen_sha: str, manifest_sha: str,
    base_seed: int, model: Path, run_dir: Path, answer_tokens: int,
    serving_identity: dict[str, Any],
) -> list[str]:
    """Validate the complete immutable authority for the one confirm run."""
    errors: list[str] = []
    if not isinstance(reservation, dict):
        return ["confirm reservation is not an object"]
    expected = {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_one_shot_reservation",
        "frozen_manifest_sha256": frozen_sha,
        "fixture_manifest_sha256": manifest_sha,
        "base_seed": base_seed,
        "model_path": str(model.expanduser().resolve()),
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
        "claims": list(ALL_CLAIMS),
    }
    for key, value in expected.items():
        if reservation.get(key) != value:
            errors.append(f"confirm reservation {key} binding mismatch")
    return errors


def _confirm_started_errors(
    started: Any, *, reservation_sha: str, base_seed: int, run_dir: Path,
    answer_tokens: int, serving_identity: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(started, dict):
        return ["confirm STARTED receipt is not an object"]
    expected = {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_run_started",
        "confirm_reservation_sha256": reservation_sha,
        "base_seed": base_seed,
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
        "claims": list(ALL_CLAIMS),
    }
    for key, value in expected.items():
        if started.get(key) != value:
            errors.append(f"confirm STARTED {key} binding mismatch")
    return errors


def _reserve_confirm_run(
    *, frozen_sha: str, manifest_sha: str, base_seed: int, model: Path,
    run_dir: Path, answer_tokens: int, serving_identity: dict[str, Any],
) -> dict[str, Any]:
    require(not CONFIRM_RESULTS.exists(),
            f"{CONFIRM_RESULTS} already exists; confirm gates cannot be rerun")
    require(run_dir.resolve() == CONFIRM_RUN_DIR.resolve(),
            f"confirm gate run directory is fixed at {CONFIRM_RUN_DIR}")
    require(not run_dir.exists(),
            f"{run_dir} already exists; confirm gate run cannot be rerun")
    reservation = {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_one_shot_reservation",
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "frozen_manifest_sha256": frozen_sha,
        "fixture_manifest_sha256": manifest_sha,
        "base_seed": base_seed,
        "model_path": str(model.expanduser().resolve()),
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
        "claims": list(ALL_CLAIMS),
        "rule": (
            "creating this reservation consumes the confirm gate attempt; an "
            "interruption or failure ends this protocol version and is never rerun"
        ),
    }
    _atomic_create_json(CONFIRM_RESERVATION, reservation)
    return reservation


def _start_confirm_run(
    *, base_seed: int, run_dir: Path, answer_tokens: int,
    serving_identity: dict[str, Any],
) -> str:
    """Create the fixed run and its immutable STARTED receipt exactly once."""
    require(run_dir.resolve() == CONFIRM_RUN_DIR.resolve(),
            f"confirm gate run directory is fixed at {CONFIRM_RUN_DIR}")
    require(CONFIRM_RESERVATION.is_file(),
            "confirm gate run has no one-shot reservation")
    reservation_sha = sha256_file(CONFIRM_RESERVATION)
    run_dir.mkdir(parents=True, exist_ok=False)
    started_path = run_dir / "STARTED.json"
    _atomic_create_json(started_path, {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_run_started",
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "confirm_reservation_sha256": reservation_sha,
        "base_seed": base_seed,
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
        "claims": list(ALL_CLAIMS),
        "rule": "this fixed confirm run is one-shot; interruption ends the protocol",
    })
    return sha256_file(started_path)


def _claim_started_path(run_dir: Path, claim: str) -> Path:
    safe_claim = "".join(ch if ch.isalnum() else "_" for ch in claim)
    return run_dir / f"CLAIM_{safe_claim}.STARTED.json"


def _claim_started_errors(
    started: Any, *, reservation_sha: str, claim: str, base_seed: int,
    run_dir: Path, answer_tokens: int, serving_identity: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(started, dict):
        return [f"confirm claim {claim} STARTED receipt is not an object"]
    expected = {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_claim_started",
        "confirm_reservation_sha256": reservation_sha,
        "claim": claim,
        "base_seed": base_seed,
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
    }
    for key, value in expected.items():
        if started.get(key) != value:
            errors.append(f"confirm claim {claim} STARTED {key} binding mismatch")
    return errors


def _authorize_confirm_claim(
    *, claim: str, base_seed: int, run_dir: Path, answer_tokens: int,
    serving_identity: dict[str, Any],
) -> None:
    """Consume one claim slot before its first confirm generation."""
    require(run_dir.resolve() == CONFIRM_RUN_DIR.resolve(),
            f"confirm gate claim escaped fixed run directory {CONFIRM_RUN_DIR}")
    require(CONFIRM_RESERVATION.is_file(),
            "confirm gate claim has no one-shot reservation")
    reservation_sha = sha256_file(CONFIRM_RESERVATION)
    reservation = json.loads(CONFIRM_RESERVATION.read_text())
    require(reservation.get("base_seed") == base_seed
            and reservation.get("run_dir") == str(run_dir.resolve())
            and reservation.get("answer_tokens") == answer_tokens
            and reservation.get("serving_identity") == serving_identity
            and reservation.get("claims") == list(ALL_CLAIMS),
            "confirm gate claim differs from its reservation")
    started_path = run_dir / "STARTED.json"
    require(started_path.is_file(), "confirm gate claim has no STARTED receipt")
    started = json.loads(started_path.read_text())
    require(not _confirm_started_errors(
        started, reservation_sha=reservation_sha, base_seed=base_seed,
        run_dir=run_dir, answer_tokens=answer_tokens,
        serving_identity=serving_identity,
    ), "confirm gate STARTED receipt differs from its reservation")
    _atomic_create_json(_claim_started_path(run_dir, claim), {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "kind": "confirm_gate_claim_started",
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "confirm_reservation_sha256": reservation_sha,
        "claim": claim,
        "base_seed": base_seed,
        "run_dir": str(run_dir.resolve()),
        "answer_tokens": answer_tokens,
        "serving_identity": serving_identity,
        "rule": "a confirm claim is never regenerated or overwritten",
    })


def _sealed_descriptor_body(descriptor: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in descriptor.items()
            if key != "descriptor_sha256"}


def _sealed_assets(descriptor: dict[str, Any], group: str) -> list[dict[str, Any]]:
    assets = descriptor.get("assets") or []
    return [asset for asset in assets
            if isinstance(asset, dict)
            and str(asset.get("logical_name", "")).startswith(group + "/")]


def _decode_trace_completion(trace_doc: dict[str, Any]) -> tuple[
        str, str, dict[str, Any] | None, bool]:
    """Reparse immutable raw output; never trust a stored parsed payload."""
    import s4_run as srun

    raw = trace_doc.get("raw")
    require(isinstance(raw, str), "gate trace raw completion is not text")
    full = "<think>" + raw
    closed = "</think>" in full
    think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
    answer = full.split("</think>", 1)[-1].strip() if closed else ""
    parsed = srun.extract_final_json(answer) if closed else None
    return think, answer, parsed, closed


def _validate_gate_trace(
    *, record: dict[str, Any], expected_tag: str, expected_seed: int,
    expected_messages: list[dict[str, Any]], expected_assets: list[dict[str, Any]],
    expected_payload: dict[str, Any] | None, int_keys: Sequence[str],
    str_keys: Sequence[str], run_dir: Path, answer_tokens: int,
    input_text_cap: int, expected_serving_identity: dict[str, Any],
    expected_round_index: int, expected_round_kind: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Bind one claim round to the exact prompt/images/raw serving trace."""
    import e2_probe_vlm as probe

    errors: list[str] = []
    if not isinstance(record, dict):
        return None, ["generation record is not an object"]
    binding = record.get("trace") or {}
    trace_path = Path(str(binding.get("path", "")))
    expected_path = run_dir / f"{expected_tag}.trace.json"
    if (trace_path.resolve() != expected_path.resolve() or not trace_path.is_file()
            or sha256_file(trace_path) != binding.get("sha256")):
        return None, ["serving trace path/hash is stale or outside the claim run"]
    try:
        trace_doc = json.loads(trace_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, ["serving trace is unreadable"]
    try:
        think, answer, parsed, closed = _decode_trace_completion(trace_doc)
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return None, [f"raw completion cannot be reparsed: {exc}"]

    validator = make_validator(int_keys, str_keys)
    schema_errors = validator(parsed) if parsed is not None else []
    reparsed_payload = parsed if parsed is not None and not schema_errors else None
    if expected_payload != reparsed_payload:
        errors.append("stored payload differs from reparsed raw completion")
    if (trace_doc.get("think") != think or trace_doc.get("answer") != answer
            or trace_doc.get("parsed_payload") != parsed):
        errors.append("trace think/answer/parsed fields differ from raw completion")

    if trace_doc.get("messages") != expected_messages:
        errors.append("trace messages differ from sealed fixture chronology")
    if record.get("messages") != expected_messages:
        errors.append("round record messages differ from sealed fixture chronology")
    messages_sha = hashlib.sha256(
        json.dumps(expected_messages, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if trace_doc.get("messages_sha256") != messages_sha:
        errors.append("trace messages digest differs from the served chronology")
    if (record.get("trace_path") != str(trace_path.resolve())
            or record.get("trace_sha256") != binding.get("sha256")):
        errors.append("round trace receipt differs from its nested trace binding")
    images = trace_doc.get("images")
    if not isinstance(images, list) or len(images) != len(expected_assets):
        errors.append("trace image inventory differs from sealed fixture assets")
        images = []
    for index, (image, asset) in enumerate(zip(images, expected_assets)):
        path = Path(str((image or {}).get("path", "")))
        if (not path.is_file() or run_dir.resolve() not in path.resolve().parents
                or sha256_file(path) != asset.get("sha256")
                or image.get("sha256") != asset.get("sha256")
                or image.get("source_size") != asset.get("size")
                or image.get("processed_size") != asset.get("size")):
            errors.append(f"trace image[{index}] differs from its sealed asset")

    exact_metadata = (
        "tag", "seed", "sampler", "reasoning_effort", "preserve_thinking",
        "serving_identity", "native_context_tokens", "round_index", "round_kind",
        "trace_tag", "max_tokens", "messages", "messages_sha256", "prompt_sha256",
        "images", "image_grid_thw",
        "visual_tokens", "expanded_prompt_tokens", "derived_text_tokens",
        "input_text_token_cap", "generator_prompt_tokens", "prompt_tokens_match",
        "token_accounting_match", "completion_contains_close", "payload_present",
        "schema_errors", "completeness", "stats",
    )
    for key in exact_metadata:
        if record.get(key) != trace_doc.get(key):
            errors.append(f"round metadata {key} differs from its trace")
    if (trace_doc.get("tag") != expected_tag
            or trace_doc.get("seed") != expected_seed
            or trace_doc.get("sampler") != probe.PRODUCTION_SAMPLER
            or trace_doc.get("reasoning_effort") != probe.REASONING_EFFORT
            or trace_doc.get("preserve_thinking") is not probe.PRESERVE_THINKING
            or trace_doc.get("serving_identity") != expected_serving_identity
            or trace_doc.get("native_context_tokens") != probe.NATIVE_CONTEXT_TOKENS
            or trace_doc.get("round_index") != expected_round_index
            or trace_doc.get("round_kind") != expected_round_kind
            or trace_doc.get("trace_tag") != expected_tag
            or trace_doc.get("max_tokens") != answer_tokens
            or trace_doc.get("input_text_token_cap") != input_text_cap):
        errors.append("trace serving configuration differs from the frozen call")
    if (trace_doc.get("completion_contains_close") is not closed
            or trace_doc.get("schema_errors") != schema_errors
            or trace_doc.get("payload_present") is not (reparsed_payload is not None)):
        errors.append("trace completion/schema classification was not mechanically derived")
    prompt = trace_doc.get("prompt")
    if (not isinstance(prompt, str)
            or hashlib.sha256(prompt.encode()).hexdigest()
            != trace_doc.get("prompt_sha256")):
        errors.append("trace prompt digest does not match the serialized prompt")
    expanded = trace_doc.get("expanded_prompt_tokens")
    if (type(expanded) is not int or expanded + answer_tokens > probe.NATIVE_CONTEXT_TOKENS
            or type(trace_doc.get("derived_text_tokens")) is not int
            or trace_doc["derived_text_tokens"] > input_text_cap):
        errors.append("trace exceeds its frozen text/native context envelope")
    if (trace_doc.get("prompt_tokens_match") is not True
            or trace_doc.get("token_accounting_match") is not True):
        errors.append("trace token accounting did not pass")
    return trace_doc, errors


def _trace_payload(
    trace_doc: dict[str, Any], int_keys: Sequence[str], str_keys: Sequence[str],
) -> dict[str, Any] | None:
    _think, _answer, parsed, _closed = _decode_trace_completion(trace_doc)
    errors = make_validator(int_keys, str_keys)(parsed) if parsed is not None else []
    return parsed if parsed is not None and not errors else None


def _authoritative_sealed_claim(
    claim: str, result: dict[str, Any], claim_manifest: dict[str, Any], *,
    namespace: str, base_seed: int, run_dir: Path, answer_tokens: int,
    serving_identity: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild truth, permutations, prompts, images, and scores from FROZEN."""
    import s4_run as srun

    errors: list[str] = []
    descriptors = claim_manifest.get("fixture_records")
    expected_count = (GX_TOTAL_FIXTURES if claim == GX_CLAIM
                      else 1 if claim in DIAGNOSTIC_CLAIMS
                      else MODEL_CLAIM_FIXTURES)
    if not isinstance(descriptors, list) or len(descriptors) != expected_count:
        return {"pass": False, "passes": 0,
                "errors": ["sealed descriptor inventory mismatch"]}
    for index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            errors.append(f"fixture {index}: sealed descriptor is malformed")
            continue
        if (descriptor.get("descriptor_sha256")
                != canonical_sha256(_sealed_descriptor_body(descriptor))):
            errors.append(f"fixture {index}: sealed descriptor digest mismatch")
        if (descriptor.get("claim") != claim
                or descriptor.get("namespace") != namespace
                or descriptor.get("index") != index
                or descriptor.get("base_seed") != base_seed
                or descriptor.get("fixture_seed")
                != fixture_seed(namespace, claim, index, base_seed)):
            errors.append(f"fixture {index}: sealed descriptor identity mismatch")
        for asset_index, asset in enumerate(descriptor.get("assets") or []):
            if (not isinstance(asset, dict)
                    or not isinstance(asset.get("logical_name"), str)
                    or not isinstance(asset.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) is None
                    or not (isinstance(asset.get("size"), list)
                            and len(asset["size"]) == 2
                            and all(type(v) is int and v > 0 for v in asset["size"]))):
                errors.append(
                    f"fixture {index}: sealed asset {asset_index} is malformed"
                )

    calls = result.get("calls") or []
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for call in calls:
        if isinstance(call, dict) and type(call.get("fixture_index")) is int:
            by_key[(call["fixture_index"], call.get("permutation_index", 0))] = call
    passed = 0

    for fixture_index, descriptor in enumerate(descriptors):
        metadata = descriptor.get("metadata") or {}
        int_keys = list(metadata.get("int_keys") or [])
        str_keys = list(metadata.get("str_keys") or [])
        if claim == GX_CLAIM:
            suite = "stability" if fixture_index < GX_STABILITY_FIXTURES else "coordinate"
            permutations = (
                counter_permutations(
                    PRODUCTION_CONTEXT_PAGES,
                    fixture_seed(
                        namespace, f"{claim}:stability:perm", fixture_index, base_seed,
                    ),
                ) if suite == "stability" else [list(range(PRODUCTION_CONTEXT_PAGES))]
            )
        elif claim == "GT_text_exact":
            permutations = counter_permutations(
                len(metadata.get("records") or []),
                fixture_seed(namespace, f"{claim}:perm", fixture_index, base_seed),
            )
        elif claim == "GP_interaction":
            permutations = counter_permutations(
                len(metadata.get("initial_page_names") or []),
                fixture_seed(namespace, f"{claim}:perm", fixture_index, base_seed),
            )
        else:
            page_count = len(metadata.get("page_names") or [])
            permutations = (
                [[0], [0]] if claim in DIAGNOSTIC_CLAIMS and page_count == 1
                else counter_permutations(
                    page_count,
                    fixture_seed(namespace, f"{claim}:perm", fixture_index, base_seed),
                )
            )

        for permutation_index, permutation in enumerate(permutations):
            call = by_key.get((fixture_index, permutation_index))
            if not isinstance(call, dict):
                errors.append(
                    f"fixture {(fixture_index, permutation_index)}: missing sealed call"
                )
                continue
            call_errors: list[str] = []
            if call.get("permutation") != permutation:
                call_errors.append("permutation differs from sealed derivation")
            if (call.get("fixture_descriptor_sha256")
                    != descriptor.get("descriptor_sha256")):
                call_errors.append("descriptor binding mismatch")

            if claim == "GT_text_exact":
                tag = f"gt_{namespace}_{fixture_index}_{permutation_index}"
                records = metadata.get("records") or []
                ledger = "\n\n".join(records[index] for index in permutation)
                expected_messages = [{"role": "user", "content": [{
                    "type": "text", "text": ledger + "\n\n" + metadata["question"],
                }]}]
                expected_assets: list[dict[str, Any]] = []
                truth = dict(metadata.get("truth") or {})
                seed = fixture_seed(
                    namespace, f"{claim}:{permutation_index}", fixture_index, base_seed,
                ) % 2**64
                record = call.get("round")
                trace, trace_errors = _validate_gate_trace(
                    record=record, expected_tag=tag, expected_seed=seed,
                    expected_messages=expected_messages, expected_assets=expected_assets,
                    expected_payload=call.get("payload"), int_keys=int_keys,
                    str_keys=str_keys, run_dir=run_dir, answer_tokens=answer_tokens,
                    input_text_cap=srun.MAX_INITIAL_PROMPT_TEXT_TOKENS,
                    expected_serving_identity=serving_identity,
                    expected_round_index=0, expected_round_kind="gate_single",
                )
            elif claim == "GP_interaction":
                tag = f"gp_{namespace}_{fixture_index}_{permutation_index}"
                initial_assets = _sealed_assets(descriptor, "initial")
                expected_assets = [initial_assets[index] for index in permutation]
                initial_items: list[dict[str, str]] = []
                for page_no in range(1, len(expected_assets) + 1):
                    initial_items.extend((
                        {"type": "text", "text": f"Page {page_no} of 10:"},
                        {"type": "image"},
                    ))
                initial_items.append({
                    "type": "text",
                    "text": ('Inspect this initial evidence. Do not answer the final '
                             'chronology question yet. Answer ONLY {"ack":"continue"}.'),
                })
                expected_messages = [{"role": "user", "content": initial_items}]
                round_entries = call.get("rounds")
                if not isinstance(round_entries, list) or len(round_entries) != 4:
                    call_errors.append("GP round inventory is not exactly four")
                    round_entries = []
                trace = None
                trace_errors = []
                interim_ok = True
                image_growth = [len(expected_assets)]
                prior_trace: dict[str, Any] | None = None
                for round_index in range(4):
                    if round_index >= len(round_entries):
                        break
                    entry = round_entries[round_index]
                    if round_index > 0:
                        if prior_trace is None:
                            call_errors.append(
                                f"GP round {round_index} has no authoritative prior trace"
                            )
                            break
                        think, answer, _parsed, _closed = _decode_trace_completion(prior_trace)
                        expected_messages.append({
                            "role": "assistant", "content": answer,
                            "reasoning_content": think,
                        })
                        round_meta = metadata["rounds"][round_index - 1]
                        round_items = [{"type": "text", "text": round_meta["text"]}]
                        round_assets = _sealed_assets(descriptor, f"round{round_index}")
                        for name in round_meta["page_names"]:
                            round_items.extend((
                                {"type": "text", "text": f"{name}:"},
                                {"type": "image"},
                            ))
                        if round_index == 3:
                            round_items.append({"type": "text", "text": metadata["question"]})
                        else:
                            round_items.append({
                                "type": "text",
                                "text": ('Retain this exact result. Do not answer the final '
                                         'question yet. Answer ONLY {"ack":"continue"}.'),
                            })
                        expected_messages.append({"role": "user", "content": round_items})
                        expected_assets.extend(round_assets)
                        image_growth.append(len(expected_assets))
                    expected_seed = fixture_seed(
                        namespace,
                        f"{claim}:{permutation_index}:r{round_index}",
                        fixture_index, base_seed,
                    ) % 2**64
                    round_int_keys = int_keys if round_index == 3 else []
                    round_str_keys = str_keys if round_index == 3 else ["ack"]
                    trace, one_errors = _validate_gate_trace(
                        record=(entry or {}).get("record"),
                        expected_tag=f"{tag}_r{round_index}", expected_seed=expected_seed,
                        expected_messages=expected_messages,
                        expected_assets=expected_assets,
                        expected_payload=(entry or {}).get("payload"),
                        int_keys=round_int_keys, str_keys=round_str_keys,
                        run_dir=run_dir, answer_tokens=answer_tokens,
                        input_text_cap=(srun.MAX_INITIAL_PROMPT_TEXT_TOKENS
                                        if round_index == 0
                                        else srun.MAX_CONTEXT_TEXT_TOKENS),
                        expected_serving_identity=serving_identity,
                        expected_round_index=round_index,
                        expected_round_kind=("gate_interaction_initial"
                                             if round_index == 0
                                             else "gate_interaction_update"),
                    )
                    trace_errors.extend(
                        f"round {round_index}: {message}" for message in one_errors
                    )
                    if trace is None:
                        interim_ok = False
                    elif round_index < 3:
                        interim_ok = interim_ok and (
                            _trace_payload(trace, [], ["ack"]) == {"ack": "continue"}
                            and trace.get("completeness") == "complete"
                        )
                    prior_trace = trace
                truth = dict(metadata.get("truth_static") or {})
                if trace is None:
                    payload = None
                    complete = False
                else:
                    payload = _trace_payload(trace, int_keys, str_keys)
                    complete = trace.get("completeness") == "complete"
                expected_score = score_call(payload, truth, int_keys)
                expected_checks = {
                    "four_generation_calls": len(round_entries) == 4,
                    "exact_image_growth": image_growth == [10, 13, 13, 16],
                    "assistant_user_interleaving": [
                        message["role"] for message in expected_messages
                    ] == ["user", "assistant", "user", "assistant", "user",
                          "assistant", "user"],
                    "intermediate_complete": interim_ok,
                    "final_complete": complete,
                }
                expected_score["completion_complete"] = complete
                expected_score["pass"] = expected_score["pass"] and complete
                expected_score["interaction_checks"] = expected_checks
                expected_score["pass"] = expected_score["pass"] and all(
                    expected_checks.values()
                )
                if call.get("truth") != truth:
                    call_errors.append("GP truth differs from sealed descriptor")
                if call.get("payload") != payload:
                    call_errors.append("GP final payload differs from final raw trace")
                if call.get("score") != expected_score:
                    call_errors.append("GP score/chronology differs from trace re-derivation")
                call_errors.extend(trace_errors)
                call_pass = not call_errors and expected_score["pass"]
                passed += bool(call_pass)
                errors.extend(
                    f"{claim} {(fixture_index, permutation_index)}: {message}"
                    for message in call_errors
                )
                continue
            else:
                if claim == GX_CLAIM:
                    suite = "stability" if fixture_index < GX_STABILITY_FIXTURES else "coordinate"
                    tag = f"gx_{suite}_{namespace}_{fixture_index}_{permutation_index}"
                    all_assets = _sealed_assets(descriptor, "pages")
                    expected_assets = [all_assets[index] for index in permutation]
                    truth = dict(metadata.get("truth") or {})
                    seed = fixture_seed(
                        namespace, f"{claim}:{suite}:{permutation_index}",
                        fixture_index, base_seed,
                    ) % 2**64
                else:
                    tag = f"{claim.split('_')[0].lower()}_{namespace}_{fixture_index}_{permutation_index}"
                    all_assets = _sealed_assets(descriptor, "pages")
                    expected_assets = [all_assets[index] for index in permutation]
                    truth = dict(metadata.get("truth_static") or metadata.get("truth") or {})
                    for key, original_index in (metadata.get("queried_pages") or {}).items():
                        truth[key] = permutation.index(original_index) + 1
                    seed = fixture_seed(
                        namespace, f"{claim}:{permutation_index}",
                        fixture_index, base_seed,
                    ) % 2**64
                items: list[dict[str, str]] = []
                for page_no in range(1, len(expected_assets) + 1):
                    items.extend((
                        {"type": "text",
                         "text": f"Page {page_no} of {len(expected_assets)}:"},
                        {"type": "image"},
                    ))
                items.append({"type": "text", "text": metadata["question"]})
                expected_messages = [{"role": "user", "content": items}]
                record = call.get("round")
                trace, trace_errors = _validate_gate_trace(
                    record=record, expected_tag=tag, expected_seed=seed,
                    expected_messages=expected_messages, expected_assets=expected_assets,
                    expected_payload=call.get("payload"), int_keys=int_keys,
                    str_keys=str_keys, run_dir=run_dir, answer_tokens=answer_tokens,
                    input_text_cap=srun.MAX_INITIAL_PROMPT_TEXT_TOKENS,
                    expected_serving_identity=serving_identity,
                    expected_round_index=0, expected_round_kind="gate_single",
                )

            call_errors.extend(trace_errors)
            if call.get("seed") != seed:
                call_errors.append("call seed differs from sealed derivation")
            if call.get("truth") != truth:
                call_errors.append("call truth differs from sealed descriptor")
            if trace is None:
                payload = None
                complete = False
            else:
                payload = _trace_payload(trace, int_keys, str_keys)
                complete = trace.get("completeness") == "complete"
            expected_score = score_call(payload, truth, int_keys)
            expected_score["completion_complete"] = complete
            expected_score["pass"] = expected_score["pass"] and complete
            if call.get("payload") != payload:
                call_errors.append("call payload differs from reparsed raw trace")
            if call.get("score") != expected_score:
                call_errors.append("stored call score differs from sealed re-derivation")
            call_pass = not call_errors and expected_score["pass"]
            passed += bool(call_pass)
            errors.extend(
                f"{claim} {(fixture_index, permutation_index)}: {message}"
                for message in call_errors
            )

    expected_calls = (GX_TOTAL_CALLS if claim == GX_CLAIM
                      else 2 if claim in DIAGNOSTIC_CLAIMS
                      else MODEL_CLAIM_REQUIRED_PASSES)
    extra_pass = True
    if claim == GX_CLAIM:
        extra_pass = (
            result.get("patch_phase_coverage")
            == claim_manifest.get("patch_phase_coverage")
            and bool((claim_manifest.get("patch_phase_coverage") or {}).get("pass"))
        )
        if not extra_pass:
            errors.append("GX phase coverage differs from the sealed fixture set")
    expected_pass = passed == expected_calls and extra_pass
    if (result.get("passes") != passed or result.get("required") != expected_calls
            or result.get("pass") is not expected_pass):
        errors.append("claim summary differs from sealed trace re-derivation")
    return {"pass": not errors and expected_pass, "passes": passed,
            "required": expected_calls, "errors": errors}


def validate_claims_document(
    document: dict[str, Any], frozen: dict[str, Any], *,
    frozen_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate a complete native confirm output against its exact freeze.

    `valid` means the artifact is structurally complete and untampered.  Gate
    performance is separate: a valid document may correctly report failed
    claims, in which case `all_selected_arms_eligible` is false and continuation
    must write STOP rather than rejecting the result artifact.
    """
    errors: list[str] = []
    if not isinstance(document, dict) or not isinstance(frozen, dict):
        return {"valid": False, "errors": ["claims document/freeze must be objects"]}
    frozen_sha = frozen_manifest_sha256 or sha256_file(SEALED_R4 / "FROZEN.json")
    if document.get("format_version") != FORMAT_VERSION:
        errors.append("claims format version mismatch")
    if document.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("claims protocol version mismatch")
    if document.get("namespace") != "confirm":
        errors.append("claims namespace is not confirm")
    if document.get("frozen_manifest_sha256") != frozen_sha:
        errors.append("claims are not bound to the exact FROZEN.json")
    if document.get("thresholds") != THRESHOLDS:
        errors.append("claims thresholds differ from executable constants")
    frozen_thresholds = ((frozen.get("confirm_assets") or {})
                         .get("gate_thresholds"))
    if frozen_thresholds != THRESHOLDS:
        errors.append("frozen gate thresholds differ from executable constants")

    base_seed = document.get("base_seed")
    if type(base_seed) is not int:
        errors.append("claims base_seed is not a JSON integer")
        base_seed = -1
    manifest_rel = document.get("fixture_manifest_path")
    manifest_sha = document.get("fixture_manifest_sha256")
    frozen_manifests = ((frozen.get("confirm_assets") or {})
                        .get("gate_fixture_manifests") or {})
    manifest: dict[str, Any] = {}
    if (not isinstance(manifest_rel, str)
            or frozen_manifests.get(manifest_rel) != manifest_sha):
        errors.append("fixture manifest path/digest is not bound by FROZEN")
    else:
        manifest_path = ROOT / manifest_rel
        if not manifest_path.is_file() or sha256_file(manifest_path) != manifest_sha:
            errors.append("fixture manifest bytes drifted after FROZEN")
        else:
            try:
                manifest = json.loads(manifest_path.read_text())
            except (OSError, json.JSONDecodeError):
                errors.append("fixture manifest is unreadable")
    if manifest:
        if (manifest.get("protocol_version") != PROTOCOL_VERSION
                or manifest.get("namespace") != "confirm"
                or manifest.get("base_seed") != base_seed):
            errors.append("fixture manifest protocol/namespace/base-seed mismatch")
        if manifest.get("generator_sha256") != sha256_file(Path(__file__)):
            errors.append("fixture manifest generator hash mismatch")
        if set(manifest.get("claims") or {}) != set(MODEL_CLAIMS) | set(DIAGNOSTIC_CLAIMS):
            errors.append("fixture manifest claim inventory mismatch")

    results = document.get("results")
    if not isinstance(results, dict) or set(results) != set(ALL_CLAIMS):
        errors.append("claims result inventory must equal ALL_CLAIMS exactly")
        results = results if isinstance(results, dict) else {}
    snapshot = frozen.get("serving_snapshot") or {}
    expected_serving_identity = {
        "checkpoint_sha256": (snapshot.get("checkpoint_fingerprint") or {}).get(
            "checkpoint_sha256"
        ),
        "verified_shards": True,
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
    }
    if document.get("serving_identity") != expected_serving_identity:
        errors.append("claims serving identity differs from FROZEN")
    run_dir = Path(str(document.get("run_dir", "")))
    if (not run_dir.is_dir()
            or run_dir.resolve() != CONFIRM_RUN_DIR.resolve()):
        errors.append("claims run directory differs from the fixed confirm gate run")
    answer_tokens = (snapshot.get("budgets") or {}).get("answer_tokens")
    if type(answer_tokens) is not int:
        errors.append("frozen gate answer-token budget is invalid")
        answer_tokens = -1

    reservation_sha = document.get("confirm_reservation_sha256")
    if (not CONFIRM_RESERVATION.is_file()
            or not isinstance(reservation_sha, str)
            or sha256_file(CONFIRM_RESERVATION) != reservation_sha):
        errors.append("confirm one-shot reservation is absent or mismatched")
    else:
        try:
            reservation = json.loads(CONFIRM_RESERVATION.read_text())
        except (OSError, json.JSONDecodeError):
            errors.append("confirm one-shot reservation is unreadable")
        else:
            errors.extend(_confirm_reservation_errors(
                reservation, frozen_sha=frozen_sha, manifest_sha=str(manifest_sha),
                base_seed=base_seed,
                model=Path(str(snapshot.get("model_path", ""))), run_dir=run_dir,
                answer_tokens=answer_tokens,
                serving_identity=expected_serving_identity,
            ))

    started_path = run_dir / "STARTED.json"
    started_sha = document.get("confirm_started_sha256")
    if (not started_path.is_file() or not isinstance(started_sha, str)
            or sha256_file(started_path) != started_sha):
        errors.append("confirm STARTED receipt is absent or mismatched")
    elif isinstance(reservation_sha, str):
        try:
            started = json.loads(started_path.read_text())
        except (OSError, json.JSONDecodeError):
            errors.append("confirm STARTED receipt is unreadable")
        else:
            errors.extend(_confirm_started_errors(
                started, reservation_sha=reservation_sha, base_seed=base_seed,
                run_dir=run_dir, answer_tokens=answer_tokens,
                serving_identity=expected_serving_identity,
            ))

    if isinstance(reservation_sha, str):
        for claim in (*MODEL_CLAIMS, *DIAGNOSTIC_CLAIMS):
            marker_path = _claim_started_path(run_dir, claim)
            if not marker_path.is_file():
                errors.append(f"confirm claim {claim} lacks its one-shot STARTED receipt")
                continue
            try:
                marker = json.loads(marker_path.read_text())
            except (OSError, json.JSONDecodeError):
                errors.append(f"confirm claim {claim} STARTED receipt is unreadable")
                continue
            errors.extend(_claim_started_errors(
                marker, reservation_sha=reservation_sha, claim=claim,
                base_seed=base_seed, run_dir=run_dir, answer_tokens=answer_tokens,
                serving_identity=expected_serving_identity,
            ))
    claim_validations: dict[str, Any] = {}
    for claim in ALL_CLAIMS:
        validation = validate_claim_result(
            claim, results.get(claim) or {}, namespace="confirm", base_seed=base_seed,
        )
        claim_validations[claim] = validation
        errors.extend(f"{claim}: {message}" for message in validation["errors"])
        if claim == "G0_protocol_serving":
            if snapshot and isinstance(results.get(claim), dict):
                try:
                    expected_g0 = g0_protocol_serving(
                        Path(str(snapshot.get("model_path", ""))), snapshot,
                    )
                    if results.get(claim) != expected_g0:
                        errors.append("G0 result differs from live mechanical re-derivation")
                except (RuntimeError, OSError, KeyError, ValueError) as exc:
                    errors.append(f"G0 could not be re-derived: {exc}")
            continue
        if not manifest:
            continue
        claim_manifest = (manifest.get("claims") or {}).get(claim) or {}
        fixture_records = claim_manifest.get("fixture_records")
        expected_count = (GX_TOTAL_FIXTURES if claim == GX_CLAIM
                          else 1 if claim in DIAGNOSTIC_CLAIMS
                          else MODEL_CLAIM_FIXTURES)
        if not isinstance(fixture_records, list) or len(fixture_records) != expected_count:
            errors.append(f"{claim}: sealed fixture-record inventory mismatch")
            continue
        for call in (results.get(claim) or {}).get("calls") or []:
            index = call.get("fixture_index")
            if (type(index) is not int or not (0 <= index < len(fixture_records))
                    or call.get("fixture_descriptor_sha256")
                    != fixture_records[index].get("descriptor_sha256")):
                errors.append(f"{claim}: call descriptor is not sealed to fixture {index}")
        if run_dir.is_dir() and answer_tokens > 0:
            authoritative = _authoritative_sealed_claim(
                claim, results.get(claim) or {}, claim_manifest,
                namespace="confirm", base_seed=base_seed, run_dir=run_dir,
                answer_tokens=answer_tokens,
                serving_identity=expected_serving_identity,
            )
            errors.extend(authoritative["errors"])
            if not authoritative["pass"]:
                claim_validations[claim] = {
                    **validation,
                    "pass": False,
                    "authority_errors": authoritative["errors"],
                }

    selected_arms = ((frozen.get("preregistration") or {}).get("arms") or [])
    if not selected_arms or any(arm not in ARM_REQUIREMENTS for arm in selected_arms):
        errors.append("frozen selected-arm inventory is invalid")
        selected_arms = []
    eligibility = derive_arm_eligibility(
        results, selected_arms, strict=True, namespace="confirm", base_seed=base_seed,
    )
    if document.get("eligibility") != eligibility:
        errors.append("stored arm eligibility differs from strict re-derivation")
    return {
        "valid": not errors,
        "errors": errors,
        "base_seed": base_seed,
        "claim_validations": claim_validations,
        "eligibility": eligibility,
        "all_selected_arms_eligible": eligibility["all_selected_arms_eligible"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", choices=["dev", "confirm"], default="dev")
    parser.add_argument("--base-seed", type=int, default=4)
    parser.add_argument("--claims", nargs="*", default=list(ALL_CLAIMS))
    parser.add_argument("--build-fixtures-only", action="store_true",
                        help="generate + verify fixtures without any model call")
    parser.add_argument("--model", type=Path,
                        default=Path.home() / "models/mlx/Qwen3.8-27B-8bit")
    parser.add_argument("--run", action="store_true",
                        help="execute model-dependent claims (requires FROZEN for "
                             "the confirm namespace)")
    args = parser.parse_args()
    sl.enforce_offline_scientific_run("s4_gates", sys.argv[1:])
    require(args.claims and len(args.claims) == len(set(args.claims)),
            "--claims must be a nonempty duplicate-free list")
    unknown_claims = set(args.claims) - set(ALL_CLAIMS)
    require(not unknown_claims, f"unknown claims: {sorted(unknown_claims)}")

    if args.build_fixtures_only:
        out_root = DEV_FIXTURES if args.namespace == "dev" else CONFIRM_FIXTURES
        if args.namespace == "confirm":
            require(not (SEALED_R4 / "FROZEN.json").exists(),
                    "confirm fixtures must be generated before FROZEN")
            require(set(args.claims) - {"G0_protocol_serving"}
                    == set(MODEL_CLAIMS) | set(DIAGNOSTIC_CLAIMS),
                    "confirm fixture generation requires the complete claim inventory")
        out_root.mkdir(parents=True, exist_ok=True)
        path = out_root / f"fixture_manifest_{args.base_seed}.json"
        if args.namespace == "confirm":
            require(not path.exists(),
                    f"sealed confirm fixture manifest already exists: {path}")
        asset_root = out_root / f"gate_assets_{args.base_seed}"
        if args.namespace == "confirm":
            require(not asset_root.exists(),
                    f"sealed confirm gate assets already exist: {asset_root}")
        asset_root.mkdir(parents=True, exist_ok=args.namespace == "dev")
        manifest: dict[str, Any] = {
            "format_version": 2,
            "protocol_version": PROTOCOL_VERSION,
            "generator_sha256": sha256_file(Path(__file__)),
            "namespace": args.namespace,
            "base_seed": args.base_seed,
            "claims": {},
        }
        for claim in args.claims:
            if claim == "G0_protocol_serving":
                continue
            builder = FIXTURE_BUILDERS[claim]
            count = (GX_TOTAL_FIXTURES if claim == GX_CLAIM
                     else 1 if claim in DIAGNOSTIC_CLAIMS else MODEL_CLAIM_FIXTURES)
            records = []
            final_fixtures = []
            for index in range(count):
                fixture = builder(args.namespace, index, args.base_seed)
                final, descriptor = _materialize_fixture(
                    claim, fixture, asset_root,
                    "".join(ch if ch.isalnum() else "_" for ch in claim)
                    + f"_{args.namespace}_{index}",
                    namespace=args.namespace, base_seed=args.base_seed,
                )
                final_fixtures.append(final)
                records.append(_portable_descriptor(descriptor))
            entry: dict[str, Any] = {
                "fixtures": count,
                "digests": [record["descriptor_sha256"] for record in records],
                "fixture_records": records,
            }
            if claim == GX_CLAIM:
                coverage = gx_phase_coverage(
                    final_fixtures[GX_STABILITY_FIXTURES:]
                )
                require(coverage["pass"],
                        f"GX fixture-set coverage failure: {coverage}")
                entry["patch_phase_coverage"] = coverage
            manifest["claims"][claim] = entry
            print(f"{claim}: {count} fixtures verified (procedural truth == PNG decode)")
        if args.namespace == "confirm":
            _atomic_create_json(path, manifest)
        else:
            path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        print(f"wrote {path}")
        return 0

    if not args.run:
        parser.error("pass --build-fixtures-only or --run")
    frozen: dict[str, Any] | None = None
    frozen_sha: str | None = None
    sealed_manifest: dict[str, Any] | None = None
    fixture_manifest_path: str | None = None
    fixture_manifest_sha: str | None = None
    if args.namespace == "confirm":
        require(set(args.claims) == set(ALL_CLAIMS),
                "confirm gate run requires every frozen claim, including GD")
        (frozen, frozen_sha, sealed_manifest, fixture_manifest_path,
         fixture_manifest_sha) = _load_confirm_binding(args.base_seed)
    import e2_probe_vlm as probe
    import s4_run as srun

    if frozen is not None:
        serving_identity = srun.verify_serving_snapshot(
            args.model, frozen["serving_snapshot"]
        )
        answer_tokens = frozen["serving_snapshot"]["budgets"]["answer_tokens"]
    else:
        live_fingerprint = probe.fingerprint(args.model)
        serving_identity = {
            "checkpoint_sha256": live_fingerprint["checkpoint_sha256"],
            "verified_shards": True,
            "snapshot_sha256": None,
        }
        answer_tokens = srun.MAX_ANSWER_TOKENS

    confirm_started_sha: str | None = None
    if frozen is not None:
        run_dir = CONFIRM_RUN_DIR
        _reserve_confirm_run(
            frozen_sha=str(frozen_sha), manifest_sha=str(fixture_manifest_sha),
            base_seed=args.base_seed, model=args.model, run_dir=run_dir,
            answer_tokens=answer_tokens, serving_identity=serving_identity,
        )
        confirm_started_sha = _start_confirm_run(
            base_seed=args.base_seed, run_dir=run_dir,
            answer_tokens=answer_tokens, serving_identity=serving_identity,
        )
    else:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        run_dir = ROOT / f"logs/s4_gate_runs/{stamp}_{args.namespace}"
        run_dir.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}
    results["G0_protocol_serving"] = g0_protocol_serving(
        args.model, (frozen or {}).get("serving_snapshot") if frozen else None,
    )
    vlm = probe.Vlm(args.model)
    for claim in args.claims:
        if claim == "G0_protocol_serving":
            continue
        results[claim] = run_model_claim(
            vlm, claim, args.namespace, args.base_seed, run_dir,
            answer_tokens=answer_tokens,
            serving_identity=serving_identity,
            sealed_claim=(sealed_manifest or {}).get("claims", {}).get(claim),
        )
        print(f"{claim}: {results[claim]['passes']}/{results[claim]['required']} "
              f"-> {'PASS' if results[claim]['pass'] else 'FAIL'}")
    eligibility = derive_arm_eligibility(
        results, list(ARM_REQUIREMENTS), strict=args.namespace == "confirm",
        namespace=args.namespace, base_seed=args.base_seed,
    )
    payload = {
        "format_version": FORMAT_VERSION, "protocol_version": PROTOCOL_VERSION,
        "namespace": args.namespace, "base_seed": args.base_seed,
        "thresholds": THRESHOLDS, "results": results, "eligibility": eligibility,
        "run_dir": str(run_dir),
        "frozen_manifest_sha256": frozen_sha,
        "fixture_manifest_path": fixture_manifest_path,
        "fixture_manifest_sha256": fixture_manifest_sha,
        "serving_identity": serving_identity,
        "confirm_reservation_sha256": (
            sha256_file(CONFIRM_RESERVATION) if args.namespace == "confirm" else None
        ),
        "confirm_started_sha256": confirm_started_sha,
    }
    out = CONFIRM_RESULTS if args.namespace == "confirm" else run_dir / "claims.json"
    if args.namespace == "confirm":
        _atomic_create_json(out, payload)
    else:
        out.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
