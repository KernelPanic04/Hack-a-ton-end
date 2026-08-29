"""Reproducible local smoke test for Gate G1 and the Phase 2 golden path."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib import request

from websockets.asyncio.client import connect


def request_json(base_url: str, method: str, path: str, payload: dict | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = request.Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


def websocket_url(base_url: str, run_id: str, token: str) -> str:
    scheme = "wss" if base_url.startswith("https://") else "ws"
    host = base_url.split("://", 1)[1]
    return f"{scheme}://{host}/ws/runs/{run_id}?token={token}"


def tree_types(node: dict[str, Any]) -> list[str]:
    types = [node["type"]]
    for child in node.get("children", []):
        types.extend(tree_types(child))
    return types


async def receive_type(socket, expected: str, limit: int = 8) -> dict[str, Any]:
    observed: list[str] = []
    for _ in range(limit):
        envelope = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        observed.append(envelope["type"])
        if envelope["type"] == expected:
            return envelope
    raise AssertionError(f"Expected {expected}; observed {observed}")


async def submit_visible_action(socket, ui_envelope: dict[str, Any]) -> dict[str, Any]:
    projection = ui_envelope["payload"]["projection"]
    ui_spec = ui_envelope["payload"]["uiSpec"]
    action = ui_spec["allowedActions"][0]
    now = datetime.now(timezone.utc).isoformat()
    await socket.send(
        json.dumps(
            {
                "schemaVersion": "1",
                "type": "ACTION_SUBMITTED",
                "runId": projection["runId"],
                "sequence": ui_envelope["sequence"],
                "timestamp": now,
                "payload": {
                    "schemaVersion": "1",
                    "idempotencyKey": f"idem_{uuid.uuid4()}",
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
    )
    accepted = await receive_type(socket, "ACTION_ACCEPTED")
    await receive_type(socket, "UI_UPDATED")
    return accepted


async def smoke(base_url: str, token: str) -> dict[str, Any]:
    skeleton = request_json(base_url, "POST", "/demo/skeleton")
    async with connect(websocket_url(base_url, skeleton["runId"], token)) as socket:
        skeleton_ui = await receive_type(socket, "UI_UPDATED")
        types = tree_types(skeleton_ui["payload"]["uiSpec"]["layout"])
        assert {"page", "alert", "decisionPanel", "timeline", "keyValue"}.issubset(types)
        await submit_visible_action(socket, skeleton_ui)
    skeleton_events = request_json(
        base_url,
        "GET",
        f"/runs/{skeleton['runId']}/events",
    )
    assert any(event["type"] == "ACTION_ACCEPTED" for event in skeleton_events)

    projection = request_json(base_url, "POST", "/runs")
    async with connect(websocket_url(base_url, projection["runId"], token)) as socket:
        latest_ui = await receive_type(socket, "UI_UPDATED")
        observed_states = [latest_ui["payload"]["projection"]["status"]]

        for _ in range(3):
            projection = request_json(
                base_url,
                "POST",
                "/demo/advance",
                {"runId": projection["runId"]},
            )
            latest_ui = await receive_type(socket, "UI_UPDATED")
            observed_states.append(projection["status"])

        assert projection["status"] == "paused"
        await submit_visible_action(socket, latest_ui)

        for _ in range(2):
            projection = request_json(
                base_url,
                "POST",
                "/demo/advance",
                {"runId": projection["runId"]},
            )
            latest_ui = await receive_type(socket, "UI_UPDATED")
            observed_states.append(projection["status"])

        assert projection["status"] == "completed"
        final_types = tree_types(latest_ui["payload"]["uiSpec"]["layout"])
        assert "timeline" in final_types

    return {
        "gateG1": "passed",
        "goldenPath": "completed",
        "runId": projection["runId"],
        "states": observed_states,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="placeholder")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(smoke(args.base_url.rstrip("/"), args.token)), indent=2))


if __name__ == "__main__":
    main()
