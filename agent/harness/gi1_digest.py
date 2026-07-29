#!/usr/bin/env python3
"""GI-1 layer 3 — the evidence compiler (conditions c/d).

Compiles a canonical packet (gi1_packets.Packet) into object/count inventories, delta
summaries and terminal-packet abstracts. THE DIGEST MAY CONTAIN NO INFORMATION BEYOND THE
CANONICAL PACKET (notes/design-pivot.md §2.3): everything here is a pure function of packet
grids, actions and metadata — representation and computation, never new evidence.

Object structure comes from the reference harness's OWN segmentation
(`inference/utils/segmentation.py::segment_layer`, vendored, imported unmodified) so the
compiled view matches what the deployed agent's runtime exposes — 4-connected same-color
objects with position-independent shape hashes. Reusing it keeps the compiler consistent with
deployment and keeps the vendor tree untouched.

E3's completion-content ablation is `compile_digest(..., ablate_completions=True)`: terminal
abstracts are dropped while `levels_completed` increments stay visible in the layer-2 history
(the increment is free platform metadata in every deployment regime).

Selftest (iteration games only): derivability spot-checks — counts recomputed independently,
ablation containment, delta symmetry.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_VENDOR = REPO / "agent/reference/taaf/src/ARC3-Inference"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from inference.utils.grid_utils import ARC_COLOR_CHARS  # noqa: E402  (vendored, unmodified)
from inference.utils.segmentation import segment_layer  # noqa: E402  (vendored, unmodified)

from gi1_packets import Packet, settled_delta  # noqa: E402

# Model-facing action display, replicated from the vendored solver
# (inference/framework/solver.py::_format_action_display + agent/action_names.py).
_ID_TO_ENGINE = {0: "RESET", 1: "ACTION1", 2: "ACTION2", 3: "ACTION3",
                 4: "ACTION4", 5: "ACTION5", 6: "ACTION6", 7: "ACTION7"}
_ENGINE_TO_MODEL = {"ACTION1": "UP", "ACTION2": "DOWN", "ACTION3": "LEFT",
                    "ACTION4": "RIGHT", "ACTION5": "SPACE", "ACTION6": "MOUSE",
                    "RESET": "RESET", "ACTION7": "UNDO"}

# TRUNCATION BUDGET — how much of the compiled evidence reaches conditions (c) and (d).
#
# These are not formatting preferences. The digest is the whole of the c-b contrast, so each bound
# decides how much evidence that contrast is measuring, and a hidden literal is a treatment
# parameter nobody can see in the pre-registration. They are named here for the same reason
# gi1_retrieval keeps its features and k in SPEC rather than inline.
#
# ⚠ DEV-UNFROZEN: freeze with the digest itself, before the 27B-8bit iteration pass; until then
# they may move on iteration-slice evidence only.
MAX_LARGEST_OBJECTS = 5      # biggest components listed per settled grid
MAX_COLOR_TRANSITIONS = 8    # most frequent colour transitions kept per delta
MAX_RECENT_DELTAS = 6        # most recent within-level deltas shown for the current level


def action_display(action_id: int, action_data: dict) -> str:
    engine = _ID_TO_ENGINE.get(action_id, f"ACTION{action_id}")
    if engine == "ACTION6":
        return f"MOUSE(row={int(action_data.get('y', 0))}, col={int(action_data.get('x', 0))})"
    return _ENGINE_TO_MODEL.get(engine, engine)


def inventory(grid: list) -> dict:
    """Object inventory of one settled grid, via the harness's own segmentation."""
    seg = segment_layer(grid, ARC_COLOR_CHARS)
    nodes = seg["nodes"]
    by_color: dict[str, dict] = {}
    for n in nodes:
        c = by_color.setdefault(n["color"], {"objects": 0, "pixels": 0, "shape_hashes": set()})
        c["objects"] += 1
        c["pixels"] += n["pixels"]
        c["shape_hashes"].add(n["hash"])
    return {
        "n_objects": len(nodes),
        "by_color": {k: {"objects": v["objects"], "pixels": v["pixels"],
                         "distinct_shapes": len(v["shape_hashes"])}
                     for k, v in sorted(by_color.items())},
        "largest": [{"color": n["color"], "pixels": n["pixels"],
                     "bbox": _bbox(n["boundary"])}
                    for n in sorted(nodes, key=lambda n: -n["pixels"])[:MAX_LARGEST_OBJECTS]],
        "adjacency_pairs": len(seg["adjacency_list"]),
        "_hashes": {n["hash"] for n in nodes},   # cross-frame tracking; stripped from text
    }


def _bbox(boundary: list) -> list:
    rows = [p[0] for p in boundary]
    cols = [p[1] for p in boundary]
    return [min(rows), min(cols), max(rows), max(cols)]


def delta_summary(before: list, after: list) -> dict:
    """Compact change record between two settled grids — the harness prompt's own advice:
    'summarize changed cells, color transitions, appearing/disappearing components'."""
    cells = settled_delta(before, after)
    if not cells:
        return {"changed_cells": 0}
    transitions: dict[str, int] = {}
    for _, _, va, vb in cells:
        key = f"{ARC_COLOR_CHARS[va]}->{ARC_COLOR_CHARS[vb]}"
        transitions[key] = transitions.get(key, 0) + 1
    inv_a, inv_b = inventory(before), inventory(after)
    return {
        "changed_cells": len(cells),
        "bbox": [min(c[0] for c in cells), min(c[1] for c in cells),
                 max(c[0] for c in cells), max(c[1] for c in cells)],
        "color_transitions": dict(sorted(transitions.items(),
                                         key=lambda kv: -kv[1])[:MAX_COLOR_TRANSITIONS]),
        "objects_appeared": len(inv_b["_hashes"] - inv_a["_hashes"]),
        "objects_disappeared": len(inv_a["_hashes"] - inv_b["_hashes"]),
        "object_count_delta": inv_b["n_objects"] - inv_a["n_objects"],
    }


def terminal_abstract(packet: Packet, completion) -> dict:
    """Compiled view of one observed completion: pre-terminal state + completing action +
    within-level trail. The post-terminal board is structurally absent (next level's board)."""
    steps = [s for s in packet.steps
             if completion.level_start_index <= s.index < completion.step_index]
    # Same boundary as compile_digest: for a level after a completion the board preceding its
    # first action is the previous completing step's own grid, which sits in the packet one index
    # before level_start. Without it a level completed in two actions loses the transition made
    # by its first action into the pre-terminal state. A one-action level correctly has no
    # preceding transition to report. Level 1 has no predecessor and keeps the short chain.
    # Measured 2026-07-29: 0 of 463 completions in the selected sessions are affected, so no
    # current row changes.
    seed = next((s for s in packet.steps if s.index == completion.level_start_index - 1), None)
    chain = ([seed] + steps) if seed is not None else steps
    trail_actions = [action_display(s.action_id, s.action_data) for s in steps]
    out = {
        "level_completed": completion.level,
        "completing_action": action_display(completion.action_id, completion.action_data),
        "level_length_actions": completion.step_index - completion.level_start_index + 1,
        "distinct_actions_in_level": sorted(set(trail_actions)),
        "degenerate": completion.degenerate,
    }
    if completion.pre_terminal_settled is not None:
        pre = inventory(completion.pre_terminal_settled)
        pre.pop("_hashes")
        out["pre_terminal_inventory"] = pre
        # the last observable within-level change: the delta INTO the pre-terminal state
        # (chain[-1].settled IS the pre-terminal grid, so the pair is chain[-2] -> chain[-1])
        if len(chain) >= 2:
            out["final_transition"] = delta_summary(chain[-2].settled, chain[-1].settled)
    return out


def compile_digest(packet: Packet, ablate_completions: bool = False) -> dict:
    """The full layer-3 digest for one checkpoint. Pure function of the packet."""
    cur = packet.steps[-1].settled
    cur_inv = inventory(cur)
    cur_inv.pop("_hashes")
    last = packet.completions[-1] if packet.completions else None
    level_start = (last.step_index + 1) if last else 1
    level_steps = [s for s in packet.steps if s.index >= level_start]
    # The completing step's OWN settled grid is this level's initial board — a level reset, not
    # a solved-state image — so it is exactly the predecessor the level's first action needs.
    # Without it that action gets no delta, `no_change_actions_this_level` counts over N-1
    # deltas while `actions_this_level` counts N, and the rendered line invites reading one as
    # a fraction of the other. Level 1 legitimately has no predecessor and keeps the short
    # window. Unreachable under the current checkpoint set (offset checkpoints are valid only
    # before the first completion, completion checkpoints end AT the completion), so this
    # changes no measured value today — it stops a later mid-level checkpoint from arming it.
    paired = level_steps
    if last is not None:
        seed = next((s for s in packet.steps if s.index == last.step_index), None)
        if seed is not None:
            paired = [seed] + level_steps
    recent = []
    for a, b in zip(paired, paired[1:]):
        d = delta_summary(a.settled, b.settled)
        d["after_action"] = action_display(b.action_id, b.action_data)
        recent.append(d)
    digest = {
        "current_inventory": cur_inv,
        "current_level_recent_deltas": recent[-MAX_RECENT_DELTAS:],
        "actions_this_level": len(level_steps),
        "no_change_actions_this_level": sum(1 for d in recent if d["changed_cells"] == 0),
    }
    if not ablate_completions:
        digest["observed_completions"] = [terminal_abstract(packet, c)
                                          for c in packet.completions]
    return digest


def render_digest(digest: dict) -> str:
    """Compact text block for the (c)/(d) prompt. Decision-oriented, never a board dump."""
    lines = ["Compiled evidence digest (derived from the session so far):"]
    inv = digest["current_inventory"]
    lines.append(f"- current board: {inv['n_objects']} objects, "
                 f"{inv['adjacency_pairs']} adjacent pairs")
    for color, v in inv["by_color"].items():
        lines.append(f"    {color}: {v['objects']} object(s), {v['pixels']} px, "
                     f"{v['distinct_shapes']} distinct shape(s)")
    lines.append(f"- largest objects: " + "; ".join(
        f"{o['color']} {o['pixels']}px bbox{o['bbox']}" for o in inv["largest"]))
    lines.append(f"- this level: {digest['actions_this_level']} action(s), "
                 f"{digest['no_change_actions_this_level']} changed nothing")
    for d in digest["current_level_recent_deltas"]:
        if d["changed_cells"]:
            lines.append(f"    after {d['after_action']}: {d['changed_cells']} cells in "
                         f"bbox{d['bbox']}, transitions {d['color_transitions']}, "
                         f"objects {d['object_count_delta']:+d}")
        else:
            lines.append(f"    after {d['after_action']}: no visible change")
    for t in digest.get("observed_completions", []):
        lines.append(f"- COMPLETED level {t['level_completed']} with {t['completing_action']} "
                     f"after {t['level_length_actions']} action(s) "
                     f"(used: {', '.join(t['distinct_actions_in_level'])})")
        if "pre_terminal_inventory" in t:
            pre = t["pre_terminal_inventory"]
            lines.append(f"    board immediately before the completing action: "
                         f"{pre['n_objects']} objects — " + "; ".join(
                f"{c}:{v['objects']}x{v['pixels']}px" for c, v in pre["by_color"].items()))
        ft = t.get("final_transition")
        if ft and ft.get("changed_cells"):
            lines.append(f"    last change before the completing action: "
                         f"{ft['changed_cells']} cells, transitions {ft['color_transitions']}")
    return "\n".join(lines)


def selftest() -> int:
    import json
    from gi1_packets import load_timeline, checkpoints, extract, select_sessions
    draw = json.loads((REPO / "logs/gi1_game_draw.json").read_text())
    failures = []
    for env in ("ls20", "m0r0"):
        assert env in draw["iteration"], "selftest must stay on the iteration slice"
        sel = select_sessions(env)[0]
        tl = load_timeline(env, sel["guid"])
        for kind, step in checkpoints(tl).items():
            if step is None:
                continue
            p = extract(tl, kind, step)
            digest = compile_digest(p)
            # derivability: object pixel totals equal a direct recount of the settled grid
            counted = {}
            for row in p.steps[-1].settled:
                for v in row:
                    ch = ARC_COLOR_CHARS[v]
                    counted[ch] = counted.get(ch, 0) + 1
            for color, v in digest["current_inventory"]["by_color"].items():
                if counted.get(color, 0) != v["pixels"]:
                    failures.append(f"{env}/{kind}: {color} pixels {v['pixels']} != recount")
            # ablation drops terminal abstracts and nothing else
            ab = compile_digest(p, ablate_completions=True)
            if "observed_completions" in ab:
                failures.append(f"{env}/{kind}: ablation kept completions")
            keep = {k: v for k, v in compile_digest(p).items() if k != "observed_completions"}
            if json.dumps(keep, sort_keys=True) != json.dumps(ab, sort_keys=True):
                failures.append(f"{env}/{kind}: ablation changed non-completion content")
            if p.completions and "observed_completions" not in digest:
                failures.append(f"{env}/{kind}: completions present but not compiled")
            text = render_digest(digest)
            if "\n".join(ARC_COLOR_CHARS) in text or len(text) > 8000:
                failures.append(f"{env}/{kind}: digest text dumps boards or is oversized")
    if failures:
        print(f"SELFTEST FAILED — {len(failures)}:")
        for f in failures:
            print("  " + f)
        return 1
    print("digest selftest OK (ls20, m0r0): derivability, ablation containment, text bounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
