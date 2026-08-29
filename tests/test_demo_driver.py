from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import UUID

from app.demo.driver import DemoDriver
from app.demo.fixture import SCRIPTED_EVENTS
from app.demo.provider import MockProvider
from app.runtime.status import StoredRunStatus


class DemoProviderAndDriverTests(unittest.IsolatedAsyncioTestCase):
    def test_mock_provider_contains_the_five_scripted_golden_path_events(self) -> None:
        provider = MockProvider()
        self.assertEqual(provider.event_count(), 5)
        self.assertEqual(
            [provider.event_at(index)["step_id"] for index in range(provider.event_count())],
            [event["step_id"] for event in SCRIPTED_EVENTS],
        )
        anomaly = provider.event_for_step("transshipment_anomaly")
        self.assertEqual(anomaly["data"]["delay_days"], 9)
        self.assertIn("pending_decision", anomaly)

    def test_mock_provider_changes_follow_up_data_for_each_accepted_action(self) -> None:
        provider = MockProvider()

        alternative = provider.event_for_step("route_resolution", "act_find_alternative")
        accepted_delay = provider.event_for_step("route_resolution", "act_accept_delay")

        self.assertEqual(alternative["data"]["recovered_days"], 6)
        self.assertEqual(accepted_delay["data"]["recovered_days"], 0)
        self.assertEqual(
            provider.event_for_step("delivery_eta", "act_accept_delay")["data"]["final_eta"],
            "2026-09-21",
        )

    async def test_driver_advances_the_current_step_with_its_scripted_event(self) -> None:
        run_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        run = SimpleNamespace(
            id=run_id,
            status=StoredRunStatus.RUNNING.value,
            current_step_id="booking_received",
        )
        driver = DemoDriver(session=None)  # type: ignore[arg-type]
        driver.run_engine.get_run = AsyncMock(return_value=run)  # type: ignore[method-assign]
        driver.run_engine.advance = AsyncMock(return_value=run)  # type: ignore[method-assign]

        result = await driver.advance(run_id)

        self.assertIs(result, run)
        event = SCRIPTED_EVENTS[0]
        driver.run_engine.advance.assert_awaited_once_with(
            run_id,
            event["step_id"],
            event["data"],
            event["verdict"],
            pending_decision=None,
        )

    async def test_driver_uses_the_action_saved_by_the_runtime(self) -> None:
        run_id = UUID("550e8400-e29b-41d4-a716-446655440000")
        run = SimpleNamespace(
            id=run_id,
            status=StoredRunStatus.RUNNING.value,
            current_step_id="route_resolution",
            state={"last_decision": {"action_id": "act_accept_delay"}},
        )
        driver = DemoDriver(session=None)  # type: ignore[arg-type]
        driver.run_engine.get_run = AsyncMock(return_value=run)  # type: ignore[method-assign]
        driver.run_engine.advance = AsyncMock(return_value=run)  # type: ignore[method-assign]

        await driver.advance(run_id)

        driver.run_engine.advance.assert_awaited_once_with(
            run_id,
            "route_resolution",
            {"chosen_action": "accept_delay", "recovered_days": 0},
            "attention",
            pending_decision=None,
        )


if __name__ == "__main__":
    unittest.main()
