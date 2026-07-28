"""S1-d — render a FIXED evidence slice per episode for the rater.

WHY THIS IS A SCRIPT AND NOT AD-HOC SLICING
-------------------------------------------
The corpus holds ~7.5 M characters of reasoning across 75 episodes — median ~100 k per episode. No
rater reads that, so every rating pass is really a rating of some SLICE of it. Which slice is therefore
part of the method, and if it varies between episodes or between runs then a frequency difference
across runs is confounded with a difference in what the rater was shown.

That confound is not hypothetical here. The S1-d first pass over run v2 sliced evidence by hand, and
its own limitations note records the consequence: "The worksheet showed early and terminal reasoning,
not every step. Categories defined on mid-episode behaviour — `hidden_state_aliasing_or_memory`
especially — are likelier to be under-counted than over-counted." A hand slice cannot be replayed, so
that statement cannot be checked and the next pass cannot be matched to it.

So the slice is fixed here, applied identically to every episode, and its parameters are written into
the worksheet header. Re-running this script reproduces the exact substrate a rating was made from.

WHAT THE SLICE IS, AND WHAT IT COSTS
------------------------------------
Per episode: the FIRST analysis step, then the LAST two. Within each, `reasoning` (the model's private
thinking), `content` (its visible output — usually an explicit "World model" summary, which is the
single most informative field for `goal_unknown`) and, on the terminal step only, `tool_code`.

This is an OPENING-AND-CLOSING slice. It is chosen because the taxonomy's dominant distinctions are
visible at the ends: whether a goal was ever stated, whether it was still unstated at termination,
whether the agent was on a working trajectory when the budget cut it. It is a poor slice for anything
defined on the middle of an episode, and those categories stay under-counted. That is a known,
recorded bias, not a silent one — see `--every-nth` to widen it, at proportional context cost.

Episodes shorter than three steps are emitted whole; nothing is elided that would have fit.

Run:
  .venv/bin/python agent/harness/s1d_worksheet.py logs/s1d_corpus_pooled.json \
      --runs kaggle_v3 kaggle_v4 --out logs/s1d_worksheet_v3v4.md
  .venv/bin/python agent/harness/s1d_worksheet.py logs/s1d_corpus_pooled.json \
      --runs kaggle_v3 --batch 1 --batch-size 10        # one readable chunk at a time
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# The slice, in one place. Every number here appears in the worksheet header, because a rating is only
# interpretable against the evidence budget it was made under.
CAP_REASONING = 1000
CAP_CONTENT = 700
CAP_TOOL_CODE = 350
HEAD_STEPS = 1          # earliest analysis steps shown
TAIL_STEPS = 2          # terminal analysis steps shown

LABELABLE = [
    "goal_unknown", "action_semantics_unknown", "perception_parsing",
    "hidden_state_aliasing_or_memory", "exploration_or_probe_selection",
    "progress_signal_misinterpretation", "irreversible_mistake",
    "invalid_output_interface", "retrieval_or_context", "reasoning_inconsistency",
    "latency_or_budget",
]


def _clip(s, n):
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n].rstrip() + f"\n      […{len(s) - n:,} more chars]"


def _render_step(step_key, entries, *, with_tool_code):
    out = [f"  --- step {step_key} ---"]
    for e in entries:
        if e.get("reasoning"):
            out.append(f"  reasoning: {_clip(e['reasoning'], CAP_REASONING)}")
        if e.get("content"):
            out.append(f"  content:   {_clip(e['content'], CAP_CONTENT)}")
        if with_tool_code:
            for tc in (e.get("tool_code") or [])[:1]:
                if tc:
                    out.append(f"  tool_code: {_clip(tc, CAP_TOOL_CODE)}")
        if e.get("finish_reason"):
            out.append(f"  finish_reason: {e['finish_reason']}")
    return out


def render(ep: dict, every_nth: int = 0) -> str:
    rb = ep["evidence"].get("reasoning_by_step") or {}
    keys = sorted(rb, key=lambda k: int(k) if str(k).isdigit() else 0)

    ratio = ep.get("action_ratio_vs_baseline")
    ratio_s = f"{ratio:.2f}x" if isinstance(ratio, (int, float)) else "—"
    total_chars = sum(len(str(v)) for v in rb.values())

    L = [
        f"### {ep['episode_id']}",
        f"game {ep['game']} · level {ep['level']} · run {ep.get('source_run')}",
        f"actions {ep.get('actions_taken')} vs human baseline {ep.get('human_baseline')} "
        f"({ratio_s}) · terminal_state {ep.get('terminal_state')} · "
        f"budget_terminated {ep.get('budget_terminated')}",
        f"distinct_actions {ep.get('distinct_actions')} · "
        f"top_action_share {ep.get('top_action_share')} · "
        f"analysis_turns {ep.get('analysis_turns')} · "
        f"steps_with_reasoning {len(keys)} · evidence {total_chars:,} chars",
        "",
    ]

    if not keys:
        L.append("  (NO REASONING EVIDENCE — not ratable on the text-defined categories)")
        return "\n".join(L) + "\n"

    if every_nth:
        shown = keys[::every_nth]
        if keys[-1] not in shown:
            shown.append(keys[-1])
    elif len(keys) <= HEAD_STEPS + TAIL_STEPS:
        shown = keys                      # short episode: nothing is elided
    else:
        shown = keys[:HEAD_STEPS] + keys[-TAIL_STEPS:]

    for i, k in enumerate(shown):
        if i and keys.index(k) > keys.index(shown[i - 1]) + 1:
            gap = keys.index(k) - keys.index(shown[i - 1]) - 1
            L.append(f"  … {gap} step(s) not shown …")
        L += _render_step(k, rb[k], with_tool_code=(k == keys[-1]))
        L.append("")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--runs", nargs="*", default=[],
                    help="restrict to these source_run values (default: all)")
    ap.add_argument("--unlabelled-only", action="store_true",
                    help="skip episodes that already carry labels")
    ap.add_argument("--every-nth", type=int, default=0,
                    help="show every Nth step instead of the head/tail slice — widens coverage of "
                         "mid-episode categories at proportional context cost")
    ap.add_argument("--batch", type=int, default=0, help="1-indexed batch to emit")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    d = json.loads(Path(a.corpus).read_text())
    eps = d["episodes"]
    if a.runs:
        eps = [e for e in eps if e.get("source_run") in a.runs]
    if a.unlabelled_only:
        eps = [e for e in eps if not e.get("labels")]
    eps.sort(key=lambda e: (e.get("source_run", ""), e["game"], e.get("level") or 0))

    total = len(eps)
    n_batches = (total + a.batch_size - 1) // a.batch_size if a.batch else 1
    if a.batch:
        eps = eps[(a.batch - 1) * a.batch_size: a.batch * a.batch_size]

    slice_desc = (f"every {a.every_nth}th step" if a.every_nth
                  else f"first {HEAD_STEPS} + last {TAIL_STEPS} analysis steps")
    head = [
        "# S1-d labelling worksheet",
        "",
        f"corpus: {a.corpus} · runs: {a.runs or 'all'} · episodes here: {len(eps)} of {total}"
        + (f" (batch {a.batch}/{n_batches})" if a.batch else ""),
        "",
        "**Evidence slice — part of the method, not a display choice.** "
        f"{slice_desc}; per entry reasoning≤{CAP_REASONING}, content≤{CAP_CONTENT} chars, "
        f"tool_code≤{CAP_TOOL_CODE} on the terminal step only. Episodes with "
        f"≤{HEAD_STEPS + TAIL_STEPS} steps are shown whole.",
        "",
        "This is an opening-and-closing slice: strong for whether a goal was ever stated and whether it "
        "was still unstated at termination, weak for anything defined mid-episode. "
        "`hidden_state_aliasing_or_memory` in particular stays under-counted.",
        "",
        f"Categories: {', '.join(LABELABLE)}",
        "",
        "---",
        "",
    ]
    text = "\n".join(head) + "\n".join(render(e, a.every_nth) + "\n" for e in eps)

    if a.out:
        Path(a.out).write_text(text)
        print(f"wrote {a.out} — {len(eps)} episodes, {len(text):,} chars")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
