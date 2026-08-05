#!/usr/bin/env python3
"""E2 slice 3, build item 2 — the renderer. A deduplicated, object-linked causal record.

`notes/e2-slice3.md` (revised after external review). Zero model calls; every function here
is a pure rendering of grids this project already holds.

WHY THIS EXISTS
---------------
In the entire E2 line the model has never seen a grid. Digests v1-v3 are feature-space
summaries — action keys, guard value sets, census counts — and slice 2 measured every textual
proxy for "look at the board" dead: the inert-object INVENTORY, positions and box sizes in
prose, produced 0 of 8 correct goals.

WHAT THE REVIEW CORRECTED, AND WHY THIS FILE IS NOT A PILE OF BOARDS
--------------------------------------------------------------------
The first draft of the note planned three or four full 64x64 text renders on the grounds that
ascii boards are "proven readable". That was too strong, and the reference harness's own
instructions say the opposite: use segmentation as the primary view, use ascii only to read a
small specific region, never scan a whole board with it. So the allocation here is
ENTITY TABLES + TARGETED CROPS, with the initial board rendered exactly once as the shared
coordinate frame everything else refers back to.

The consequence is that this record is deduplicated by construction: no state is rendered
twice, later frames are described as differences from the one board that is shown, and a full
snapshot appears only where the scene's topology changed enough that a difference would be
harder to read than a board.

PROVENANCE — every block carries a tag
--------------------------------------
    OBSERVED          recorded frames and actions, as stored
    REPLAY-VERIFIED   re-executed against the engine today and confirmed cell for cell
    MINER-INFERRED    rules, effect classes, statuses and failure typing — derived, fallible

Slice 2 blurred these, and a mined majority-tier rule was read as ground truth. The prompt
states the distinction once and every section header carries its tag.

CONVENTIONS INHERITED, NOT CHOSEN HERE
--------------------------------------
Objects are `es_candidates._Objects`: 4-connected same-colour components over the state-local
background. Entities and their stable ids come from `e2_entities`. The letter table is the
reference harness's colour legend; the letter -> VALUE binding is verified against the shipped
environment sources, which declare the sixteen colour constants as `range(16)` in this order,
so `R` is colour 8 as a matter of record rather than of guesswork.

PUBLISHING: rendered frames of competition games are fine in LOCAL logs and prompts and must
never reach a committed artifact. Nothing here writes to `logs/`; callers own that rule.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_entities as ent  # noqa: E402

# ---------------------------------------------------------------------------------------
# Colour coding
# ---------------------------------------------------------------------------------------
LETTERS = "WwgGcBMPRbSYOrNp"
NAMES = (
    "white", "off-white", "gray", "dark gray", "off-black", "black", "magenta", "pink",
    "red", "blue", "light blue", "yellow", "orange", "maroon", "green", "purple",
)

# Crop geometry. Crops are ADAPTIVE — sized to the union of changed cells, not to a fixed
# 11x11 — because 11x11 is simply wrong for a global effect, and a window that silently shows
# a fraction of the change is worse than a full board that says it is one.
CROP_MARGIN = 3
MAX_CROP_SPAN = 26  # beyond this a crop stops being a crop; render the board and say so


def letter(value: int) -> str:
    value = int(value)
    return LETTERS[value] if 0 <= value < len(LETTERS) else "?"


def colour_name(value: int) -> str:
    value = int(value)
    return NAMES[value] if 0 <= value < len(NAMES) else "unknown"


def legend_lines(values: Iterable[int]) -> list[str]:
    """The letter -> numeric-colour join, for the colours actually rendered.

    The digest speaks in numeric colours and the board speaks in letters; without this the
    two halves of the prompt are about different objects. This is the join slice 2 never had.
    """
    return [
        f"    {letter(v)} = colour {v:<3d} ({colour_name(v)})"
        for v in sorted({int(v) for v in values})
    ]


def grid_values(grid: Sequence[Sequence[int]]) -> set[int]:
    return {int(v) for row in grid for v in row}


# ---------------------------------------------------------------------------------------
# Grids and crops
# ---------------------------------------------------------------------------------------


def render_grid(
    grid: Sequence[Sequence[int]],
    *,
    row_range: tuple[int, int] | None = None,
    col_range: tuple[int, int] | None = None,
) -> list[str]:
    """A board as letters, with ABSOLUTE row and column rulers.

    Absolute even for a crop, so a coordinate read off a crop means the same thing in the
    initial board and in a predicate about it. One coordinate system for the whole record.
    """
    height = len(grid)
    width = len(grid[0]) if height else 0
    top, bottom = row_range or (0, height - 1)
    left, right = col_range or (0, width - 1)
    out = [
        "     " + "".join(
            str(col // 10) if col % 10 == 0 else " " for col in range(left, right + 1)
        ),
        "     " + "".join(str(col % 10) for col in range(left, right + 1)),
    ]
    for row in range(top, bottom + 1):
        out.append(f"{row:>4} " + "".join(letter(grid[row][col]) for col in range(left, right + 1)))
    return out


def changed_cells(
    pre: Sequence[Sequence[int]], post: Sequence[Sequence[int]]
) -> list[tuple[int, int, int, int]]:
    """`(row, col, before, after)` for every differing cell."""
    out = []
    for row, (pre_row, post_row) in enumerate(zip(pre, post, strict=True)):
        # Row equality first, at C speed. These boards are 64x64 and almost every row is
        # untouched by any single action, so the cell loop runs on a handful of rows instead
        # of all 64 — the difference between a two-second digest and a two-minute one once
        # this is called across a 3,000-transition store.
        if pre_row == post_row:
            continue
        for col, (a, b) in enumerate(zip(pre_row, post_row, strict=True)):
            if a != b:
                out.append((row, col, int(a), int(b)))
    return out


def ever_changed(store: list, post_missing: set[int]) -> set[tuple[int, int]]:
    """Every cell that changed at least once anywhere in the store.

    Its complement is the static layer — which the entity table reports as a COLUMN rather
    than as a second full board render. Completion rows are skipped: their post frame is a
    placeholder for the pre frame (`e2_dose.load_store`), so diffing them would report zero
    changed cells and quietly widen the static layer.
    """
    seen: set[tuple[int, int]] = set()
    for transition in store:
        if transition.step in post_missing:
            continue
        for row, col, _, _ in changed_cells(transition.pre, transition.post):
            seen.add((row, col))
    return seen


def crop_bounds(
    grid: Sequence[Sequence[int]], cells: Iterable[tuple[int, int]], *, margin: int = CROP_MARGIN
) -> tuple[tuple[int, int], tuple[int, int], bool]:
    """The window covering `cells` with a margin, and whether it is still a crop.

    Returns `(rows, cols, is_crop)`. When the union of interesting cells is wider than
    `MAX_CROP_SPAN` in either direction the caller is told to render the whole board instead —
    the alternative is a window that contains part of the change while looking like it
    contains all of it.
    """
    height = len(grid)
    width = len(grid[0]) if height else 0
    cells = list(cells)
    if not cells:
        return (0, height - 1), (0, width - 1), False
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    span_rows = max(rows) - min(rows) + 1
    span_cols = max(cols) - min(cols) + 1
    if span_rows > MAX_CROP_SPAN or span_cols > MAX_CROP_SPAN:
        return (0, height - 1), (0, width - 1), False
    return (
        (max(0, min(rows) - margin), min(height - 1, max(rows) + margin)),
        (max(0, min(cols) - margin), min(width - 1, max(cols) + margin)),
        True,
    )


def render_pair(
    pre: Sequence[Sequence[int]],
    post: Sequence[Sequence[int]],
    cells: Iterable[tuple[int, int]],
    *,
    indent: str = "    ",
) -> list[str]:
    """`before` and `after` side by side over one adaptive window, sharing a row ruler.

    Side by side rather than stacked: the two boards are meant to be COMPARED cell by cell,
    and stacking puts a screen of text between the cells being compared.
    """
    rows, cols, is_crop = crop_bounds(pre, cells)
    before = render_grid(pre, row_range=rows, col_range=cols)
    after = render_grid(post, row_range=rows, col_range=cols)
    width = max(len(line) for line in before)
    header = (
        f"{indent}rows {rows[0]}-{rows[1]}, cols {cols[0]}-{cols[1]}"
        if is_crop
        else f"{indent}the change is too spread out to crop — the FULL board, before | after"
    )
    return [f"{header}   (before | after)"] + [
        f"{indent}{b.ljust(width)}   |   {a}" for b, a in zip(before, after, strict=True)
    ]


# ---------------------------------------------------------------------------------------
# The entity map
# ---------------------------------------------------------------------------------------


def entity_table(
    entities: list[ent.Entity], *, max_rows: int | None = None, columns: str = "full"
) -> list[str]:
    """The join between what the model sees and the handles its predicates must use.

    Nothing in any previous slice gave it this. The columns are chosen to be exactly what the
    predicate grammar quantifies over: `cN` (colour), bbox (`bbox_overlap`, `bbox_contains`,
    `row_aligned`, `col_aligned`), the normalized shape key (`same_shape`), and per-colour
    counts (`count`, `empty`, `exactly_one`).
    """
    compact = columns == "compact"
    lines = [
        "    id  colour  box(rows,cols)      size    cells  shape  status"
        + ("" if compact else "  contains / touches")
    ]
    shown = entities if max_rows is None else entities[:max_rows]
    for entity in shown:
        top, left, bottom, right = entity.bbox
        children = (
            ",".join(str(i) for i in entity.children[: ent.MAX_CHILDREN])
            + (f",+{len(entity.children) - ent.MAX_CHILDREN}" if len(entity.children) > ent.MAX_CHILDREN else "")
            if entity.children
            else "-"
        )
        touching = (
            ",".join(str(i) for i in entity.adjacent[: ent.MAX_ADJACENT])
            + (f",+{len(entity.adjacent) - ent.MAX_ADJACENT}" if len(entity.adjacent) > ent.MAX_ADJACENT else "")
            if entity.adjacent
            else "-"
        )
        lines.append(
            f"   #{entity.eid:<3d} c{entity.colour:<3d}{letter(entity.colour)}  "
            f"r{top:>2d}-{bottom:<2d} c{left:>2d}-{right:<2d}  "
            f"{entity.height:>2d}x{entity.width:<2d}  {entity.area:>5d}  "
            f"{entity.shape_key:<5s}  {entity.status:<7s}"
            + ("" if compact else f" {children} / {touching}")
        )
    if max_rows is not None and len(entities) > max_rows:
        lines.append(
            f"    (+{len(entities) - max_rows} further entities NOT listed — the table is "
            f"truncated, so absence from it means nothing here)"
        )
    repeated = [
        key for key, count in Counter(e.shape_key for e in entities).items() if count > 1
    ]
    if repeated:
        lines.append(
            f"    shape keys carried by more than one entity, i.e. pairs that satisfy "
            f"same_shape: {', '.join(sorted(repeated))}"
        )
    return lines


# ---------------------------------------------------------------------------------------
# Actions and histories
# ---------------------------------------------------------------------------------------


def action_text(transition: Any) -> str:
    if transition.action_id == 6:
        data = transition.action_data or {}
        return f"ACTION6(row={data.get('y')}, col={data.get('x')})"
    return f"ACTION{transition.action_id}"


def click_cell(transition: Any) -> tuple[int, int] | None:
    if transition.action_id != 6:
        return None
    data = transition.action_data or {}
    row, col = data.get("y"), data.get("x")
    return (row, col) if isinstance(row, int) and isinstance(col, int) else None


def chains(store: list) -> list[list]:
    """Maximal runs of stored transitions the explorer actually walked back to back.

    `e2_dose.load_store` shares one grid object per stored state digest, so `a.post is b.pre`
    is a digest comparison, not a deep one.
    """
    if not store:
        return []
    out = [[store[0]]]
    for previous, current in zip(store, store[1:]):
        if previous.post is current.pre and current.step == previous.step + 1:
            out[-1].append(current)
        else:
            out.append([current])
    return out


def history_lines(store: list, index: int, *, suffix: int = 8) -> list[str]:
    """The history that reached a stored transition — block 5's whole point.

    The first draft rendered the same board twice and omitted this. If two identical-looking
    situations behave differently, the suspected cause IS the history, so the exhibit has to
    carry it: where the last RESET was, how many actions since, the mix of action types, the
    recent action suffix, and the click-colour sequence. These are also exactly the
    quantities the counter grammar can express, so a latent proposed from this block is
    writable in the language that scores it.
    """
    reset_at = None
    for position in range(index, -1, -1):
        if store[position].action_id == 0:
            reset_at = position
            break
    window = store[(reset_at + 1 if reset_at is not None else 0) : index + 1]
    kinds = Counter(f"ACTION{t.action_id}" for t in window)
    recent = " -> ".join(action_text(t) for t in store[max(0, index - suffix + 1) : index + 1])
    clicks = [
        t.guards.get("click_colour")
        for t in window
        if t.action_id == 6 and t.guards.get("click_colour") is not None
    ]
    return [
        f"      last RESET: "
        + (f"{index - reset_at} actions ago" if reset_at is not None else "none in this record"),
        f"      actions since that point: {len(window)}   "
        f"by type: {', '.join(f'{k}x{v}' for k, v in sorted(kinds.items()))}",
        f"      last {min(suffix, index + 1)} actions: {recent}",
        f"      colours clicked since that point, in order: "
        + (", ".join(str(int(c)) for c in clicks[-16:]) if clicks else "none")
        + (f"   (last 16 of {len(clicks)})" if len(clicks) > 16 else ""),
    ]


# ---------------------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------------------


@dataclass
class FrameCaps:
    """Every cap that can change a reading. Declared in the prompt where it applies.

    Slice 1.1 measured what an undeclared cap costs: the digest asserted complete value sets
    while showing six features, and 21 of 24 traces then inferred "unlisted => constant".
    """

    episode_steps: int = 60
    diff_cells: int = 10
    snapshots: int = 2  # full boards inside the episode, at scene-phase changes
    gallery_keys: int = 8
    gallery_examples: int = 2
    unresolved_keys: int = 12
    key_examples: int = 2
    # 80 because the protocol set's opening frames hold 4-65 entities (measured): at this
    # value nothing truncates on any of the eight, so the table is COMPLETE and "absent from
    # the table" soundly means "not on the board".
    max_entities: int = 80
    # Rev 2's last trim step: `compact` drops the contains/touches columns, which are the
    # widest and the most redundant with the bboxes above them. The colour, box, size and
    # shape columns are never dropped — they are the join to the grammar.
    entity_columns: str = "full"
    alias_examples: int = 2
    refuted_examples: int = 2
    # MEASURED, and the reason this cap exists: on dc22 the crop falls back to a full
    # board whenever a change is too spread out to window, and blocks 4 and 4b together
    # produced 28 of them — 163k of a 248k-character record, four times the whole budget.
    # So the fallback is rationed: the first few global changes are shown as boards, and
    # after that the cell list and the changed bounding box carry it, with a pointer back.
    global_examples: int = 2
    completion_frames: int = 3  # intermediate frames rendered from the capture

    # Rev 2: three FULL frames only in block 3 (pre-completion, solved terminal, next
    # level). The capture keeps all 20/27 locally; rendering them would cost more than the
    # rest of the block together. Unique intermediates appear as compressed diffs instead.
    completion_diffs: int = 12


# ---------------------------------------------------------------------------------------
# Episode selection and contrast selection
# ---------------------------------------------------------------------------------------


def _episode(store: list, span: int, effect_mode) -> tuple[list, str]:
    """The window of consecutive actions to render, and why it was chosen.

    NOT "the deepest route", and not "the last N steps" either. The criterion is coverage:
    the window maximizing the number of distinct `(action key, effect class)` pairs it
    contains, with distinct boards breaking ties. An episode is the only place in this
    record where ORDER is visible, so it should be the order that shows the most mechanics —
    a window of sixty no-change clicks is a temporally faithful rendering of nothing.

    Where the store holds a completion, that route wins outright: it is the only sequence in
    this project that ends in the thing the model is being asked to characterize.
    """
    if span <= 0:
        return [], "disabled"
    runs = chains(store)
    for run in runs:
        for index, transition in enumerate(run):
            if transition.completed:
                return run[max(0, index + 1 - span) : index + 1], (
                    "the route that ends in this run's recorded level completion"
                )
    best: tuple[int, int, list] = (-1, -1, [])
    for run in runs:
        for start in range(0, max(1, len(run) - span + 1)):
            window = run[start : start + span]
            if not window:
                continue
            pairs = {(t.key(), effect_mode(t.effect)) for t in window}
            states = len({id(t.pre) for t in window})
            if (len(pairs), states) > (best[0], best[1]):
                best = (len(pairs), states, window)
    return best[2], (
        f"the run of consecutive actions covering the most distinct (action, outcome) "
        f"pairs — {best[0]} of them, over {best[1]} distinct boards"
    )


def _scene_key(entities: list[ent.Entity]) -> tuple:
    """What counts as a change of scene phase: the multiset of entity colours and shapes.

    A move does not change it; an entity appearing, vanishing or changing shape does. That
    is the line rev 2 draws for spending a full snapshot inside an episode, and it is
    computed rather than eyeballed.
    """
    return tuple(sorted(Counter((e.colour, e.shape_key) for e in entities).items()))


def matched_contrast(rows: list, count: int, post_missing: set[int], effect_mode) -> list:
    """Up to `count` transitions of one key, chosen to be a CONTRAST rather than examples.

    Rev 2's block 4: an effect / no-effect pair under otherwise similar conditions, or two
    different effects. So one row per distinct outcome class, largest first, and a
    did-nothing row is deliberately kept when the key has one — "the same action did nothing
    here" is half the contrast, not a wasted slot.
    """
    usable = [row for row in rows if row.step not in post_missing]
    if not usable:
        return []
    by_effect: dict[Any, list] = {}
    for row in usable:
        by_effect.setdefault(effect_mode(row.effect), []).append(row)
    ordered = sorted(by_effect.items(), key=lambda item: -len(item[1]))
    changing = [group for effect, group in ordered if effect]
    null = [group for effect, group in ordered if not effect]
    picked: list = []
    for group in changing[:1] + null[:1] + changing[1:]:
        if len(picked) == count:
            break
        picked.append(group[0])
    return picked


def no_separation_pairs(store: list, post_missing: set[int], effect_mode) -> dict[tuple, tuple]:
    """Per action key, two stored actions the MINER'S VOCABULARY cannot tell apart.

    Same key, identical values on every feature the miner has, different outcome. This is
    the miner's no-separation assertion made concrete, and rev 2 puts it in block 4 — where
    it belongs — rather than in block 5. It is a VOCABULARY GAP, channel C's business: the
    boards are different, so it is not evidence of hidden state, and presenting it as an
    alias exhibit would invite exactly the latent the evidence does not support.

    Measured availability, for the record: dc22 464 such pairs, m0r0 310, ls20 50, ft09 0.
    """
    groups: dict[tuple, list] = {}
    for transition in store:
        if transition.step in post_missing:
            continue
        signature = (
            transition.key(),
            tuple(
                sorted(
                    (name, tuple(value) if isinstance(value, list) else value)
                    for name, value in transition.guards.items()
                )
            ),
        )
        groups.setdefault(signature, []).append(transition)
    out: dict[tuple, tuple] = {}
    for (key, _), rows in groups.items():
        if key in out:
            continue
        outcomes: dict[Any, Any] = {}
        for transition in rows:
            outcomes.setdefault(effect_mode(transition.effect), transition)
        if len(outcomes) > 1:
            first, second, *_ = list(outcomes.values())
            out[key] = (first, second)
    return out


# ---------------------------------------------------------------------------------------
# The record — six blocks, each tagged with its provenance
# ---------------------------------------------------------------------------------------

PREAMBLE = """THE RECORD — the boards this evidence was collected on, and what happened on them.

Every block below is tagged with where it came from, and the tags mean different things:
  OBSERVED         frames and actions exactly as this run recorded them.
  REPLAY-VERIFIED  re-executed against the game engine and confirmed cell for cell today.
  MINER-INFERRED   derived by the mechanical miner — rules, outcome classes, statuses.
                   These are inferences and some of them are wrong. Never read one as a fact.
Cells are letter-coded; the legend binds each letter to the NUMERIC colour that the sections
above and the predicate grammar both use. Rulers are absolute row and column indices, and a
coordinate means the same thing in every view, including every crop.
An ENTITY is a 4-connected same-colour component measured against the board's background
colour; cells of the background colour are not entities.
ENTITY IDS ARE LOCAL TO THE BLOCK THEY APPEAR IN. Inside one episode, or inside one
before/after pair, the same id is the same thing. Across blocks they are NOT comparable, and
no id here asserts that an entity in one part of this record is the entity of the same
number somewhere else — the run's branches are unrelated and matching across them would
invent an identity nothing observed."""


def frames_section(
    game: str,
    store: list,
    post_missing: set[int],
    pending: list[tuple],
    *,
    key_text,
    effect_text,
    effect_mode,
    resolved: dict[tuple, str],
    refuted_events: list[dict[str, Any]] | None = None,
    completion: dict[str, Any] | None = None,
    alias_probe: dict[str, Any] | None = None,
    caps: FrameCaps | None = None,
) -> tuple[str, dict[str, Any]]:
    """Digest v4's rendered record, plus the metadata the readout needs.

    Returns `(text, meta)`. `meta` carries counts, ids and caps — never a grid: it is what
    the committed result file records, and rendered frames of competition games never enter
    a committed artifact.
    """
    caps = caps or FrameCaps()
    meta: dict[str, Any] = {"caps": caps.__dict__.copy(), "blocks": {}}
    if not store:
        return "", {"skipped": "empty store"}

    initial = store[0].pre
    moving = ever_changed(store, post_missing)
    scene_tracker = ent.Tracker()
    scene = scene_tracker.observe(initial)
    status = ent.annotate(scene, moving)

    lines: list[str] = [PREAMBLE, ""]
    lines.extend(legend_lines(grid_values(initial)))

    # --- 1. initial scene + entity map -------------------------------------------------
    lines.append("")
    lines.append(
        f"[1] THE INITIAL SCENE  (OBSERVED)  — step {store[0].step}, level 1. This board is\n"
        f"    rendered ONCE; every later block refers back to it by coordinate."
    )
    lines.extend(render_grid(initial))
    lines.append("")
    lines.append(
        f"[1b] THE ENTITY MAP OF THAT BOARD  (geometry OBSERVED; status MINER-INFERRED)\n"
        f"     `contains` is bounding-box containment — the same relation the grammar writes\n"
        f"     bbox_contains. `touches` is 4-adjacency. `shape` is the cell set up to\n"
        f"     translation, so two entities sharing a shape key satisfy same_shape.\n"
        f"     status: inert = not one of its cells changed anywhere in this run's "
        f"{len(store)} actions;\n"
        f"     touched = at least one did; hud? = touched and lying entirely outside the\n"
        f"     largest never-changing structure, which is a GUESS at a status display and\n"
        f"     nothing more. Inert is a fact about this run, not about the game: one\n"
        f"     autonomous exploration never tried most of what there is to try, so an inert\n"
        f"     entity is one that NOTHING TRIED here moved, not one the game cannot move."
    )
    lines.extend(entity_table(scene, max_rows=caps.max_entities, columns=caps.entity_columns))
    # The entity ids travel out with the metadata: `evidence_ids` in the extraction schema is
    # checked against them, and a citation checker that did not know which ids exist would be
    # counting strings rather than validating grounding.
    meta["blocks"]["scene"] = {
        "step": store[0].step,
        **status,
        "entity_ids": [entity.eid for entity in scene[: caps.max_entities]],
    }

    # --- 2. the causal episode ---------------------------------------------------------
    episode, why = _episode(store, caps.episode_steps, effect_mode)
    if episode:
        lines.append("")
        lines.append(
            f"[2] THE CAUSAL EPISODE  (OBSERVED)  — {len(episode)} consecutive actions this\n"
            f"    run took, in order. Chosen as {why}.\n"
            f"    Each line is one action and what changed, named by ENTITY — the board is\n"
            f"    not repeated. Entity ids in this block are the episode's own and are stable\n"
            f"    within it. Changes confined to hud?-status entities are flagged, because a\n"
            f"    status display changing is not the game changing. Cell lists are capped at\n"
            f"    {caps.diff_cells} with the remainder counted. A full board appears only\n"
            f"    where the scene's composition itself changed, at most {caps.snapshots} times."
        )
        lines.extend(_episode_lines(episode, caps, effect_text))
        meta["blocks"]["episode"] = {
            "steps": len(episode),
            "first_step": episode[0].step,
            "last_step": episode[-1].step,
            "ends_in_completion": bool(episode[-1].completed),
            "selected": why,
        }

    # --- 3. completion and goal contrasts ----------------------------------------------
    lines.append("")
    if completion and completion.get("captured"):
        block, completion_meta = _completion_lines(completion, caps)
        lines.extend(block)
        meta["blocks"]["completion"] = completion_meta
    else:
        lines.append(
            "[3] WHAT COMPLETION LOOKS LIKE — not available for this game. This run never\n"
            "    completed a level, so nothing in this record shows you a solved board. That\n"
            "    is a fact about the exploration, not about how hard the level is."
        )
        meta["blocks"]["completion"] = {"available": False}

    events = sorted(
        refuted_events or [], key=lambda event: (-event["step"], event["predicate"])
    )
    by_step = {transition.step: transition for transition in store}
    lines.append("")
    if events:
        lines.append(
            f"[3b] SATISFIED, AND THE LEVEL DID NOT ADVANCE  (OBSERVED)\n"
            f"     The negative half of the same contrast, and the strongest evidence in this\n"
            f"     record about what the completion condition is NOT. {len(events)}\n"
            f"     mechanically enumerated candidates were true of the board at a step that\n"
            f"     did not complete the level; the "
            f"{min(len(events), caps.refuted_examples)} that survived the most evidence\n"
            f"     before being refuted are shown as boards."
        )
        for event in events[: caps.refuted_examples]:
            transition = by_step.get(event["step"])
            if transition is None:
                continue
            lines.append("")
            lines.append(
                f"  `{event['predicate']}` was TRUE of this board at step {event['step']}, "
                f"and {action_text(transition)} did not complete the level:"
            )
            lines.extend(f"  {line}" for line in _condition_view(transition.pre, event["predicate"]))
        meta["blocks"]["refuted_boards"] = min(len(events), caps.refuted_examples)
    else:
        lines.append(
            "[3b] SATISFIED, AND THE LEVEL DID NOT ADVANCE — none recorded for this game."
        )
        meta["blocks"]["refuted_boards"] = 0

    # --- 4. matched contrasts ----------------------------------------------------------
    # One budget shared by blocks 4 and 4b: the ration is on the RECORD, not per block, so a
    # game whose every effect is board-wide cannot spend it twice.
    render_budget = {"global": caps.global_examples}
    by_key: dict[tuple, list] = {}
    for transition in store:
        by_key.setdefault(transition.key(), []).append(transition)
    ordered_keys = sorted(by_key, key=lambda k: -len(by_key[k]))[: caps.gallery_keys]
    if caps.gallery_examples and ordered_keys:
        lines.append("")
        lines.append(
            f"[4] MATCHED CONTRASTS PER ACTION  (transitions OBSERVED; rules MINER-INFERRED)\n"
            f"    Not arbitrary examples: one per distinct outcome class, and where an action\n"
            f"    has a did-nothing case it is one of them — the PAIR is the evidence, not\n"
            f"    either half. Crops are sized to the cells that actually changed; a change\n"
            f"    too spread out to crop is shown as a full board and says so. The\n"
            f"    {len(ordered_keys)} keys with the most evidence are shown, of {len(by_key)}\n"
            f"    in this run, up to {caps.gallery_examples} examples each."
        )
        for key in ordered_keys:
            rows = by_key[key]
            rule = resolved.get(key)
            lines.append("")
            lines.append(
                f"  {key_text(key)} — {len(rows)} stored actions"
                + (
                    f"\n    MINER-INFERRED RULE — this mechanic is already solved, spend no "
                    f"reasoning on it: {rule}"
                    if rule
                    else "\n    the miner could NOT resolve this key"
                )
            )
            for transition in matched_contrast(
                rows, caps.gallery_examples, post_missing, effect_mode
            ):
                lines.extend(_contrast_lines(transition, effect_text, caps, render_budget))
    meta["blocks"]["contrasts"] = {
        "keys_shown": len(ordered_keys) if caps.gallery_examples else 0,
        "keys_total": len(by_key),
    }

    # --- 4b. the no-separation witnesses, shown ----------------------------------------
    witnesses = no_separation_pairs(store, post_missing, effect_mode)
    shown_keys = [key for key in pending if key in witnesses][: caps.unresolved_keys]
    if caps.key_examples and shown_keys:
        lines.append("")
        lines.append(
            f"[4b] WHERE THE FEATURE VOCABULARY RUNS OUT  (OBSERVED; the claim that no\n"
            f"     feature separates them is MINER-INFERRED)\n"
            f"     For each unresolved key, two stored actions that agree on EVERY feature\n"
            f"     the miner has and still had different outcomes. The boards are different —\n"
            f"     so this is a missing WORD, not a hidden variable — and what is missing is\n"
            f"     whatever distinguishes the two situations below.\n"
            f"     {len(shown_keys)} of {len(pending)} unresolved keys have such a pair."
        )
        for key in shown_keys:
            first, second = witnesses[key]
            lines.append("")
            lines.append(f"  {key_text(key)} — same features, different outcome:")
            lines.extend(_contrast_lines(first, effect_text, caps, render_budget))
            lines.extend(_contrast_lines(second, effect_text, caps, render_budget))
        meta["blocks"]["no_separation"] = {
            "keys_shown": len(shown_keys),
            "keys_with_a_witness": len(witnesses),
            "unresolved_keys": len(pending),
        }

    # --- 5. alias exhibits -------------------------------------------------------------
    block, alias_meta = _alias_block(game, alias_probe, caps)
    lines.append("")
    lines.extend(block)
    meta["blocks"]["alias"] = alias_meta

    return "\n".join(lines), meta


# ---------------------------------------------------------------------------------------
# Block helpers
# ---------------------------------------------------------------------------------------


def _condition_view(grid: Sequence[Sequence[int]], predicate: str) -> list[str]:
    """The part of a board a refuted condition is ABOUT, as a crop.

    Rev 2 asks for block 3b as crops, and a whole board is the wrong unit here: the claim is
    about specific colours, so the view is the bounding box of the entities of the colours the
    condition names, with a margin. Where the condition names no colour, or its entities span
    most of the board anyway, the full board is rendered — that is the honest fallback, and
    `crop_bounds` says which one happened.
    """
    colours = {int(match) for match in re.findall(r"\bc(\d+)\b", predicate or "")}
    if not colours:
        return render_grid(grid)
    cells: list[tuple[int, int]] = []
    for entity in ent.Tracker().observe(grid):
        if entity.colour in colours:
            cells.extend(entity.cells)
    if not cells:
        return render_grid(grid)
    rows, cols, is_crop = crop_bounds(grid, cells, margin=4)
    view = render_grid(grid, row_range=rows, col_range=cols)
    if is_crop:
        view.insert(
            0,
            f"  (rows {rows[0]}-{rows[1]}, cols {cols[0]}-{cols[1]} — the part of the board "
            f"this condition is about; colours {', '.join(f'c{c}' for c in sorted(colours))})",
        )
    return view


def _cells_of(transition: Any) -> list[tuple[int, int]]:
    cells = [(row, col) for row, col, _, _ in changed_cells(transition.pre, transition.post)]
    click = click_cell(transition)
    if click is not None:
        cells.append(click)
    return cells


def _episode_lines(episode: list, caps: FrameCaps, effect_text) -> list[str]:
    """Per-step lines naming entities, with hud?-only changes flagged and rare snapshots.

    The tracker is created HERE and lives only for this episode: rev 2's identity-scope rule
    is that ids are stable within one episode or one pair and never across unrelated store
    branches. The episode is a genuinely consecutive run of frames, so tracking within it is
    a claim the frames support.
    """
    tracker = ent.Tracker()
    previous = tracker.observe(episode[0].pre)
    moving_here: set[tuple[int, int]] = set()
    for transition in episode:
        for row, col, _, _ in changed_cells(transition.pre, transition.post):
            moving_here.add((row, col))
    ent.annotate(previous, moving_here)
    hud = {entity.eid for entity in previous if entity.status == "hud?"}

    lines: list[str] = []
    phase = _scene_key(previous)
    snapshots = 0
    for transition in episode:
        changes = changed_cells(transition.pre, transition.post)
        cells = [(row, col) for row, col, _, _ in changes]
        current = tracker.observe(transition.post)
        touched = sorted(
            set(ent.entities_touching(previous, cells)) | set(ent.entities_touching(current, cells))
        )
        click = click_cell(transition)
        clicked = ent.entity_of(previous, *click) if click else None
        head = f"  step {transition.step:>5d}: {action_text(transition):<24s}"
        if clicked is not None:
            head += f" on entity #{clicked.eid} (c{clicked.colour})"
        elif click is not None:
            head += " on the background"
        if not changes:
            lines.append(f"{head}  ->  nothing changed")
        else:
            hud_only = bool(touched) and set(touched) <= hud
            marker = "   [status display only]" if hud_only else ""
            detail = ", ".join(
                f"({row},{col}) {letter(before)}->{letter(after)}"
                for row, col, before, after in changes[: caps.diff_cells]
            )
            more = (
                ""
                if len(changes) <= caps.diff_cells
                else f", +{len(changes) - caps.diff_cells} more cells"
            )
            lines.append(
                f"{head}  ->  {effect_text(transition.effect)}{marker}\n"
                f"        entities {', '.join(f'#{i}' for i in touched) or 'none'}; "
                f"{len(changes)} cells: {detail}{more}"
            )
        if transition.completed:
            lines.append("        *** THIS ACTION COMPLETED THE LEVEL ***")
        current_phase = _scene_key(current)
        if current_phase != phase and snapshots < caps.snapshots:
            snapshots += 1
            lines.append(
                "        the scene's composition changed here — an entity appeared, vanished"
            )
            lines.append("        or changed shape. The board after this action:")
            lines.extend(f"        {line}" for line in render_grid(transition.post))
        phase = current_phase
        previous = current
    return lines


def _contrast_lines(
    transition: Any, effect_text, caps: FrameCaps, budget: dict[str, int] | None = None
) -> list[str]:
    """One before/after example. Entity ids are LOCAL TO THIS PAIR and say so.

    A window centred on the click is not enough, and assuming it was would have shipped an
    empty exhibit: measured on lf52, a click at (34,29) changes exactly one cell, at (0,0).
    These games put counters and status rows far from the thing you touched, so the crop is
    sized to the union of the changed cells AND the click.
    """
    changes = changed_cells(transition.pre, transition.post)
    click = click_cell(transition)
    before_scene = ent.Tracker().observe(transition.pre)
    clicked = ent.entity_of(before_scene, *click) if click else None
    head = f"    step {transition.step}: {action_text(transition)}"
    if clicked is not None:
        head += f", on an entity of colour c{clicked.colour} at rows " \
                f"{clicked.bbox[0]}-{clicked.bbox[2]}, cols {clicked.bbox[1]}-{clicked.bbox[3]}"
    elif click is not None:
        head += ", on the background"
    head += f"  ->  {effect_text(transition.effect)}"
    lines = [head]
    if not changes:
        lines.append("      nothing changed. The board around the action:")
        if click is not None:
            rows, cols, _ = crop_bounds(transition.pre, [click])
            lines.extend(
                f"      {line}"
                for line in render_grid(transition.pre, row_range=rows, col_range=cols)
            )
        return lines
    lines.append(f"      {len(changes)} cells changed")
    cells = _cells_of(transition)
    _, _, is_crop = crop_bounds(transition.pre, cells)
    if not is_crop:
        # Too spread out to window. A full board pair costs about as much as thirty crops, so
        # only the first few are rendered; after that the cell list above and the bounding box
        # below are the evidence, and the record says so rather than quietly showing less.
        if budget is not None and budget.get("global", 0) <= 0:
            rows = [row for row, _, _, _ in changes]
            cols = [col for _, col, _, _ in changes]
            lines.append(
                f"      the change spans rows {min(rows)}-{max(rows)}, cols {min(cols)}-"
                f"{max(cols)} — too spread out to window. The cells are listed above; no board"
            )
            lines.append(
                "      is rendered for it, because a board-wide change of this shape is "
                "already shown once above."
            )
            return lines
        if budget is not None:
            budget["global"] = budget.get("global", 0) - 1
    lines.extend(render_pair(transition.pre, transition.post, cells, indent="      "))
    return lines


def _alias_block(
    game: str, probe: dict[str, Any] | None, caps: FrameCaps
) -> tuple[list[str], dict[str, Any]]:
    """Block 5, under rev 2's strict semantics: identical board, same action, different result.

    Nothing weaker qualifies. Two different boards that the miner's features cannot tell
    apart is a missing WORD and lives in block 4b; putting it here would invite a hidden-state
    latent that the evidence does not support.

    The exhibits do not come from the store. MEASURED: the store retains only ONE outcome for
    every pair its graph flags as conflicted, on all eight games — the flag records that a
    conflict was seen live, and the other board was never kept. They come from
    `e2_alias_probe.py`, which drives two verified histories of different length to the same
    board, checks cell for cell that both really reached it, and then takes the same action
    from each. That is why this block is REPLAY-VERIFIED and why it exists at all.
    """
    usable = [
        row
        for row in ((probe or {}).get("probes") or [])
        if row.get("probed") and row.get("outcomes_differ")
    ]
    if not usable:
        return (
            [
                "[5] SAME BOARD, SAME ACTION, DIFFERENT RESULT — none for this game.",
                "    No pair of histories in this record reaches one board and then diverges,",
                "    so nothing here is evidence that this game has state you cannot see. Do",
                "    not propose a hidden variable to explain evidence that is not present.",
            ],
            {"available": False, "exhibits": 0},
        )
    lines = [
        f"[5] SAME BOARD, SAME ACTION, DIFFERENT RESULT  (REPLAY-VERIFIED)",
        f"    {len(usable)} such cases, {min(len(usable), caps.alias_examples)} shown. Each",
        f"    was produced by driving TWO DIFFERENT HISTORIES to the same board — confirmed",
        f"    cell for cell before the action — and then taking the same action from each.",
        f"    The boards are identical. The histories are not. Whatever decides the outcome",
        f"    is therefore something the board does not show, and the histories below are the",
        f"    only place it can be.",
    ]
    for row in usable[: caps.alias_examples]:
        action = row["action"]
        action_name = (
            f"ACTION6(row={action[1]}, col={action[2]})" if action[0] == 6 else f"ACTION{action[0]}"
        )
        lines.append("")
        lines.append(f"  the board, rendered once — both histories reach exactly this:")
        lines.extend(f"    {line}" for line in render_grid(row["board"]))
        lines.append(
            f"  history A: {row['routes']['a_actions']} actions since the game was created."
        )
        lines.append(
            f"  history B: {row['routes']['b_actions']} actions — the same route plus "
            f"{len(row['routes']['cycle'])} action(s) that returned to this same board."
        )
        lines.append(
            f"  then {action_name} from each. The results differ in {row['differing_cells']} "
            f"cells:"
        )
        cells = [
            (r, c)
            for r, c, _, _ in changed_cells(row["after_a"], row["after_b"])
        ]
        lines.extend(render_pair(row["after_a"], row["after_b"], cells, indent="    "))
        lines.append("    (left: the result after history A. right: after history B.)")
    return lines, {
        "available": True,
        "exhibits": len(usable),
        "shown": min(len(usable), caps.alias_examples),
        "flagged_pairs_probed": len((probe or {}).get("probes") or []),
    }


def _completion_lines(capture: dict[str, Any], caps: FrameCaps) -> tuple[list[str], dict[str, Any]]:
    """The priority exhibit: the only solved board this project has ever retained.

    Captured today by re-executing the verified walked route and keeping every frame the
    engine returned (`e3_completion_capture.py`); the gate was that the route reproduced the
    recorded pre-action board cell for cell. The explorer stored only the COUNT of these
    frames, so without that capture this block would not exist.

    Rev 2: THREE full boards only — the last incomplete state, the solved terminal, and the
    next level's opening frame. The intermediates are the animation, and an animation is
    worth its differences, not twenty renders of a 64x64 board. Each unique one appears as a
    one-line diff against its predecessor.

    The next-level frame is labelled unambiguously as a DIFFERENT LEVEL. It is the most
    misreadable frame in the whole record: it looks like a board and it is not this one.
    """
    completion = capture["completion"]
    frames = capture["frames"]
    roles = completion["roles"] or []
    action = completion["action"]
    # RENDERER CONTRACT (rev 2.1). Frames are selected BY ROLE and never by position, and a
    # capture without usable roles fails loudly instead of falling back to indexing.
    #
    # Reading "the last frame" as the solved board would have been the single most corrupting
    # error available in this block: on a non-WIN completion the engine advances within the
    # same response, so the LAST frame already belongs to the next level. Measured on all four
    # captures — sp80 20 frames, lf52 27, r11l 23, lp85 2 — the solved board is the
    # PENULTIMATE frame every time. Indexing would have shown the model the wrong level's
    # board as the winning state on every game that has one.
    if completion.get("role_error") or not roles:
        raise ValueError(
            f"completion capture has no usable frame roles "
            f"({completion.get('role_error') or 'roles empty'}); refusing to guess by position"
        )
    if len(roles) != len(frames):
        raise ValueError(
            f"completion capture has {len(frames)} frames and {len(roles)} roles; "
            f"refusing to align them by position"
        )
    action_name = (
        f"ACTION6(row={action[1]}, col={action[2]})" if action[0] == 6 else f"ACTION{action[0]}"
    )
    terminal = next(
        (frame for frame, role in zip(frames, roles) if role == "solved_terminal"), None
    )
    next_level = next(
        (frame for frame, role in zip(frames, roles) if role == "next_level_initial"), None
    )
    if terminal is None:
        raise ValueError("completion capture carries no solved_terminal frame")

    lines = [
        f"[3] WHAT COMPLETION LOOKS LIKE  (REPLAY-VERIFIED — re-executed today; the route\n"
        f"    reproduced the recorded board cell for cell before the action below was taken)\n"
        f"    This is the ONE sequence in this record that ends with the level complete. The\n"
        f"    engine returned {completion['frames_returned']} frames for this single action;\n"
        f"    the stored evidence kept none of them.",
        "",
        "  THE LAST INCOMPLETE BOARD — one action short:",
    ]
    lines.extend(f"  {line}" for line in render_grid(capture["last_incomplete_frame"]))
    lines.append("")
    lines.append(f"  THE COMPLETING ACTION: {action_name}")

    # every UNIQUE frame of the sequence as a diff against its predecessor
    previous = capture["last_incomplete_frame"]
    diffs: list[str] = []
    for index, (frame, role) in enumerate(zip(frames, roles)):
        if frame == previous:
            continue
        changes = changed_cells(previous, frame)
        detail = ", ".join(
            f"({row},{col}) {letter(before)}->{letter(after)}"
            for row, col, before, after in changes[: caps.diff_cells]
        )
        more = (
            "" if len(changes) <= caps.diff_cells else f", +{len(changes) - caps.diff_cells} more"
        )
        diffs.append(
            f"    frame {index + 1:>2d} ({role}): {len(changes):>4d} cells changed: {detail}{more}"
        )
        previous = frame
    if diffs:
        lines.append(
            f"  WHAT THE BOARD DID, FRAME BY FRAME — {len(diffs)} of the "
            f"{completion['frames_returned']} returned frames differ from the one before\n"
            f"  them. Each line is that difference. Mid-animation boards are not states you\n"
            f"  could have acted on."
        )
        lines.extend(diffs[: caps.completion_diffs])
        if len(diffs) > caps.completion_diffs:
            lines.append(
                f"    (+{len(diffs) - caps.completion_diffs} further frame differences not "
                f"shown)"
            )
    lines.append("")
    lines.append(
        "  THE SOLVED BOARD — this level, complete. This is the frame the engine labelled\n"
        "  solved; it is NOT the last frame it returned, because the last one already belongs\n"
        "  to the next level. Whatever completion condition you propose, it must be TRUE of\n"
        "  this board:"
    )
    lines.extend(f"  {line}" for line in render_grid(terminal))
    if next_level is not None:
        lines.append("")
        lines.append(
            "  THE NEXT LEVEL'S OPENING BOARD — A DIFFERENT LEVEL, shown so that you do not\n"
            "  mistake it for part of this one. Your completion condition is about the level\n"
            "  above it, NOT about this board:"
        )
        lines.extend(f"  {line}" for line in render_grid(next_level))
    lines.append("")
    lines.append(
        f"  engine metadata at the completing action, verbatim: state={completion['state']}, "
        f"levels_completed={completion['levels_completed']}, win_levels="
        f"{completion.get('win_levels')} — the run's total, so a level being solved is not\n"
        f"  the game being won. Actions available afterwards: "
        f"{', '.join(str(a) for a in completion['available_actions']) or 'none reported'}"
    )
    return lines, {
        "frames_returned": completion["frames_returned"],
        "unique_frame_diffs": len(diffs),
        "diffs_shown": min(len(diffs), caps.completion_diffs),
        "full_boards_rendered": 1 + (terminal is not None) + (next_level is not None),
        "roles": sorted(set(roles)),
    }
