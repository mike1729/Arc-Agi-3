#!/usr/bin/env python3
"""MU representations: the seven renderers over one evidence window.

Implements MU SS3 (``notes/mu-representation-screen.md``). Every arm starts from the SAME
evidence window with the same withholdings, and the task framing, question, and output
schema are produced once, arm-independently; ``tests/test_mu_render.py`` asserts they are
byte-identical across all seven arms. The arms are INTERFACE BUNDLES over that window, not
pure re-renderings of one another: grid ⊂ objects ⊂ events ⊂ card add computed layers,
map is deliberately lossy, verbal is computed from the object registry, and film is an
exact re-rendering of grid. A difference between adjacent nested bundles identifies the
added layer; grid vs film is the only matched-information pure-rendering contrast; map and
verbal are ranked as bundles, never attributed to formatting alone (MU SS3).

Arms (MU SS3):

  grid     P0     exact indexed grid text + legend + deterministic deltas
  objects  P1-live  grid + the runtime object table with referent aliases
  events   P2-live  objects + relation, identity-lineage, and event tables
  card     events + the per-action effect catalogue accumulated from the shown prefix only
  map      coarse semantic map: one glyph per object on a downsampled lattice
  verbal   deterministic template sentences over the state inventory and the event stream
  film     successive delta-only frames (changed cells only) over the shown prefix

Presentation determinizations, frozen per representation before measurement (MU SS3: one
canonical form each, no per-game tuning):

  * Cell characters are the vendored reference's ``ARC_COLOR_CHARS``
    (``inference/utils/grid_utils``), mirrored here so MU renders exactly what GI-1 and the
    live harness rendered; ``tests/test_mu_render.py`` asserts the mirror.
  * Coordinates are (row, col), zero-based, row-major, printed row-then-column everywhere.
    Grids carry a two-line column ruler (tens, units) and a two-digit row index.
  * State economy, applied uniformly to every arm that shows cells: the window's FIRST
    state is rendered in full, each later state as a delta from its predecessor, and the
    query state in full because every probe asks about it. Where the delta list would be
    longer in characters than the full board, the full board is printed instead: both
    encodings are exact, so the choice is pure economy and never a truncation.
  * Object tables are rendered in full at the first and query states and as object-level
    changes in between, the same economy as the grid arm. Relations are rendered as the
    query state's 4-adjacency lists: the full pairwise matrix is quadratic in an object
    count that reaches 352 on m0r0, while every other frozen relation is derivable from the
    bounding boxes already in the table.
  * ``map`` lattice: cell (i,j) covers rows 4i..4i+3 and cols 4j..4j+3 of the 64x64 board;
    it shows the character of the highest-priority object whose CENTROID lies in it —
    priority is (more pixels, then smaller bbox top-left, then smaller colour) — and '.'
    when no centroid falls in it. The coarseness is the arm, not a defect.
  * ``verbal`` narrates the object inventory of the first and query states as well as the
    event stream. A pure event narration could not answer MU-T1 at all, so its T1 result
    would measure the omission rather than the rendering.
  * Withholding is honoured by every arm through ``case["reveal"]``: MU-T2 relabels the
    query state's objects B1..Bm in frozen hash order and withholds the last transition's
    derived tables (lineage, events, catalogue, verbal sentences), because those tables
    ARE the answer. Cell-level evidence for that transition is always shown.

Run:
  .venv/bin/python agent/harness/mu_render.py --demo ls20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/harness"))

from mu_probes import (  # noqa: E402
    COLOR_NAMES,
    MAP_LATTICE,
    EvidenceWindow,
    MuObject,
    action_label,
    adjacency_lists,
    build_catalogue,
    condition_text,
    output_schema,
    sha256_bytes,
)

ARMS = ("grid", "objects", "events", "card", "map", "verbal", "film")
GRID_SIZE = 64
UNCHANGED_CHAR = "."

# Mirror of the vendored inference/utils/grid_utils.ARC_COLOR_CHARS, indexed by cell value.
ARC_COLOR_CHARS = "WwgGcBMPRbSYOrNp"

RELATION_TEXT = {
    "adjacent": "adjacent(A,B) holds when some cell of A is 4-adjacent to some cell of B",
    "bbox_overlap": "bbox_overlap(A,B) holds when the bounding boxes of A and B intersect",
    "bbox_contains": "bbox_contains(A,B) holds when the bounding box of A contains that of B",
    "row_aligned": "row_aligned(A,B) holds when the row ranges of A and B overlap",
    "col_aligned": "col_aligned(A,B) holds when the column ranges of A and B overlap",
}


# ====================================================================================
# Primitive text
# ====================================================================================


def colour_legend() -> str:
    return "; ".join(
        f"{ARC_COLOR_CHARS[value]}={value}:{COLOR_NAMES[value]}" for value in range(16)
    )


def format_grid(grid: list) -> str:
    tens = "".join(str((column // 10) % 10) for column in range(len(grid[0])))
    units = "".join(str(column % 10) for column in range(len(grid[0])))
    lines = [f"    {tens}", f"    {units}"]
    for index, row in enumerate(grid):
        lines.append(f"{index:>3} " + "".join(ARC_COLOR_CHARS[int(value)] for value in row))
    return "\n".join(lines)


def cell_deltas(before: list, after: list) -> list[tuple[int, int, int, int]]:
    return [
        (row, col, int(left), int(right))
        for row, (brow, arow) in enumerate(zip(before, after))
        for col, (left, right) in enumerate(zip(brow, arow))
        if left != right
    ]


def format_delta(before: list, after: list) -> str:
    """Whichever EXACT encoding of the successor state is shorter; never a truncation."""
    deltas = cell_deltas(before, after)
    if not deltas:
        return "changed cells: 0 (the board is identical)"
    listed = "changed cells: {n}\n{body}".format(
        n=len(deltas),
        body="  ".join(
            f"({row},{col}) {ARC_COLOR_CHARS[old]}->{ARC_COLOR_CHARS[new]}"
            for row, col, old, new in deltas
        ),
    )
    full = f"changed cells: {len(deltas)}; the full board after the action is\n" + format_grid(
        after
    )
    return listed if len(listed) <= len(full) else full


def format_delta_canvas(before: list, after: list) -> str:
    deltas = {(row, col): new for row, col, _, new in cell_deltas(before, after)}
    if not deltas:
        return "(no cell changed)"
    canvas = [
        [
            ARC_COLOR_CHARS[deltas[(row, col)]] if (row, col) in deltas else UNCHANGED_CHAR
            for col in range(len(after[0]))
        ]
        for row in range(len(after))
    ]
    return format_grid_chars(canvas)


def format_grid_chars(rows: list[list[str]]) -> str:
    tens = "".join(str((column // 10) % 10) for column in range(len(rows[0])))
    units = "".join(str(column % 10) for column in range(len(rows[0])))
    lines = [f"    {tens}", f"    {units}"]
    for index, row in enumerate(rows):
        lines.append(f"{index:>3} " + "".join(row))
    return "\n".join(lines)


OBJECT_TABLE_HEADER = (
    "columns: name | value | pixels | bbox top,left,bottom,right | centroid row,col"
)


def object_row(item: MuObject, label: str | None = None) -> str:
    name = label if label is not None else item.alias
    top, left, bottom, right = item.bbox
    return (
        f"{name} {item.colour} {item.pixels} {top},{left},{bottom},{right} "
        f"{item.centroid[0]},{item.centroid[1]}"
    )


def outcome_text(alias: str, outcome: dict[str, Any]) -> str:
    kind = outcome["kind"]
    if kind == "moved":
        return f"{alias} moved by ({outcome['delta'][0]},{outcome['delta'][1]})"
    if kind == "recoloured":
        return f"{alias} recoloured to {outcome['to']}"
    if kind == "disappeared":
        return f"{alias} disappeared"
    if kind == "unchanged":
        return f"{alias} unchanged"
    return f"{alias} changed shape ({outcome.get('reason', 'reshaped')})"


def lattice(objects: tuple[MuObject, ...]) -> str:
    factor = GRID_SIZE // MAP_LATTICE
    best: dict[tuple[int, int], MuObject] = {}
    for item in objects:
        cell = (item.centroid[0] // factor, item.centroid[1] // factor)
        current = best.get(cell)
        if current is None or (
            -item.pixels,
            item.bbox,
            item.colour,
        ) < (-current.pixels, current.bbox, current.colour):
            best[cell] = item
    rows = [
        [
            ARC_COLOR_CHARS[best[(row, col)].colour] if (row, col) in best else UNCHANGED_CHAR
            for col in range(MAP_LATTICE)
        ]
        for row in range(MAP_LATTICE)
    ]
    return format_grid_chars(rows)


# ====================================================================================
# Window presentation helpers
# ====================================================================================


def state_name(index: int) -> str:
    return f"S{index}"


def _labels_for_query(case: dict[str, Any]) -> dict[str, str] | None:
    """MU-T2 relabelling: query-state alias -> B label, in the case's frozen hash order."""
    if not case.get("reveal", {}).get("relabel_query_state"):
        return None
    return {alias: f"B{index}" for index, alias in enumerate(case["label_order"], 1)}


def _transition_header(index: int, window: EvidenceWindow) -> str:
    transition = window.transitions[index]
    return (
        f"{state_name(index)} -> {state_name(index + 1)}   "
        f"action {action_label(transition.action)}"
    )


def cell_evidence(window: EvidenceWindow, *, canvas: bool) -> list[str]:
    """The cell-level spine shared by `grid` and `film`; never withheld."""
    blocks = [f"{state_name(0)} (full board)\n{format_grid(window.states[0].grid)}"]
    for index, transition in enumerate(window.transitions):
        body = (
            format_delta_canvas(transition.pre.grid, transition.post.grid)
            if canvas
            else format_delta(transition.pre.grid, transition.post.grid)
        )
        blocks.append(f"{_transition_header(index, window)}\n{body}")
    last = len(window.states) - 1
    if last > 0:
        blocks.append(
            f"{state_name(last)} (full board, the current state)\n"
            f"{format_grid(window.query.grid)}"
        )
    return blocks


def object_evidence(window: EvidenceWindow, case: dict[str, Any]) -> list[str]:
    reveal = case["reveal"]
    labels = _labels_for_query(case)
    blocks = []
    table = "\n".join(object_row(item) for item in window.states[0].objects)
    blocks.append(
        f"{state_name(0)} objects ({len(window.states[0].objects)} rows)\n"
        f"{OBJECT_TABLE_HEADER}\n{table}"
    )
    for index in range(len(window.transitions)):
        if index > reveal["derived_through"]:
            continue
        transition = window.transitions[index]
        changes = [
            outcome_text(alias, outcome)
            for alias, outcome in sorted(transition.outcomes.items())
            if outcome["kind"] != "unchanged"
        ]
        if transition.appeared:
            changes.append(f"{transition.appeared} object(s) appeared")
        body = "; ".join(changes) if changes else "no object changed"
        blocks.append(f"{_transition_header(index, window)}\nobject changes: {body}")
    last = len(window.states) - 1
    if labels is not None:
        rows = sorted(
            window.query.objects, key=lambda item: int(labels[item.alias][1:])
        )
        table = "\n".join(object_row(item, labels[item.alias]) for item in rows)
        blocks.append(
            f"{state_name(last)} objects ({len(rows)} rows; identifiers withheld, "
            f"rows in scrambled order)\n{OBJECT_TABLE_HEADER}\n{table}"
        )
    elif last > 0:
        table = "\n".join(object_row(item) for item in window.query.objects)
        blocks.append(
            f"{state_name(last)} objects ({len(window.query.objects)} rows, "
            f"the current state)\n{OBJECT_TABLE_HEADER}\n{table}"
        )
    return blocks


def semantic_evidence(window: EvidenceWindow, case: dict[str, Any]) -> list[str]:
    reveal = case["reveal"]
    labels = _labels_for_query(case)
    blocks = []
    for index in range(len(window.transitions)):
        if index > reveal["derived_through"]:
            continue
        transition = window.transitions[index]
        post_by_track = transition.post.by_track
        lineage = [
            f"{item.alias} -> {post_by_track[item.track_id].alias}"
            for item in transition.pre.objects
            if item.track_id in post_by_track
        ]
        events = [
            f"{alias}: {outcome['kind']}"
            for alias, outcome in sorted(transition.outcomes.items())
        ]
        blocks.append(
            f"{_transition_header(index, window)}\n"
            f"identity ({state_name(index)} -> {state_name(index + 1)}): "
            + ("; ".join(lineage) if lineage else "no object persisted")
            + f"\nevents: " + "; ".join(events)
            + f"\nappeared: {transition.appeared}; "
            f"level_increment: {transition.level_increment}"
        )
    last = len(window.states) - 1
    adjacency = adjacency_lists(window.query.objects)
    if labels is not None:
        adjacency = {
            labels[alias]: sorted(labels[other] for other in others)
            for alias, others in adjacency.items()
        }
    body = (
        "\n".join(f"{alias}: {', '.join(others)}" for alias, others in sorted(adjacency.items()))
        or "no two objects touch"
    )
    blocks.append(f"{state_name(last)} adjacency (4-connected contact)\n{body}")
    return blocks


def catalogue_evidence(window: EvidenceWindow, case: dict[str, Any]) -> list[str]:
    reveal = case["reveal"]
    shown = EvidenceWindow(
        env=window.env,
        guid=window.guid,
        role=window.role,
        probe=window.probe,
        states=window.states[: reveal["derived_through"] + 2],
        transitions=window.transitions[: reveal["derived_through"] + 1],
        tracker=window.tracker,
    )
    catalogue = build_catalogue(shown)
    if not catalogue:
        return ["action effect catalogue (from the shown prefix only)\n(no action observed)"]
    lines = []
    for key, entry in catalogue.items():
        kinds = ", ".join(f"{kind}x{count}" for kind, count in entry["kinds"].items())
        levels = "; ".join(
            f"level {level}: " + ", ".join(f"{kind}x{count}" for kind, count in counts.items())
            for level, counts in entry["by_level"].items()
        )
        lines.append(
            f"{key}: n={entry['n']} effects[{kinds}] "
            f"median_changed_cells={entry['median_changed_cells']} | by level -> {levels}"
        )
    return [
        "action effect catalogue (from the shown prefix only)\n" + "\n".join(lines)
    ]


def verbal_evidence(window: EvidenceWindow, case: dict[str, Any]) -> list[str]:
    reveal = case["reveal"]
    labels = _labels_for_query(case)

    def inventory(state, name: str, label_map: dict[str, str] | None) -> str:
        sentences = []
        rows = list(state.objects)
        if label_map is not None:
            rows = sorted(rows, key=lambda item: int(label_map[item.alias][1:]))
        for item in rows:
            who = label_map[item.alias] if label_map else item.alias
            top, left, bottom, right = item.bbox
            sentences.append(
                f"{who} is a {item.colour_name} object of {item.pixels} cells spanning rows "
                f"{top}-{bottom} and columns {left}-{right}, centred at ({item.centroid[0]},"
                f"{item.centroid[1]})."
            )
        return f"{name} contains {len(rows)} objects.\n" + "\n".join(sentences)

    blocks = [inventory(window.states[0], state_name(0), None)]
    for index in range(len(window.transitions)):
        if index > reveal["derived_through"]:
            blocks.append(
                f"{_transition_header(index, window)}\n"
                f"The action was taken; its object-level effect is not narrated here."
            )
            continue
        transition = window.transitions[index]
        parts = [outcome_text(alias, outcome) + "." for alias, outcome in
                 sorted(transition.outcomes.items()) if outcome["kind"] != "unchanged"]
        if transition.appeared:
            parts.append(f"{transition.appeared} new object(s) appeared.")
        if transition.level_increment:
            parts.append("The level was completed.")
        if not parts:
            parts = ["Nothing changed."]
        blocks.append(
            f"{action_label(transition.action)} was taken in {state_name(index)}: "
            + " ".join(parts)
        )
    last = len(window.states) - 1
    if last > 0:
        blocks.append(
            inventory(window.query, f"{state_name(last)} (the current state)", labels)
            + ("\nIdentifiers are withheld and the rows are in scrambled order."
               if labels else "")
        )
    return blocks


# ====================================================================================
# Arms
# ====================================================================================


ARM_NOTES = {
    "grid": "Each state is given as an exact character grid; intermediate states are given "
            "as exact lists of changed cells.",
    "objects": "Each state is given as an exact character grid plus a table of its objects; "
               "intermediate states are given as changed cells and object-level changes.",
    "events": "As well as grids and object tables, each step lists which object became "
              "which, what happened to each object, and which objects touch.",
    "card": "As well as grids, object tables, identity and events, a catalogue summarises "
            "what each action did in the steps shown.",
    "map": "The board is given ONLY as a coarse 16x16 map: each cell holds the character of "
           "the largest object centred in the corresponding 4x4 block of the board, or '.'.",
    "verbal": "The board and every step are described ONLY in sentences.",
    "film": "Each state is given as a character grid in which cells that did not change "
            "since the previous state are shown as '.'.",
}


def representation(arm: str, case: dict[str, Any], window: EvidenceWindow) -> str:
    if arm == "grid":
        blocks = cell_evidence(window, canvas=False)
    elif arm == "objects":
        blocks = cell_evidence(window, canvas=False) + object_evidence(window, case)
    elif arm == "events":
        blocks = (
            cell_evidence(window, canvas=False)
            + object_evidence(window, case)
            + semantic_evidence(window, case)
        )
    elif arm == "card":
        blocks = (
            cell_evidence(window, canvas=False)
            + object_evidence(window, case)
            + semantic_evidence(window, case)
            + catalogue_evidence(window, case)
        )
    elif arm == "map":
        blocks = [
            f"{state_name(index)} map"
            + (" (the current state)" if index == len(window.states) - 1 and index else "")
            + f"\n{lattice(state.objects)}"
            + (
                ""
                if index == 0
                else f"\n(reached from {state_name(index - 1)} by "
                     f"{action_label(window.transitions[index - 1].action)})"
            )
            for index, state in enumerate(window.states)
        ]
    elif arm == "verbal":
        blocks = verbal_evidence(window, case)
    elif arm == "film":
        blocks = cell_evidence(window, canvas=True)
    else:
        raise ValueError(f"unknown arm: {arm}")
    return f"REPRESENTATION ({arm})\n{ARM_NOTES[arm]}\n\n" + "\n\n".join(blocks)


# ====================================================================================
# Arm-independent framing, question, and schema
# ====================================================================================


def preamble(window: EvidenceWindow) -> str:
    states = len(window.states)
    return (
        "You are given consecutive states of one level of a 64x64 grid game and the actions "
        "taken between them.\n"
        f"There are {states} states, named {state_name(0)} to {state_name(states - 1)}; "
        f"{state_name(states - 1)} is the current state.\n"
        "Cells hold a value 0-15. An OBJECT is a maximal set of same-value cells connected "
        "up/down/left/right.\n"
        "Objects are named <colour>#<k>, where k numbers the objects of that colour on that "
        "state in reading order of their bounding-box top-left corner (smaller row first, "
        "then smaller column). Two objects of one colour can share that corner; ties are "
        "then broken by smaller bounding-box bottom row, then smaller right column, then "
        "MORE cells, then the topmost-leftmost cell. Names are per state: the same object "
        "can be named differently on two states.\n"
        "Coordinates are (row, col), zero-based, with row 0 at the top.\n"
        f"Cell characters: {colour_legend()}."
    )


def question_block(case: dict[str, Any]) -> str:
    probe = case["probe"]
    question = case["question"]
    current = state_name(len(case["window"]) - 1)
    if probe == "T1":
        relation = question["relation"]
        return (
            f"QUESTION (about {current})\n"
            f"count: how many objects of colour {question['count_colour']} are on {current}?\n"
            f"bbox: the bounding box of {question['bbox_alias']} on {current}, as "
            f"[top,left,bottom,right].\n"
            f"size: how many cells does {question['size_alias']} occupy on {current}?\n"
            f"relation: on {current}, does {relation['name']}({relation['left']},"
            f"{relation['right']}) hold? {RELATION_TEXT[relation['name']]}."
        )
    if probe == "T2":
        previous = state_name(len(case["window"]) - 2)
        rows = "\n".join(
            f"{row['label']} contains the cell ({row['anchor'][0]},{row['anchor'][1]})"
            for row in question["row_detail"]
        )
        return (
            f"QUESTION (identity between {previous} and {current})\n"
            f"The objects of {current} are identified as B1..Bn instead of being named, and "
            f"their order is scrambled.\n"
            f"For each identifier below, give the name of the SAME object on {previous}, or "
            f"\"new\" if that object did not exist on {previous}.\n"
            f"{rows}"
        )
    if probe == "T3":
        objects = ", ".join(question["objects"])
        return (
            f"QUESTION (about the next action)\n"
            f"From {current}, the action {question['action']} is taken. Its result is NOT "
            f"shown above.\n"
            f"For each of these objects, named on {current}, give its outcome: \"moved\" "
            f"with delta [drow,dcol], \"disappeared\", \"recoloured\", or \"unchanged\".\n"
            f"Objects: {objects}\n"
            f"Also give no_op (true only if no cell of the board changes) and "
            f"level_increment (1 only if this action completes the level)."
        )
    options = "\n".join(
        f"{option['label']} = {action_label(option)}" for option in question["options"]
    )
    if probe == "T4":
        return (
            f"QUESTION (control from {current})\n"
            f"Choose the ONE offered action that, taken in {current}, will "
            f"{question['condition_text']}.\n"
            f"{options}"
        )
    return (
        f"QUESTION (terminal action from {current})\n"
        f"{current} is one action away from completing the level. Choose the offered action "
        f"that completes it.\n"
        f"{options}"
    )


def schema_block(case: dict[str, Any]) -> str:
    schema = output_schema(case)
    return (
        "ANSWER\n"
        "Reply with one bare JSON object and nothing else. It must satisfy this schema:\n"
        + json.dumps(schema, sort_keys=True, separators=(",", ":"))
    )


def render_case(
    arm: str, case: dict[str, Any], window: EvidenceWindow
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the chat messages for one (arm, case) plus the audit metadata."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    head = preamble(window)
    body = representation(arm, case, window)
    question = question_block(case)
    schema = schema_block(case)
    prompt = "\n\n".join([head, body, question, schema])
    messages = [{"role": "user", "content": prompt}]
    return messages, {
        "arm": arm,
        "case_id": case["case_id"],
        "characters": len(prompt),
        "blocks": {
            "preamble": len(head),
            "representation": len(body),
            "question": len(question),
            "schema": len(schema),
        },
        "question_sha256": sha256_bytes(question.encode()),
        "prompt_sha256": sha256_bytes(prompt.encode()),
    }


# ====================================================================================
# Demo
# ====================================================================================


def _demo(env: str) -> int:
    import mu_probes as probes

    partition = probes.es_partition()
    row = next(item for item in partition[env] if item["role"] == "S")
    stubs = probes.session_stubs(env, row["guid"])
    index = next(
        position
        for position in range(len(stubs) - 1, -1, -1)
        if probes.window_members(stubs, position, probes.PREFIX_WINDOW["T1"]) is not None
    )
    members = probes.window_members(stubs, index, probes.PREFIX_WINDOW["T1"])
    grids = probes.collect_grids(
        env,
        row["guid"],
        {f"{stubs[i]['step']}.{stubs[i]['frame_index']}" for i in members},
    )
    window = probes.build_window(env, row["guid"], "S", "T1", stubs, grids, members)
    case = probes.build_t1(window)
    questions = set()
    for arm in ARMS:
        _, meta = render_case(arm, case, window)
        questions.add(meta["question_sha256"])
        print(f"{arm:>8}: {meta['characters']:>7} chars  {meta['blocks']}")
    print(f"question identical across arms: {len(questions) == 1}")
    print()
    print(render_case("map", case, window)[0][0]["content"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", metavar="ENV")
    args = parser.parse_args()
    if args.demo:
        return _demo(args.demo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
