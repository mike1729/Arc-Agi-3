#!/usr/bin/env python3
"""E2 slice 3, build item 5b — the contamination gate. Run before the night, every time.

`notes/e2-slice3.md`: "the prompt must never name the five stock goal shapes — they are
channel A's control. Grep-gated before the night."

WHY THIS IS A GATE AND NOT A HABIT
----------------------------------
Channel A's control is the prior library: the five default goal shapes the reference brings
to every game, which fire on 21 of its 42 wins. The whole comparison is "did the model reach
a goal the control did not". If the prompt names those shapes, `in_prior_library` stops
measuring convergence and starts measuring compliance — and the failure is silent, because a
contaminated prompt produces a perfectly well-formed result.

The second half of the gate is the ANCHOR, which slice 2 demonstrated the cost of: its
channel-C request named `clicked_adjacent_to:C` as the previous win, and ft09's cell duly
re-proposed `clicked_adjacent_to:11` and `:12`. Naming a past answer inside the question is
the same defect wearing different clothes.

Every rendered prompt is checked, not a sample, and the exit status is non-zero on any hit so
a run script cannot proceed past it.

Run:
  .venv/bin/python agent/harness/e2_contamination.py --frames
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
import e2_slice as sl  # noqa: E402

# The five stock shapes, and the phrasings that would give them away. Deliberately broader
# than the shape names themselves: the contamination that matters is the model being told
# what a goal usually looks like, in any words.
FORBIDDEN = {
    "avatar": r"\bavatar\b",
    "salient target": r"\bsalient\b",
    "every X into its Y": r"\b(into|onto) its\b",
    "clear/collect all X": r"\b(clear|collect) (them |the )?all\b",
    "copy the template": r"\btemplate\b",
    "align the two matching": r"\balign(ing|ed)?\b.{0,30}\bmatch",
    "stock-goal framing": r"\b(stock|default|usual|typical|common) goal",
    "goal-shape framing": r"\bgoal shapes?\b",
    "prior library": r"\bprior librar",
}

# The ANCHOR check, and why it is scoped to the REQUEST rather than the whole prompt.
#
# `clicked_adjacent_to:C` is a real member of the miner's guard vocabulary, and the digest
# names it in feature listings, strata tables and no-separation witnesses — hundreds of times
# on the dense games. That is EVIDENCE: a channel-C proposal has to know what the vocabulary
# already contains, or "missing" means nothing. Measured: 306 hits across the eight prompts,
# every one of them a value set, a stratum or a witness.
#
# What rev 2 removed is the sentence in the channel-C QUESTION that named it as the previous
# payout. Slice 2 had it and ft09's cell duly re-proposed `clicked_adjacent_to:11` and `:12`.
# So the anchor is a defect of the request, not of the evidence, and the gate checks the
# request — everything in the templated prompt that is not the digest.
FORBIDDEN_IN_REQUEST = {
    "channel-C anchor": r"clicked_adjacent_to",
    "past-payout framing": r"\b(already )?paid out\b|\bprevious slice named\b|"
                           r"\bmoved the mechanical floor\b",
}


def check(text: str, patterns: dict[str, str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for label, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - 60)
            hits.append((label, text[start : match.end() + 60].replace("\n", " ")))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(dsl.SLICE2_GAMES))
    parser.add_argument("--frames", action="store_true", help="check the slice-3 (v4) prompts")
    args = parser.parse_args()

    total = 0
    for game in args.games:
        caps = None
        if args.frames:
            caps, _ = sl.fit_caps(game, None, sl.TOKEN_BUDGET)
        digest = sl.build_digest(game, None, with_frames=args.frames, caps=caps)
        prompt = sl.build_prompt(digest)
        # The request is the templated prompt with the evidence removed: the framing, the
        # grammars, the reasoning contract and the three questions.
        request = prompt.replace(digest["text"], "\n[DIGEST]\n")
        hits = check(prompt, FORBIDDEN) + check(request, FORBIDDEN_IN_REQUEST)
        total += len(hits)
        print(
            f"{game:5s} prompt {len(prompt):7d} chars, request {len(request):6d} chars  "
            + ("CLEAN" if not hits else f"*** {len(hits)} HITS ***"),
            flush=True,
        )
        for label, context in hits:
            print(f"        {label}: ...{context}...")

    print(f"\n{total} total hits across {len(args.games)} prompts")
    if total:
        print("GATE: FAIL — do not run the night until every hit is resolved or justified")
        return 1
    print("GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
