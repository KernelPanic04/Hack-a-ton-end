import json
import unittest

from pydantic import ValidationError

from app.schemas.contracts import UISpec
from app.synthesis.llm_upgrade import (
    LLMUISpecUpgrade,
    merge_llm_upgrade,
    structured_output_format,
    validate_llm_upgrade,
)


def valid_spec() -> dict:
    return {
        "schemaVersion": "1",
        "runId": "run_example",
        "workflowId": "wf_example",
        "workflowVersion": 1,
        "stateVersion": 0,
        "generatedBy": "deterministic",
        "reason": "The current state is stable, so the layout emphasizes progress.",
        "allowedActions": [
            {
                "actionId": "act_review",
                "label": "Review",
                "risk": "medium",
                "requiresHuman": True,
                "payloadSchema": {},
            }
        ],
        "layout": {
            "id": "ui_root",
            "type": "page",
            "props": {"title": "Run overview", "subtitle": None, "eyebrow": None},
            "children": [
                {
                    "id": "ui_progress",
                    "type": "section",
                    "props": {
                        "title": "Progress",
                        "description": None,
                        "columns": 2,
                        "emphasis": "normal",
                    },
                    "children": [
                        {
                            "id": "ui_metric",
                            "type": "metric",
                            "props": {
                                "label": "Completion",
                                "value": 50,
                                "supportingText": None,
                                "trend": "flat",
                                "emphasis": "normal",
                            },
                        },
                        {
                            "id": "ui_decision",
                            "type": "decisionPanel",
                            "props": {
                                "decisionId": "dec_review",
                                "title": "Review required",
                                "message": None,
                                "actions": [{"actionId": "act_review", "label": "Review"}],
                                "status": "idle",
                                "errorMessage": None,
                                "emphasis": "warning",
                            },
                        },
                    ],
                }
            ],
        },
    }


class UISpecContractTests(unittest.TestCase):
    def test_valid_spec_is_accepted(self):
        spec = UISpec.model_validate(valid_spec())
        self.assertEqual(spec.layout.type, "page")

    def test_unknown_component_is_rejected(self):
        payload = valid_spec()
        payload["layout"]["children"][0]["children"][0]["type"] = "unregistered"
        with self.assertRaises(ValidationError):
            UISpec.model_validate(payload)

    def test_unknown_props_are_rejected(self):
        payload = valid_spec()
        payload["layout"]["props"]["extra"] = "not allowed"
        with self.assertRaises(ValidationError):
            UISpec.model_validate(payload)

    def test_decision_action_must_be_permitted(self):
        payload = valid_spec()
        action = payload["layout"]["children"][0]["children"][1]["props"]["actions"][0]
        action["actionId"] = "act_other"
        with self.assertRaises(ValidationError):
            UISpec.model_validate(payload)

    def test_rejected_decision_needs_message(self):
        payload = valid_spec()
        panel = payload["layout"]["children"][0]["children"][1]["props"]
        panel["status"] = "rejected"
        with self.assertRaises(ValidationError):
            UISpec.model_validate(payload)

    def test_llm_upgrade_cannot_supply_backend_metadata(self):
        upgrade = validate_llm_upgrade(
            json.dumps(
                {
                    "reason": "A concise hierarchy improves scanability.",
                    "layout": valid_spec()["layout"],
                }
            )
        )
        merged = merge_llm_upgrade(UISpec.model_validate(valid_spec()), upgrade)
        self.assertEqual(merged.generated_by, "llm")
        self.assertEqual(merged.allowed_actions[0].action_id, "act_review")

    def test_strict_schema_forbids_unknown_object_properties(self):
        schema = structured_output_format()["schema"]
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), {"reason", "layout"})

        def objects(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    yield value
                for child in value.values():
                    yield from objects(child)
            elif isinstance(value, list):
                for child in value:
                    yield from objects(child)

        for object_schema in objects(schema):
            self.assertEqual(object_schema["additionalProperties"], False)
            self.assertEqual(
                set(object_schema.get("required", [])),
                set(object_schema.get("properties", {})),
            )

        def has_default(value):
            if isinstance(value, dict):
                return "default" in value or any(has_default(child) for child in value.values())
            if isinstance(value, list):
                return any(has_default(child) for child in value)
            return False

        self.assertFalse(has_default(schema))

        def has_one_of(value):
            if isinstance(value, dict):
                return "oneOf" in value or any(has_one_of(child) for child in value.values())
            if isinstance(value, list):
                return any(has_one_of(child) for child in value)
            return False

        self.assertFalse(has_one_of(schema))


if __name__ == "__main__":
    unittest.main()
