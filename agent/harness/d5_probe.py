"""D5 probe — does the local MLX server return parsed OpenAI `tool_calls`?

D5 is the deviation the reference freeze names as "the most likely single point of failure":
`tool_call_parser: qwen3_coder` and `reasoning_parser: qwen3` are vLLM *server-side* features, and
if the MLX server does not implement them the solver cannot act at all.

The probe is deliberately faithful rather than convenient: it builds the request with TAAF's own
`build_chat_payload` and TAAF's own single-`python`-tool schema, so a pass here is evidence about the
harness and not about a hand-rolled request.

Run:  .venv/bin/python agent/harness/d5_probe.py [--provider vllm|openrouter]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, "agent/work/taaf/src/ARC3-Inference")
from inference.utils.openai_compat import build_chat_payload  # noqa: E402

BASE_URL = "http://127.0.0.1:1234/v1"
MODEL = os.path.expanduser(os.environ.get("MLX_MODEL_PATH", "~/models/mlx/Qwen3.6-27B-4bit"))  # server routes by the path it loaded

# TAAF's actual tool schema (inference/agent/tool_agent.py::_tools), reproduced exactly.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "python",
            "description": "Run a short ephemeral Python snippet and return its stdout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code to run. The snippet is ephemeral and is not saved "
                            "across tool calls."
                        ),
                    },
                },
                "required": ["code"],
            },
        },
    }
]

PROMPT = (
    "Use the python tool to compute the number of distinct colours in this ARC grid "
    "and print it: [[1,1,2],[2,3,3],[1,0,0]]. Call the tool; do not answer directly."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="vllm", choices=["vllm", "openrouter"])  # match the local config
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    payload = build_chat_payload(
        provider=args.provider,
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=2048,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        thinking=True,
        tools=TOOLS,
        tool_choice="auto",
        seed=42,
    )

    print(f"provider={args.provider}  payload keys={sorted(payload)}")
    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=args.timeout,
    )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:2000])
        return 1

    body = r.json()
    choice = body["choices"][0]
    msg = choice["message"]
    tool_calls = msg.get("tool_calls") or []

    print(f"finish_reason      : {choice.get('finish_reason')!r}")
    print(f"content chars      : {len(msg.get('content') or '')}")
    print(f"reasoning_content  : {len(msg.get('reasoning_content') or '')} chars")
    print(f"tool_calls parsed  : {len(tool_calls)}")
    for tc in tool_calls:
        fn = tc.get("function", {})
        print(f"  name={fn.get('name')!r}")
        raw_args = fn.get("arguments", "")
        try:
            parsed = json.loads(raw_args)
            print(f"  arguments JSON-valid: True  keys={sorted(parsed)}")
            print(f"  code: {parsed.get('code', '')[:200]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  arguments JSON-valid: False ({exc}) raw={raw_args[:200]!r}")

    usage = body.get("usage") or {}
    print(f"usage              : {usage}")

    # A non-empty tool_calls array is NOT sufficient: a wrong function name, malformed JSON, or a
    # missing `code` argument would all pass that test while leaving the solver unable to act.
    usable = False
    if tool_calls:
        fn = tool_calls[0].get("function", {})
        if fn.get("name") == "python":
            try:
                usable = isinstance(json.loads(fn.get("arguments", "")).get("code"), str)
            except Exception:  # noqa: BLE001
                usable = False
    verdict = "PASS" if usable else "FAIL"
    print(f"\nD5 VERDICT: {verdict} — a USABLE `python` tool call with JSON-valid `code` "
          f"{'was returned' if usable else 'was NOT returned'} "
          f"(raw tool_calls present: {bool(tool_calls)})")
    if not usable:
        print("content preview:", (msg.get("content") or "")[:600])
    return 0 if usable else 2


if __name__ == "__main__":
    raise SystemExit(main())
