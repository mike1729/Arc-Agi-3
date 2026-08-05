#!/usr/bin/env python3
"""E2 slice 3, build item 6 — the mandatory budget probe. One model call, before the night.

Protocol of `notes/think-budget-recheck.md`, run against the largest slice-3 prompt.

WHAT IT DECIDES, AND WHAT IT MAY NOT
------------------------------------
Two questions, both of which have to be answered before 16 cells are committed to a GPU:

  1. DOES THE THINK BLOCK STILL CLOSE inside `THINK_BUDGET`? An unclosed block VOIDS a cell,
     and a budget that no longer fits would void all sixteen. `notes/e2-slice3.md`: if it
     does not close, STOP AND REPORT — no unilateral budget raise.
  2. WHAT IS WARM PREFILL AT THIS PROMPT SIZE? The wall estimate for the night needs it, and
     it cannot be extrapolated from slice 2's 19.4k prompts.

The slice-2 precedent is the reason this is not skippable and also the reason not to assume
the answer: digest v3 grew the prompt 59% and the think block did not move at all, because
the growth was entirely prefill. Slice 3 roughly doubles the prompt again. Neither direction
is safe to guess.

INSTRUMENT RULES, IDENTICAL TO THE NIGHT'S
------------------------------------------
Direct `mlx_lm`, no server. `enable_thinking=True`. The first decoded token is NEVER
constrained. Same model, same temperature, same seed handling, same mechanical verdict.

The trace is written to `logs/e2_slice_traces/` under an `_s3probe` tag, which `.gitignore`
excludes — it contains a rendered board.

Run:
  .venv/bin/python agent/harness/e2_budget_probe.py --game dc22
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
import e2_slice as sl  # noqa: E402
from rs_transitions import ROOT  # noqa: E402

OUTPUT = ROOT / "logs/e2_slice3_budget_probe.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game",
        default=None,
        help="game to probe; default is whichever slice-3 prompt is largest",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--model", type=Path, default=sl.MODEL)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    game = args.game
    fits: dict[str, Any] = {}
    if game is None:
        print("sizing every slice-3 prompt to find the largest ...", flush=True)
        for candidate in dsl.SLICE2_GAMES:
            _, report = sl.fit_caps(candidate, None, sl.TOKEN_BUDGET, args.model)
            fits[candidate] = report["f_prompt_tokens"]
            print(f"  {candidate}: {report['f_prompt_tokens']} tokens", flush=True)
        game = max(fits, key=lambda name: fits[name])
        print(f"largest: {game}", flush=True)

    caps, fit = sl.fit_caps(game, None, sl.TOKEN_BUDGET, args.model)
    digest = sl.build_digest(game, None, with_frames=True, caps=caps)
    prompt = sl.build_prompt(digest)

    print(f"loading {args.model.name} ...", flush=True)
    start = time.monotonic()
    qwen = sl.Qwen(args.model)
    print(f"loaded in {time.monotonic() - start:.1f}s", flush=True)

    print(
        f"probing {game}: {len(prompt)} chars / {fit['f_prompt_tokens']} tokens, "
        f"think budget {sl.THINK_BUDGET}",
        flush=True,
    )
    call = qwen.generate(
        [{"role": "user", "content": prompt}],
        max_tokens=sl.THINK_BUDGET,
        thinking=True,
        seed=args.seed,
    )
    verdict = sl.thinking_verdict(call)

    tokenizer = qwen.tokenizer
    generated = tokenizer.encode(call["raw"])
    think_tokens = None
    closing = None
    if call["think_closed"]:
        before = call["raw"].split("</think>", 1)[0]
        think_tokens = len(tokenizer.encode(before))
        closing = len(tokenizer.encode(before + "</think>"))

    tag = f"{game}_full_s3probe_b{sl.THINK_BUDGET}"
    sl.TRACES.mkdir(parents=True, exist_ok=True)
    (sl.TRACES / f"{tag}.think.json").write_text(
        json.dumps({"prompt": prompt, **call, "verdict": verdict}, indent=2)
    )

    passed = bool(call["think_closed"] and all(verdict.values()))
    document = {
        "note": "notes/e2-slice3.md build item 6; protocol notes/think-budget-recheck.md",
        "game": game,
        "model": str(args.model),
        "seed": args.seed,
        "think_budget": sl.THINK_BUDGET,
        "prompt": {
            "chars": len(prompt),
            "tokens": fit["f_prompt_tokens"],
            "fb_chat_tokens": fit["fb_chat_tokens"],
            "trim_step": fit["trim_step"],
            "caps": fit["caps"],
        },
        "generation": {
            "total_tokens": len(generated),
            "think_tokens": think_tokens,
            "closing_tag_at_token": closing,
            "spare_tokens": sl.THINK_BUDGET - len(generated),
            "think_chars": call["think_chars"],
            "answer_chars": len(call["answer"]),
        },
        "timing": {
            "wall_seconds": call["wall_seconds"],
            "prompt_tps": call["prompt_tps"],
            "generation_tps": call["generation_tps"],
        },
        "verdict": verdict,
        "gate": "PASS" if passed else "FAIL",
        "other_prompt_sizes": fits or None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))

    print(json.dumps(document["generation"] | document["timing"], indent=2))
    print(f"\nGATE: {document['gate']}")
    if not passed:
        print(
            "The think block did not close inside the budget. STOP — do not raise "
            "THINK_BUDGET unilaterally; report this and let the note's owner decide."
        )
    print(f"wrote {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
