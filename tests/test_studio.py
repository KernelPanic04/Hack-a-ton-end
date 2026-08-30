import json
import unittest
from unittest.mock import Mock

from app.studio.llm import StudioUIGenerator
from app.studio.schema import StudioUISpec


def response(payload: dict) -> dict:
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}


VALID_LAYOUT = {
    "reason": "Dos botones lado a lado.",
    "layout": {
        "id": "ui_page",
        "type": "page",
        "props": {"title": "Botones"},
        "children": [
            {
                "id": "ui_row",
                "type": "section",
                "props": {
                    "direction": "row",
                    "gap": "md",
                    "align": "center",
                    "justify": "start",
                    "columns": 1,
                    "emphasis": "normal",
                },
                "children": [
                    {
                        "id": "ui_btn_1",
                        "type": "button",
                        "props": {"label": "Guardar", "variant": "primary", "size": "md"},
                    },
                    {
                        "id": "ui_btn_2",
                        "type": "button",
                        "props": {"label": "Cancelar", "variant": "secondary", "size": "md"},
                    },
                ],
            }
        ],
    },
}


class StudioUIGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_a_row_layout_with_two_buttons(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )

        spec = await generator.generate("crea dos botones, uno al lado del otro")

        self.assertEqual(spec.generated_by, "llm")
        section = spec.layout.children[0]
        self.assertEqual(section.type, "section")
        self.assertEqual(section.props.direction, "row")
        self.assertEqual([child.type for child in section.children], ["button", "button"])
        StudioUISpec.model_validate(spec.model_dump(mode="json"))

    async def test_disabled_returns_blank_fallback(self) -> None:
        generator = StudioUIGenerator(api_key="")

        self.assertFalse(generator.enabled)
        spec = await generator.generate("crea dos botones")

        self.assertEqual(spec.generated_by, "fallback")
        self.assertIn("deshabilitada", spec.reason)

    async def test_exhausted_retries_return_blank_fallback_with_real_error(self) -> None:
        request_response = Mock(return_value={"output": []})  # always invalid
        generator = StudioUIGenerator(
            api_key="test-key", enabled=True, retries=2, request_response=request_response
        )

        spec = await generator.generate("crea dos botones")

        self.assertEqual(request_response.call_count, 3)
        self.assertEqual(spec.generated_by, "fallback")
        self.assertIn("3 intentos", spec.reason)
        self.assertIn("no output_text content", spec.reason)

    async def test_no_run_or_workflow_metadata_is_required(self) -> None:
        generator = StudioUIGenerator(
            api_key="test-key",
            enabled=True,
            request_response=lambda *_args: response(VALID_LAYOUT),
        )

        spec = await generator.generate("crea dos botones")

        dumped = spec.model_dump(mode="json", by_alias=True)
        for field in ("runId", "workflowId", "workflowVersion", "stateVersion", "allowedActions"):
            self.assertNotIn(field, dumped)


if __name__ == "__main__":
    unittest.main()
