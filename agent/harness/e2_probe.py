#!/usr/bin/env python3
"""E2 bring-up — verify that Qwen thinking actually fires on the local MLX path.

The screens died on this exact instrument: the July serving path (mlx_vlm server,
guided JSON) decoded without thinking, and every Qwen number measured through it was
voided (CLAUDE.md, 2026-08-04). The standing rule: NEVER constrain the first decoded
token; think first, extract after. This probe is the gate every E2 Qwen call runs
behind — it uses mlx_lm DIRECTLY (no server layer), renders the chat template with
`enable_thinking=True`, asserts the rendered prompt does not pre-fill an empty think
block, generates freely, and writes the RAW trace to logs/ for audit.

Pass criteria (mechanical, no judgment call):
  1. rendered prompt contains no "<think>\n\n</think>" pre-fill;
  2. the completion opens a think block and closes it;
  3. the think body is substantive (>= 200 chars, not whitespace);
  4. non-empty answer text after </think>.

Run:
  .venv/bin/python agent/harness/e2_probe.py
  .venv/bin/python agent/harness/e2_probe.py --model ~/models/mlx/Qwen3.6-35B-A3B-4bit
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

MODEL = Path.home() / "models/mlx/Qwen3.6-27B-4bit"  # (w) the S1-measured family
OUTPUT = Path(__file__).resolve().parents[2] / "logs/e2_thinking_probe.json"

# Small but real: requires actual multi-step reasoning, answerable in one paragraph.
PROBE_MESSAGES = [
    {
        "role": "user",
        "content": (
            "In a grid game, pressing UP moved a blue square from (5,3) to (4,3) in "
            "three separate observations, but in a fourth observation with a red wall "
            "at (3,3), pressing UP twice left the square at (4,3). State the movement "
            "rule including its guard, then predict what happens if the square is at "
            "(2,2) with a red wall at (0,2) and UP is pressed twice."
        ),
    }
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument("--temp", type=float, default=0.6)  # (w) Qwen thinking default
    parser.add_argument("--top-p", type=float, default=0.95)  # (w)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    t0 = time.monotonic()
    model, tokenizer = load(str(args.model))
    load_seconds = time.monotonic() - t0

    prompt = tokenizer.apply_chat_template(
        PROBE_MESSAGES,
        add_generation_prompt=True,
        enable_thinking=True,
        tokenize=False,
    )
    prefill_empty_think = "<think>\n\n</think>" in prompt
    # Qwen3 templates open the think block inside the generation prompt when thinking
    # is enabled; either the prompt ends with an open tag or the model must emit one.
    prompt_opens_think = prompt.rstrip().endswith("<think>")

    sampler = make_sampler(temp=args.temp, top_p=args.top_p)
    pieces: list[str] = []
    generation_tps = prompt_tps = None
    t1 = time.monotonic()
    for response in stream_generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=args.max_tokens,
        sampler=sampler,
    ):
        pieces.append(response.text)
        generation_tps = getattr(response, "generation_tps", None)
        prompt_tps = getattr(response, "prompt_tps", None)
    wall = time.monotonic() - t1
    completion = "".join(pieces)

    full = ("<think>" + completion) if prompt_opens_think else completion
    think_open = "<think>" in full
    think_close = "</think>" in full
    think_body = full.split("<think>", 1)[-1].split("</think>", 1)[0] if think_open else ""
    answer = full.split("</think>", 1)[-1].strip() if think_close else ""

    verdict = {
        "no_prefilled_empty_think": not prefill_empty_think,
        "think_opened": think_open,
        "think_closed": think_close,
        "think_substantive": len(think_body.strip()) >= 200,
        "answer_nonempty": bool(answer),
    }
    passed = all(verdict.values())

    document = {
        "model": str(args.model),
        "sampling": {"temp": args.temp, "top_p": args.top_p, "max_tokens": args.max_tokens},
        "load_seconds": round(load_seconds, 1),
        "wall_seconds": round(wall, 1),
        "prompt_tps": prompt_tps,
        "generation_tps": generation_tps,
        "prompt_opens_think": prompt_opens_think,
        "prompt_tail": prompt[-200:],
        "verdict": verdict,
        "passed": passed,
        "think_chars": len(think_body.strip()),
        "raw_completion": completion,  # the auditable trace — never truncate this
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2))

    print(f"model            {args.model.name}")
    print(f"load             {load_seconds:.1f}s   generation {wall:.1f}s")
    print(f"prompt_tps       {prompt_tps}   generation_tps {generation_tps}")
    print(f"prompt opens <think>: {prompt_opens_think}   pre-filled empty think: {prefill_empty_think}")
    print(f"think chars      {len(think_body.strip())}")
    print(f"verdict          {verdict}")
    print(f"PASSED           {passed}")
    print(f"\nwrote {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
