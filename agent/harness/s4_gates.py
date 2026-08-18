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
GX_COORDINATE_FIXTURES = 8          # 8/8 exact, all patch phases covered
PATCH_PHASE_GRIDS = (16, 32)        # phases verified on the FINAL rendered bbox

THRESHOLDS = {
    "model_claim_calls": MODEL_CLAIM_REQUIRED_PASSES,
    "model_claim_required_passes": MODEL_CLAIM_REQUIRED_PASSES,
    "gx_coordinate_fixtures": GX_COORDINATE_FIXTURES,
    "gx_required_exact": GX_COORDINATE_FIXTURES,
    "g0_required": "100% mechanical",
    "no_retry_no_majority_no_silent_repair": True,
    "plus_minus_one_is_a_fail": True,
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_sha256(value: Any) -> str:
    return sd.canonical_sha256(value)


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
    cluttered = index % 2 == 1
    grid = _sparse_board(rng, objects=14 if cluttered else 4)
    target_colour = _unique_cell_colour(grid, rng)
    # Coordinate schedule covers edges, quadrants, and all patch phases: the
    # window origin (r0*cell_px+gutter) is constant mod 32, so phase coverage is
    # scheduled through the target's offset INSIDE the window.
    phase = index % 4
    quadrant = index % 4
    base_r = (4, 4, 52, 52)[quadrant] + int(rng.integers(0, 6))
    base_c = (4, 52, 4, 52)[quadrant] + int(rng.integers(0, 6))
    row = min(62, max(1, base_r + phase))
    col = min(62, max(1, base_c + (index // 4 + phase) % 4))
    grid[row, col] = target_colour
    window_r0 = max(0, row - int(rng.integers(2, 7)))
    window_c0 = max(0, col - int(rng.integers(2, 7)))
    window = (window_r0, window_c0,
              min(63, window_r0 + int(rng.integers(8, 14))),
              min(63, window_c0 + int(rng.integers(8, 14))))
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
    y0 = sr.RULER_GUTTER_PX + (row - r0) * plate.cell_px
    x0 = sr.RULER_GUTTER_PX + (col - c0) * plate.cell_px
    phases = {f"mod{g}": [int(y0 % g), int(x0 % g)] for g in PATCH_PHASE_GRIDS}
    question = (
        f"The image is a magnified window of a 64x64 board with explicit rulers: "
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
        "question": question,
        "truth": {"target_row": row, "target_col": col},
        "target_pixel_origin": [int(y0), int(x0)],
        "patch_phases": phases,
        "int_keys": ["target_row", "target_col"],
    }


def gx_phase_coverage(fixtures: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """All scheduled phases must appear across the eight sealed coordinates."""
    seen: dict[str, set[int]] = {"row_mod16": set(), "col_mod16": set()}
    for fixture in fixtures:
        y_mod, x_mod = fixture["patch_phases"]["mod16"]
        seen["row_mod16"].add(y_mod)
        seen["col_mod16"].add(x_mod)
    return {key: sorted(values) for key, values in seen.items()}


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
    ledger = "\n\n".join(
        text_boards
        + [sd.render_text_block(effect_record), sd.render_text_block(no_effect_record)]
    )
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
        "ledger": ledger, "question": question, "truth": truth,
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
    ]
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
    pages = [
        ("raw", raw),
        ("marked", marked),
        ("component_board", sr.render_board(comp_board)),
    ]
    ledger = (
        f"component {comp_id}: bbox=({comp_r},{comp_c},{comp_r + 3},{comp_c + 3}) "
        f"[DERIVED-EXACT]"
    )
    question = (
        f"{ledger}\nThe magenta ring on the marked page is drawn by the recorder. "
        "Report: whether the ring is part of the game state or an annotation; the "
        "colour id of the CELL the ring surrounds; which page number shows the raw "
        f"unannotated copy of the same board; and the colour id of component "
        f"{comp_id} per its ledger bbox. Think first. Then answer with ONLY a JSON "
        'object: {"ring_is": "annotation"|"game_state", "ringed_cell_colour": <int>, '
        '"raw_page": <int>, "component_colour": <int>}'
    )
    return {
        "claim": "GO_overlay_readout", "namespace": namespace, "index": index,
        "pages": pages, "question": question,
        "queried_pages": {"raw_page": 0},
        "truth_static": {
            "ring_is": "annotation", "ringed_cell_colour": under,
            "component_colour": comp_colour,
        },
        "int_keys": ["ringed_cell_colour", "raw_page", "component_colour"],
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
         "pages": [(f"{probe_tag}_result",
                    sr.storyboard(result_frames, cols=3, cell_px=8))],
         "text": (f"probe {probe_tag} result: replayed prefix, performed the "
                  "requested action, all response frames in order; the LAST frame "
                  "is the settled state [OBSERVED]")},
        {"label": f"K{2000 + index}",
         "pages": [],
         "text": (f"retrieval K{2000 + index} failed: request is invalid or absent "
                  "from the frozen observation store; it was not rewritten")},
        {"label": f"K{2001 + index}",
         "pages": [(f"K{2001 + index}_result",
                    sr.render_ruler_frame(settled))],
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
    require(total_images <= 16, "GP fixture exceeds the 16-image envelope")
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


def verify_fixture_decode(claim: str, fixture: dict[str, Any]) -> None:
    """Independently re-decode produced plates; truth must match construction.

    GX and GT verify inside their builders (ruler decode / RLE decode).  The
    page claims verify here: rendered pixels, not renderer intent, carry truth.
    """
    if claim == "GV_raw_readout":
        by_name = {name: plate for name, plate in fixture["pages"]}
        pre = sr.decode_board(by_name["causal_pre_4px"])
        post = sr.decode_board(by_name["causal_post_4px"])
        changed = np.argwhere(pre != post)
        require(changed.size > 0, "GV fixture pre/post decode shows no change")
        added = all(pre[r, c] == 0 for r, c in changed)
        require(added == (fixture["truth_static"]["change_kind"] == "added"),
                "GV fixture change-kind truth does not match decoded plates")
        green = sr.decode_board(by_name["green_board"])
        colours = set(int(v) for v in np.unique(green)) - {0}
        require(colours == {3}, "GV green-board fixture decode mismatch")
    elif claim == "GO_overlay_readout":
        by_name = {name: plate for name, plate in fixture["pages"]}
        raw = sr.decode_board(by_name["raw"])
        marked_meta = by_name["marked"].meta
        r, c = marked_meta["click"]
        require(int(raw[r, c]) == fixture["truth_static"]["ringed_cell_colour"],
                "GO ringed-cell truth does not match decoded raw plate")
        comp = sr.decode_board(by_name["component_board"])
        colours = set(int(v) for v in np.unique(comp)) - set(
            int(v) for v in np.unique(raw))
        require(colours == {fixture["truth_static"]["component_colour"]},
                "GO component colour does not match decoded component plate")
    elif claim == "GP_interaction":
        last_round = fixture["rounds"][-1]
        name, plate = last_round["pages"][0]
        require(plate.meta.get("profile") == sr.RULER_FRAME_PROFILE,
                "GP settled retrieval is not the certified ruler frame")
        sr.decode_ruler_view(plate)  # must decode exactly (raises otherwise)


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


def derive_arm_eligibility(
    claim_results: dict[str, dict[str, Any]], selected_arms: Sequence[str],
) -> dict[str, Any]:
    """Mechanical: an arm is eligible iff every claim in its requirement set
    passed.  GD never appears in any requirement set."""
    arms: dict[str, Any] = {}
    for arm in selected_arms:
        require(arm in ARM_REQUIREMENTS, f"unknown arm {arm!r}")
        blocking = [
            claim for claim in ARM_REQUIREMENTS[arm]
            if not (claim_results.get(claim) or {}).get("pass")
        ]
        arms[arm] = {"eligible": not blocking, "blocking_claims": blocking,
                     "requirement_set": list(ARM_REQUIREMENTS[arm])}
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


def g0_protocol_serving(model_path: Path) -> dict[str, Any]:
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
        "interaction_rounds": srun.INTERACTION_ROUNDS,
    }
    # Template invariants on a fixture conversation (tokenizer-level, no weights).
    rendered = auditor.tokenizer.apply_chat_template(
        [{"role": "user", "content": "fixture"}],
        tokenize=False, add_generation_prompt=True,
        enable_thinking=True, reasoning_effort=probe.REASONING_EFFORT,
    )
    checks["template_opens_think"] = rendered.rstrip().endswith("<think>")
    import re
    marker = rendered.rfind("<|im_start|>assistant")
    checks["no_prefilled_think"] = (
        marker != -1 and not re.search(r"<think>\s*</think>", rendered[marker:])
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
    mechanical_pass = all([
        checks["sampler_agreement"], checks["template_opens_think"],
        checks["no_prefilled_think"], all(blind.values()),
        checks["allowlist_excludes_source"],
    ])
    return {
        "claim": "G0_protocol_serving", "kind": "mechanical",
        "pass": mechanical_pass, "checks": checks,
        "rule": "mechanical, must pass 100%; a temp-0 model call may diagnose "
                "wiring but cannot authorize an inferential arm",
    }


# ----------------------------------------------------------------- claim runs


def _fixture_pages_to_files(pages, work: Path, tag: str) -> list[Path]:
    paths = []
    for page_index, (name, plate) in enumerate(pages):
        paths.append(plate.save(work / f"{tag}_p{page_index + 1:02d}_{name}.png"))
    return paths


def run_model_claim(
    vlm, claim: str, namespace: str, base_seed: int, run_dir: Path,
    *, answer_tokens: int,
) -> dict[str, Any]:
    """Six production-sampler calls (3 fixtures x 2 counter-permutations); 6/6.

    GX runs its eight sealed coordinate fixtures instead (8/8 exact).
    GD runs one fixture x 2 permutations, reported without blocking anything.
    """
    import s4_run as srun

    sl.enforce_offline_scientific_run(f"s4_gates:{claim}", [])
    builder = FIXTURE_BUILDERS[claim]
    work = run_dir / "boards"
    work.mkdir(parents=True, exist_ok=True)
    calls: list[dict[str, Any]] = []
    passes = 0

    if claim == GX_CLAIM:
        fixtures = [builder(namespace, i, base_seed) for i in range(GX_COORDINATE_FIXTURES)]
        coverage = gx_phase_coverage(fixtures)
        for fixture in fixtures:
            tag = f"gx_{namespace}_{fixture['index']}"
            plate = sr.render_ruler_crop(
                np.asarray(fixture["grid"], dtype=np.uint8),
                tuple(fixture["window"]), margin=0, cell_px=32,
            )
            path = plate.save(work / f"{tag}.png")
            items = [{"type": "text", "text": "Image:"}, {"type": "image"},
                     {"type": "text", "text": fixture["question"]}]
            validator = make_validator(fixture["int_keys"])
            record, payload, _ = srun.ask_chat(
                vlm, [{"role": "user", "content": items}], [path],
                seed=fixture_seed(namespace, claim, fixture["index"], base_seed) % 2**64,
                max_tokens=answer_tokens, run_dir=run_dir, tag=tag,
                payload_validator=validator,
            )
            score = score_call(payload, fixture["truth"], fixture["int_keys"])
            passes += bool(score["pass"])
            calls.append({"tag": tag, "fixture_index": fixture["index"],
                          "truth": fixture["truth"], "payload": payload,
                          "score": score, "round": record})
        result_pass = passes == GX_COORDINATE_FIXTURES
        return {"claim": claim, "kind": "model", "namespace": namespace,
                "profile": PRECISION_PROFILE, "calls": calls,
                "passes": passes, "required": GX_COORDINATE_FIXTURES,
                "patch_phase_coverage": coverage, "pass": result_pass}

    n_fixtures = 1 if claim in DIAGNOSTIC_CLAIMS else MODEL_CLAIM_FIXTURES
    required = (2 if claim in DIAGNOSTIC_CLAIMS
                else MODEL_CLAIM_REQUIRED_PASSES)
    for index in range(n_fixtures):
        fixture = builder(namespace, index, base_seed)
        if claim == "GT_text_exact":
            for perm_index in range(MODEL_CLAIM_PERMUTATIONS):
                tag = f"gt_{namespace}_{index}_{perm_index}"
                prefix = "" if perm_index == 0 else (
                    "(The records below repeat the same evidence in a different "
                    "order.)\n")
                items = [{"type": "text",
                          "text": prefix + fixture["ledger"] + "\n\n" + fixture["question"]}]
                validator = make_validator(fixture["int_keys"],
                                           fixture.get("str_keys", ()))
                record, payload, _ = srun.ask_chat(
                    vlm, [{"role": "user", "content": items}], [],
                    seed=fixture_seed(namespace, f"{claim}:{perm_index}", index,
                                      base_seed) % 2**64,
                    max_tokens=answer_tokens, run_dir=run_dir, tag=tag,
                    payload_validator=validator,
                )
                score = score_call(payload, fixture["truth"], fixture["int_keys"])
                passes += bool(score["pass"])
                calls.append({"tag": tag, "score": score, "payload": payload,
                              "truth": fixture["truth"], "round": record})
            continue
        if claim == "GP_interaction":
            for perm_index in range(MODEL_CLAIM_PERMUTATIONS):
                tag = f"gp_{namespace}_{index}_{perm_index}"
                pages = list(fixture["initial_pages"])
                if perm_index == 1:
                    pages = pages[::-1]
                initial_paths = _fixture_pages_to_files(pages, work, tag + "_init")
                messages: list[dict[str, Any]] = []
                items = []
                for page_no, path in enumerate(initial_paths, start=1):
                    items.append({"type": "text", "text": f"Page {page_no} of 10:"})
                    items.append({"type": "image"})
                images = list(initial_paths)
                messages.append({"role": "user", "content": items})
                for round_entry in fixture["rounds"]:
                    round_items = [{"type": "text", "text": round_entry["text"]}]
                    for name, plate in round_entry["pages"]:
                        round_items.append({"type": "text", "text": f"{name}:"})
                        round_items.append({"type": "image"})
                        images.append(plate.save(work / f"{tag}_{name}.png"))
                    messages.append({"role": "user", "content": round_items})
                messages.append({"role": "user",
                                 "content": [{"type": "text",
                                              "text": fixture["question"]}]})
                validator = make_validator(fixture["int_keys"],
                                           fixture.get("str_keys", ()))
                record, payload, _ = srun.ask_chat(
                    vlm, messages, images,
                    seed=fixture_seed(namespace, f"{claim}:{perm_index}", index,
                                      base_seed) % 2**64,
                    max_tokens=answer_tokens, run_dir=run_dir, tag=tag,
                    payload_validator=validator,
                )
                score = score_call(payload, fixture["truth_static"], fixture["int_keys"])
                passes += bool(score["pass"])
                calls.append({"tag": tag, "score": score, "payload": payload,
                              "truth": fixture["truth_static"], "round": record})
            continue
        # page-permutation claims: GV, GO, GD
        n_pages = len(fixture["pages"])
        permutations = counter_permutations(
            n_pages, fixture_seed(namespace, f"{claim}:perm", index, base_seed)
        )
        for perm_index, permutation in enumerate(permutations):
            tag = f"{claim.split('_')[0].lower()}_{namespace}_{index}_{perm_index}"
            ordered = [fixture["pages"][i] for i in permutation]
            paths = _fixture_pages_to_files(ordered, work, tag)
            items = []
            for page_no, path in enumerate(paths, start=1):
                items.append({"type": "text", "text": f"Page {page_no} of {len(paths)}:"})
                items.append({"type": "image"})
            items.append({"type": "text", "text": fixture["question"]})
            truth = permuted_truth(fixture, permutation)
            validator = make_validator(fixture["int_keys"], fixture.get("str_keys", ()))
            record, payload, _ = srun.ask_chat(
                vlm, [{"role": "user", "content": items}], paths,
                seed=fixture_seed(namespace, f"{claim}:{perm_index}", index,
                                  base_seed) % 2**64,
                max_tokens=answer_tokens, run_dir=run_dir, tag=tag,
                payload_validator=validator,
            )
            score = score_call(payload, truth, fixture["int_keys"])
            passes += bool(score["pass"])
            calls.append({"tag": tag, "permutation": permutation, "score": score,
                          "payload": payload, "truth": truth, "round": record})

    result = {
        "claim": claim,
        "kind": "model_diagnostic" if claim in DIAGNOSTIC_CLAIMS else "model",
        "namespace": namespace, "calls": calls, "passes": passes,
        "required": required, "pass": passes >= required,
    }
    if claim in DIAGNOSTIC_CLAIMS:
        result["blocking"] = False
        result["note"] = "reported diagnostic; consumed by no arm requirement set"
    return result


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

    if args.build_fixtures_only:
        out_root = DEV_FIXTURES if args.namespace == "dev" else CONFIRM_FIXTURES
        manifest: dict[str, Any] = {"namespace": args.namespace,
                                    "base_seed": args.base_seed, "claims": {}}
        for claim in args.claims:
            if claim == "G0_protocol_serving":
                continue
            builder = FIXTURE_BUILDERS[claim]
            count = (GX_COORDINATE_FIXTURES if claim == GX_CLAIM
                     else 1 if claim in DIAGNOSTIC_CLAIMS else MODEL_CLAIM_FIXTURES)
            digests = []
            for index in range(count):
                fixture = builder(args.namespace, index, args.base_seed)
                verify_fixture_decode(claim, fixture)
                serializable = {k: v for k, v in fixture.items() if k != "pages"
                                and k != "initial_pages" and k != "rounds"}
                digests.append(canonical_sha256(serializable))
            manifest["claims"][claim] = {"fixtures": count, "digests": digests}
            print(f"{claim}: {count} fixtures verified (procedural truth == PNG decode)")
        out_root.mkdir(parents=True, exist_ok=True)
        path = out_root / f"fixture_manifest_{args.base_seed}.json"
        path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        print(f"wrote {path}")
        return 0

    if not args.run:
        parser.error("pass --build-fixtures-only or --run")
    if args.namespace == "confirm":
        frozen_path = SEALED_R4 / "FROZEN.json"
        require(frozen_path.is_file(),
                "confirm-namespace gate runs require the sealed FROZEN.json")
    import e2_probe_vlm as probe

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = ROOT / f"logs/s4_gate_runs/{stamp}_{args.namespace}"
    run_dir.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}
    results["G0_protocol_serving"] = g0_protocol_serving(args.model)
    vlm = probe.Vlm(args.model)
    for claim in args.claims:
        if claim == "G0_protocol_serving":
            continue
        results[claim] = run_model_claim(
            vlm, claim, args.namespace, args.base_seed, run_dir,
            answer_tokens=20_000,
        )
        print(f"{claim}: {results[claim]['passes']}/{results[claim]['required']} "
              f"-> {'PASS' if results[claim]['pass'] else 'FAIL'}")
    eligibility = derive_arm_eligibility(results, list(ARM_REQUIREMENTS))
    payload = {
        "format_version": FORMAT_VERSION, "protocol_version": PROTOCOL_VERSION,
        "namespace": args.namespace, "base_seed": args.base_seed,
        "thresholds": THRESHOLDS, "results": results, "eligibility": eligibility,
        "run_dir": str(run_dir),
    }
    out = run_dir / "claims.json"
    out.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
