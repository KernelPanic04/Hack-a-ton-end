"""In-memory, per-run WebSocket fan-out used by the demo runtime."""

from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.schemas.contracts import ServerEnvelope


class RunWebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[run_id].add(websocket)

    def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        connections = self._connections.get(run_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(run_id, None)

    async def publish(self, envelope: ServerEnvelope) -> None:
        stale: list[WebSocket] = []
        for websocket in tuple(self._connections.get(envelope.run_id, ())):
            try:
                await websocket.send_json(envelope.model_dump(mode="json"))
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(envelope.run_id, websocket)
