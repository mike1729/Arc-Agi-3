#!/usr/bin/env python3
"""GI-1 layer 2 (baseline rendering) + condition prompt assembly.

Layer 2 reproduces the reference harness's native presentation "as closely as offline replay
permits" (notes/design-pivot.md §2.3), from the vendored reference unmodified:

  - grid IMAGE:  `inference/agent/vision_context.py::frame_to_png_data_url`, exact ARC color
    map, nearest-neighbor upscale pinned to 4 (the frozen S1 config value);
  - grid TEXT:   `inference/utils/grid_utils.py::format_grid_ascii`;
  - framing:     the harness's own system-prompt addenda (`inference/agent/prompts.py`);
  - action names per `agent/action_names.py` / `framework/solver.py` (via gi1_digest).

RUNNER NOTE. `inference/agent/__init__.py` imports the full ToolAgent stack (`requests`, …),
none of which rendering needs, and which the repo's plain python3 does not carry. The leaf
modules are therefore loaded by file path behind a stub package entry that skips ONLY that
__init__'s re-exports. Image generation additionally needs Pillow and is loaded lazily: text
assembly and the text half of the selftest run under plain python3; the full selftest
(including image checks) runs under `.venv/bin/python`, which the selftest reports honestly.

THE OFFLINE REDUCTION, stated once: the live harness gives the model a `python` tool over
runtime views and lets it inspect what it chooses. Offline single-shot queries cannot offer a
tool loop, so the PYTHON / STRUCTURED_RUNTIME_STATE / TOOL_SESSION addenda are omitted and the
runtime views are rendered as text: initial/previous/current frame ascii, the chronological
action list with level-completion markers, and `valid_actions`. Identical for (a) and (b), so
(b)−(a) still isolates output structure.

E3 COMPLETION-CONTENT ABLATION applies to the WHOLE prompt, not the digest alone (review P1):
with `ablate_completions=True`, layer 2 withholds every rendered frame that is the pre-terminal
grid of an observed completion and withholds the completing action's identity in the history
list, while the `levels_completed` increment markers stay visible; layer 3 drops terminal
abstracts; retrieval falls back to the state query. What remains is exactly "the bare fact a
level was completed".

Layer containment holds by construction and is asserted: prompt(c) = prompt(b) + digest;
prompt(d) = prompt(c) + exemplars.

FROZEN FOR GI-1 ITERATION: the TASK BLOCKS (instruction wording, JSON schema text) froze
after MoE-only iteration-slice development and before the measured 27B-8bit iteration pass.
The structured predicate fields come from gi1_predicate_schema (one source of truth with the
gold layer and the K4 scorer).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
_VENDOR = REPO / "agent/reference/taaf/src/ARC3-Inference"
for p in (str(_VENDOR), str(Path(__file__).parent)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_vendored(relpath: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _VENDOR / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub package entry: skips inference/agent/__init__.py (whose only content is ToolAgent/Frame
# re-exports and whose import chain needs `requests`). Leaf modules load underneath it.
if "inference.agent" not in sys.modules:
    _stub = types.ModuleType("inference.agent")
    _stub.__path__ = [str(_VENDOR / "inference/agent")]
    sys.modules["inference.agent"] = _stub

_prompts = _load_vendored("inference/agent/prompts.py", "inference.agent.prompts")
GAME_OVERVIEW_ADDENDUM = _prompts.GAME_OVERVIEW_ADDENDUM
VISUAL_GAME_ADDENDUM = _prompts.VISUAL_GAME_ADDENDUM
MULTIMODAL_CONTEXT_ADDENDUM = _prompts.MULTIMODAL_CONTEXT_ADDENDUM

from inference.utils.grid_utils import format_grid_ascii  # noqa: E402  (light imports)

from s2_apply_labels import TAXONOMY  # noqa: E402  — the closed 10-class codebook
from gi1_digest import action_display, compile_digest, render_digest  # noqa: E402
from gi1_packets import Packet  # noqa: E402
from gi1_predicate_schema import PREDICATE_FIELDS, render_field_guide  # noqa: E402
from gi1_retrieval import query, render_exemplars  # noqa: E402

UPSCALE = 4  # frozen S1 config: multimodal.context = current_grid at upscale 4
_VC = None


def _vision_context():
    global _VC
    if _VC is None:
        try:
            import PIL  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "image rendering needs Pillow — run under .venv/bin/python") from e
        if "inference.agent.runtime_state" not in sys.modules:
            _load_vendored("inference/agent/runtime_state.py",
                           "inference.agent.runtime_state")
        _VC = _load_vendored("inference/agent/vision_context.py",
                             "inference.agent.vision_context")
    return _VC


OFFLINE_CONTEXT_NOTE = (
    "\n\nOffline analysis note:\n"
    "- This turn is analysis only: there is no python tool and no action to take.\n"
    "- You are reviewing a play session up to a checkpoint. The runtime views are rendered as\n"
    "  text below: frame ascii renders, the chronological action list, and valid_actions.\n"
    "- The attached image shows the current frame, exactly as in live play.\n"
)

# ---------------------------------------------------------------- task blocks (GI-1 iteration frozen)

TASK_A_FREEFORM = (
    "\n\nTask:\n"
    "State your current best understanding of this game's goal — the condition that completes "
    "a level. Answer in a few sentences, being specific about which objects, colors, counts, "
    "regions or relations matter and what must become true of them. If you are uncertain, say "
    "what the leading possibilities are and what evidence supports each.\n"
)

# One-line glosses verbatim from the codebook's defining appendix
# (docs/arc-agi-3-screening-experiments-and-results.md, evaluation apparatus, lines 609-618).
CODEBOOK_GLOSSES = {
    "state_relations": "a relation between objects or cells (adjacency, containment, alignment)",
    "quantified_object_conditions": "a condition holding over some or all objects of a kind",
    "counts": "a cardinality reaching a target",
    "region_membership": "an object inside or outside a designated region",
    "symmetry_and_template_match": "the grid matching a symmetry or a supplied template",
    "all_instances_transformed": "every instance of a kind having undergone a transformation",
    "event_occurrence": "a specific event having happened at all",
    "ordered_event_programs": "several events having happened in order",
    "action_conditioned_terminal_triggers": "the condition depending on the action, not only the state",
    "cumulative_counters": "an accumulated quantity crossing a threshold",
}
assert set(CODEBOOK_GLOSSES) == set(TAXONOMY) == set(PREDICATE_FIELDS), \
    "codebook / gloss / predicate-schema drift"


def _codebook_block() -> str:
    lines = ["Goal-class codebook (closed set — every hypothesis must use exactly one class):"]
    for name, desc in CODEBOOK_GLOSSES.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


TASK_BCD_HYPOTHESES = (
    "\n\nTask:\n"
    "Produce your TOP-3 hypotheses for this game's goal — the condition that completes a "
    "level. Do not commit to one: maintain alternatives until evidence separates them.\n\n"
    "{codebook}\n\n{field_guide}\n\n"
    "For every enum field, copy one allowed value exactly as printed above; do not paraphrase "
    "it (for example write `adjacent`, never `adjacent to`).\n\n"
    "Reply with STRICT JSON only, no prose outside it. Your first output character must be "
    "`{{` and your final output character must be `}}`. Do not use Markdown code fences "
    "(``` or ```json). Use this shape:\n"
    "{{\n"
    '  "hypotheses": [\n'
    "    {{\n"
    '      "rank": 1,\n'
    '      "class": "<one codebook class>",\n'
    '      "predicate": {{ ... exactly the fields listed above for that class; entity fields '
    "are short concrete descriptions naming colors/shapes/roles ... }},\n"
    '      "evidence_for": "<observations supporting it>",\n'
    '      "evidence_against": "<observations or gaps weighing against it>"\n'
    "    }},\n"
    "    {{ ... rank 2 ... }},\n"
    "    {{ ... rank 3 ... }}\n"
    "  ],\n"
    '  "discriminating_probe": "<the cheapest single action expected to distinguish the '
    'rank-1 and rank-2 hypotheses, and what each predicts it would do>"\n'
    "}}\n\n"
    "Final format check: output the JSON object itself. Do not add ```json, ```, commentary, "
    "or any character before the opening `{{` or after the closing `}}`.\n"
)


def _bcd_task() -> str:
    return TASK_BCD_HYPOTHESES.format(codebook=_codebook_block(),
                                      field_guide=render_field_guide())


def system_prompt() -> str:
    # Lead sentence and addendum ORDER follow tool_agent._build_system_prompt, which appends
    # GAME -> (runtime state) -> MULTIMODAL -> VISUAL -> (python, tool session). The retained
    # three must keep that relative order: every condition is matched either way, but (a) is the
    # rerun of the S1 status quo and its value depends on being as close to the reference
    # baseline as an offline replay allows. The omitted addenda are the offline reduction
    # documented in the module docstring.
    return ("You are a coding agent solving a grid-based puzzle game."
            + GAME_OVERVIEW_ADDENDUM + MULTIMODAL_CONTEXT_ADDENDUM + VISUAL_GAME_ADDENDUM
            + OFFLINE_CONTEXT_NOTE)


def _preterminal_indices(packet: Packet) -> set[int]:
    return {c.step_index - 1 for c in packet.completions if not c.degenerate}


def ablation_contamination(packet: Packet) -> list[dict]:
    """Checkpoints where E3's completion-content ablation would not actually withhold the board.

    `_frame_block` withholds by step INDEX, so a pre-terminal board that also occupies another
    rendered slot still reaches the model under ablation. Withholding by board CONTENT instead
    closes that leak and opens the opposite one: `initial_frame` is not terminal-packet content,
    and dropping it because it happens to match would make the ablation strip more than the
    treatment declares — breaking matched information just as surely, in the other direction.
    Two identical boards are genuinely ambiguous evidence, so neither rule is right. The honest
    move is to detect the case, report it, and drop those rows from E3 rather than average them
    in silently.

    One entry per (completion, leaking slot); empty means the ablation is clean. `current_frame`
    is never withheld by design — it is the situation, not evidence about the completed level —
    and the attached image shows that same board, so covering the slot covers the image.

    Measured 2026-07-29: empty at all 189 completion checkpoints of the 21 non-reserved games."""
    preterm = _preterminal_indices(packet)
    # Keyed by step index so a slot is counted once: on a two-step packet `previous_frame` IS
    # `initial_frame` — same index, same grid — and reporting it twice would say a single board
    # leaked through two doors. Registration order decides the name; current_frame first because
    # it is the one slot ablation never withholds.
    slots: dict[int, tuple] = {packet.steps[-1].index:
                              ("current_frame", packet.steps[-1].settled)}
    if len(packet.steps) >= 2:
        slots.setdefault(packet.steps[-2].index,
                         ("previous_frame", packet.steps[-2].settled))
    slots.setdefault(1, ("initial_frame", packet.initial_settled))
    leaks = []
    for c in packet.completions:
        if c.degenerate or c.pre_terminal_settled is None:
            continue
        for index, (label, grid) in sorted(slots.items()):
            withheld = label != "current_frame" and index in preterm
            if not withheld and grid == c.pre_terminal_settled:
                leaks.append({"level": c.level, "slot": label, "step": index})
    return leaks


ABLATED_FRAME_NOTE = "(frame withheld under completion-content ablation)"
ABLATED_ACTION_NOTE = "(completing action withheld)"


def _action_history_lines(packet: Packet, ablate: bool) -> list[str]:
    completed_at = {c.step_index: c for c in packet.completions}
    lines = []
    for s in packet.steps:
        c = completed_at.get(s.index)
        display = ABLATED_ACTION_NOTE if (ablate and c) \
            else action_display(s.action_id, s.action_data)
        entry = f"{s.index:>4}  {display}"
        # Under ablation the completing step reduces to the bare fact that a level ended. These
        # flags are properties OF the completing action — an UNDO that returned no frame, a step
        # that forced a full reset — so leaving them while withholding the action name hands back
        # a piece of what was withheld. Measured 2026-07-29: no completing step in the selected
        # sessions carries either flag, so this is latent rather than a correction to any row.
        withheld = ablate and c
        if s.n_frames == 0 and not withheld:
            entry += "  (no frame returned)"
        if s.full_reset and not withheld:
            entry += "  (full reset)"
        if c:
            entry += f"  → LEVEL COMPLETED (levels_completed = {c.level})"
        lines.append(entry)
    return lines


def _frame_block(label: str, grid: list, index: int, preterm: set[int], ablate: bool) -> list[str]:
    if ablate and index in preterm:
        return [f"{label}: {ABLATED_FRAME_NOTE}", ""]
    return [f"{label} ascii:", format_grid_ascii(grid), ""]


def baseline_user_text(packet: Packet, ablate_completions: bool = False) -> str:
    steps = packet.steps
    cur, n = steps[-1], len(steps)
    preterm = _preterminal_indices(packet)
    valid = [action_display(a, {}) if a != 6 else "MOUSE" for a in cur.available_actions]
    parts = [
        f"Session under review — checkpoint {packet.checkpoint_kind} "
        f"(after {n} recorded action(s), level {cur.levels_completed + 1}).",
        f"valid_actions: {valid}",
        "",
        "Action history (chronological; frames before previous_frame are not shown, their "
        "actions are listed):",
        *_action_history_lines(packet, ablate_completions),
        "",
    ]
    if packet.initial_is_post_action:
        parts.append("(note: this client recorded no leading RESET frame, so the first frame "
                     "below is already post-action)")
    parts += _frame_block("initial_frame (step 1, level 1)", packet.initial_settled, 1,
                          preterm, ablate_completions)
    if n >= 2:
        prev = steps[-2]
        parts += _frame_block(f"previous_frame (step {prev.index})", prev.settled, prev.index,
                              preterm, ablate_completions)
    parts += [f"current_frame (step {cur.index}, shown in the attached image) ascii:",
              format_grid_ascii(cur.settled)]
    return "\n".join(parts)


def image_part(packet: Packet) -> dict:
    vc = _vision_context()
    url = vc.frame_to_png_data_url(SimpleNamespace(grid=packet.steps[-1].settled),
                                   upscale=UPSCALE)
    return {"type": "image_url", "image_url": {"url": url}}


def assemble(condition: str, packet: Packet, index: list | None = None,
             ablate_completions: bool = False, with_image: bool = True) -> list[dict]:
    """OpenAI-style messages for conditions a/b/c/d. Floors (e/f) are programmatic — see
    gi1_retrieval. `ablate_completions` applies E3's ablation to EVERY layer of the prompt."""
    text = baseline_user_text(packet, ablate_completions)
    if condition in ("c", "d"):
        digest = compile_digest(packet, ablate_completions=ablate_completions)
        text += "\n\n" + render_digest(digest)
    if condition == "d":
        if index is None:
            raise ValueError("condition d needs a retrieval index")
        hits, _ = query(index, packet, ablate_completions=ablate_completions)
        text += "\n\n" + render_exemplars(hits)
    if condition == "a":
        text += TASK_A_FREEFORM
    elif condition in ("b", "c", "d"):
        text += _bcd_task()
    else:
        raise ValueError(f"unknown prompt condition {condition!r} (floors are programmatic)")
    content: list[dict] = [{"type": "text", "text": text}]
    if with_image:
        content.append(image_part(packet))
    return [{"role": "system", "content": system_prompt()},
            {"role": "user", "content": content}]


def selftest() -> int:
    from gi1_packets import load_timeline, checkpoints, extract, select_sessions
    from gi1_retrieval import build_index

    try:
        import PIL  # noqa: F401
        has_pil = True
    except ImportError:
        has_pil = False

    draw = json.loads((REPO / "logs/gi1_game_draw.json").read_text())
    index = build_index(draw["iteration"])
    failures = []
    for env in ("ls20", "m0r0"):
        sel = select_sessions(env)[0]
        tl = load_timeline(env, sel["guid"])
        cps = checkpoints(tl)
        kind, step = next((k, s) for k, s in cps.items() if s is not None)
        p = extract(tl, kind, step)

        msgs = {c: assemble(c, p, index=index, with_image=has_pil) for c in "abcd"}
        texts = {c: msgs[c][1]["content"][0]["text"] for c in "abcd"}
        if msgs["a"][0]["content"] != msgs["b"][0]["content"]:
            failures.append(f"{env}: system prompts differ between (a) and (b)")
        if texts["a"].replace(TASK_A_FREEFORM, "") != texts["b"].replace(_bcd_task(), ""):
            failures.append(f"{env}: (a)/(b) share more than the task block difference")
        if not texts["c"].startswith(texts["b"].replace(_bcd_task(), "")):
            failures.append(f"{env}: (c) is not (b) + digest")
        if not texts["d"].startswith(texts["c"].replace(_bcd_task(), "")):
            failures.append(f"{env}: (d) is not (c) + exemplars")
        for needle in list(TAXONOMY) + ['"predicate"', "target_count", "events_in_order"]:
            if needle not in texts["b"]:
                failures.append(f"{env}: {needle} missing from task block")
                break
        if format_grid_ascii(p.steps[-1].settled) not in texts["a"]:
            failures.append(f"{env}: current_frame ascii missing from baseline text")

        # E3 ablation must remove completion CONTENT from the whole prompt (review P1)
        comp = cps.get("completion:1")
        if comp:
            pc = extract(tl, "completion:1", comp)
            pre_grid = pc.completions[0].pre_terminal_settled
            act_line = action_display(pc.completions[0].action_id,
                                      pc.completions[0].action_data)
            plain = assemble("d", pc, index=index, with_image=False)[1]["content"][0]["text"]
            abl = assemble("d", pc, index=index, ablate_completions=True,
                           with_image=False)[1]["content"][0]["text"]
            pre_ascii = format_grid_ascii(pre_grid)
            if pre_ascii not in plain:
                failures.append(f"{env}: pre-terminal frame absent from UNablated prompt")
            if pre_ascii in abl:
                failures.append(f"{env}: ABLATED prompt leaks the pre-terminal frame")
            if f"{pc.completions[0].step_index:>4}  {act_line}" in abl:
                failures.append(f"{env}: ABLATED prompt leaks the completing action")
            if "LEVEL COMPLETED" not in abl:
                failures.append(f"{env}: ablation removed the increment (must stay visible)")
            if "- COMPLETED level" in abl:
                failures.append(f"{env}: ABLATED prompt leaks digest terminal abstracts")

        if has_pil:
            import base64
            import io
            from PIL import Image
            vc = _vision_context()
            url = msgs["a"][1]["content"][1]["image_url"]["url"]
            img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
            if img.size != (64 * UPSCALE, 64 * UPSCALE):
                failures.append(f"{env}: image size {img.size} != {(256, 256)}")
            if img.getpixel((0, 0)) != vc.ARC_COLOR_MAP[p.steps[-1].settled[0][0]]:
                failures.append(f"{env}: image pixel (0,0) mismatches grid + color map")
    if failures:
        print(f"SELFTEST FAILED — {len(failures)}:")
        for f in failures:
            print("  " + f)
        return 1
    note = "" if has_pil else "  [image checks SKIPPED — no Pillow under this interpreter; " \
                              "run .venv/bin/python for the full test]"
    print("render selftest OK: a/b differ only in task block; c = b + digest; "
          "d = c + exemplars; ablation strips pre-terminal frame + completing action while "
          "keeping increments; structured predicate schema embedded" + note)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
