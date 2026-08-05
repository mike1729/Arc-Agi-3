#!/usr/bin/env python3
"""E2 probe channel — execute Qwen's probes and measure what they were worth.

`notes/e2-probe-channel.md`. Zero model calls: this scores outputs the E2 slice already
produced. Both slices judged `next_probe` the strongest channel in the run and neither
scored it; this turns the judged channel into a measured one.

TWO QUESTIONS, IN ORDER
-----------------------
1. Does executing a probe resolve the unresolved miner key it targets, and does it beat
   RANDOM probing at equal action cost? The control is load-bearing: without it,
   "the probe resolved the key" may only mean "any new evidence resolves the key".
2. Can natural-language probes be executed mechanically at all — how often are they
   translatable, reachable, or already answered by evidence the model was holding?

THE TRANSLATOR ADDS NOTHING
---------------------------
`PROBES` below is the whole translation and it is written by hand, once, before anything
runs. Each entry carries the verbatim probe text next to its formal spec so the two can be
compared by eye. The rules the translation follows:

  * a precondition is a conjunction over the miner's OWN v1 guard vocabulary (present:C,
    count:C, adj:C:direction) evaluated on the pre-state, plus a small set of COMPUTED
    predicates that read the grid the way the probe text does (is cell (r,c) background,
    does colour C's object touch colour D, what is the horizontal gap between two
    components). Reading a colour off the grid to find cells to click is reading; deciding
    WHICH colour when the text does not say is inventing;
  * a clause that would require inventing content is not translated. If it is the whole
    probe, the probe is `untranslatable` and the minimal missing piece is named. If it is
    one arm or one modifier of an otherwise executable probe, it is recorded verbatim in
    `dropped_arms` / `unenforced_clauses` and the probe runs WITHOUT it — dropping a
    constraint makes a probe weaker, never different, and the omission is on the record;
  * `out-of-band` is a probe that asks for instrumentation or logging rather than a game
    action. Nothing is executed for it.

Vocabulary: the digests these probes were written from are v1 — verified, not assumed
(`--stage verify-vocab` re-derives one and checks the stored prompt contains no
`clicked_adjacent_to` line). v1 is therefore the primary scoring vocabulary; v2 deltas are
reported alongside because they cost seconds.

DETERMINISM
-----------
Every state is reached by FULL PREFIX REPLAY from RESET (REPLAY-DET). Two states with the
same hash are never treated as interchangeable — m0r0's alias conflicts are exactly the
case where the latent parity is fixed by the prefix and not by the settled frame.

Run:
  .venv/bin/python agent/harness/e2_probe_channel.py --stage specs
  .venv/bin/python agent/harness/e2_probe_channel.py --stage run --jobs 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from arcengine import ActionInput, GameAction  # noqa: E402

from e1_candidates import segment  # noqa: E402
from e1_explorer import SIMPLE_ACTIONS, tier1_nodes  # noqa: E402
from e2_dose import load_store  # noqa: E402
from es_candidates import _Objects  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames  # noqa: E402
from rs_e0 import Rule, mine, score  # noqa: E402
from rs_transitions import (  # noqa: E402
    ITERATION_GAMES,
    ROOT,
    Transition,
    effect_signature,
    guard_features,
    load_game,
    set_vocab,
)

STORE = ROOT / "logs/e1_store_v2"
PROBE_STORE = ROOT / "logs/e2_probe_channel_store"   # local-only (.gitignore /logs/*/*)
SPECS_OUT = ROOT / "logs/e2_probe_specs.json"
OUTPUT = ROOT / "logs/e2_probe_channel.json"
TRACES = ROOT / "logs/e2_slice_traces"
FORMAT_VERSION = 1

MODE = "full"                 # the layer the slice ran on
CANDIDATE_CAP = 96            # e1_explorer's tier-1 cap, reused for the control
TRANSITION_CAP = 8            # (w) executed transitions per spec; logged when it binds
MAX_STATES_PER_ARM = 12       # (w) satisfying states considered per arm before selection
CONTROL_REPLICATES = 5        # (w)
CONTROL_SEEDS = (1, 2, 3, 4, 5)   # never 20260804 — that is the slice's own phase-1 seed


# ======================================================================================
# Step 1 — the translation. Written by hand; nothing below invents a clause.
# ======================================================================================
#
# probe_id     <game>_<dose>_s<n>   dose "125" or "full"; s0 = seed 20260804, s1/s2 = the
#                                   slice-1.1 reruns at seeds 1 and 2
# nl_class     executable-as-stated | out-of-band | untranslatable
# contrast     across_arms | across_repetitions | single_outcome | none
#              — `single_outcome` means the probe asks what happens and predicts no
#                difference between two conditions; it is scored for key resolution but
#                NOT for discrimination, because there is nothing to discriminate.
# targeted     list of miner keys, or "executed" when the probe's own text leaves the key
#              to whatever colour the click lands on.
#
# precondition entries are [feature, op, value] with op in eq/ne/in/not_in. A feature
# `adj:C:*` matches if ANY of the four directions satisfies the test.

PROBES: list[dict[str, Any]] = [
    # ---- seed 20260804 (slice 1) -----------------------------------------------------
    {
        "probe_id": "dc22_125_s0", "game": "dc22", "dose": 125, "seed": 20260804,
        "verbatim": "Execute ACTION6 on colour 8 in a state where adj:13:left=8 and "
                    "count:0=14 to observe whether it triggers the appear(4)x5 + "
                    "disappear(...) chain, flips the hidden toggle, or does nothing.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 8]],
        "contrast": "single_outcome",
        "predicted_contrast": "one of: the appear(4)x5+disappear chain / a hidden-toggle "
                              "flip / no change",
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:13:left", "eq", 8], ["count:0", "eq", 14]],
                  "steps": [{"t": "click", "colour": 8}]}],
    },
    {
        "probe_id": "dc22_full_s0", "game": "dc22", "dose": None, "seed": 20260804,
        "verbatim": "Execute ACTION6 on colour 0 in two carefully constructed states that "
                    "are identical in all adj:* features but differ in count:3 "
                    "(specifically, one state with count:3=1 and one with count:3=2).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 0]],
        "contrast": "across_arms",
        "predicted_contrast": "the two count:3 values give different effects, with every "
                              "adj:* feature held equal",
        "match_on": "adj",
        "arms": [
            {"arm_id": "count3=1", "precondition": [["count:3", "eq", 1]],
             "steps": [{"t": "click", "colour": 0}]},
            {"arm_id": "count3=2", "precondition": [["count:3", "eq", 2]],
             "steps": [{"t": "click", "colour": 0}]},
        ],
    },
    {
        "probe_id": "ft09_125_s0", "game": "ft09", "dose": 125, "seed": 20260804,
        "verbatim": "Perform ACTION6 on two carefully chosen colour-9 components in a "
                    "fresh state: one that is directly adjacent (orthogonally) to the "
                    "colour-12 object, and one that is not adjacent to colour 12 (e.g., "
                    "isolated or touching only background/other colours).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 9]],
        "contrast": "across_arms",
        "predicted_contrast": "a colour-9 component touching colour 12 behaves differently "
                              "from one that does not",
        "same_state": True,
        "arms": [
            {"arm_id": "touching12", "precondition": [],
             "steps": [{"t": "click", "colour": 9, "touching": 12}]},
            {"arm_id": "not_touching12", "precondition": [],
             "steps": [{"t": "click", "colour": 9, "not_touching": 12}]},
        ],
    },
    {
        "probe_id": "ft09_full_s0", "game": "ft09", "dose": None, "seed": 20260804,
        "verbatim": "ACTION6 on colour 9 when count:8 == 16 and present:11 == True.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 9]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated — the probe names a condition and asks for the "
                              "outcome",
        "arms": [{"arm_id": "a",
                  "precondition": [["count:8", "eq", 16], ["present:11", "eq", True]],
                  "steps": [{"t": "click", "colour": 9}]}],
    },
    {
        "probe_id": "ls20_125_s0", "game": "ls20", "dose": 125, "seed": 20260804,
        "verbatim": "Record the exact grid coordinates of objects 11 and 12 before each "
                    "transition, and log the global step count.",
        "nl_class": "out-of-band",
        "missing_piece": "no game action is requested — this asks the harness to log "
                         "coordinates and a step counter",
        "targeted": [], "contrast": "none", "arms": [],
    },
    {
        "probe_id": "ls20_full_s0", "game": "ls20", "dose": None, "seed": 20260804,
        "verbatim": "Execute a controlled positional test: Reset to a known state, place "
                    "colours 9 and 12 at a fixed coordinate, and systematically press each "
                    "action while varying their distance to the nearest grid edge and "
                    "adjacent obstacles.",
        "nl_class": "untranslatable",
        "missing_piece": "a primitive that PLACES an object at a chosen coordinate. The "
                         "action set has none, and the probe names no action sequence that "
                         "would reach such a configuration.",
        "targeted": [], "contrast": "none", "arms": [],
    },
    {
        "probe_id": "m0r0_125_s0", "game": "m0r0", "dose": 125, "seed": 20260804,
        "verbatim": "Execute ACTION2 from the initial state, then immediately perform "
                    "ACTION6 on colour 11 when adj:12:left == 11.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 11]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "press", "id": 2},
                            {"t": "click", "colour": 11,
                             "require": [["adj:12:left", "eq", 11]]}]}],
    },
    {
        "probe_id": "m0r0_full_s0", "game": "m0r0", "dose": None, "seed": 20260804,
        "verbatim": "Execute ACTION5 repeatedly from a single, fixed visual state to see if "
                    "results strictly alternate between no-change and reshape(0).",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 5]],
        "contrast": "across_repetitions",
        "predicted_contrast": "successive ACTION5 presses alternate between no-change and "
                              "reshape(0)",
        "translation_note": "the text fixes no particular state; the origin is used, "
                            "deterministically",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "press", "id": 5, "repeat": 8}]}],
    },
    {
        "probe_id": "tu93_125_s0", "game": "tu93", "dose": 125, "seed": 20260804,
        "verbatim": "Execute ACTION2 in a state where adj:9:right=4 (or adj:9:left=2), "
                    "then immediately follow with ACTION1 or ACTION4 to shift the swapped "
                    "4/9 pair toward the color 14 tile.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1], ["A", 4]],
        "contrast": "across_arms",
        "predicted_contrast": "the follow-up action shifts the swapped 4/9 pair; which of "
                              "ACTION1/ACTION4 does so is what the arms separate",
        "translation_note": "'toward the color 14 tile' names no action-to-direction "
                            "mapping, so both stated follow-ups are executed rather than "
                            "one being chosen",
        "arms": [
            {"arm_id": "right4_then_A1", "precondition": [["adj:9:right", "eq", 4]],
             "steps": [{"t": "press", "id": 2}, {"t": "press", "id": 1}]},
            {"arm_id": "right4_then_A4", "precondition": [["adj:9:right", "eq", 4]],
             "steps": [{"t": "press", "id": 2}, {"t": "press", "id": 4}]},
            {"arm_id": "left2_then_A1", "precondition": [["adj:9:left", "eq", 2]],
             "steps": [{"t": "press", "id": 2}, {"t": "press", "id": 1}]},
            {"arm_id": "left2_then_A4", "precondition": [["adj:9:left", "eq", 2]],
             "steps": [{"t": "press", "id": 2}, {"t": "press", "id": 4}]},
        ],
    },
    {
        "probe_id": "tu93_full_s0", "game": "tu93", "dose": None, "seed": 20260804,
        "verbatim": "Execute ACTION1/2/3/4 when object 4 is directly adjacent to color 14 "
                    "in the direction of 14.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1], ["A", 2], ["A", 3], ["A", 4]],
        "contrast": "across_arms",
        "predicted_contrast": "the four actions differ when object 4 abuts colour 14",
        "translation_note": "'in the direction of 14' names no action-to-direction mapping; "
                            "all four stated actions are executed under adj:4:<any>=14",
        "arms": [
            {"arm_id": f"A{n}", "precondition": [["adj:4:*", "eq", 14]],
             "steps": [{"t": "press", "id": n}]}
            for n in (1, 2, 3, 4)
        ],
    },
    {
        "probe_id": "vc33_125_s0", "game": "vc33", "dose": 125, "seed": 20260804,
        "verbatim": "Execute ACTION6 on colour 0 (or 5) in a state where adj:7:down == 0 "
                    "but count:0 == 1 (or vice versa) to break the perfect correlation and "
                    "reveal whether the true causal guard is spatial or numerical.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 0], ["A6", 5]],
        "contrast": "across_arms",
        "predicted_contrast": "clicking colour 0 and colour 5 under a correlation-breaking "
                              "state separates a spatial guard from a numerical one",
        "dropped_arms": ["'(or vice versa)' — the swapped condition names no literal value "
                         "for count:0, and a guard tests feature = one literal value"],
        "arms": [
            {"arm_id": "click0",
             "precondition": [["adj:7:down", "eq", 0], ["count:0", "eq", 1]],
             "steps": [{"t": "click", "colour": 0}]},
            {"arm_id": "click5",
             "precondition": [["adj:7:down", "eq", 0], ["count:0", "eq", 1]],
             "steps": [{"t": "click", "colour": 5}]},
        ],
    },
    {
        "probe_id": "vc33_full_s0", "game": "vc33", "dose": None, "seed": 20260804,
        "verbatim": "Execute ACTION6 on any colour in a state where count:0 == 1 AND "
                    "count:4 == 1.",
        "nl_class": "executable-as-stated",
        "targeted": "executed",
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "arms": [{"arm_id": "a",
                  "precondition": [["count:0", "eq", 1], ["count:4", "eq", 1]],
                  "steps": [{"t": "click", "any_present_colour": True}]}],
    },

    # ---- seed 1 (slice 1.1) ----------------------------------------------------------
    {
        "probe_id": "dc22_125_s1", "game": "dc22", "dose": 125, "seed": 1,
        "verbatim": "Probe the compound condition for ACTION6 validity by constructing a "
                    "state where adj:13:down=4 but varying adj:14:left systematically.",
        "nl_class": "untranslatable",
        "missing_piece": "the click target. ACTION6 needs a cell and the probe names no "
                         "colour, component or coordinate to click.",
        "targeted": [], "contrast": "none", "arms": [],
    },
    {
        "probe_id": "dc22_full_s1", "game": "dc22", "dose": None, "seed": 1,
        "verbatim": "Execute ACTION6 on colour 2 from a state where adj:13:down=4 and "
                    "adj:14:left=2, then immediately repeat the exact same action without "
                    "moving.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 2]],
        "contrast": "across_repetitions",
        "predicted_contrast": "the second identical click differs from the first",
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:13:down", "eq", 4], ["adj:14:left", "eq", 2]],
                  "steps": [{"t": "click", "colour": 2}, {"t": "repeat"}]}],
    },
    {
        "probe_id": "ft09_125_s1", "game": "ft09", "dose": 125, "seed": 1,
        "verbatim": "Perform ACTION6 on colour 9 when count:8=16, count:9=20, and "
                    "adj:12:right=edge, but deliberately place the clicked colour 9 at a "
                    "different relative distance or offset from colour 12 than in the four "
                    "successful transitions.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 9]],
        "contrast": "single_outcome",
        "predicted_contrast": "an unseen clicked-component offset from colour 12 fails to "
                              "reproduce the successful outcome",
        "translation_note": "'a different offset from colour 12' is resolved as: the "
                            "top-left cell of the clicked colour-9 component minus the "
                            "top-left cell of colour 12's object, a vector not taken by any "
                            "stored transition of this key. Selecting an existing component "
                            "is reading; 'place' is not executable and is not attempted.",
        "arms": [{"arm_id": "a",
                  "precondition": [["count:8", "eq", 16], ["count:9", "eq", 20],
                                   ["adj:12:right", "eq", "edge"]],
                  "steps": [{"t": "click", "colour": 9, "novel_offset_to": 12}]}],
    },
    {
        "probe_id": "ft09_full_s1", "game": "ft09", "dose": None, "seed": 1,
        "verbatim": "Execute ACTION6 on colour 8 at a location where count:8 = 17 and "
                    "count:9 = 19, but adj:12:right = edge (or any value other than 11).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 8]],
        "contrast": "across_arms",
        "predicted_contrast": "adj:12:right away from 11 changes the outcome",
        "arms": [
            {"arm_id": "edge",
             "precondition": [["count:8", "eq", 17], ["count:9", "eq", 19],
                              ["adj:12:right", "eq", "edge"]],
             "steps": [{"t": "click", "colour": 8}]},
            {"arm_id": "not11",
             "precondition": [["count:8", "eq", 17], ["count:9", "eq", 19],
                              ["adj:12:right", "not_in", [11, "edge"]]],
             "steps": [{"t": "click", "colour": 8}]},
        ],
    },
    {
        "probe_id": "ls20_125_s1", "game": "ls20", "dose": 125, "seed": 1,
        "verbatim": "Construct a state where color 12 has a color 3 directly to its right, "
                    "but no color 3 to its left, up, or down, then press ACTION2.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 2]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated — a directional adjacency condition and one "
                              "action",
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:12:right", "eq", 3], ["adj:12:left", "ne", 3],
                                   ["adj:12:up", "ne", 3], ["adj:12:down", "ne", 3]],
                  "steps": [{"t": "press", "id": 2}]}],
    },
    {
        "probe_id": "ls20_full_s1", "game": "ls20", "dose": None, "seed": 1,
        "verbatim": "The single most informative test is to log target_cell_colour for "
                    "every transition, then replay a controlled sequence to confirm if the "
                    "condition is target_cell_empty.",
        "nl_class": "out-of-band",
        "missing_piece": "asks for logging, and for a feature the miner already has: "
                         "click_colour and click_on_background are in the v1 vocabulary "
                         "and were in the digest the probe was written from",
        "targeted": [], "contrast": "none", "arms": [],
    },
    {
        "probe_id": "m0r0_125_s1", "game": "m0r0", "dose": 125, "seed": 1,
        "verbatim": "Execute ACTION6 on colour 5 twice in immediate succession from the "
                    "exact initial state (e3fc5841).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 5]],
        "contrast": "across_repetitions",
        "predicted_contrast": "the second identical click differs from the first",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "click", "colour": 5}, {"t": "repeat"}]}],
    },
    {
        "probe_id": "m0r0_full_s1", "game": "m0r0", "dose": None, "seed": 1,
        "verbatim": "Replay the exact initial state (e3fc5841) and execute ACTION1 "
                    "repeatedly in a tight loop, logging the outcome of each press to "
                    "confirm deterministic cycling or isolate RNG state.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1]],
        "contrast": "across_repetitions",
        "predicted_contrast": "repeated ACTION1 from a fixed state cycles deterministically",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "press", "id": 1, "repeat": 8}]}],
    },
    {
        "probe_id": "tu93_125_s1", "game": "tu93", "dose": 125, "seed": 1,
        "verbatim": "Explicitly test adj:9:left for ACTION1, ACTION2, and ACTION4 by "
                    "manipulating object 9's position until a 2, 4, or empty cell is "
                    "directly to its left, then pressing the action.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1], ["A", 2], ["A", 4]],
        "contrast": "across_arms",
        "predicted_contrast": "adj:9:left in {2, 4, empty} separates the three actions' "
                              "outcomes",
        "translation_note": "'manipulating until' is executed as finding a stored state "
                            "with that adjacency; the store is searched, nothing is placed",
        "arms": [
            {"arm_id": f"left{v!r}_A{n}", "precondition": [["adj:9:left", "eq", v]],
             "steps": [{"t": "press", "id": n}]}
            for v in (2, 4, None) for n in (1, 2, 4)
        ],
    },
    {
        "probe_id": "tu93_full_s1", "game": "tu93", "dose": None, "seed": 1,
        "verbatim": "Run a focused exploration that deliberately places the colour-4 object "
                    "directly adjacent to the colour-9 object in the click direction while "
                    "holding all other adjacencies constant to observe whether this yields "
                    "the toggle effect or the reshape-only effect.",
        "nl_class": "untranslatable",
        "missing_piece": "the action. 'the click direction' presupposes a click the probe "
                         "never specifies, and no ACTION is named anywhere in the text.",
        "targeted": [], "contrast": "none", "arms": [],
    },
    {
        "probe_id": "vc33_125_s1", "game": "vc33", "dose": 125, "seed": 1,
        "verbatim": "Execute ACTION6 on colour 0 in a state where adj:7:down=None and "
                    "count:0=1, but systematically vary the untracked adjacency adj:0:right "
                    "(or adj:0:down) to determine if direct object-to-object adjacency is "
                    "the true condition.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 0]],
        "contrast": "across_arms",
        "predicted_contrast": "varying adj:0:right under a fixed adj:7:down/count:0 changes "
                              "the outcome iff object-to-object adjacency is the real guard",
        "stratify": {"kind": "feature", "name": "adj:0:right"},
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:7:down", "eq", None], ["count:0", "eq", 1]],
                  "steps": [{"t": "click", "colour": 0}]}],
    },
    {
        "probe_id": "vc33_full_s1", "game": "vc33", "dose": None, "seed": 1,
        "verbatim": "Deliberately construct a state where adj:7:right = 4, adj:7:down = "
                    "None, and count:0 = 1, then execute ACTION6 on colour 3 (or any "
                    "neutral colour).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 3]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:7:right", "eq", 4], ["adj:7:down", "eq", None],
                                   ["count:0", "eq", 1]],
                  "steps": [{"t": "click", "colour": 3}]}],
    },

    # ---- seed 2 (slice 1.1) ----------------------------------------------------------
    {
        "probe_id": "dc22_125_s2", "game": "dc22", "dose": 125, "seed": 2,
        "verbatim": "Execute ACTION6 on a colour instance explicitly placed at the top-left "
                    "board corner (guaranteeing adj:CLICKED:up=None and "
                    "adj:CLICKED:left=None), while logging click_row, click_col, and "
                    "adj:CLICKED:direction.",
        "nl_class": "executable-as-stated",
        "targeted": "executed",
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "unenforced_clauses": ["the logging clause (click_row, click_col, "
                               "adj:CLICKED:direction) is instrumentation, not an action; "
                               "the executed transitions carry all three anyway"],
        "translation_note": "'placed at the top-left corner' is executed as clicking cell "
                            "(0,0) in a state where that cell is not background",
        "arms": [{"arm_id": "a", "precondition": [["bg_at:0:0", "eq", False]],
                  "steps": [{"t": "click", "cell": [0, 0]}]}],
    },
    {
        "probe_id": "dc22_full_s2", "game": "dc22", "dose": None, "seed": 2,
        "verbatim": "Execute ACTION6 on colour 2 twice consecutively on the exact same "
                    "object and log the exact pixel boundary of colour 0 before and after "
                    "each click to map the reshape effect to a deterministic state machine.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 2]],
        "contrast": "across_repetitions",
        "predicted_contrast": "the second identical click differs from the first",
        "arms": [{"arm_id": "a", "precondition": [["present:2", "eq", True]],
                  "steps": [{"t": "click", "colour": 2}, {"t": "repeat"}]}],
    },
    {
        "probe_id": "ft09_125_s2", "game": "ft09", "dose": 125, "seed": 2,
        "verbatim": "Execute ACTION6 on colour 9 when count:9=20, adj:12:right=edge, but "
                    "deliberately ensure count:8=17.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 9]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "arms": [{"arm_id": "a",
                  "precondition": [["count:9", "eq", 20], ["adj:12:right", "eq", "edge"],
                                   ["count:8", "eq", 17]],
                  "steps": [{"t": "click", "colour": 9}]}],
    },
    {
        "probe_id": "ft09_full_s2", "game": "ft09", "dose": None, "seed": 2,
        "verbatim": "Click ACTION6 on colour 8 when count:8 = 17 but count:9 = 20 (or 18) "
                    "to confirm the trigger strictly requires the conjunction count:8=17 "
                    "AND count:9=19.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 8]],
        "contrast": "across_arms",
        "predicted_contrast": "count:9 off 19 suppresses the trigger, in both directions",
        "arms": [
            {"arm_id": "count9=20",
             "precondition": [["count:8", "eq", 17], ["count:9", "eq", 20]],
             "steps": [{"t": "click", "colour": 8}]},
            {"arm_id": "count9=18",
             "precondition": [["count:8", "eq", 17], ["count:9", "eq", 18]],
             "steps": [{"t": "click", "colour": 8}]},
        ],
    },
    {
        "probe_id": "ls20_125_s2", "game": "ls20", "dose": 125, "seed": 2,
        "verbatim": "Test ACTION2 with a controlled adj:12:down condition by placing a 3 "
                    "directly below object 12 and pressing ACTION2 to confirm the "
                    "directional adjacency rule.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 2]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated",
        "arms": [{"arm_id": "a", "precondition": [["adj:12:down", "eq", 3]],
                  "steps": [{"t": "press", "id": 2}]}],
    },
    {
        "probe_id": "ls20_full_s2", "game": "ls20", "dose": None, "seed": 2,
        "verbatim": "Execute ACTION1 in two carefully constructed states where adj:12:up = "
                    "3 is true in both, but count:3 differs or the shape/orientation of "
                    "object 3 differs.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1]],
        "contrast": "across_arms",
        "predicted_contrast": "count:3 changes the outcome at fixed adj:12:up=3",
        "dropped_arms": ["'or the shape/orientation of object 3 differs' — shape is not a "
                         "guard feature and the probe names no shape to hold or vary"],
        "stratify": {"kind": "feature", "name": "count:3"},
        "arms": [{"arm_id": "a", "precondition": [["adj:12:up", "eq", 3]],
                  "steps": [{"t": "press", "id": 1}]}],
    },
    {
        "probe_id": "m0r0_125_s2", "game": "m0r0", "dose": 125, "seed": 2,
        "verbatim": "Execute ACTION6 on colour 11 twice consecutively from the initial "
                    "state (e3fc5841).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 11]],
        "contrast": "across_repetitions",
        "predicted_contrast": "the second identical click differs from the first",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "click", "colour": 11}, {"t": "repeat"}]}],
    },
    {
        "probe_id": "m0r0_full_s2", "game": "m0r0", "dose": None, "seed": 2,
        "verbatim": "Execute ACTION1 repeatedly from the initial state for 6-8 turns, "
                    "logging the exact effect each time to reveal the hidden phase update "
                    "rule.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1]],
        "contrast": "across_repetitions",
        "predicted_contrast": "repeated ACTION1 from a fixed state reveals a phase cycle",
        "duplicate_of": "m0r0_full_s1",
        "arms": [{"arm_id": "a", "start": "origin", "precondition": [],
                  "steps": [{"t": "press", "id": 1, "repeat": 8}]}],
    },
    {
        "probe_id": "tu93_125_s2", "game": "tu93", "dose": 125, "seed": 2,
        "verbatim": "Construct a controlled test state where adj:4:up=2 and adj:9:down=4 "
                    "while holding all other tracked adjacencies constant to the reshape "
                    "group's values and apply ACTION1.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1]],
        "contrast": "single_outcome",
        "predicted_contrast": "none stated beyond the named adjacency conjunction",
        "unenforced_clauses": ["'holding all other tracked adjacencies constant to the "
                               "reshape group's values' — the probe names neither the group "
                               "nor the values, so the conjunction is executed without it"],
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:4:up", "eq", 2], ["adj:9:down", "eq", 4]],
                  "steps": [{"t": "press", "id": 1}]}],
    },
    {
        "probe_id": "tu93_full_s2", "game": "tu93", "dose": None, "seed": 2,
        "verbatim": "Execute ACTION1 in a state where adj:6:right=0 and adj:4:down=9, then "
                    "systematically vary the clicked cell coordinates or force a change in "
                    "count:0 while holding all adjacency relations constant.",
        "nl_class": "executable-as-stated",
        "targeted": [["A", 1]],
        "contrast": "across_arms",
        "predicted_contrast": "count:0 changes the outcome at fixed adj:6:right/adj:4:down",
        "dropped_arms": ["'vary the clicked cell coordinates' — ACTION1 has no clicked cell"],
        "unenforced_clauses": ["'holding all adjacency relations constant' — no values named"],
        "stratify": {"kind": "feature", "name": "count:0"},
        "arms": [{"arm_id": "a",
                  "precondition": [["adj:6:right", "eq", 0], ["adj:4:down", "eq", 9]],
                  "steps": [{"t": "press", "id": 1}]}],
    },
    {
        "probe_id": "vc33_125_s2", "game": "vc33", "dose": 125, "seed": 2,
        "verbatim": "ACTION6 on colour 9 when count:0=2 and adj:7:down=0, but manipulate "
                    "the horizontal distance between the two 0 objects (e.g., place them "
                    "adjacent vs. separated by 1+ background cells).",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 9]],
        "contrast": "across_arms",
        "predicted_contrast": "the horizontal gap between the two colour-0 objects changes "
                              "the outcome",
        "translation_note": "'horizontal distance between the two 0 objects' is the minimum "
                            "column gap between their cell sets; states are searched, "
                            "nothing is placed",
        "stratify": {"kind": "hgap", "colour": 0},
        "arms": [{"arm_id": "a",
                  "precondition": [["count:0", "eq", 2], ["adj:7:down", "eq", 0]],
                  "steps": [{"t": "click", "colour": 9}]}],
    },
    {
        "probe_id": "vc33_full_s2", "game": "vc33", "dose": None, "seed": 2,
        "verbatim": "Execute ACTION6 on colour 0 in a controlled state where count:0=1, "
                    "count:4=2, and adj:7:right=4, but deliberately vary the adjacency of "
                    "colour 0 to colour 4.",
        "nl_class": "executable-as-stated",
        "targeted": [["A6", 0]],
        "contrast": "across_arms",
        "predicted_contrast": "whether colour 0 touches colour 4 changes the outcome",
        "stratify": {"kind": "touch", "colour": 0, "other": 4},
        "arms": [{"arm_id": "a",
                  "precondition": [["count:0", "eq", 1], ["count:4", "eq", 2],
                                   ["adj:7:right", "eq", 4]],
                  "steps": [{"t": "click", "colour": 0}]}],
    },
]

ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ======================================================================================
# Grid predicates — the computed half of a precondition
# ======================================================================================


def _hash_state(level: int, grid: list) -> str:
    return hashlib.sha256(
        json.dumps([level, grid], separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _components(grid: list, colour: int) -> list[list[tuple[int, int]]]:
    """4-connected same-colour components of `colour`, background included.

    Deliberately not `_Objects`: a probe may name the background colour, and the click
    target has to exist for it either way.
    """
    height, width = len(grid), len(grid[0])
    seen: set[tuple[int, int]] = set()
    out = []
    for row in range(height):
        for col in range(width):
            if int(grid[row][col]) != colour or (row, col) in seen:
                continue
            stack, cells = [(row, col)], []
            seen.add((row, col))
            while stack:
                r, c = stack.pop()
                cells.append((r, c))
                for dr, dc in ORTHOGONAL:
                    nr, nc = r + dr, c + dc
                    if (
                        0 <= nr < height and 0 <= nc < width
                        and (nr, nc) not in seen
                        and int(grid[nr][nc]) == colour
                    ):
                        seen.add((nr, nc))
                        stack.append((nr, nc))
            out.append(sorted(cells))
    return out


def _touches(grid: list, cells: list[tuple[int, int]], colour: int) -> bool:
    height, width = len(grid), len(grid[0])
    members = set(cells)
    for r, c in cells:
        for dr, dc in ORTHOGONAL:
            nr, nc = r + dr, c + dc
            if 0 <= nr < height and 0 <= nc < width and (nr, nc) not in members:
                if int(grid[nr][nc]) == colour:
                    return True
    return False


def computed_feature(name: str, grid: list) -> Any:
    """The grid predicates a probe's own words require, and no others."""
    if name.startswith("bg_at:"):
        _, row, col = name.split(":")
        return int(grid[int(row)][int(col)]) == _Objects(grid).background
    if name.startswith("hgap:"):
        colour = int(name.split(":")[1])
        parts = _components(grid, colour)
        if len(parts) != 2:
            return None
        left = {c for _, c in parts[0]}
        right = {c for _, c in parts[1]}
        return max(0, max(min(left), min(right)) - min(max(left), max(right)) - 1)
    if name.startswith("touch:"):
        _, colour, other = name.split(":")
        return any(
            _touches(grid, cells, int(other))
            for cells in _components(grid, int(colour))
        )
    raise KeyError(name)


def feature_value(name: str, grid: list, guards: dict) -> Any:
    if name in guards:
        return guards[name]
    if name.startswith(("bg_at:", "hgap:", "touch:")):
        return computed_feature(name, grid)
    return None


def _test(op: str, actual: Any, expected: Any) -> bool:
    actual = tuple(actual) if isinstance(actual, list) else actual
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    raise ValueError(f"unknown op: {op}")


def satisfies(precondition: list, grid: list, guards: dict) -> bool:
    for name, op, expected in precondition:
        if name.endswith(":*"):  # adj:C:* — any direction
            stem = name[:-1]
            values = [
                guards.get(f"{stem}{d}") for d in ("up", "down", "left", "right")
            ]
            if not any(_test(op, value, expected) for value in values):
                return False
            continue
        present = name in guards or name.startswith(("bg_at:", "hgap:", "touch:"))
        if not present:
            # `present:C`/`count:C` are absent exactly when the colour is absent; every
            # other absence means the guard is undefined here (adj: needs a single object).
            if name.startswith("present:") and op == "eq" and expected is False:
                continue
            return False
        if not _test(op, feature_value(name, grid, guards), expected):
            return False
    return True


# ======================================================================================
# Store access
# ======================================================================================


class GameStore:
    """The frozen E1 v2 store for one game, plus the human targets. Never mutated."""

    def __init__(self, game: str):
        self.game = game
        self.graph = json.loads((STORE / f"{game}.graph.json").read_text())
        self.states: dict[str, list] = json.loads(
            (STORE / f"{game}.states.json").read_text()
        )
        self.prefix: dict[str, list] = self.graph["prefix"]
        self.origin: str = self.graph["origin"]
        self.edges: dict[tuple[str, tuple], str] = {
            (source, tuple(action)): target
            for source, action, target in (
                (row[0], row[1], row[2]) for row in self.graph["edges"]
            )
        }
        self.transitions, _ = load_store(game)
        human = load_game(game, max_level=2)
        self.human_l1 = [t for t in human if t.level == 1]
        self.human_l2 = [t for t in human if t.level == 2]
        self._guards: dict[str, dict] = {}

    def guards(self, digest: str) -> dict:
        if digest not in self._guards:
            grid = self.states[digest]
            self._guards[digest] = guard_features(grid, _Objects(grid), 0, {})
        return self._guards[digest]

    def satisfying(self, precondition: list, limit: int) -> list[str]:
        """Stored states meeting the precondition, shortest prefix first (cheap replay)."""
        out = []
        for digest in sorted(self.prefix, key=lambda d: (len(self.prefix[d]), d)):
            grid = self.states[digest]
            if satisfies(precondition, grid, self.guards(digest)):
                out.append(digest)
                if len(out) >= limit:
                    break
        return out

    def satisfying_all(self, precondition: list) -> list[str]:
        return self.satisfying(precondition, limit=10 ** 9)


# ======================================================================================
# Click-target resolution — reading the grid the way the probe's text does
# ======================================================================================


def click_targets(step: dict, grid: list, store: GameStore, key_offsets: set) -> list:
    if "cell" in step:
        row, col = step["cell"]
        return [(row, col)]
    if step.get("any_present_colour"):
        objects = _Objects(grid)
        return [
            min(objects.by_colour[colour][0]["cells"])
            for colour in sorted(objects.by_colour)
        ]
    colour = step["colour"]
    parts = [cells for cells in _components(grid, colour)]
    if "touching" in step:
        parts = [c for c in parts if _touches(grid, c, step["touching"])]
    if "not_touching" in step:
        parts = [c for c in parts if not _touches(grid, c, step["not_touching"])]
    if "novel_offset_to" in step:
        other = _components(grid, step["novel_offset_to"])
        if not other:
            return []
        anchor = min(min(cells) for cells in other)
        parts = [
            c for c in parts
            if (min(c)[0] - anchor[0], min(c)[1] - anchor[1]) not in key_offsets
        ]
    return [min(cells) for cells in parts]


def stored_click_offsets(store: GameStore, colour: int, other: int) -> set:
    """Offsets (clicked component top-left minus colour-`other` top-left) already in the
    store for ACTION6 on `colour`. The reference set `novel_offset_to` is measured against."""
    seen = set()
    for transition in store.transitions:
        if transition.action_id != 6 or transition.guards.get("click_colour") != colour:
            continue
        row, col = transition.action_data["y"], transition.action_data["x"]
        grid = transition.pre
        parts = _components(grid, other)
        if not parts:
            continue
        anchor = min(min(cells) for cells in parts)
        own = next(
            (cells for cells in _components(grid, colour) if (row, col) in set(cells)),
            None,
        )
        if own is None:
            continue
        top = min(own)
        seen.add((top[0] - anchor[0], top[1] - anchor[1]))
    return seen


# ======================================================================================
# Planning — arms, strata, and the already-answered check
# ======================================================================================


def expand_arms(spec: dict, store: GameStore) -> list[dict]:
    """Explicit arms, or one arm per stratum value when the probe says 'vary X'."""
    arms = [dict(arm) for arm in spec.get("arms", [])]
    stratify = spec.get("stratify")
    if stratify is None:
        return arms
    base = arms[0]
    if stratify["kind"] == "feature":
        name = stratify["name"]
    elif stratify["kind"] == "hgap":
        name = f"hgap:{stratify['colour']}"
    else:
        name = f"touch:{stratify['colour']}:{stratify['other']}"
    values: dict[Any, None] = {}
    for digest in store.satisfying_all(base["precondition"]):
        grid = store.states[digest]
        value = feature_value(name, grid, store.guards(digest))
        values.setdefault(
            tuple(value) if isinstance(value, list) else value, None
        )
    out = []
    for value in sorted(values, key=repr):
        arm = dict(base)
        arm["arm_id"] = f"{name}={value}"
        arm["precondition"] = base["precondition"] + [[name, "eq", value]]
        out.append(arm)
    return out or arms


def _action_matches(step: dict, transition: Transition, grid: list) -> bool:
    if step["t"] == "press":
        return transition.action_id == step["id"]
    if step["t"] != "click" or transition.action_id != 6:
        return False
    row, col = transition.action_data["y"], transition.action_data["x"]
    if "cell" in step:
        return [row, col] == list(step["cell"])
    if step.get("any_present_colour"):
        return True
    if int(grid[row][col]) != step["colour"]:
        return False
    own = next(
        (c for c in _components(grid, step["colour"]) if (row, col) in set(c)), None
    )
    if own is None:
        return False
    if "touching" in step and not _touches(grid, own, step["touching"]):
        return False
    if "not_touching" in step and _touches(grid, own, step["not_touching"]):
        return False
    return True


def stored_answer(
    arm: dict, store: GameStore, rows: list[Transition] | None = None
) -> list[Transition]:
    """Store transitions that already run this arm's FIRST step under its precondition.

    Multi-step arms are answered only when the whole chain exists; that is checked by the
    caller through the graph, because a chain is a property of edges, not of rows.
    """
    steps = arm["steps"]
    if len(steps) != 1 or steps[0].get("repeat"):
        return []
    if steps[0].get("novel_offset_to"):
        # `novel_offset_to` selects an offset NO stored transition takes; by construction
        # the store cannot already answer it.
        return []
    out = []
    for transition in (store.transitions if rows is None else rows):
        grid = transition.pre
        if not satisfies(arm["precondition"], grid, transition.guards):
            continue
        if _action_matches(steps[0], transition, grid):
            out.append(transition)
    return out


# ======================================================================================
# Execution
# ======================================================================================


class Runner:
    """ONE engine per game, returned to the origin by RESET before each replay — exactly
    how E1 routed (`e1_explorer.reset_route`). No forking, no second environment: a fresh
    `new_game()` per instance would be a different execution path from the one that built
    the store, and on a game with hidden state that difference is not neutral."""

    def __init__(self, game: str):
        self.driver = ReplayDriver(game)
        self.engine = ReplayDriver(game).new_game()
        self.level = 1

    def _perform(self, action_id: int, data: dict) -> dict:
        response = self.driver.perform(
            self.engine, ActionInput(id=GameAction.from_id(action_id), data=dict(data))
        )
        frames = _plain_frames(response.frame or [])
        return {
            "grid": frames[-1] if frames else None,
            "levels": int(response.levels_completed or 0),
        }

    def reset_to(self, prefix: list) -> dict:
        result = self._perform(0, {})
        for action_id, row, col in prefix:
            result = self._perform(
                action_id, {} if row is None else {"y": row, "x": col}
            )
        return result


def execute_instance(
    runner: Runner, store: GameStore, digest: str, steps: list, click: tuple | None
) -> tuple[list[dict], str | None]:
    """Replay to `digest`, then apply the arm's steps. Returns rows and a failure note."""
    prefix = store.prefix[digest]
    result = runner.reset_to(prefix)
    if result["grid"] != store.states[digest]:
        return [], "replay diverged from the stored state"
    rows: list[dict] = []
    grid = result["grid"]
    last_click: tuple | None = None
    plan: list[tuple[int, dict]] = []
    for step in steps:
        if step["t"] == "press":
            for _ in range(step.get("repeat", 1)):
                plan.append((step["id"], {}))
        elif step["t"] == "repeat":
            plan.append((6, {"y": last_click[0], "x": last_click[1]}))
        else:
            if click is None:
                return [], "no click target"
            last_click = click
            plan.append((6, {"y": click[0], "x": click[1]}))
    # `repeat` needs the previous click, so the plan is built with `last_click` filled in
    # above; a `repeat` never precedes its click because the specs never write one.
    for action_id, data in plan:
        result = runner._perform(action_id, data)
        post = result["grid"]
        if post is None:
            rows.append({"action": [action_id, data.get("y"), data.get("x")],
                         "pre": grid, "post": None, "completed": False})
            break
        rows.append({
            "action": [action_id, data.get("y"), data.get("x")],
            "pre": grid,
            "post": post,
            "completed": result["levels"] > 0,
        })
        if result["levels"] > 0:
            break
        grid = post
    return rows, None


def to_transition(game: str, guid: str, step: int, row: dict) -> Transition | None:
    pre, post = row["pre"], row["post"]
    if post is None:
        return None
    action_id, click_row, click_col = row["action"]
    data = {"y": click_row, "x": click_col} if action_id == 6 else {}
    pre_objects = _Objects(pre)
    return Transition(
        game=game, guid=guid, step=step, level=1, action_id=action_id,
        action_data=data, pre=pre, post=post, completed=bool(row["completed"]),
        effect=effect_signature(pre_objects, _Objects(post)),
        guards=guard_features(pre, pre_objects, action_id, data),
    )


# ======================================================================================
# Scoring
# ======================================================================================


def key_of(kind: str, value: Any) -> tuple:
    return ("A6", value) if kind == "A6" else ("A", value)


def key_state(rules: dict[str, Rule], key: tuple) -> dict[str, Any]:
    """Is `key` resolved, and on what support? Unresolved == the miner emitted a
    majority-tier rule for it (`e2_slice.unresolved_keys`' own definition)."""
    owned = [rule for rule in rules.values() if rule.key == key]
    if not owned:
        return {"present": False, "resolved": False, "tier": None, "support": 0}
    tiers = {rule.tier for rule in owned}
    return {
        "present": True,
        "resolved": "majority" not in tiers,
        "tier": sorted(tiers)[0] if len(tiers) == 1 else "mixed",
        "support": sum(rule.support for rule in owned),
        "rules": len(owned),
    }


def key_accuracy(rules: dict[str, Rule], train: list, test: list, key: tuple) -> Any:
    target = [t for t in test if t.key() == key]
    if not target:
        return None
    return score(rules, train, target, MODE)["accuracy_over_all"]


def _canon(effect: Any) -> tuple:
    """An effect signature as a hashable value, whether it arrived as tuples or as the
    JSON lists a stored/serialized row carries."""
    if isinstance(effect, (list, tuple)):
        return tuple(_canon(item) for item in effect)
    return effect


def discrimination(arm_effects: dict[str, list], contrast: str) -> dict[str, Any]:
    """realized / partial / not, mechanically.

    across_arms         the arms' effect SETS differ; disjoint and both non-empty is
                        `realized`, overlapping but unequal is `partial`, equal is `not`
    across_repetitions  successive identical actions produced >= 2 distinct effects
    single_outcome      the probe predicted no difference; nothing to discriminate
    """
    if contrast == "single_outcome" or contrast == "none":
        return {"verdict": "n/a", "reason": "the probe states no differential prediction"}
    sets = {arm: {_canon(e) for e in effects} for arm, effects in arm_effects.items()
            if effects}
    if contrast == "across_repetitions":
        effects = [_canon(e) for row in arm_effects.values() for e in row]
        if len(effects) < 2:
            return {"verdict": "not-evaluable", "reason": "fewer than two executions"}
        return {
            "verdict": "realized" if len(set(effects)) > 1 else "not",
            "distinct_effects": len(set(effects)),
            "executions": len(effects),
        }
    if len(sets) < 2:
        return {"verdict": "not-evaluable",
                "reason": f"only {len(sets)} arm(s) produced evidence"}
    values = list(sets.values())
    pairwise_equal = all(v == values[0] for v in values)
    disjoint = all(
        not (values[i] & values[j])
        for i in range(len(values)) for j in range(i + 1, len(values))
    )
    verdict = "not" if pairwise_equal else ("realized" if disjoint else "partial")
    return {"verdict": verdict, "arms": len(sets),
            "effect_sets": {arm: len(s) for arm, s in sets.items()}}


# ======================================================================================
# The random control
# ======================================================================================


def control_transitions(
    store: GameStore, runner: Runner, count: int, seed: int, tag: str
) -> list[Transition]:
    """`count` transitions from uniformly-random stored states, each an UNTRIED tier-1
    candidate there. Equal action cost to the probe it is the control for."""
    rng = random.Random(f"{seed}:{tag}")
    digests = sorted(store.prefix)
    out: list[Transition] = []
    attempts = 0
    while len(out) < count and attempts < count * 20:
        attempts += 1
        digest = digests[rng.randrange(len(digests))]
        grid = store.states[digest]
        candidates = [(a, None, None) for a in SIMPLE_ACTIONS]
        candidates += [
            (6, node["point"][0], node["point"][1])
            for node in tier1_nodes(segment(grid), CANDIDATE_CAP)
        ]
        untried = [c for c in candidates if (digest, c) not in store.edges]
        if not untried:
            continue
        action = untried[rng.randrange(len(untried))]
        result = runner.reset_to(store.prefix[digest])
        if result["grid"] != store.states[digest]:
            continue
        action_id, row, col = action
        step = runner._perform(action_id, {} if row is None else {"y": row, "x": col})
        if step["grid"] is None:
            continue
        transition = to_transition(
            store.game, f"control:{tag}:{seed}", len(out),
            {"action": [action_id, row, col], "pre": grid, "post": step["grid"],
             "completed": step["levels"] > 0},
        )
        if transition is not None:
            out.append(transition)
    return out


# ======================================================================================
# Per-game driver
# ======================================================================================


def determinism_gate(store: GameStore, runner: Runner) -> dict[str, Any]:
    """Three stored prefixes replayed end-to-end: shortest, median, longest."""
    ordered = sorted(store.prefix, key=lambda d: (len(store.prefix[d]), d))
    ordered = [d for d in ordered if store.prefix[d]]
    if not ordered:
        return {"checked": 0, "passed": 0, "ok": False, "note": "no non-empty prefix"}
    picks = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    rows = []
    for digest in picks:
        prefix = store.prefix[digest]
        result = runner.reset_to([])
        current = _hash_state(1, result["grid"])
        divergence = None
        for index, action in enumerate(prefix):
            action_id, click_row, click_col = action
            result = runner._perform(
                action_id, {} if click_row is None else {"y": click_row, "x": click_col}
            )
            if result["grid"] is None:
                divergence = {"step": index, "action": action, "note": "no frame"}
                break
            reached = _hash_state(1, result["grid"])
            expected = store.edges.get((current, tuple(action)))
            if divergence is None and expected is not None and expected != reached:
                divergence = {"step": index, "action": action, "from": current,
                              "store_edge_to": expected, "replay_to": reached}
            current = reached
        rows.append({
            "state": digest,
            "prefix_actions": len(prefix),
            "match": result["grid"] == store.states[digest],
            "first_divergence": divergence,
        })
    return {
        "checked": len(rows),
        "passed": sum(row["match"] for row in rows),
        "ok": all(row["match"] for row in rows),
        "replays": rows,
    }


def run_game(game: str, vocab: str) -> dict[str, Any]:
    set_vocab(vocab)
    started = time.monotonic()
    store = GameStore(game)
    runner = Runner(game)
    gate = determinism_gate(store, runner)

    baseline_v1, _ = mine(store.transitions, MODE)
    floors = {
        "human_l1": score(baseline_v1, store.transitions, store.human_l1, MODE),
        "human_l2": score(baseline_v1, store.transitions, store.human_l2, MODE),
    }

    results: list[dict[str, Any]] = []
    executed_rows: list[dict] = []
    # A failed gate stops EXECUTION on the game (notes/e2-probe-channel.md step 2), not
    # classification: the funnel up to "would have executed" costs no game action and is
    # the answer to question 2 whether or not the store's prefixes are replayable.
    for spec in [s for s in PROBES if s["game"] == game]:
        row = run_spec(
            spec, store, runner, baseline_v1, executed_rows, blocked=not gate["ok"]
        )
        results.append(row)

    # per-game union: store + every executed probe transition
    probe_transitions = [
        t for t in (
            to_transition(game, f"probe:{r['probe_id']}", i, r)
            for i, r in enumerate(executed_rows)
        ) if t is not None
    ]
    union = store.transitions + probe_transitions
    union_rules, _ = mine(union, MODE)
    union_scores = {
        "human_l1": score(union_rules, union, store.human_l1, MODE),
        "human_l2": score(union_rules, union, store.human_l2, MODE),
    }
    return {
        "game": game,
        "vocab": vocab,
        "gate": gate,
        "execution_blocked": not gate["ok"],
        "store_transitions": len(store.transitions),
        "store_states": len(store.states),
        "probe_transitions": len(probe_transitions),
        "floor": floors,
        "union": union_scores,
        "probes": results,
        "rows": executed_rows if vocab == "v1" else [],
        "seconds": round(time.monotonic() - started, 1),
    }


def run_spec(
    spec: dict, store: GameStore, runner: Runner, baseline: dict, sink: list,
    blocked: bool = False,
) -> dict[str, Any]:
    probe_id = spec["probe_id"]
    row: dict[str, Any] = {
        "probe_id": probe_id, "game": spec["game"], "dose": spec["dose"],
        "seed": spec["seed"], "nl_class": spec["nl_class"],
        "contrast": spec["contrast"], "targeted": spec["targeted"],
    }
    if spec["nl_class"] != "executable-as-stated":
        row["category"] = spec["nl_class"]
        row["missing_piece"] = spec.get("missing_piece")
        return row

    arms = expand_arms(spec, store)
    if spec.get("stratify"):
        # "systematically vary X" is only executable if X actually varies among the states
        # the store can reach. One stratum means the requested variation does not exist.
        row["strata_found"] = len(arms)
    key_offsets: set = set()
    for arm in arms:
        for step in arm["steps"]:
            if step.get("novel_offset_to"):
                key_offsets |= stored_click_offsets(
                    store, step["colour"], step["novel_offset_to"]
                )

    arm_rows: list[dict[str, Any]] = []
    planned: list[tuple[dict, str, tuple | None]] = []
    for arm in arms:
        entry: dict[str, Any] = {"arm_id": arm["arm_id"]}
        if arm.get("start") == "origin":
            digests = [store.origin]
        else:
            digests = store.satisfying_all(arm["precondition"])
        entry["satisfying_states"] = len(digests)
        if not digests:
            entry["status"] = "unreachable-in-store"
            arm_rows.append(entry)
            continue
        stored = stored_answer(arm, store)
        if stored:
            entry["status"] = "already-answered"
            entry["stored_transitions"] = len(stored)
            # ...and was it already answered by the evidence the MODEL was holding, i.e.
            # inside the dose prefix it was shown? That is a stronger claim than "the
            # explorer got there eventually" and the two are counted separately.
            dose = spec["dose"]
            entry["answered_at_dose"] = len(
                stored_answer(arm, store, store.transitions[:dose] if dose else
                              store.transitions)
            )
            entry["effects"] = sorted({repr(t.effect) for t in stored})
            entry["effect_list"] = [list(t.effect) for t in stored]
            arm_rows.append(entry)
            continue
        chosen = None
        for digest in digests:
            grid = store.states[digest]
            first = arm["steps"][0]
            if first["t"] == "press":
                chosen = (digest, None)
                break
            targets = click_targets(first, grid, store, key_offsets)
            if targets:
                chosen = (digest, targets[0])
                break
        if chosen is None:
            entry["status"] = "unreachable-in-store"
            entry["note"] = "no click target satisfying the probe's own selection rule"
            arm_rows.append(entry)
            continue
        entry["status"] = "planned"
        entry["state"] = chosen[0]
        entry["click"] = list(chosen[1]) if chosen[1] else None
        arm_rows.append(entry)
        planned.append((arm, chosen[0], chosen[1]))

    # same_state: both arms must click in ONE state, as the probe says
    if spec.get("same_state") and len(planned) == 2:
        planned = _colocate(spec, arms, store, key_offsets) or planned
    if spec.get("match_on") == "adj":
        matched = _match_adj(arms, store)
        if matched:
            planned = matched
            for entry, (_, digest, click) in zip(
                [e for e in arm_rows if e["status"] == "planned"], matched
            ):
                entry["state"], entry["click"] = digest, list(click) if click else None

    budget = TRANSITION_CAP if not blocked else 0
    cap_bound = False
    if blocked:
        for entry in arm_rows:
            if entry["status"] == "planned":
                entry["status"] = "blocked-by-determinism-gate"
        planned = []
    for arm, digest, click in planned:
        if budget <= 0:
            cap_bound = True
            break
        rows, failure = execute_instance(runner, store, digest, arm["steps"], click)
        if failure:
            next(e for e in arm_rows if e["arm_id"] == arm["arm_id"])["status"] = failure
            continue
        rows = rows[:budget]
        budget -= len(rows)
        for record in rows:
            record["probe_id"] = probe_id
            record["arm_id"] = arm["arm_id"]
            sink.append(record)
        entry = next(e for e in arm_rows if e["arm_id"] == arm["arm_id"])
        entry["status"] = "executed"
        entry["transitions"] = len(rows)
        entry["effect_list"] = [_effect_of(r) for r in rows if r["post"] is not None]

    row["arms"] = arm_rows
    statuses = {entry["status"] for entry in arm_rows}
    if "executed" in statuses:
        row["category"] = "executed"
    elif "blocked-by-determinism-gate" in statuses:
        row["category"] = "blocked-by-determinism-gate"
    elif statuses == {"already-answered"}:
        row["category"] = "already-answered"
    elif statuses <= {"unreachable-in-store"}:
        row["category"] = "unreachable-in-store"
    else:
        row["category"] = "mixed"
    row["cap_bound"] = cap_bound
    row["executed_transitions"] = sum(
        e.get("transitions", 0) for e in arm_rows if e["status"] == "executed"
    )

    effects_by_arm = {
        e["arm_id"]: e.get("effect_list", [])
        for e in arm_rows if e["status"] in ("executed", "already-answered")
    }
    row["discrimination"] = discrimination(effects_by_arm, spec["contrast"])

    # targeted-key resolution, on store + THIS probe's transitions only
    mine_rows = [
        t for t in (
            to_transition(spec["game"], f"probe:{probe_id}", i, r)
            for i, r in enumerate(sink) if r["probe_id"] == probe_id
        ) if t is not None
    ]
    row["probe_only_transitions"] = len(mine_rows)
    if mine_rows:
        train = store.transitions + mine_rows
        rules, _ = mine(train, MODE)
        keys = _targeted_keys(spec, mine_rows)
        row["targeted_keys"] = [list(k) for k in keys]
        row["key_resolution"] = [
            {
                "key": list(key),
                "before": key_state(baseline, key),
                "after": key_state(rules, key),
                "human_l1_accuracy_before": key_accuracy(
                    baseline, store.transitions, store.human_l1, key),
                "human_l1_accuracy_after": key_accuracy(
                    rules, train, store.human_l1, key),
                "human_l2_accuracy_before": key_accuracy(
                    baseline, store.transitions, store.human_l2, key),
                "human_l2_accuracy_after": key_accuracy(
                    rules, train, store.human_l2, key),
            }
            for key in keys
        ]
        row["union_human_l1"] = score(rules, train, store.human_l1, MODE)[
            "accuracy_over_all"]
        row["union_human_l2"] = score(rules, train, store.human_l2, MODE)[
            "accuracy_over_all"]
        row["control"] = run_control(
            spec, store, runner, baseline, len(mine_rows), keys
        )
    else:
        # nothing executed: the probe is already-answered or unreachable. The targeted
        # key's CURRENT state is still the datum — an already-answered probe that names a
        # key the full store already resolved is the model asking for evidence the
        # explorer's own policy went and collected.
        keys = _targeted_keys(spec, [])
        row["targeted_keys"] = [list(k) for k in keys]
        row["key_resolution"] = [
            {"key": list(key), "before": key_state(baseline, key),
             "after": key_state(baseline, key), "no_execution": True}
            for key in keys
        ]
    return row


def _effect_of(record: dict) -> list:
    if record["post"] is None:
        return []
    return [list(event) for event in effect_signature(
        _Objects(record["pre"]), _Objects(record["post"])
    )]


def _targeted_keys(spec: dict, transitions: list[Transition]) -> list[tuple]:
    if spec["targeted"] == "executed":
        return sorted({t.key() for t in transitions}, key=repr)
    return [key_of(kind, value) for kind, value in spec["targeted"]]


def _colocate(spec, arms, store, key_offsets):
    """One state in which BOTH arms have a click target — `same_state` probes."""
    for digest in sorted(store.prefix, key=lambda d: (len(store.prefix[d]), d)):
        grid = store.states[digest]
        picks = []
        for arm in arms:
            if not satisfies(arm["precondition"], grid, store.guards(digest)):
                break
            targets = click_targets(arm["steps"][0], grid, store, key_offsets)
            if not targets:
                break
            picks.append((arm, digest, targets[0]))
        if len(picks) == len(arms):
            return picks
    return None


def _match_adj(arms, store):
    """A pair of states, one per arm, agreeing on every adj:* feature."""
    buckets: list[dict] = []
    for arm in arms:
        found = {}
        for digest in store.satisfying(arm["precondition"], MAX_STATES_PER_ARM * 20):
            guards = store.guards(digest)
            signature = tuple(sorted(
                (k, repr(v)) for k, v in guards.items() if k.startswith("adj:")
            ))
            found.setdefault(signature, digest)
        buckets.append(found)
    shared = set(buckets[0])
    for found in buckets[1:]:
        shared &= set(found)
    if not shared:
        return None
    signature = sorted(shared)[0]
    out = []
    for arm, found in zip(arms, buckets):
        digest = found[signature]
        grid = store.states[digest]
        first = arm["steps"][0]
        click = None
        if first["t"] == "click":
            targets = click_targets(first, grid, store, set())
            if not targets:
                return None
            click = targets[0]
        out.append((arm, digest, click))
    return out


def run_control(spec, store, runner, baseline, count, keys) -> dict[str, Any]:
    """Same number of transitions, random state + untried tier-1 candidate. 5 replicates."""
    replicates = []
    for seed in CONTROL_SEEDS:
        rows = control_transitions(store, runner, count, seed, spec["probe_id"])
        train = store.transitions + rows
        rules, _ = mine(train, MODE)
        replicates.append({
            "seed": seed,
            "transitions": len(rows),
            "resolved": [
                {"key": list(key), "after": key_state(rules, key)} for key in keys
            ],
            "human_l1": score(rules, train, store.human_l1, MODE)["accuracy_over_all"],
            "human_l2": score(rules, train, store.human_l2, MODE)["accuracy_over_all"],
        })
    resolved_counts = [
        sum(1 for entry in rep["resolved"] if entry["after"]["resolved"])
        for rep in replicates
    ]
    return {
        "replicates": replicates,
        "keys": len(keys),
        "resolved_fraction_mean": (
            round(sum(resolved_counts) / (len(replicates) * len(keys)), 4)
            if keys else None
        ),
    }


# ======================================================================================
# CLI
# ======================================================================================


def verify_vocab() -> dict[str, Any]:
    """The digests these probes were written from carry no `clicked_adjacent_to` line —
    so they are v1. Measured here rather than assumed."""
    rows = []
    for path in sorted(TRACES.glob("*.think.json")):
        prompt = json.loads(path.read_text()).get("prompt", "")
        rows.append({"trace": path.name, "clicked_adjacent_to": prompt.count(
            "clicked_adjacent_to")})
    return {
        "traces": len(rows),
        "with_v2_feature": sum(1 for row in rows if row["clicked_adjacent_to"]),
        "conclusion": "v1" if all(r["clicked_adjacent_to"] == 0 for r in rows) else "mixed",
    }


def write_specs() -> None:
    counts = Counter(spec["nl_class"] for spec in PROBES)
    document = {
        "format_version": FORMAT_VERSION,
        "note": "notes/e2-probe-channel.md step 1 — the pre-registration. Committed "
                "before any probe was executed.",
        "vocabulary": "v1 (the digests the probes were written from)",
        "vocabulary_check": verify_vocab(),
        "probes": len(PROBES),
        "nl_classes": dict(counts),
        "duplicates": [
            spec["probe_id"] for spec in PROBES if spec.get("duplicate_of")
        ],
        "caps": {"transitions_per_spec": TRANSITION_CAP,
                 "states_per_arm": MAX_STATES_PER_ARM,
                 "control_replicates": CONTROL_REPLICATES,
                 "control_seeds": list(CONTROL_SEEDS)},
        "specs": PROBES,
    }
    SPECS_OUT.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"wrote {SPECS_OUT}: {len(PROBES)} probes, {dict(counts)}")


def persist_rows(results: list[dict]) -> None:
    PROBE_STORE.mkdir(parents=True, exist_ok=True)
    for row in results:
        rows = row.get("rows") or []
        if not rows:
            continue
        states: dict[str, list] = {}
        lines = []
        for index, record in enumerate(rows):
            pre_hash = _hash_state(1, record["pre"])
            states[pre_hash] = record["pre"]
            post_hash = None
            if record["post"] is not None:
                post_hash = _hash_state(1, record["post"])
                states[post_hash] = record["post"]
            lines.append(json.dumps({
                "step": index, "probe_id": record["probe_id"],
                "arm_id": record["arm_id"], "action": record["action"],
                "pre": pre_hash, "post": post_hash,
                "completed": record["completed"],
            }))
        (PROBE_STORE / f"{row['game']}.states.json").write_text(json.dumps(states))
        (PROBE_STORE / f"{row['game']}.transitions.jsonl").write_text(
            "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("specs", "run", "verify-vocab"),
                        default="run")
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if args.stage == "specs":
        write_specs()
        return 0
    if args.stage == "verify-vocab":
        print(json.dumps(verify_vocab(), indent=2))
        return 0

    document: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "specs": str(SPECS_OUT.relative_to(ROOT)),
        "primary_vocabulary": "v1",
        "caps": {"transitions_per_spec": TRANSITION_CAP,
                 "control_replicates": CONTROL_REPLICATES,
                 "control_seeds": list(CONTROL_SEEDS)},
        "games": {},
    }
    for vocab in ("v1", "v2"):
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(_job, game, vocab): game for game in args.games}
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                game = row["game"]
                document["games"].setdefault(game, {})[vocab] = row
                if "error" in row:
                    print(f"{game:5s} {vocab} ERROR {row['error']}", flush=True)
                    continue
                if "stopped" in row:
                    print(f"{game:5s} {vocab} STOPPED gate="
                          f"{row['gate']['passed']}/{row['gate']['checked']} "
                          f"{row['stopped']}", flush=True)
                    continue
                print(
                    f"{game:5s} {vocab} gate={row['gate']['passed']}/"
                    f"{row['gate']['checked']} probes={len(row['probes'])} "
                    f"probe_transitions={row.get('probe_transitions', 0)} "
                    f"L1 {row['floor']['human_l1']['accuracy_over_all']} -> "
                    f"{row['union']['human_l1']['accuracy_over_all']} "
                    f"L2 {row['floor']['human_l2']['accuracy_over_all']} -> "
                    f"{row['union']['human_l2']['accuracy_over_all']} "
                    f"({row['seconds']}s)", flush=True
                )
        if vocab == "v1":
            persist_rows([document["games"][g]["v1"] for g in args.games
                          if "v1" in document["games"].get(g, {})])
    for game in document["games"]:
        for vocab in document["games"][game]:
            document["games"][game][vocab].pop("rows", None)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


def _job(game: str, vocab: str) -> dict[str, Any]:
    try:
        return run_game(game, vocab)
    except Exception as error:  # a failing game must not take the run down
        import traceback
        return {"game": game, "vocab": vocab,
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc()}


if __name__ == "__main__":
    raise SystemExit(main())
