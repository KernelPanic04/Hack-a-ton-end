import unittest

from app.synthesis.benchmark import _output_text


class BenchmarkResponseTests(unittest.TestCase):
    def test_extracts_response_text_from_a_message(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": '{"reason":"ok"}'},
                    ]
                }
            ]
        }
        self.assertEqual(_output_text(response), '{"reason":"ok"}')

    def test_rejects_response_without_text_content(self) -> None:
        with self.assertRaises(ValueError):
            _output_text({"output": []})
