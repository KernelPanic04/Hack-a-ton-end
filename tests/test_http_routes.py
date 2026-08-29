import unittest
from uuid import UUID

from fastapi import HTTPException

from main import WorkflowVersionCreateRequest, _run_uuid, app


class HttpRoutesTests(unittest.TestCase):
    def test_runtime_http_and_websocket_routes_are_registered(self) -> None:
        routes = {
            (route.path, frozenset(getattr(route, "methods", []) or []))
            for route in app.routes
        }
        self.assertIn(("/runs", frozenset({"POST"})), routes)
        self.assertIn(("/workflows/{workflow_id}/versions", frozenset({"POST"})), routes)
        self.assertIn(("/demo/skeleton", frozenset({"POST"})), routes)
        self.assertIn(("/demo/advance", frozenset({"POST"})), routes)
        self.assertIn(("/runs/{run_id}/projection", frozenset({"GET"})), routes)
        self.assertIn(("/runs/{run_id}/snapshot", frozenset({"GET"})), routes)
        self.assertIn(("/runs/{run_id}/events", frozenset({"GET"})), routes)
        self.assertTrue(any(route.path == "/ws/runs/{run_id}" for route in app.routes))

    def test_run_id_parser_accepts_wire_and_raw_uuid(self) -> None:
        value = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(_run_uuid(f"run_{value}"), UUID(value))
        self.assertEqual(_run_uuid(value), UUID(value))

    def test_run_id_parser_rejects_invalid_id_as_client_error(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _run_uuid("run_not-a-uuid")
        self.assertEqual(raised.exception.status_code, 422)

    def test_workflow_version_request_accepts_a_camel_case_base_version(self) -> None:
        request = WorkflowVersionCreateRequest.model_validate(
            {
                "baseVersion": 1,
                "steps": [
                    {
                        "id": "unseen_runtime_audit",
                        "type": "generic.runtime",
                        "title": "Unseen runtime audit",
                        "objective": "Inspect a prior value.",
                        "inputs": ["previous.data.value"],
                        "requiresHumanReview": True,
                    }
                ],
            }
        )

        self.assertEqual(request.base_version, 1)
        self.assertTrue(request.steps[0].requires_human_review)


if __name__ == "__main__":
    unittest.main()
