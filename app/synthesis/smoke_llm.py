"""One real, bounded LLM upgrade call against a recorded projection fixture.

Run from the repository root:
    .venv/Scripts/python.exe -m app.synthesis.smoke_llm

The script prints only a safe result summary. It never prints API keys, the
request payload, or the generated layout.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from argparse import ArgumentParser
from pathlib import Path

from app.schemas.contracts import RunProjection, UISpec
from app.synthesis import DeterministicComposer, LLMComposer
from app.synthesis.benchmark import load_local_environment


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "demo"
    / "fixtures"
    / "run_projection_pending_decision.json"
)


async def run_smoke_test(*, fixture_path: Path, model: str) -> dict[str, object]:
    projection = RunProjection.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    baseline = DeterministicComposer().compose(projection)

    started = time.perf_counter()
    upgraded = await LLMComposer(model=model).compose_upgrade(projection, baseline)
    result = upgraded if upgraded is not None else baseline
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    UISpec.model_validate(result.model_dump(mode="json"))

    return {
        "fixture": fixture_path.name,
        "model": model,
        "latencyMs": latency_ms,
        "generatedBy": result.generated_by,
        # "fallback" means every retry failed and a blank placeholder was
        # shown instead of a deterministic guess; upgraded is None only when
        # the composer is disabled outright (not exercised by this script,
        # since it requires OPENAI_API_KEY).
        "usedBlankFallback": result.generated_by == "fallback",
        "stateVersion": result.state_version,
        "allowedActionCount": len(result.allowed_actions),
        "pydanticValidated": True,
    }


def main() -> int:
    parser = ArgumentParser(description="Run one real LLM UISpec upgrade smoke test.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Exit successfully when the blank fallback is used (all retries failed).",
    )
    args = parser.parse_args()

    load_local_environment()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY must be set in the environment or local .env")
    if not args.fixture.is_file():
        raise SystemExit(f"Fixture does not exist: {args.fixture}")

    result = asyncio.run(run_smoke_test(fixture_path=args.fixture, model=args.model))
    print(json.dumps(result, separators=(",", ":")))
    if result["usedBlankFallback"] and not args.allow_fallback:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
