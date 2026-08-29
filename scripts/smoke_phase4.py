"""Reproducible Phase 4 trial-by-fire against a running backend.

Creates a never-before-used step at runtime, appends it to the selected base
workflow, executes the complete run, resolves both human decisions over the
real WebSocket, and verifies the final UISpec plus append-only event log.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from websockets.sync.client import connect


JsonObject = dict[str, Any]


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: JsonObject | None = None,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - explicit local demo URL
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} returned {exc.code}: {detail}") from exc


def websocket_url(base_url: str, run_id: str, token: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit(
        (scheme, parsed.netloc, f"/ws/runs/{run_id}", urlencode({"token": token}), "")
    )


def submit_action(
    base_url: str,
    token: str,
    projection: JsonObject,
    preferred_action: str,
) -> JsonObject:
    decision = projection.get("pendingDecision")
    if not isinstance(decision, dict):
        raise AssertionError("The run has no pending decision")
    actions = projection.get("availableActions", [])
    action = next(
        (item for item in actions if item.get("actionId") == preferred_action),
        None,
    )
    if action is None:
        raise AssertionError(f"Action {preferred_action} is not available")

    timestamp = datetime.now(timezone.utc).isoformat()
    action_event = {
        "schemaVersion": "1",
        "idempotencyKey": f"idem_phase4_{uuid.uuid4().hex}",
        "runId": projection["runId"],
        "workflowVersion": projection["workflowVersion"],
        "stateVersion": projection["stateVersion"],
        "decisionId": decision["decisionId"],
        "actionId": action["actionId"],
        "payload": {},
        "timestamp": timestamp,
    }
    envelope = {
        "schemaVersion": "1",
        "type": "ACTION_SUBMITTED",
        "runId": projection["runId"],
        "sequence": projection["lastSequence"],
        "timestamp": timestamp,
        "payload": action_event,
    }

    with connect(websocket_url(base_url, projection["runId"], token), open_timeout=5) as socket:
        socket.recv(timeout=5)  # Current UI_UPDATED snapshot sent on connect.
        socket.send(json.dumps(envelope))
        while True:
            message = json.loads(socket.recv(timeout=10))
            if message.get("type") == "ACTION_REJECTED":
                raise AssertionError(
                    f"Action rejected: {message['payload'].get('code')} "
                    f"{message['payload'].get('message')}"
                )
            if message.get("type") == "ACTION_ACCEPTED":
                return message["payload"]["projection"]


def walk_nodes(node: JsonObject):
    yield node
    for child in node.get("children", []):
        if isinstance(child, dict):
            yield from walk_nodes(child)


def wait_for_snapshot(base_url: str, run_id: str, state_version: int) -> JsonObject:
    for _ in range(30):
        try:
            snapshot = request_json(base_url, f"/runs/{run_id}/snapshot")
            if snapshot["payload"]["uiSpec"]["stateVersion"] == state_version:
                return snapshot
        except RuntimeError:
            pass
        time.sleep(0.1)
    raise AssertionError("The final UISpec snapshot was not persisted in time")


def run_trial(base_url: str, token: str) -> JsonObject:
    health = request_json(base_url, "/health")
    assert health == {"status": "ok"}

    base_run = request_json(base_url, "/runs", method="POST")
    suffix = uuid.uuid4().hex[:10]
    step_id = f"unseen_runtime_audit_{suffix}"
    step_title = f"Unseen runtime audit {suffix}"
    new_version = request_json(
        base_url,
        f"/workflows/{base_run['workflowId']}/versions",
        method="POST",
        body={
            "baseVersion": base_run["workflowVersion"],
            "steps": [
                {
                    "id": step_id,
                    "type": "generic.runtime",
                    "title": step_title,
                    "objective": "Inspect a prior runtime value and require a human acknowledgement.",
                    "inputs": ["delivery_eta.data.final_eta"],
                    "requiresHumanReview": True,
                }
            ],
        },
    )
    assert new_version["steps"][-1]["id"] == step_id
    assert len(new_version["steps"]) > 1, "The base workflow was not preserved"

    run = request_json(
        base_url,
        "/runs",
        method="POST",
        body={"workflowVersionId": new_version["workflowVersionId"]},
    )
    run_id = run["runId"]
    wire_step_id = f"step_{step_id}"

    for _ in range(20):
        projection = request_json(base_url, f"/runs/{run_id}/projection")
        current = projection.get("currentStep") or {}
        if current.get("id") == wire_step_id:
            break
        if projection["status"] == "paused":
            projection = submit_action(
                base_url,
                token,
                projection,
                "act_find_alternative",
            )
        elif projection["status"] == "running":
            request_json(
                base_url,
                "/demo/advance",
                method="POST",
                body={"runId": run_id},
            )
        else:
            raise AssertionError(f"Run ended before invented step: {projection['status']}")
    else:
        raise AssertionError("Invented step was not reached")

    active_snapshot = request_json(base_url, f"/runs/{run_id}/snapshot")
    active_nodes = list(walk_nodes(active_snapshot["payload"]["uiSpec"]["layout"]))
    active_timeline = next(node for node in active_nodes if node.get("type") == "timeline")
    assert any(
        item["id"] == wire_step_id and item["status"] == "active"
        for item in active_timeline["props"]["items"]
    )

    reviewed = request_json(
        base_url,
        "/demo/advance",
        method="POST",
        body={"runId": run_id},
    )
    assert reviewed["status"] == "paused"
    result = reviewed["operation"][step_id]["data"]
    assert result["missing_inputs"] == []
    assert result["resolved_inputs"]["input_1"]["value"] == "2026-09-15"

    review_snapshot = request_json(base_url, f"/runs/{run_id}/snapshot")
    review_spec = review_snapshot["payload"]["uiSpec"]
    assert review_spec["generatedBy"] == "deterministic"
    assert any(
        node.get("type") == "decisionPanel"
        for node in walk_nodes(review_spec["layout"])
    )

    completed = submit_action(base_url, token, reviewed, "act_acknowledge")
    assert completed["status"] == "completed"
    final_snapshot = wait_for_snapshot(base_url, run_id, completed["stateVersion"])
    final_spec = final_snapshot["payload"]["uiSpec"]
    final_nodes = list(walk_nodes(final_spec["layout"]))
    final_timeline = next(node for node in final_nodes if node.get("type") == "timeline")
    assert any(
        item["id"] == wire_step_id and item["status"] == "completed"
        for item in final_timeline["props"]["items"]
    )

    events = request_json(base_url, f"/runs/{run_id}/events")
    step_events = [event for event in events if event.get("stepId") == wire_step_id]
    step_event_types = [event["type"] for event in step_events]
    assert "STEP_STARTED" in step_event_types
    assert "DECISION_REQUIRED" in step_event_types
    assert "STEP_COMPLETED" in step_event_types

    return {
        "gate": "H17/G4",
        "workflowVersion": new_version["version"],
        "preservedBaseSteps": len(new_version["steps"]) - 1,
        "inventedStepId": wire_step_id,
        "runId": run_id,
        "status": completed["status"],
        "resolvedInput": result["resolved_inputs"]["input_1"],
        "generatedBy": final_spec["generatedBy"],
        "timelineStatus": "completed",
        "eventTypes": step_event_types,
        "exportedEvents": len(events),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="replace-with-a-shared-demo-token")
    args = parser.parse_args()
    print(json.dumps(run_trial(args.base_url, args.token), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
