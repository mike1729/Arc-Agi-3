#!/usr/bin/env python3
"""E2 trace autopsy — the rater's half (`notes/e2-trace-autopsy.md`).

ZERO MODEL CALLS. Encodes one rater's labels for all 84 transcribed proposals across the
12 cells, joins them to the mechanical claim ledger (`e2_autopsy.py`) and — only after the
labels are fixed — to the verification outcomes in `logs/e2_slice.json`.

EVERY LABEL CARRIES A VERBATIM TRACE QUOTE, and every quote is checked to occur in the
trace it is attributed to (`_verify`, which raises). A label whose quote cannot be found is
a build error, not a footnote. Quotes are our own model's output, so they are committable;
competition game source is NEVER quoted, only paraphrased (PUBLISHING.md).

LABEL SCOPE. Labels are assigned per CELL-MECHANISM and then applied to each rule that the
mechanism produced, because that is what the traces actually contain: one line of reasoning
per cell yielding a family of rules. Per-rule departures are recorded in `overrides`. The
output row for every rule names the mechanism it inherits, so the granularity is visible
rather than implied.

BLINDING — declared deviation. `notes/e2-trace-autopsy.md` asks for label-before-join. It
was followed for 10 of 12 cells. Two exceptions, both recorded in the output:
  * the 8 refuted dose-125 rules are published in `notes/e2-slice.md` §"The dose asymmetry",
    so their outcome was known to the rater before any trace was opened — no blinding was
    ever available for them;
  * `dc22_125`'s `verification` array was read while establishing the schema of
    `logs/e2_slice.json`, before its trace was read.
Everything else was labelled from the trace and digest alone, then joined.

Run:
  .venv/bin/python agent/harness/e2_autopsy_labels.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TRACES = ROOT / "logs/e2_slice_traces"
CLAIMS = ROOT / "logs/e2_autopsy_claims.json"
SLICE = ROOT / "logs/e2_slice.json"
OUTPUT = ROOT / "logs/e2_trace_autopsy.json"

# ======================================================================================
# The label vocabulary
# ======================================================================================
# Layer 1 READING and layer 3 EXPRESSIBILITY are as defined in the note. Layer 2 REASONING
# carries the note's four types plus two the traces forced and which are declared here as
# additions, not smuggled in:
#
#   example-row-as-group-constant (READING) — the digest prints ONE example transition's
#       guards per effect group under the header "varying guards". The trace reads that row
#       as the group's constant value and builds rules on it. It is a reading error by the
#       note's own definition (an assertion the digest does not support), but its cause is
#       the digest's display, which is why it is called out by name rather than folded into
#       a generic misread.
#   digest-assertion-overridden (REASONING) — the digest states that no single guard in the
#       vocabulary separates the key. The trace derives a separating single guard anyway,
#       NOTICES the contradiction, and resolves it by inventing a defect in the miner
#       instead of doubting its own reading.
LAYERS = {
    "example-row-as-group-constant": "READING",
    "misread-corrected": "READING",
    "evidence-weight-blind": "REASONING",
    "overgeneralization": "REASONING",
    "alternative-dropped": "REASONING",
    "guard-misread": "REASONING",
    "digest-assertion-overridden": "REASONING",
    "vocabulary-limit-named": "EXPRESSIBILITY",
    "guard-outside-vocabulary": "EXPRESSIBILITY",
}

# ======================================================================================
# Labels
# ======================================================================================
# `mechanisms`  the labelled lines of reasoning in the cell, each with its licensing quote.
# `rules`       mechanism name per proposal index (or a list for several).
# `goal`        {correct | partial | wrong | unfalsifiable} against the game's real
#               completion condition, read from source and PARAPHRASED in `goal_truth`.
# `hidden`      {correct | wrong | licensed-none} — "licensed-none" where the digest
#               recorded no alias conflicts, which makes "None" an evidence-backed answer.
# `probe`       {discriminating | non-discriminating | out-of-band} — would running it
#               actually separate the hypotheses the cell proposed?

LABELS: dict[str, dict[str, Any]] = {
    "tu93_125": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "evidence-weight-blind"],
                "quote": "This implies the feature was constant across those transitions.",
                "note": "Six rules follow from reading one example row per group as the "
                        "group's constant. The trace states the inference explicitly.",
            },
        },
        "extra": {
            "misread-corrected": "The numbers after the colon are the *values*, not counts!",
            "digest-assertion-overridden": "Why did the miner fail?",
            "evidence-weight-blind": "This is perfectly consistent.",
            "overgeneralization": "This might be a boundary case or noise.",
        },
        "rules": {i: "row-constant" for i in range(6)},
        "goal": "correct",
        "goal_truth": "the level advances when every mover sprite stands on an exit tile; "
                      "with one mover and one static target visible in the evidence this "
                      "coincides with the trace's 'move 4 or 9 onto 14'",
        "goal_quote": "almost always the goal marker",
        "hidden": "wrong",
        "hidden_truth": "the game does carry an unrendered phase variable; the digest "
                        "recorded no alias conflicts, so the evidence did not show it",
        "probe": "non-discriminating",
        "probe_why": "it re-runs the configuration the rules were fitted to rather than a "
                     "configuration on which the group-constancy reading would break",
    },
    "tu93_full": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "digest-assertion-overridden"],
                "quote": "`adj:4:left` is always 9.",
                "note": "Twelve rules from one systematic theory: each action reads the "
                        "adjacency in its own direction. Built on the same example-row read.",
            },
        },
        "extra": {
            "alternative-dropped": "If it cannot, say so explicitly rather than inventing a rule that fits.",
        },
        "rules": {i: "row-constant" for i in range(12)},
        "goal": "correct",
        "goal_truth": "as tu93_125 — all movers onto exit tiles",
        "goal_quote": "Complete the level by moving object 4 (or 9) onto color 14.",
        "hidden": "wrong",
        "hidden_truth": "as tu93_125",
        "probe": "discriminating",
        "probe_why": "positioning 4 adjacent to 14 in the action's direction would test the "
                     "directional theory directly",
    },
    "dc22_125": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "digest-assertion-overridden"],
                "quote": "That *should* separate them! Why does the miner say it can't?",
                "note": "The trace names the contradiction between its own separating guard "
                        "and the digest's assertion, and proceeds on its own reading.",
            },
        },
        "extra": {
            "vocabulary-limit-named": "cannot name",
        },
        "rules": {i: "row-constant" for i in range(8)},
        "goal": "wrong",
        "goal_truth": "the level advances when the avatar sprite occupies the goal tile — "
                      "a reach-the-target level, not a clear-the-board one",
        "goal_quote": "**clearing or consolidating the colour-0 objects**",
        "hidden": "wrong",
        "hidden_truth": "the game's declared hidden state is a step counter, not a toggle "
                        "or a selection cursor",
        "probe": "non-discriminating",
        "probe_why": "it names a state by the same example-row guards it is trying to test",
    },
    "dc22_full": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant"],
                "quote": "Within a group, they are fixed.",
                "note": "The same trace states the CORRECT reading earlier — 'within each "
                        "group, the guards vary' — then reverses it and builds on the "
                        "reversal. Both statements are in one trace.",
            },
        },
        "extra": {
            "misread-corrected": "within each group, the guards vary",
        },
        "rules": {i: "row-constant" for i in range(7)},
        "goal": "wrong",
        "goal_truth": "as dc22_125 — avatar onto the goal tile",
        "goal_quote": "Reduce the board to a state with zero components of colour 3",
        "hidden": "licensed-none",
        "hidden_truth": "a step counter exists but no alias conflict was shown",
        "probe": "discriminating",
        "probe_why": "it asks for two states identical in every adj feature and differing "
                     "only in count:3 — the correct shape for isolating a single guard",
    },
    "ft09_125": {
        "mechanisms": {
            "expressibility": {
                "labels": ["vocabulary-limit-named", "guard-outside-vocabulary"],
                "quote": "the vocabulary can't express \"clicked object is adjacent to C\"",
                "note": "The diagnosis success of the run. Both proposals were rejected by "
                        "the harness for naming a guard outside the vocabulary — which is "
                        "exactly what the prompt asked the model to do.",
            },
        },
        "rules": {0: "expressibility", 1: "expressibility"},
        "goal": "wrong",
        "goal_truth": "an edge-matching condition: every tile must satisfy a per-edge "
                      "match/mismatch constraint against its neighbour, not a removal count",
        "goal_quote": "until all colour-9 objects are removed",
        "hidden": "licensed-none",
        "hidden_truth": "the game carries a hidden counter; no alias conflict was shown",
        "probe": "discriminating",
        "probe_why": "a paired adjacent/non-adjacent click is the minimal test of the "
                     "adjacency hypothesis it proposed",
    },
    "ft09_full": {
        "mechanisms": {
            "count-theory": {
                "labels": ["digest-assertion-overridden", "overgeneralization"],
                "quote": "The miner failed because it likely",
                "note": "This trace reads the digest format CORRECTLY and still overrides "
                        "the digest's no-single-guard assertion, by attributing the miner a "
                        "defect it has no evidence for.",
            },
        },
        "extra": {
            "misread-corrected": "It doesn't mean they are constant. It just lists the values seen.",
            "guard-outside-vocabulary": "count:8 == 16 & present:11 == True",
        },
        "rules": {i: "count-theory" for i in range(5)},
        "goal": "wrong",
        "goal_truth": "as ft09_125 — a per-edge matching condition over neighbouring tiles",
        "goal_quote": "**balancing the counts of colours 8 and 9 to 18 each**",
        "hidden": "licensed-none",
        "hidden_truth": "as ft09_125",
        "probe": "discriminating",
        "probe_why": "it isolates present:11 at fixed count:8, the one interaction its rule "
                     "set leaves untested",
    },
    "ls20_125": {
        "mechanisms": {
            "expressibility": {
                "labels": ["vocabulary-limit-named"],
                "quote": "outside the vocabulary",
                "note": "Declines to guard at all: four guard-free baseline rules plus a "
                        "named list of candidate missing features (distance, parity, "
                        "direction). A diagnosis, scored as four unguarded rules.",
            },
        },
        "rules": {i: "expressibility" for i in range(4)},
        "goal": "wrong",
        "goal_truth": "the level advances once the avatar has reached every target sprite; "
                      "a collect-them-all level",
        "goal_quote": "**synchronizing the singletons (11 and 12)",
        "hidden": "correct",
        "hidden_truth": "it names an incomplete feature vocabulary and a step counter among "
                        "the candidates; the game does carry a step counter",
        "probe": "out-of-band",
        "probe_why": "it asks for instrumentation the agent cannot obtain in play — exact "
                     "coordinates and a global step count — rather than an action",
    },
    "ls20_full": {
        "mechanisms": {
            "expressibility": {
                "labels": ["vocabulary-limit-named"],
                "quote": "The miner couldn't find a single guard that separates them.",
                "note": "As ls20_125: four guard-free rules, differing only in the effect "
                        "they attach to every action.",
            },
        },
        "rules": {i: "expressibility" for i in range(4)},
        "goal": "unfalsifiable",
        "goal_truth": "as ls20_125 — reach every target; the trace's 'position or merge the "
                      "active pieces to clear the board or reach a target configuration' "
                      "admits no test",
        "goal_quote": "or reach a target configuration",
        "hidden": "licensed-none",
        "hidden_truth": "a step counter exists; no alias conflict was shown",
        "probe": "out-of-band",
        "probe_why": "it asks to place objects at chosen coordinates, which is not an "
                     "available action",
    },
    "m0r0_125": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "digest-assertion-overridden"],
                "quote": "So `adj:12:left == 11` perfectly separates them! Why did the miner fail?",
                "note": "Seventeen rules — the largest proposal set in the run — all keyed "
                        "on adj:12:left, from one example row per group.",
            },
        },
        "extra": {
            "guard-misread": "It should have `adj:10:up`.",
            "guard-outside-vocabulary": "adj:12:left == 11",
        },
        "rules": {i: "row-constant" for i in range(17)},
        "goal": "partial",
        "goal_truth": "the level advances when no unmatched piece remains — pieces brought "
                      "together merge and become inert; the trace has the repositioning but "
                      "not the pairing-to-zero",
        "goal_quote": "**repositioning the two colour-10 blocks into a target configuration**",
        "hidden": "correct",
        "hidden_truth": "the game's declared hidden state is an action count, and its own "
                        "mode toggles on that count's parity — the trace named turn parity",
        "probe": "discriminating",
        "probe_why": "m0r0 is the one cell whose digest recorded alias conflicts, and the "
                     "probe targets the parity it inferred from them",
    },
    "m0r0_full": {
        "mechanisms": {
            "count-theory": {
                "labels": ["digest-assertion-overridden", "guard-misread"],
                "quote": "I should not claim `count:10` separates it if the miner says it doesn't",
                "note": "The trace states the discipline the digest requires of it and then "
                        "breaks it in the same paragraph, proposing count:10 with an "
                        "invented excuse for the miner.",
            },
        },
        "extra": {
            "guard-outside-vocabulary": "adj:10:down == 0",
        },
        "rules": {i: "count-theory" for i in range(10)},
        "goal": "wrong",
        "goal_truth": "as m0r0_125 — no unmatched piece remains; the lock-and-key path is "
                      "invented",
        "goal_quote": "reshape the two colour-0 components into a continuous path or key shape",
        "hidden": "correct",
        "hidden_truth": "as m0r0_125 — action count and its parity",
        "probe": "discriminating",
        "probe_why": "repeating one action from a fixed visual state is the direct test of "
                     "an alternating hidden phase",
    },
    "vc33_125": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "evidence-weight-blind"],
                "quote": "Here, `adj:7:down` is always 0.",
                "note": "Six rules on adj:7:down and count:0, read off the example rows.",
            },
        },
        "extra": {
            "alternative-dropped": "The miner couldn't separate them because *both* vary.",
            "guard-outside-vocabulary": "adj:7:down",
        },
        "rules": {i: "row-constant" for i in range(6)},
        "goal": "wrong",
        "goal_truth": "the level advances when every key object satisfies its matching "
                      "slot/barrier relation — an assignment condition, not board clearing",
        "goal_quote": "clearing the board of all non-background objects",
        "hidden": "licensed-none",
        "hidden_truth": "a step counter exists; no alias conflict was shown",
        "probe": "discriminating",
        "probe_why": "it explicitly asks for the state that breaks the correlation between "
                     "the two candidate guards — the best probe in the run",
    },
    "vc33_full": {
        "mechanisms": {
            "row-constant": {
                "labels": ["example-row-as-group-constant", "digest-assertion-overridden"],
                "quote": "Why did the miner fail?",
                "note": "Three rules, and the trace itself floats the correct explanation — "
                        "that the shown values are only examples — before discarding it.",
            },
        },
        "extra": {
            "alternative-dropped": "maybe the values listed are just examples and there's overlap not shown",
        },
        "rules": {i: "row-constant" for i in range(3)},
        "goal": "wrong",
        "goal_truth": "as vc33_125 — a per-key matching condition",
        "goal_quote": "manipulating the counts of colours 0, 4, and 7",
        "hidden": "licensed-none",
        "hidden_truth": "as vc33_125",
        "probe": "discriminating",
        "probe_why": "it names a specific untested count configuration",
    },
}

# Outcome knowledge that predates the labelling, declared rather than hidden.
BLINDING_EXCEPTIONS = {
    "dc22_125": "verification array read during schema discovery, before the trace",
    "_refuted_eight": "the 8 refuted dose-125 rules are published in notes/e2-slice.md",
}


# ======================================================================================
# Build
# ======================================================================================


def _body(cell: str) -> str:
    """The whole completion: think body plus the stated answer. Reasoning labels quote the
    think body; goal labels quote the answer, and both are the model's own output."""
    return json.loads((TRACES / f"{cell}.think.json").read_text())["raw"]


def _verify(cell: str, body: str, quote: str) -> str:
    """A quote that is not in its trace is a build error, not a footnote."""
    if quote not in body:
        raise SystemExit(f"QUOTE NOT FOUND in {cell}: {quote!r}")
    return quote


def _proposals(cell: str) -> list[dict[str, Any]]:
    answer = json.loads((TRACES / f"{cell}.extract0.json").read_text())["answer"]
    obj = json.loads(re.sub(r"^```json|```$", "", answer.strip(), flags=re.M))
    return obj.get("rules", [])


def _rule_text(rule: dict[str, Any]) -> str:
    guard = rule.get("guard")
    key = f"A{rule.get('action_id')}"
    if rule.get("click_colour") is not None:
        key += f":{rule['click_colour']}"
    guard_text = "-" if not guard else f"{guard['feature']}={guard['value']}"
    effect = [
        "".join(str(x) for x in e) if isinstance(e, list) else str(e)
        for e in rule.get("effect", [])
    ]
    return f"{key} | {guard_text} -> {'+'.join(effect) or 'no-change'}"


def build() -> dict[str, Any]:
    claims = {c["cell"]: c for c in json.loads(CLAIMS.read_text())["cells"]}
    outcomes = {f"{c['game']}_{c['dose'] if c['dose'] != 'full' else 'full'}": c
                for c in json.loads(SLICE.read_text())["cells"]}
    outcomes = {
        f"{c['game']}_{'full' if c['dose'] is None else c['dose']}": c
        for c in json.loads(SLICE.read_text())["cells"]
    }

    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []

    for cell, spec in LABELS.items():
        body = _body(cell)
        proposals = _proposals(cell)
        outcome = outcomes[cell]
        verification = outcome.get("verification", [])
        joinable = len(verification) == len(proposals)

        for name, mech in spec["mechanisms"].items():
            _verify(cell, body, mech["quote"])
        for quote in spec.get("extra", {}).values():
            _verify(cell, body, quote)
        _verify(cell, body, spec["goal_quote"])

        for index, rule in enumerate(proposals):
            mechanism = spec["rules"][index]
            mech = spec["mechanisms"][mechanism]
            row = {
                "cell": cell,
                "rule_index": index,
                "rule": _rule_text(rule),
                "mechanism": mechanism,
                "labels": [{"label": label, "layer": LAYERS[label]} for label in mech["labels"]],
                "quote": mech["quote"],
                "quote_scope": "cell-mechanism",
                "note": mech["note"],
            }
            if joinable:
                row["outcome"] = {
                    "kept": verification[index]["kept"],
                    "support_on_store": verification[index]["support_on_store"],
                    "contradicted_on_store": verification[index]["contradicted_on_store"],
                }
            else:
                row["outcome"] = {
                    "kept": False,
                    "reason": "parse_rejected — guard outside the miner's vocabulary",
                }
            rows.append(row)

        cells.append(
            {
                "cell": cell,
                "proposals": len(proposals),
                "goal": {
                    "label": spec["goal"],
                    "quote": spec["goal_quote"],
                    "truth_paraphrase": spec["goal_truth"],
                },
                "hidden_state": {
                    "label": spec["hidden"],
                    "truth_paraphrase": spec["hidden_truth"],
                },
                "next_probe": {"label": spec["probe"], "why": spec["probe_why"]},
                "extra_labels": [
                    {"label": label, "layer": LAYERS[label], "quote": quote}
                    for label, quote in spec.get("extra", {}).items()
                ],
                "reading_claims": claims[cell]["rates"],
                "lexicon": claims[cell]["lexicon"],
            }
        )

    return {
        "format_version": 1,
        "source_note": "notes/e2-trace-autopsy.md",
        "blinding": {
            "policy": "label before joining outcomes",
            "followed_for": [c for c in LABELS if c != "dc22_125"],
            "exceptions": BLINDING_EXCEPTIONS,
            "raters": 1,
        },
        "layers": LAYERS,
        "cells": cells,
        "rules": rows,
    }


def summarise(report: dict[str, Any]) -> None:
    from collections import Counter

    layer = Counter()
    label = Counter()
    for row in report["rules"]:
        for item in row["labels"]:
            layer[item["layer"]] += 1
            label[item["label"]] += 1
    kept = sum(1 for r in report["rules"] if r["outcome"].get("kept"))

    print(f"rules labelled: {len(report['rules'])}   kept by verification: {kept}")
    print("\nlabel incidence (rules carrying the label):")
    for name, n in label.most_common():
        print(f"  {n:4d}  {LAYERS[name]:15s} {name}")
    print("\ngoal labels:", dict(Counter(c["goal"]["label"] for c in report["cells"])))
    print("hidden labels:", dict(Counter(c["hidden_state"]["label"] for c in report["cells"])))
    print("probe labels:", dict(Counter(c["next_probe"]["label"] for c in report["cells"])))


if __name__ == "__main__":
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    summarise(report)
