"""Semantics-free exact temporal delta records (slice-4 protocol revision 4).

For every selected transition and live probe result the packet carries a
deterministic record derived only from the observed arrays:

  - the ordered frame IDs (pre, intermediates, settled/response frames);
  - changed-cell count and inclusive bounding box per adjacent frame pair;
  - a palette-transition histogram per pair;
  - exact sparse deltas as ``(row, col, before, after)``; and
  - a lossless compact run-length delta when the sparse form would exceed its
    frozen limit.

These records state what changed, never what any object means or what the goal
is.  Every derived fact is bound to the frame/TID/EID it came from and to the
SHA-256 of the exact grids it was computed over, so a record can be re-derived
and byte-compared by an auditor without trusting the builder.

Pure functions over ``list[list[int]]`` grids; no model, no file system, no
game knowledge.  Frozen limits live here and are bound into FROZEN.json.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

FORMAT_VERSION = 1

# Frozen limit: a pair whose changed-cell count exceeds this is carried as a
# lossless run-length delta instead of one quadruple per cell.  96 cells keeps
# the worst sparse pair under ~1.3k characters while covering every observed
# single-object event in the pilot games.
SPARSE_DELTA_LIMIT = 96


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validated(grid: Any, label: str) -> list[list[int]]:
    require(isinstance(grid, (list, tuple)) and grid, f"{label}: empty or invalid grid")
    width = None
    rows: list[list[int]] = []
    for row_index, row in enumerate(grid):
        require(isinstance(row, (list, tuple)) and row, f"{label}: row {row_index} invalid")
        width = len(row) if width is None else width
        require(len(row) == width, f"{label}: not rectangular")
        out_row = []
        for value in row:
            value = int(value)
            require(0 <= value <= 15, f"{label}: non-palette value {value}")
            out_row.append(value)
        rows.append(out_row)
    return rows


def grid_sha256(grid: Any, label: str = "grid") -> str:
    return canonical_sha256(_validated(grid, label))


def pair_delta(pre: Any, post: Any, *, label: str = "pair") -> dict[str, Any]:
    """Exact change description for one adjacent frame pair."""
    pre_rows = _validated(pre, f"{label}.pre")
    post_rows = _validated(post, f"{label}.post")
    require(len(pre_rows) == len(post_rows) and len(pre_rows[0]) == len(post_rows[0]),
            f"{label}: pre/post shapes differ")
    changed: list[tuple[int, int, int, int]] = []
    histogram: dict[str, int] = {}
    r0 = c0 = None
    r1 = c1 = -1
    for r, (pre_row, post_row) in enumerate(zip(pre_rows, post_rows)):
        for c, (before, after) in enumerate(zip(pre_row, post_row)):
            if before == after:
                continue
            changed.append((r, c, before, after))
            key = f"{before}->{after}"
            histogram[key] = histogram.get(key, 0) + 1
            r0 = r if r0 is None else min(r0, r)
            c0 = c if c0 is None else min(c0, c)
            r1 = max(r1, r)
            c1 = max(c1, c)
    record: dict[str, Any] = {
        "changed_cells": len(changed),
        "bbox": None if r0 is None else [r0, c0, r1, c1],
        "palette_transitions": {key: histogram[key] for key in sorted(histogram)},
    }
    if len(changed) <= SPARSE_DELTA_LIMIT:
        record["sparse"] = [list(item) for item in changed]
    else:
        record["rle"] = _rle_delta(changed)
    return record


def _rle_delta(changed: Sequence[tuple[int, int, int, int]]) -> list[str]:
    """Lossless compact delta: row-major runs of consecutive cells sharing one
    ``before->after`` transition, encoded ``r<row>:c<first>-c<last>:<before>><after>``."""
    runs: list[str] = []
    active: tuple[int, int, int, int, int] | None = None  # row, c_first, c_last, before, after
    for r, c, before, after in changed:  # changed is generated row-major
        if active is not None and active[0] == r and active[2] + 1 == c \
                and active[3] == before and active[4] == after:
            active = (active[0], active[1], c, before, after)
            continue
        if active is not None:
            runs.append(_format_run(active))
        active = (r, c, c, before, after)
    if active is not None:
        runs.append(_format_run(active))
    return runs


def _format_run(run: tuple[int, int, int, int, int]) -> str:
    row, c_first, c_last, before, after = run
    span = f"c{c_first}" if c_first == c_last else f"c{c_first}-c{c_last}"
    return f"r{row}:{span}:{before}>{after}"


def decode_rle_delta(runs: Sequence[str]) -> list[tuple[int, int, int, int]]:
    """Exact inverse of ``_rle_delta`` — auditors re-derive and compare."""
    out: list[tuple[int, int, int, int]] = []
    for run in runs:
        row_part, span, transition = run.split(":")
        require(row_part.startswith("r") and ">" in transition, f"malformed run {run!r}")
        row = int(row_part[1:])
        before, after = (int(v) for v in transition.split(">"))
        if "-" in span:
            first, last = span.split("-")
            c_first, c_last = int(first[1:]), int(last[1:])
        else:
            c_first = c_last = int(span[1:])
        for c in range(c_first, c_last + 1):
            out.append((row, c, before, after))
    return out


def apply_pair_delta(pre: Any, record: dict[str, Any]) -> list[list[int]]:
    """Apply a pair record to its pre grid; the result must equal the post grid."""
    rows = [list(row) for row in _validated(pre, "apply.pre")]
    if record.get("changed_cells", 0) == 0:
        return rows
    cells = ([tuple(item) for item in record["sparse"]] if "sparse" in record
             else decode_rle_delta(record["rle"]))
    require(len(cells) == record["changed_cells"], "delta cell count mismatch")
    for r, c, before, after in cells:
        require(rows[r][c] == before, f"delta base mismatch at ({r},{c})")
        rows[r][c] = after
    return rows


def sequence_record(
    frame_ids: Sequence[str],
    grids: Sequence[Any],
    *,
    binding: dict[str, Any],
) -> dict[str, Any]:
    """The full semantics-free record for one ordered observed frame sequence.

    ``binding`` names where the frames came from (tid / eid / probe label …) and
    is stored verbatim; the grids themselves are bound by per-frame SHA-256.
    """
    require(len(frame_ids) == len(grids) and len(grids) >= 1,
            "sequence record needs matched non-empty frame_ids/grids")
    require(all(isinstance(fid, str) and fid for fid in frame_ids),
            "frame ids must be non-empty strings")
    require(isinstance(binding, dict) and binding, "binding must be a non-empty object")
    frames = [{"frame_id": fid, "grid_sha256": grid_sha256(grid, fid)}
              for fid, grid in zip(frame_ids, grids)]
    pairs = []
    for index in range(len(grids) - 1):
        pair = pair_delta(grids[index], grids[index + 1],
                          label=f"{frame_ids[index]}->{frame_ids[index + 1]}")
        pairs.append({"pre": frame_ids[index], "post": frame_ids[index + 1], **pair})
    record = {
        "kind": "temporal_delta_record",
        "format_version": FORMAT_VERSION,
        "sparse_delta_limit": SPARSE_DELTA_LIMIT,
        "binding": dict(binding),
        "frames": frames,
        "pairs": pairs,
    }
    record["record_sha256"] = canonical_sha256(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )
    return record


def verify_sequence_record(record: dict[str, Any], grids: Sequence[Any]) -> None:
    """Re-derive the record from the grids and require byte equality."""
    require(record.get("kind") == "temporal_delta_record"
            and record.get("format_version") == FORMAT_VERSION,
            "not a temporal delta record")
    rebuilt = sequence_record(
        [frame["frame_id"] for frame in record["frames"]], grids,
        binding=record["binding"],
    )
    require(rebuilt == record, "temporal delta record does not re-derive from its grids")
    for index in range(len(grids) - 1):
        applied = apply_pair_delta(grids[index], record["pairs"][index])
        require(grid_sha256(applied) == record["frames"][index + 1]["grid_sha256"],
                f"pair {index} does not reproduce its post frame")


def render_text_block(record: dict[str, Any], *, include_cells: bool = True) -> str:
    """Compact deterministic text rendering for the ledger (semantics-free).

    ``include_cells=False`` emits only the per-pair summary lines (count, bbox,
    palette histogram); use it when the same transitions' exact boards are
    already losslessly encoded elsewhere in the carrier, so cell lists would be
    redundant token spend.  The full record still travels in the manifest.
    """
    lines = [
        "DELTA-RECORD "
        + json.dumps(record["binding"], sort_keys=True, separators=(",", ":")),
        "frames " + " ".join(frame["frame_id"] for frame in record["frames"]),
    ]
    for pair in record["pairs"]:
        head = (f"{pair['pre']}->{pair['post']} changed={pair['changed_cells']} "
                f"bbox={pair['bbox']} "
                + json.dumps(pair["palette_transitions"], sort_keys=True,
                             separators=(",", ":")))
        lines.append(head)
        if not include_cells:
            continue
        if pair.get("sparse") is not None:
            lines.append("cells " + ";".join(
                f"({r},{c}):{b}>{a}" for r, c, b, a in pair["sparse"]))
        elif pair.get("rle") is not None:
            lines.append("rle " + ";".join(pair["rle"]))
    return "\n".join(lines)
