import unittest
from uuid import UUID

from fastapi import HTTPException

from main import _run_uuid, app


class HttpRoutesTests(unittest.TestCase):
    def test_runtime_endpoints_are_registered_without_websocket_routes(self) -> None:
        routes = {(route.path, frozenset(route.methods or [])) for route in app.routes}
        self.assertIn(("/runs", frozenset({"POST"})), routes)
        self.assertIn(("/demo/advance", frozenset({"POST"})), routes)
        self.assertIn(("/runs/{run_id}/projection", frozenset({"GET"})), routes)
        self.assertIn(("/runs/{run_id}/events", frozenset({"GET"})), routes)

    def test_run_id_parser_accepts_wire_and_raw_uuid(self) -> None:
        value = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(_run_uuid(f"run_{value}"), UUID(value))
        self.assertEqual(_run_uuid(value), UUID(value))

    def test_run_id_parser_rejects_invalid_id_as_client_error(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _run_uuid("run_not-a-uuid")
        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
