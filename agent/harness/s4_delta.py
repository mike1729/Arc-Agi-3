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
import re
import string
from collections import Counter
from itertools import groupby
from typing import Any, Sequence

FORMAT_VERSION = 1

# Frozen limit: a pair whose changed-cell count exceeds this is carried as a
# lossless run-length delta instead of one quadruple per cell.  96 cells keeps
# the worst sparse pair under ~1.3k characters while covering every observed
# single-object event in the pilot games.
SPARSE_DELTA_LIMIT = 96

# Every cell of a 64x64 pair is recoverable from the model-facing carrier.  The
# constant remains explicit because packet/run validators bind it into the
# experiment; 4096 means there is no summary-only large-delta branch.
MODEL_VISIBLE_CELL_LIMIT = 64 * 64

_MASK_CODES = string.ascii_lowercase + string.ascii_uppercase


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
    validate_sequence_record_structure(record)
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


def validate_sequence_record_structure(record: Any) -> dict[str, Any]:
    """Fail closed on a record even when the source grids are not loaded.

    This validates the lossless cell payload, summaries, chain, and record hash.
    ``verify_sequence_record`` remains the stronger grid-level audit.
    """
    require(isinstance(record, dict), "temporal delta record must be an object")
    require(set(record) == {
        "kind", "format_version", "sparse_delta_limit", "binding", "frames",
        "pairs", "record_sha256",
    }, "temporal delta record has an incomplete or unknown schema")
    require(record["kind"] == "temporal_delta_record"
            and record["format_version"] == FORMAT_VERSION
            and record["sparse_delta_limit"] == SPARSE_DELTA_LIMIT,
            "temporal delta version/limit drift")
    require(isinstance(record["binding"], dict) and record["binding"],
            "temporal delta binding is empty")
    expected_sha = canonical_sha256(
        {key: value for key, value in record.items() if key != "record_sha256"}
    )
    require(record["record_sha256"] == expected_sha,
            "temporal delta record digest mismatch")
    frames = record["frames"]
    require(isinstance(frames, list) and len(frames) >= 1,
            "temporal delta record needs at least one bound frame")
    frame_ids: list[str] = []
    for frame in frames:
        require(isinstance(frame, dict) and set(frame) == {"frame_id", "grid_sha256"},
                "temporal delta frame has an invalid schema")
        require(isinstance(frame["frame_id"], str) and frame["frame_id"],
                "temporal delta frame ID is empty")
        require(isinstance(frame["grid_sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", frame["grid_sha256"]) is not None,
                "temporal delta frame grid digest is invalid")
        frame_ids.append(frame["frame_id"])
    require(len(set(frame_ids)) == len(frame_ids),
            "temporal delta frame IDs are not unique")
    pairs = record["pairs"]
    require(isinstance(pairs, list) and len(pairs) == len(frames) - 1,
            "temporal delta pair count does not match its frame chain")
    for index, pair in enumerate(pairs):
        require(isinstance(pair, dict), "temporal delta pair must be an object")
        has_sparse, has_rle = "sparse" in pair, "rle" in pair
        expected_keys = {
            "pre", "post", "changed_cells", "bbox", "palette_transitions",
            "sparse" if has_sparse else "rle",
        }
        require(has_sparse != has_rle and set(pair) == expected_keys,
                "temporal delta pair has an invalid exact schema")
        require(pair["pre"] == frame_ids[index]
                and pair["post"] == frame_ids[index + 1],
                "temporal delta pair breaks its frame chain")
        raw_cells = pair["sparse"] if has_sparse else decode_rle_delta(pair["rle"])
        require(isinstance(raw_cells, list), "temporal delta cell payload is invalid")
        cells = [tuple(cell) for cell in raw_cells]
        require(all(len(cell) == 4 and all(type(value) is int for value in cell)
                    for cell in cells),
                "temporal delta cells must be integer quadruples")
        require(all(0 <= r < 64 and 0 <= c < 64 and 0 <= before <= 15
                    and 0 <= after <= 15 and before != after
                    for r, c, before, after in cells),
                "temporal delta cell is outside the 64x64 palette grid")
        require(cells == sorted(cells, key=lambda cell: (cell[0], cell[1]))
                and len({(cell[0], cell[1]) for cell in cells}) == len(cells),
                "temporal delta cells are duplicated or not row-major")
        require(pair["changed_cells"] == len(cells),
                "temporal delta changed-cell count mismatch")
        require(has_sparse == (len(cells) <= SPARSE_DELTA_LIMIT),
                "temporal delta sparse/RLE threshold drift")
        bbox = (None if not cells else [
            min(cell[0] for cell in cells), min(cell[1] for cell in cells),
            max(cell[0] for cell in cells), max(cell[1] for cell in cells),
        ])
        require(pair["bbox"] == bbox, "temporal delta bbox mismatch")
        histogram: dict[str, int] = {}
        for _r, _c, before, after in cells:
            key = f"{before}->{after}"
            histogram[key] = histogram.get(key, 0) + 1
        require(pair["palette_transitions"]
                == {key: histogram[key] for key in sorted(histogram)},
                "temporal delta palette histogram mismatch")
    return record


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


def _pair_cells(pair: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    cells = ([tuple(item) for item in pair["sparse"]] if "sparse" in pair
             else decode_rle_delta(pair["rle"]))
    require(len(cells) == pair["changed_cells"],
            "model carrier delta cell count mismatch")
    return cells


def _rle_symbols(symbols: Sequence[str], *, separated: bool) -> str:
    runs: list[str] = []
    for symbol, values in groupby(symbols):
        count = sum(1 for _ in values)
        if separated:
            runs.append(symbol + (f"*{count}" if count > 1 else ""))
        else:
            runs.append(symbol + (str(count) if count > 1 else ""))
    return ("," if separated else "").join(runs)


def _repeat_rows(rows: Sequence[str]) -> str:
    groups: list[str] = []
    for row, values in groupby(rows):
        count = sum(1 for _ in values)
        groups.append(row + (f"^{count}" if count > 1 else ""))
    return "/".join(groups)


def encode_exact_pair(pair: dict[str, Any]) -> str:
    """Lossless, compact, model-readable encoding for one 64x64 delta pair.

    The bbox anchors a row/flat RLE. ``.`` means unchanged.  The usual mapped
    form assigns a single letter to each ``before>after`` transition.  A
    delimiter-safe hexadecimal fallback covers the full 240-transition domain.
    The shorter row-repeated or flat form is selected without consulting any
    model result.
    """
    changed = pair.get("changed_cells")
    require(type(changed) is int and 0 <= changed <= MODEL_VISIBLE_CELL_LIMIT,
            "model carrier changed-cell count is invalid")
    if changed == 0:
        require(pair.get("bbox") is None, "zero delta unexpectedly has a bbox")
        return "-"
    cells = _pair_cells(pair)
    bbox = pair.get("bbox")
    require(isinstance(bbox, list) and len(bbox) == 4,
            "non-empty delta lacks a bbox")
    r0, c0, r1, c1 = bbox
    transitions = list(dict.fromkeys((before, after)
                                     for _r, _c, before, after in cells))
    cell_transitions = {(r, c): (before, after)
                        for r, c, before, after in cells}
    prefix = ",".join(str(value) for value in bbox)
    candidates: list[str] = []

    def bodies(symbol_at, *, separated: bool) -> tuple[str, str]:
        rows = []
        flat: list[str] = []
        for row in range(r0, r1 + 1):
            symbols = [symbol_at(row, col) for col in range(c0, c1 + 1)]
            rows.append(_rle_symbols(symbols, separated=separated))
            flat.extend(symbols)
        return _repeat_rows(rows), _rle_symbols(flat, separated=separated)

    if len(transitions) <= len(_MASK_CODES):
        codes = {transition: _MASK_CODES[index]
                 for index, transition in enumerate(transitions)}
        mapping = ",".join(
            f"{codes[transition]}={transition[0]}>{transition[1]}"
            for transition in transitions
        )
        rows, flat = bodies(
            lambda row, col: codes[cell_transitions[(row, col)]]
            if (row, col) in cell_transitions else ".",
            separated=False,
        )
        candidates.extend((
            f"{prefix}|M:{mapping}|R:{rows}",
            f"{prefix}|M:{mapping}|F:{flat}",
        ))

    rows, flat = bodies(
        lambda row, col: (
            f"{cell_transitions[(row, col)][0]:x}"
            f"{cell_transitions[(row, col)][1]:x}"
        ) if (row, col) in cell_transitions else ".",
        separated=True,
    )
    candidates.extend((
        f"{prefix}|H|R:{rows}",
        f"{prefix}|H|F:{flat}",
    ))
    encoded = min(candidates, key=lambda value: (len(value), value))
    require(decode_exact_pair(encoded) == cells,
            "model-facing exact delta does not round-trip")
    return encoded


def _decode_symbol_runs(
    text: str, *, mapping: dict[str, tuple[int, int]] | None,
) -> list[tuple[int, int] | None]:
    decoded: list[tuple[int, int] | None] = []
    if mapping is not None:
        position = 0
        pattern = re.compile(r"([.A-Za-z])(\d*)")
        while position < len(text):
            match = pattern.match(text, position)
            require(match is not None, "malformed mapped exact-delta RLE")
            symbol, raw_count = match.groups()
            require(symbol == "." or symbol in mapping,
                    "unknown exact-delta transition code")
            count = int(raw_count or "1")
            require(count > 0, "zero-length exact-delta run")
            value = None if symbol == "." else mapping[symbol]
            decoded.extend([value] * count)
            position = match.end()
        return decoded

    require(bool(text), "empty hexadecimal exact-delta row")
    for run in text.split(","):
        symbol, raw_count = run.split("*", 1) if "*" in run else (run, "1")
        require(symbol == "." or re.fullmatch(r"[0-9a-f]{2}", symbol) is not None,
                "malformed hexadecimal exact-delta symbol")
        count = int(raw_count)
        require(count > 0, "zero-length exact-delta run")
        if symbol == ".":
            value = None
        else:
            value = (int(symbol[0], 16), int(symbol[1], 16))
            require(value[0] != value[1],
                    "hex exact-delta run encodes an unchanged cell")
        decoded.extend([value] * count)
    return decoded


def decode_exact_pair(encoded: str) -> list[tuple[int, int, int, int]]:
    """Exact inverse of :func:`encode_exact_pair`, for packet/run audits."""
    if encoded == "-":
        return []
    parts = encoded.split("|", 2)
    require(len(parts) == 3, "exact-delta carrier needs bbox, codec, and body")
    bbox_text, codec, body = parts
    bbox = [int(value) for value in bbox_text.split(",")]
    require(len(bbox) == 4, "exact-delta bbox is malformed")
    r0, c0, r1, c1 = bbox
    require(0 <= r0 <= r1 < 64 and 0 <= c0 <= c1 < 64,
            "exact-delta bbox is outside the board")
    mapping: dict[str, tuple[int, int]] | None
    if codec.startswith("M:"):
        mapping = {}
        raw_mapping = codec.removeprefix("M:")
        require(bool(raw_mapping), "mapped exact-delta codec is empty")
        for item in raw_mapping.split(","):
            symbol, transition = item.split("=", 1)
            before_text, after_text = transition.split(">", 1)
            before, after = int(before_text), int(after_text)
            require(len(symbol) == 1 and symbol in _MASK_CODES
                    and symbol not in mapping and 0 <= before <= 15
                    and 0 <= after <= 15 and before != after,
                    "mapped exact-delta dictionary is invalid")
            mapping[symbol] = (before, after)
    else:
        require(codec == "H", "unknown exact-delta codec")
        mapping = None
    mode, payload = body.split(":", 1)
    require(mode in {"R", "F"}, "unknown exact-delta layout")
    width, height = c1 - c0 + 1, r1 - r0 + 1
    values: list[tuple[int, int] | None] = []
    if mode == "F":
        values = _decode_symbol_runs(payload, mapping=mapping)
        require(len(values) == width * height,
                "flat exact-delta payload has the wrong area")
    else:
        rows: list[list[tuple[int, int] | None]] = []
        for grouped in payload.split("/"):
            row_text, raw_repeat = (grouped.rsplit("^", 1)
                                    if "^" in grouped else (grouped, "1"))
            repeat = int(raw_repeat)
            require(repeat > 0, "zero exact-delta row repetition")
            row = _decode_symbol_runs(row_text, mapping=mapping)
            require(len(row) == width, "exact-delta row has the wrong width")
            rows.extend([list(row) for _ in range(repeat)])
        require(len(rows) == height, "exact-delta payload has the wrong height")
        values = [value for row in rows for value in row]
    cells = []
    for offset, transition in enumerate(values):
        if transition is None:
            continue
        row, col = divmod(offset, width)
        cells.append((r0 + row, c0 + col, transition[0], transition[1]))
    return cells


def render_carrier_block(record: dict[str, Any]) -> str:
    """Compact, model-facing rendering of a complete audited record.

    TID/EID bindings, ordered frame suffixes, and every exact pair delta are
    visible.  No large-change summary branch exists.
    """
    validate_sequence_record_structure(record)
    binding = record["binding"]
    tid = str(
        binding.get("tid") or binding.get("start_tid")
        or binding.get("probe_label") or "-"
    )
    evidence_ids = binding.get("evidence_ids") or []
    eid_text = ",".join(str(value) for value in evidence_ids) or "-"

    def short_frame(frame_id: str) -> str:
        prefix = tid + "."
        suffix = frame_id[len(prefix):] if frame_id.startswith(prefix) else frame_id
        return suffix.replace("frame:", "f")

    frames = ",".join(short_frame(frame["frame_id"]) for frame in record["frames"])
    lines = [f"D {tid} eids={eid_text} frames={frames}"]
    lines.append(
        "codec bbox|M:code=before>after|R(row-RLE) or F(flat-RLE); "
        ".=unchanged; ^N repeats a row"
    )
    for index, pair in enumerate(record["pairs"]):
        lines.append(f"p{index}={encode_exact_pair(pair)}")
    return "\n".join(lines)


def render_carrier_collection(records: Sequence[dict[str, Any]]) -> str:
    """Dictionary-compress exact pair masks without hiding any changed cell."""
    payloads: list[str] = []
    for record in records:
        validate_sequence_record_structure(record)
        for pair in record["pairs"]:
            encoded = encode_exact_pair(pair)
            require(decode_exact_pair(encoded) == _pair_cells(pair),
                    "exact pair carrier lost a changed cell")
            payloads.append(encoded)
    counts = Counter(payloads)
    aliases = {
        payload: f"m{index}"
        for index, payload in enumerate(
            value for value in dict.fromkeys(payloads)
            if value != "-" and counts[value] >= 2
        )
    }

    lines = [
        "TEMPORAL-EXACT: pair=bbox|transition-codes|row/flat-RLE; "
        ".=unchanged; ^N=row repeat; every changed cell is recoverable"
    ]
    for payload, alias in aliases.items():
        lines.append(f"M {alias}={payload}")

    payload_index = 0
    for record in records:
        binding = record["binding"]
        tid = str(binding.get("tid") or "-")
        def short_frame(frame_id: str) -> str:
            prefix = tid + "."
            suffix = frame_id[len(prefix):] if frame_id.startswith(prefix) else frame_id
            return suffix.replace("frame:", "f")

        short_frames = [short_frame(frame["frame_id"]) for frame in record["frames"]]
        frame_prefix = short_frames[:1] if short_frames[:1] == ["pre"] else []
        response_frames = short_frames[len(frame_prefix):]
        if len(response_frames) >= 3 and response_frames == [
            f"f{index}" for index in range(len(response_frames))
        ]:
            short_frames = frame_prefix + [f"f0-f{len(response_frames) - 1}"]
        frames = ",".join(short_frames)
        default_frames = "pre,f0" if tid.startswith("S") else (
            "pre,post" if tid.startswith("K") else ""
        )
        frame_field = "" if frames == default_frames else f" f={frames}"
        record_payloads = payloads[payload_index:payload_index + len(record["pairs"])]
        payload_index += len(record["pairs"])
        pair_codes = ";".join(aliases.get(payload, payload)
                              for payload in record_payloads) or "-"
        lines.append(f"D {tid}{frame_field} p={pair_codes}")
    require(payload_index == len(payloads), "exact carrier payload accounting drift")
    return "\n".join(lines)
