"""Direct tests for `gi1_render` — GI-1 layer 2 (baseline rendering) + condition assembly.

WHY THIS FILE EXISTS. What this module renders is what the marginal reads MEAN. (b)−(a)
isolates output structure only if (a) and (b) carry byte-identical evidence; (c)−(b) isolates
the evidence compiler only if (c) is (b) plus the digest and nothing else; (d)−(c) isolates
retrieval on the same terms (notes/design-pivot.md §2.3–2.4). Those are containment properties
of a string, and a one-line drift in a prompt block reassigns a measured difference to the
wrong cause — quietly, with no crash and nothing in the logs to notice it.

`gi1_render.py --selftest` does check the containments, but by `str.replace` / `startswith`
against two real games, and only where the replay mirror is on disk. Three things it cannot
reach:

  - `replace` is not equality. It would pass if (a) and (b) differed anywhere the task blocks
    happen to normalize away; the tests below assert the shared prefix byte-for-byte.
  - The E3 ablation's structural edge case — a completion on step 2, where the pre-terminal
    grid IS the initial board and BOTH rendered frame slots point at it — occurs at no
    checkpoint in the measured corpus, so no real session exercises that collapse.
  - Degenerate (line-1) completions, MOUSE actions, empty-frame steps, single-step packets and
    the post-action-initial note are branch-level shapes a two-game selftest reaches by luck.

Two groups, split by what they need:

  - SYNTHETIC tests build `Packet` objects directly, on 4x4 boards of a single color so that
    "is this board in the prompt?" cannot pass by accident, and against a hand-built retrieval
    index so no corpus scan is needed.
  - CORPUS tests re-assert the containments and the ablation on a real 64x64 session, and skip
    when the mirror is absent.

THE IMPORT IS GUARDED ON PURPOSE. `gi1_render` loads the vendored reference prompts by
absolute path at import time, so it raises wherever `agent/reference/` is absent — a bare
sandbox, or a checkout without the vendor tree. This file must SKIP there, never ERROR: a
collection error in one test file stops the harness for every module in the repo, not just for
this one. `run_mutation_harness.stage_sandbox` does stage the seven vendored files these tests
need, so in the harness they run rather than skip; the guard is for everything else.

Run:
  .venv/bin/python -m pytest tests/test_gi1_render.py -q
"""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_packets as P    # noqa: E402

VENDOR = Path(__file__).resolve().parents[1] / "agent/reference/taaf/src/ARC3-Inference"
REQUIRED_VENDOR = (
    VENDOR / "inference/agent/prompts.py",
    VENDOR / "inference/utils/grid_utils.py",
    VENDOR / "inference/utils/segmentation.py",
)
MISSING_VENDOR = [path for path in REQUIRED_VENDOR if not path.exists()]
if MISSING_VENDOR:                                      # pragma: no cover - no vendor tree
    R = None
    IMPORT_ERROR = FileNotFoundError(
        "missing vendored reference files: " + ", ".join(str(path) for path in MISSING_VENDOR))
else:
    # Deliberately unguarded. Once the required vendor files exist, ImportError,
    # AssertionError, dependency drift, and every other implementation failure must fail
    # collection rather than turn the whole render suite into green skips.
    import gi1_render as R    # noqa: E402
    IMPORT_ERROR = None

# A MARK, not `pytest.skip(..., allow_module_level=True)`. Both skip; only this one leaves the
# tests collected. A module-level skip makes this file contribute zero tests, and pytest exits
# 5 ("no tests ran") when it is invoked on its own — a green run that reads as a broken
# invocation. Marking every test reports the skips and exits 0.
pytestmark = pytest.mark.skipif(
    R is None, reason=f"gi1_render needs the vendored reference tree: {IMPORT_ERROR}")

# Resolved at import, like the packet tests: the corpus is read-only here, never faked.
CORPUS_PRESENT = (P is not None and P.CORPUS.exists() and P.SESSIONS_TABLE.exists()
                  and P.DRAW.exists())
requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT, reason="replay corpus not present (mutation sandbox / no mirror)")


# --------------------------------------------------------------------------- synthetic packets

def _grid(fill: int, n: int = 4) -> list:
    """A settled board of one color. Distinct `fill` gives a distinct ascii render of the same
    length as every other, so no board's render is a substring of another's — which is what
    lets "this board is absent from the prompt" be asserted by containment."""
    return [[fill] * n for _ in range(n)]


def _step(index: int, action_id: int, fill: int, *, levels: int = 0, actions=(1, 2, 3),
          n_frames: int = 1, data: dict | None = None, full_reset: bool = False) -> P.Step:
    return P.Step(index=index, action_id=action_id, action_data=dict(data or {}),
                  n_frames=n_frames, settled=_grid(fill), levels_completed=levels,
                  available_actions=list(actions), state="NOT_FINISHED",
                  full_reset=full_reset)


def _completion(steps: list, at: int, *, level: int = 1, level_start: int = 1) -> P.Completion:
    """Built from the same steps `load_timeline` would have built it from — the pre-terminal
    grid is the board at `at`-1, and a completion on line 1 has none and is degenerate."""
    s = steps[at - 1]
    return P.Completion(step_index=at, level=level, increment=1, action_id=s.action_id,
                        action_data=s.action_data, level_start_index=level_start,
                        pre_terminal_settled=steps[at - 2].settled if at >= 2 else None,
                        degenerate=at < 2)


def _packet(steps: list, completions=(), kind: str = "offset:10") -> P.Packet:
    return P.Packet(env="zz01", guid="g1", checkpoint_kind=kind,
                    checkpoint_step=steps[-1].index, initial_settled=steps[0].settled,
                    initial_is_post_action=steps[0].action_id != 0, steps=list(steps),
                    completions=list(completions),
                    available_actions=steps[-1].available_actions)


def _zero_completion() -> P.Packet:
    """S1's stuck-on-level-1 regime: evidence, no terminal transition (design-pivot §2.3)."""
    return _packet([_step(1, 0, 1), _step(2, 1, 2), _step(3, 2, 3)])


def _step_two_completion() -> P.Packet:
    """The initial-frame edge case: the completion lands on step 2, so its pre-terminal grid is
    the very first recorded board and both rendered frame slots resolve to it."""
    steps = [_step(1, 0, 1), _step(2, 1, 2, levels=1)]
    return _packet(steps, [_completion(steps, 2)], kind="completion:1")


def _late_completion() -> P.Packet:
    """A completion at step 5: initial and current boards stay visible, only the step-4
    pre-terminal board is withheld — the other side of the same ablation boundary."""
    steps = [_step(1, 0, 1), _step(2, 1, 2), _step(3, 2, 3), _step(4, 3, 4),
             _step(5, 4, 5, levels=1)]
    return _packet(steps, [_completion(steps, 5)], kind="completion:1")


def _degenerate_completion() -> P.Packet:
    """A completion on the very first recorded line: an increment with no pre-terminal grid."""
    steps = [_step(1, 5, 1, levels=1), _step(2, 1, 2, levels=1)]
    return _packet(steps, [_completion(steps, 1)], kind="completion:1")


# The two ablation points the design distinguishes: the pre-terminal grid as the very first
# recorded board, and as an interior board with frames on both sides of it.
ABLATABLE = pytest.mark.parametrize(
    "build", [_step_two_completion, _late_completion],
    ids=["step-2-initial-frame", "later-completion"])


# --------------------------------------------------------------------------- synthetic index

def _abstract(level: int, action: str, length: int, *, pre=True, transition=True) -> dict:
    out = {"level_completed": level, "completing_action": action,
           "level_length_actions": length, "distinct_actions_in_level": ["UP"],
           "degenerate": False}
    if pre:
        out["pre_terminal_inventory"] = {"n_objects": 2,
                                         "by_color": {"w": {"objects": 2, "pixels": 8}}}
    if transition:
        out["final_transition"] = {"changed_cells": 4, "color_transitions": {"w->g": 4}}
    return out


# Three source games, so the default k=3 and the one-record-per-game cap both bind, and all
# three `render_exemplars` branches (full / inventory only / neither) get rendered.
INDEX = [
    {"env": "aa11", "guid": "s-aa11", "step": 9, "level": 1,
     "vector": [0.9 if i % 3 == 0 else 0.1 for i in range(42)],
     "abstract": _abstract(1, "SPACE", 9)},
    {"env": "bb22", "guid": "s-bb22", "step": 4, "level": 2,
     "vector": [0.1 if i % 3 == 0 else 0.9 for i in range(42)],
     "abstract": _abstract(2, "MOUSE(row=1, col=2)", 4, transition=False)},
    {"env": "cc33", "guid": "s-cc33", "step": 21, "level": 3,
     "vector": [0.4 + 0.01 * i for i in range(42)],
     "abstract": _abstract(3, "UP", 21, pre=False, transition=False)},
]


def _text(condition: str, packet: P.Packet, **kw) -> str:
    """The user text of one assembled condition. Text-only unless a test says otherwise."""
    kw.setdefault("with_image", False)
    return R.assemble(condition, packet, **kw)[1]["content"][0]["text"]


def _body(text: str) -> str:
    """The evidence half of a (b)/(c)/(d) prompt: everything before the shared task block.
    Asserting the task block is the exact suffix is half the containment claim — if the task
    text moved, the marginal reads would no longer be comparing like with like."""
    task = R._bcd_task()
    assert text.endswith(task), "the (b)/(c)/(d) task block is not the prompt's suffix"
    return text[:-len(task)]


# --------------------------------------------------------------------- (a)/(b) shared context

def test_conditions_a_and_b_share_the_rendered_evidence_byte_for_byte():
    """The whole meaning of (b)−(a). Not "similar", not "the same after normalization": the
    two prompts are one identical evidence string plus two different task blocks."""
    p = _late_completion()
    shared = R.baseline_user_text(p)
    ta, tb = _text("a", p), _text("b", p)
    assert ta == shared + R.TASK_A_FREEFORM
    assert tb == shared + R._bcd_task()
    assert ta[:len(shared)] == tb[:len(shared)] == shared
    assert ta[len(shared):] != tb[len(shared):]   # and the difference is real, not vacuous


def test_the_system_prompt_is_byte_identical_across_all_four_conditions():
    """The framing is evidence too; a per-condition system prompt would confound every read."""
    p = _late_completion()
    rendered = {json.dumps(R.assemble(c, p, index=INDEX, with_image=False)[0], sort_keys=True)
                for c in "abcd"}
    assert len(rendered) == 1


def test_the_attached_image_is_byte_identical_between_a_and_b():
    pytest.importorskip("PIL")
    p = _late_completion()
    a = R.assemble("a", p, with_image=True)[1]["content"][1]
    b = R.assemble("b", p, with_image=True)[1]["content"][1]
    assert a == b


def test_the_free_form_condition_carries_none_of_the_codebook_vocabulary():
    """(a) is the S1 status quo. If a class name leaked into its prompt it would already be
    receiving part of (b)'s treatment, and (b)−(a) would understate the effect."""
    p = _late_completion()
    ta, tb = _text("a", p), _text("b", p)
    assert R._codebook_block() not in ta
    assert R.render_field_guide() not in ta
    # `counts` is also an ordinary English word and (a) uses it in that sense; the nine
    # snake_case identifiers are unambiguous, so they are what is checked for.
    assert not [cls for cls in R.TAXONOMY if "_" in cls and cls in ta]
    assert not [cls for cls in R.TAXONOMY if cls not in tb]


def test_conditions_a_and_b_carry_no_digest_and_no_exemplars_even_when_an_index_is_passed():
    p = _late_completion()
    for condition in ("a", "b"):
        text = _text(condition, p, index=INDEX)
        assert "Compiled evidence digest" not in text
        assert "Analogous completions retrieved" not in text


# ------------------------------------------------------------------------ additive containment

def test_condition_c_is_condition_b_plus_the_compiled_digest_and_nothing_else():
    """(c)−(b) isolates the evidence compiler only under exact containment."""
    p = _late_completion()
    body_b, body_c = _body(_text("b", p)), _body(_text("c", p))
    digest = R.render_digest(R.compile_digest(p))
    assert digest                                  # a vacuous digest would fake containment
    assert body_c == body_b + "\n\n" + digest


def test_condition_d_is_condition_c_plus_the_retrieved_exemplars_and_nothing_else():
    """(d)−(c) isolates retrieval on the same terms."""
    p = _late_completion()
    body_c = _body(_text("c", p))
    body_d = _body(_text("d", p, index=INDEX))
    hits, _kind = R.query(INDEX, p)
    assert hits
    assert body_d == body_c + "\n\n" + R.render_exemplars(hits)


def test_the_layers_are_strictly_additive_so_each_body_is_a_prefix_of_the_next():
    """The property stated as containment rather than as three equalities: b ⊂ c ⊂ d."""
    p = _late_completion()
    body_b = _body(_text("b", p))
    body_c = _body(_text("c", p))
    body_d = _body(_text("d", p, index=INDEX))
    assert body_c.startswith(body_b) and len(body_c) > len(body_b)
    assert body_d.startswith(body_c) and len(body_d) > len(body_c)


def test_the_task_block_is_identical_across_b_c_and_d():
    p = _late_completion()
    task = R._bcd_task()
    for condition in ("b", "c", "d"):
        assert _text(condition, p, index=INDEX).endswith(task)


def test_the_digest_layer_is_present_at_a_zero_completion_checkpoint_too():
    """Containment must not depend on there being a completion to compile."""
    p = _zero_completion()
    body_b, body_c = _body(_text("b", p)), _body(_text("c", p))
    assert body_c == body_b + "\n\n" + R.render_digest(R.compile_digest(p))
    assert "Compiled evidence digest" in body_c


# ---------------------------------------------------------------- completion-content ablation

@ABLATABLE
def test_ablation_withholds_the_pre_terminal_board_from_the_whole_prompt(build):
    """E3: the pre-terminal grid is completion CONTENT and must not survive anywhere in the
    prompt — not in the frame blocks, not in the digest, not via retrieval (review P1)."""
    p = build()
    pre_ascii = R.format_grid_ascii(p.completions[0].pre_terminal_settled)
    plain = _text("d", p, index=INDEX)
    ablated = _text("d", p, index=INDEX, ablate_completions=True)
    assert pre_ascii in plain            # the unablated prompt really does carry it
    assert pre_ascii not in ablated
    assert R.ABLATED_FRAME_NOTE in ablated


def test_the_step_two_completion_collapses_both_frame_slots():
    """The edge case the corpus never reaches: with the completion on step 2, `initial_frame`
    and `previous_frame` are the same withheld board, so BOTH slots must be withheld and the
    current frame is the only board the model sees."""
    p = _step_two_completion()
    ablated = R.baseline_user_text(p, True)
    assert ablated.count(R.ABLATED_FRAME_NOTE) == 2
    assert R.format_grid_ascii(_grid(1)) not in ablated
    assert R.format_grid_ascii(_grid(2)) in ablated       # current frame, never ablated


def test_a_later_completion_withholds_one_slot_and_keeps_the_initial_board():
    """The control for the test above: ablation is targeted at the pre-terminal board, not a
    blanket blackout of the session's frames."""
    p = _late_completion()
    ablated = R.baseline_user_text(p, True)
    assert ablated.count(R.ABLATED_FRAME_NOTE) == 1
    assert R.format_grid_ascii(_grid(1)) in ablated       # initial board survives
    assert R.format_grid_ascii(_grid(5)) in ablated       # current board survives
    assert R.format_grid_ascii(_grid(4)) not in ablated   # pre-terminal board does not


@ABLATABLE
def test_ablation_withholds_the_completing_action_from_the_history(build):
    p = build()
    c = p.completions[0]
    line = f"{c.step_index:>4}  {R.action_display(c.action_id, c.action_data)}"
    plain = R.baseline_user_text(p)
    ablated = R.baseline_user_text(p, True)
    assert line in plain
    assert line not in ablated
    assert R.ABLATED_ACTION_NOTE in ablated


@ABLATABLE
def test_ablation_keeps_the_levels_completed_increment_visible(build):
    """The count is free platform metadata in every deployment regime (design-pivot §5, E3),
    so hiding it would test a state that does not occur. What is withheld is the content of
    the terminal transition, never the bare fact that a level was completed."""
    p = build()
    ablated = _text("d", p, index=INDEX, ablate_completions=True)
    assert "→ LEVEL COMPLETED (levels_completed = 1)" in ablated
    assert ", level 2)." in ablated              # the header's current-level number survives


@ABLATABLE
def test_ablation_leaves_every_non_completing_history_line_untouched(build):
    """Ablation removes the terminal transition, not the trajectory that led to it."""
    p = build()
    ablated = R.baseline_user_text(p, True)
    for s in p.steps:
        if s.index == p.completions[0].step_index:
            continue
        assert f"{s.index:>4}  {R.action_display(s.action_id, s.action_data)}" in ablated


@ABLATABLE
def test_ablation_drops_the_terminal_abstracts_but_keeps_the_rest_of_the_digest(build):
    """Asserted on (c), deliberately: `render_exemplars` emits the same "board immediately
    before the completing action" wording for RETRIEVED completions, which are another game's
    and are not ablated, so (d) cannot distinguish the two sources by text."""
    p = build()
    plain, ablated = _text("c", p), _text("c", p, ablate_completions=True)
    assert "- COMPLETED level" in plain
    assert "board immediately before the completing action" in plain
    assert "- COMPLETED level" not in ablated
    assert "board immediately before the completing action" not in ablated
    assert "Compiled evidence digest" in ablated          # the compiler layer itself remains


@ABLATABLE
def test_ablation_reaches_retrieval_so_exemplars_come_from_the_state_query(build):
    """The ablation applies to EVERY layer: with the completions withheld they can no longer
    anchor the query, and (d) must render the state-query neighbours instead."""
    p = build()
    assert R.query(INDEX, p)[1] == "terminal"
    hits_ablated, kind = R.query(INDEX, p, ablate_completions=True)
    assert kind == "state"
    body = _body(_text("d", p, index=INDEX, ablate_completions=True))
    assert body.endswith("\n\n" + R.render_exemplars(hits_ablated))


def test_a_degenerate_completion_withholds_the_action_but_has_no_frame_to_withhold():
    """A completion on line 1 has no pre-terminal board at all, so the frame note must NOT
    appear — withholding a board that was never evidence would make the ablated and unablated
    prompts differ for a reason unrelated to completion content."""
    p = _degenerate_completion()
    ablated = R.baseline_user_text(p, True)
    assert R.ABLATED_FRAME_NOTE not in ablated
    assert R.ABLATED_ACTION_NOTE in ablated
    assert "→ LEVEL COMPLETED (levels_completed = 1)" in ablated


def test_ablation_is_a_no_op_when_the_packet_has_no_completions():
    """The zero-completion rows are reported separately and never averaged in (design-pivot
    §5). If ablation perturbed them at all, the E3 contrast would carry a second difference."""
    p = _zero_completion()
    assert R.baseline_user_text(p) == R.baseline_user_text(p, True)
    assert (_text("d", p, index=INDEX)
            == _text("d", p, index=INDEX, ablate_completions=True))


# ------------------------------------------------------------------------- image / text paths

def test_the_text_only_path_emits_exactly_one_content_part():
    p = _late_completion()
    content = R.assemble("b", p, with_image=False)[1]["content"]
    assert [part["type"] for part in content] == ["text"]


def test_the_multimodal_path_appends_the_current_frame_at_the_frozen_upscale():
    """The frozen S1 config is `multimodal.context = current_grid` at upscale 4; the image is
    the CURRENT board, not the initial one, and its colors come from the vendored map."""
    pytest.importorskip("PIL")
    from PIL import Image
    p = _late_completion()
    content = R.assemble("b", p, with_image=True)[1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url"]
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert img.size == (4 * R.UPSCALE, 4 * R.UPSCALE)
    colors = R._vision_context().ARC_COLOR_MAP
    assert img.getpixel((0, 0)) == colors[p.steps[-1].settled[0][0]]
    assert img.getpixel((0, 0)) != colors[p.initial_settled[0][0]]


def test_the_prompt_text_is_identical_with_and_without_the_image():
    """The image is additive, so a text-only run and a multimodal run stay comparable."""
    pytest.importorskip("PIL")
    p = _late_completion()
    with_image = R.assemble("c", p, with_image=True)[1]["content"][0]["text"]
    assert with_image == _text("c", p)


@pytest.mark.parametrize("build", [_zero_completion, _step_two_completion, _late_completion,
                                   _degenerate_completion],
                         ids=["zero", "step-2", "later", "degenerate"])
def test_the_current_frame_is_never_a_pre_terminal_frame(build):
    """Why `image_part` needs no ablation branch. Pre-terminal indices are `step_index - 1` of
    completions at or before the checkpoint, so they are strictly below the checkpoint step —
    the board in the image can never be one of them, at any checkpoint."""
    p = build()
    assert p.steps[-1].index not in R._preterminal_indices(p)


def test_the_image_is_unchanged_by_the_ablation():
    """Follows from the test above, asserted end-to-end so the two cannot drift apart."""
    pytest.importorskip("PIL")
    p = _late_completion()
    plain = R.assemble("d", p, index=INDEX, with_image=True)[1]["content"][1]
    ablated = R.assemble("d", p, index=INDEX, ablate_completions=True,
                         with_image=True)[1]["content"][1]
    assert plain == ablated


# --------------------------------------------------------------------- codebook / field guide

def test_the_gloss_the_taxonomy_and_the_predicate_schema_name_the_same_classes():
    """The module asserts this at import; asserted here too so the drift is a named test
    failure rather than an ImportError from three modules away."""
    assert set(R.CODEBOOK_GLOSSES) == set(R.TAXONOMY) == set(R.PREDICATE_FIELDS)
    assert len(R.TAXONOMY) == 10                 # the codebook is closed at 10 classes


def test_every_class_reaches_the_prompt_with_its_defining_gloss():
    tb = _text("b", _late_completion())
    for name, gloss in R.CODEBOOK_GLOSSES.items():
        assert f"- {name}: {gloss}" in tb


def test_every_predicate_field_and_enum_option_reaches_the_prompt():
    """The scorer compares hypothesis fields against gold field by field, so a field the
    prompt never named is a field the model cannot be marked wrong on."""
    tb = _text("b", _late_completion())
    guide = {line.split(":", 1)[0][2:]: line
             for line in R.render_field_guide().splitlines() if line.startswith("- ")}
    assert set(guide) == set(R.PREDICATE_FIELDS)
    for cls, fields in R.PREDICATE_FIELDS.items():
        assert guide[cls] in tb
        for name, spec in fields.items():
            assert name in guide[cls]
            if spec[0] == "enum":
                assert f"{name} ∈ {{{', '.join(spec[1])}}}" in guide[cls]
            elif spec[0] == "int":
                assert f"{name}: integer" in guide[cls]


def test_the_requested_json_shape_names_every_key_the_scorer_reads():
    tb = _text("b", _late_completion())
    for key in ("hypotheses", "rank", "class", "predicate", "evidence_for",
                "evidence_against", "discriminating_probe"):
        assert f'"{key}"' in tb


# ----------------------------------------------------------------------- assembly error paths

@pytest.mark.parametrize("condition", ["e", "f", "", "A", "ab", "abcd"])
def test_conditions_outside_a_to_d_are_refused(condition):
    """(e) and (f) are programmatic floors and have no prompt; silently rendering one would
    put a Qwen call where the design says there is none."""
    with pytest.raises(ValueError, match="unknown prompt condition"):
        R.assemble(condition, _late_completion(), index=INDEX, with_image=False)


def test_condition_d_without_a_retrieval_index_raises():
    with pytest.raises(ValueError, match="condition d needs a retrieval index"):
        R.assemble("d", _late_completion(), index=None, with_image=False)


@pytest.mark.parametrize("condition", ["a", "b", "c"])
def test_conditions_a_to_c_need_no_retrieval_index(condition):
    assert _text(condition, _late_completion(), index=None)


# ------------------------------------------------------------------- baseline rendering detail

def test_the_header_reports_the_checkpoint_kind_and_the_level_being_played():
    p = _late_completion()
    text = R.baseline_user_text(p)
    assert text.startswith("Session under review — checkpoint completion:1 "
                           "(after 5 recorded action(s), level 2).")


def test_mouse_actions_render_row_and_col_but_valid_actions_names_the_action_only():
    """`action_display(6, {})` would render MOUSE(row=0, col=0) — an advertised capability
    printed as a concrete coordinate the session never took."""
    steps = [_step(1, 0, 1), _step(2, 6, 2, data={"x": 3, "y": 7}, actions=(1, 6))]
    text = R.baseline_user_text(_packet(steps))
    assert "   2  MOUSE(row=7, col=3)" in text
    assert "valid_actions: ['UP', 'MOUSE']" in text


def test_a_step_with_no_returned_frame_and_a_full_reset_are_both_marked():
    """cn04's empty-`frame` lines carry the previous board forward; the history has to say so,
    or the model reads a repeated board as a real no-op observation."""
    steps = [_step(1, 0, 1), _step(2, 1, 1, n_frames=0), _step(3, 0, 2, full_reset=True)]
    text = R.baseline_user_text(_packet(steps))
    assert "   2  UP  (no frame returned)" in text
    assert "   3  RESET  (full reset)" in text
    assert text.count("(no frame returned)") == 1     # only the step that returned none
    assert text.count("(full reset)") == 1


def test_the_post_action_initial_note_appears_only_for_clients_that_recorded_no_reset():
    """cn04 and some lf52 sessions open on an action, so their "initial board" is already
    post-action; the renderer says so instead of letting it read as the level's start."""
    note = "this client recorded no leading RESET frame"
    with_reset = _packet([_step(1, 0, 1), _step(2, 1, 2)])
    without = _packet([_step(1, 3, 1), _step(2, 1, 2)])
    assert with_reset.initial_is_post_action is False
    assert note not in R.baseline_user_text(with_reset)
    assert without.initial_is_post_action is True
    assert note in R.baseline_user_text(without)


def test_a_single_step_packet_renders_no_previous_frame_block():
    """Boundary: with one recorded action there is no board before the current one, and the
    renderer must omit the slot rather than repeat the current board under a stale label."""
    text = R.baseline_user_text(_packet([_step(1, 0, 1)]))
    assert "previous_frame (step " not in text        # the fixed preamble names it regardless
    assert "initial_frame (step 1, level 1) ascii:" in text
    assert "current_frame (step 1, shown in the attached image) ascii:" in text


def test_the_system_prompt_carries_the_vendored_addenda_in_the_reference_order():
    """GAME -> MULTIMODAL -> VISUAL, matching tool_agent._build_system_prompt. Every condition
    is matched whichever order we pick, so this is not about the contrast: (a) is the rerun of
    the S1 status quo, and its whole value is being as close to the reference baseline as an
    offline replay allows. An earlier version of this test asserted the inverted order and so
    blessed the drift instead of catching it."""
    sp = R.system_prompt()
    positions = [sp.index(block) for block in (R.GAME_OVERVIEW_ADDENDUM,
                                               R.MULTIMODAL_CONTEXT_ADDENDUM,
                                               R.VISUAL_GAME_ADDENDUM,
                                               R.OFFLINE_CONTEXT_NOTE)]
    assert positions == sorted(positions)
    assert sp.startswith("You are a coding agent solving a grid-based puzzle game.")


_TOOL_AGENT = (Path(__file__).resolve().parents[1]
               / "agent/reference/taaf/src/ARC3-Inference/inference/agent/tool_agent.py")


@pytest.mark.skipif(not _TOOL_AGENT.exists(),
                    reason="full vendored reference source not present")
def test_the_reference_source_still_appends_those_addenda_in_that_order():
    """Anti-drift, read from the reference rather than taken on trust from the comment beside
    it. Reads the file as text, so it needs none of tool_agent's own dependencies. This is the
    only render test that may skip on a missing vendor tree; the order assertion above runs
    everywhere, which is what keeps a skip from hiding the regression."""
    retained = ["GAME_OVERVIEW_ADDENDUM", "MULTIMODAL_CONTEXT_ADDENDUM", "VISUAL_GAME_ADDENDUM"]
    appended = [line.split("+=", 1)[1].strip()
                for line in _TOOL_AGENT.read_text().splitlines() if "prompt +=" in line]
    assert [name for name in appended if name in retained] == retained


def test_the_system_prompt_omits_the_tool_loop_addenda():
    """The offline reduction, stated once in the module docstring: a single-shot query has no
    python tool, so promising one would describe a capability the turn does not have."""
    sp = R.system_prompt()
    for omitted in (R._prompts.PYTHON_ADDENDUM,
                    R._prompts.STRUCTURED_RUNTIME_STATE_ADDENDUM,
                    R._prompts.COMPACT_TOOL_SESSION_ADDENDUM):
        assert omitted not in sp


def test_the_current_frame_ascii_is_always_rendered():
    """The one board every condition is guaranteed to see, ablated or not."""
    for build in (_zero_completion, _step_two_completion, _late_completion,
                  _degenerate_completion):
        p = build()
        current = R.format_grid_ascii(p.steps[-1].settled)
        assert current in R.baseline_user_text(p)
        assert current in R.baseline_user_text(p, True)


# --------------------------------------------------------------------------- measured corpus

def _real_packet(env: str = "ls20", kind: str = "completion:1") -> P.Packet:
    sel = P.select_sessions(env)[0]
    tl = P.load_timeline(env, sel["guid"])
    step = P.checkpoints(tl)[kind]
    assert step is not None, f"{env} has no {kind} checkpoint — re-measure the fixture"
    return P.extract(tl, kind, step)


@requires_corpus
def test_the_shared_context_and_containment_hold_on_a_real_session():
    """The synthetic packets fix the shapes; this fixes that a real 64x64 session with a real
    history does not break the property some other way."""
    p = _real_packet()
    shared = R.baseline_user_text(p)
    assert _text("a", p) == shared + R.TASK_A_FREEFORM
    body_b, body_c = _body(_text("b", p)), _body(_text("c", p))
    body_d = _body(_text("d", p, index=INDEX))
    assert body_c == body_b + "\n\n" + R.render_digest(R.compile_digest(p))
    assert body_d == body_c + "\n\n" + R.render_exemplars(R.query(INDEX, p)[0])


@requires_corpus
def test_the_ablation_holds_on_a_real_completion_checkpoint():
    p = _real_packet()
    c = p.completions[0]
    assert not c.degenerate
    pre_ascii = R.format_grid_ascii(c.pre_terminal_settled)
    plain = _text("d", p, index=INDEX)
    ablated = _text("d", p, index=INDEX, ablate_completions=True)
    assert pre_ascii in plain
    assert pre_ascii not in ablated
    assert f"{c.step_index:>4}  {R.action_display(c.action_id, c.action_data)}" not in ablated
    assert f"→ LEVEL COMPLETED (levels_completed = {c.level})" in ablated
    assert "- COMPLETED level" not in ablated


@requires_corpus
def test_a_real_current_frame_renders_at_sixty_four_squared_times_the_upscale():
    pytest.importorskip("PIL")
    from PIL import Image
    p = _real_packet("ls20", "offset:10")
    url = R.assemble("a", p, with_image=True)[1]["content"][1]["image_url"]["url"]
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert img.size == (P.GRID * R.UPSCALE, P.GRID * R.UPSCALE)
    assert img.getpixel((0, 0)) == R._vision_context().ARC_COLOR_MAP[p.steps[-1].settled[0][0]]


# ----------------------------------------------------------------- ablation contamination

def test_a_clean_packet_reports_no_ablation_contamination():
    """The ordinary shape: the pre-terminal board sits only at the slot the ablation withholds."""
    steps = [_step(1, 0, 1), _step(2, 1, 2), _step(3, 2, 3), _step(4, 3, 4, levels=1)]
    packet = _packet(steps, [_completion(steps, 4)])
    assert R.ablation_contamination(packet) == []


def test_a_pre_terminal_board_recurring_at_an_unwithheld_slot_is_reported():
    """The leak this detector exists for: the board returns to an earlier rendered state before
    the completing action, so withholding by step index still ships it at the other slot."""
    steps = [_step(1, 0, 7), _step(2, 1, 2), _step(3, 2, 7), _step(4, 3, 4, levels=1)]
    packet = _packet(steps, [_completion(steps, 4)])
    assert R.ablation_contamination(packet) == [
        {"level": 1, "slot": "initial_frame", "step": 1}]
    # and the leak is real: the withheld board is still in the ablated prompt
    assert R.format_grid_ascii(_grid(7)) in R.baseline_user_text(packet, ablate_completions=True)


def test_a_pre_terminal_board_equal_to_the_current_board_is_reported():
    """current_frame is never withheld — it is the situation, not evidence about the completed
    level — so a pre-terminal board that recurs there leaks however the indices fall."""
    steps = [_step(1, 0, 1), _step(2, 1, 5), _step(3, 2, 5, levels=1)]
    packet = _packet(steps, [_completion(steps, 3)])
    assert R.ablation_contamination(packet) == [
        {"level": 1, "slot": "current_frame", "step": 3}]


def test_the_withheld_slot_is_not_itself_reported_as_a_leak():
    """The step-2 case, where initial_frame IS the pre-terminal board and the ablation already
    withholds it. Reporting that would make every such checkpoint look contaminated."""
    assert R.ablation_contamination(_step_two_completion()) == []


def test_a_degenerate_completion_is_never_reported():
    """It has no pre-terminal board to leak, so it cannot contaminate the ablation — even if a
    caller hands one in carrying a grid it should not have."""
    steps = [_step(1, 0, 1, levels=1), _step(2, 1, 2)]
    forged = P.Completion(step_index=1, level=1, increment=1, action_id=0, action_data={},
                          level_start_index=1, pre_terminal_settled=_grid(1), degenerate=True)
    assert R.ablation_contamination(_packet(steps, [forged])) == []


def test_a_single_step_packet_is_handled_without_reaching_for_a_previous_frame():
    assert R.ablation_contamination(_packet([_step(1, 0, 1)])) == []
