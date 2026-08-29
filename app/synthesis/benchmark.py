"""One-shot real-network benchmark for the strict UI upgrade schema.

Run from the repository root:
    .venv\\Scripts\\python.exe -m app.synthesis.benchmark

It reads OPENAI_API_KEY from the environment or a local .env file and never
prints the key, request body, or generated UI content.
"""

from __future__ import annotations

import json
import os
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.synthesis.llm_upgrade import structured_output_format, validate_llm_upgrade


MODEL = "gpt-5.4-mini"
RESPONSES_URL = "https://api.openai.com/v1/responses"


def load_local_environment(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries only when absent from the process env."""

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("Responses API returned no output_text content")


def measure_once(
    api_key: str,
    *,
    model: str = MODEL,
    reasoning_effort: str = "none",
) -> dict[str, Any]:
    """Make one bounded request and return only non-sensitive benchmark facts."""

    payload = {
        "model": model,
        "store": False,
        "reasoning": {"effort": reasoning_effort},
        "max_output_tokens": 500,
        "instructions": (
            "Create a concise declarative run overview. Prefer a clear hierarchy "
            "with one section and one metric. Return data that matches the supplied schema."
        ),
        "input": "The run is active and 50 percent complete. Show progress clearly.",
        "text": {"format": structured_output_format()},
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started = time.perf_counter()
    with urlopen(request, timeout=20) as response:  # nosec B310: fixed HTTPS endpoint
        body = json.loads(response.read().decode("utf-8"))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    validate_llm_upgrade(_output_text(body))
    usage = body.get("usage") or {}
    return {
        "model": body.get("model", model),
        "reasoningEffort": reasoning_effort,
        "status": body.get("status"),
        "latencyMs": latency_ms,
        "structuredOutputValidated": True,
        "inputTokens": usage.get("input_tokens"),
        "outputTokens": usage.get("output_tokens"),
        "totalTokens": usage.get("total_tokens"),
        "serviceTier": body.get("service_tier"),
    }


def main() -> int:
    parser = ArgumentParser(description="Measure one strict structured-output call.")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument(
        "--reasoning-effort",
        default="none",
        choices=("none", "low", "medium", "high", "xhigh"),
    )
    args = parser.parse_args()

    load_local_environment()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY must be set in the environment or local .env")

    try:
        result = measure_once(
            api_key,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
        print(json.dumps(result, separators=(",", ":")))
    except HTTPError as error:
        message = ""
        try:
            detail = json.loads(error.read().decode("utf-8"))
            message = str(detail.get("error", {}).get("message", ""))
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = "no JSON error detail returned"
        raise SystemExit(f"OpenAI request failed with HTTP {error.code}: {message}") from error
    except URLError as error:
        raise SystemExit(f"OpenAI network request failed: {error.reason}") from error


if __name__ == "__main__":
    raise SystemExit(main())
