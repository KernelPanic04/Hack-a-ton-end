from pathlib import Path
import re
import unittest


class SynthesisHonestyTests(unittest.TestCase):
    def test_synthesis_has_no_domain_specific_shortcuts(self) -> None:
        synthesis_dir = Path(__file__).parents[1] / "app" / "synthesis"
        forbidden = re.compile(r"\b(?:booking|vessel|bol)\b", re.IGNORECASE)
        violations: list[str] = []

        for source in synthesis_dir.glob("*.py"):
            for line_number, line in enumerate(source.read_text().splitlines(), start=1):
                if forbidden.search(line):
                    violations.append(f"{source.name}:{line_number}")

        self.assertEqual(violations, [])
