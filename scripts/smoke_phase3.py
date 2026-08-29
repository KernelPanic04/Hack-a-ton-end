"""Two-tab smoke for the Phase 3 stale-action rejection."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from websockets.asyncio.client import connect

from smoke_phase2 import receive_type, request_json, websocket_url


def action_envelope(ui_envelope: dict[str, Any], idempotency_key: str) -> str:
    projection = ui_envelope["payload"]["projection"]
    action = ui_envelope["payload"]["uiSpec"]["allowedActions"][0]
    now = datetime.now(timezone.utc).isoformat()
    return json.dumps(
        {
            "schemaVersion": "1",
            "type": "ACTION_SUBMITTED",
            "runId": projection["runId"],
            "sequence": ui_envelope["sequence"],
            "timestamp": now,
            "payload": {
                "schemaVersion": "1",
                "idempotencyKey": idempotency_key,
                "runId": projection["runId"],
                "workflowVersion": projection["workflowVersion"],
                "stateVersion": projection["stateVersion"],
                "decisionId": projection["pendingDecision"]["decisionId"],
                "actionId": action["actionId"],
                "payload": {},
                "timestamp": now,
            },
        }
    )


async def smoke(base_url: str, token: str) -> dict[str, Any]:
    projection = request_json(base_url, "POST", "/demo/skeleton")
    url = websocket_url(base_url, projection["runId"], token)

    async with connect(url) as first_tab, connect(url) as stale_tab:
        first_ui = await receive_type(first_tab, "UI_UPDATED")
        stale_ui = await receive_type(stale_tab, "UI_UPDATED")

        await first_tab.send(action_envelope(first_ui, f"idem_{uuid.uuid4()}"))
        await receive_type(first_tab, "ACTION_ACCEPTED")
        resumed_ui = await receive_type(first_tab, "UI_UPDATED")
        assert resumed_ui["payload"]["projection"]["status"] == "running"

        await stale_tab.send(action_envelope(stale_ui, f"idem_{uuid.uuid4()}"))
        rejected = await receive_type(stale_tab, "ACTION_REJECTED")
        assert rejected["payload"]["code"] == "STALE_STATE_VERSION"

    events = request_json(base_url, "GET", f"/runs/{projection['runId']}/events")
    assert events[-1]["type"] == "ACTION_REJECTED"
    return {
        "gateG3Policy": "passed",
        "rejection": rejected["payload"]["code"],
        "runId": projection["runId"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="placeholder")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(smoke(args.base_url.rstrip("/"), args.token)), indent=2))


if __name__ == "__main__":
    main()
