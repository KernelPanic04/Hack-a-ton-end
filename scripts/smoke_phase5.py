"""Verify that HTTP payloads produce a contract-safe UISpec snapshot."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from websockets.sync.client import connect


REGISTRY_TYPES = {
    "page",
    "section",
    "metric",
    "alert",
    "timeline",
    "keyValue",
    "compare",
    "decisionPanel",
    "step",
}


def request_json(base_url: str, path: str, *, method: str = "GET") -> Any:
    request = Request(f"{base_url.rstrip('/')}{path}", method=method)
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - explicit smoke URL
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} returned {exc.code}: {detail}") from exc


def walk_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        if isinstance(child, dict):
            yield from walk_nodes(child)


def websocket_url(base_url: str, run_id: str, token: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path_prefix = parsed.path.rstrip("/")
    path = f"{path_prefix}/ws/runs/{run_id}"
    return urlunsplit(
        (scheme, parsed.netloc, path, urlencode({"token": token}), "")
    )


def verify_websocket_snapshot(base_url: str, run_id: str, token: str) -> None:
    with connect(websocket_url(base_url, run_id, token), open_timeout=5) as socket:
        envelope = json.loads(socket.recv(timeout=5))
    assert envelope["type"] == "UI_UPDATED"
    assert envelope["runId"] == run_id


def wait_for_snapshot(
    base_url: str,
    run_id: str,
    *,
    expected_generator: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            latest = request_json(base_url, f"/runs/{run_id}/snapshot")
        except RuntimeError:
            time.sleep(0.1)
            continue
        generated_by = latest["payload"]["uiSpec"]["generatedBy"]
        if expected_generator == "any" or generated_by == expected_generator:
            return latest
        time.sleep(0.2)

    actual = latest["payload"]["uiSpec"]["generatedBy"] if latest else "unavailable"
    raise AssertionError(
        f"Expected generatedBy={expected_generator}, last snapshot was {actual}"
    )


def run_smoke(
    base_url: str,
    *,
    expected_generator: str,
    timeout_seconds: float,
    token: str | None,
) -> dict[str, Any]:
    assert request_json(base_url, "/health") == {"status": "ok"}
    projection = request_json(base_url, "/runs", method="POST")
    snapshot = wait_for_snapshot(
        base_url,
        projection["runId"],
        expected_generator=expected_generator,
        timeout_seconds=timeout_seconds,
    )

    payload = snapshot["payload"]
    ui_spec = payload["uiSpec"]
    nodes = list(walk_nodes(ui_spec["layout"]))
    node_types = {node["type"] for node in nodes}

    assert snapshot["type"] == "UI_UPDATED"
    assert payload["projection"]["runId"] == projection["runId"] == ui_spec["runId"]
    assert ui_spec["stateVersion"] == payload["projection"]["stateVersion"]
    assert isinstance(ui_spec["reason"], str) and ui_spec["reason"].strip()
    assert node_types <= REGISTRY_TYPES
    assert nodes[0]["type"] == "page"
    if token:
        verify_websocket_snapshot(base_url, projection["runId"], token)

    return {
        "gate": "H20/G5",
        "runId": projection["runId"],
        "stateVersion": ui_spec["stateVersion"],
        "generatedBy": ui_spec["generatedBy"],
        "reason": ui_spec["reason"],
        "nodeTypes": sorted(node_types),
        "contractSafe": True,
        "websocketSnapshot": "passed" if token else "not-requested",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--expected-generator",
        choices=("deterministic", "llm", "any"),
        default="deterministic",
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--token")
    args = parser.parse_args()
    print(
        json.dumps(
            run_smoke(
                args.base_url,
                expected_generator=args.expected_generator,
                timeout_seconds=args.timeout,
                token=args.token,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
