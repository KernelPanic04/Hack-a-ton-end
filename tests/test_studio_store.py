import unittest
import uuid

from app.studio.schema import StudioPageNode
from app.studio.store import StoredMessage, _ids_to_prune, _latest_layout, _to_history


LAYOUT_A = {
    "id": "ui_page",
    "type": "page",
    "props": {"title": "A"},
    "children": [{"id": "ui_text_a", "type": "text", "props": {"content": "A"}}],
}
LAYOUT_B = {
    "id": "ui_page",
    "type": "page",
    "props": {"title": "B"},
    "children": [{"id": "ui_text_b", "type": "text", "props": {"content": "B"}}],
}


def row(role: str, content: str, layout: dict | None = None) -> StoredMessage:
    return StoredMessage(id=uuid.uuid4(), role=role, content=content, layout=layout)


class ToHistoryTests(unittest.TestCase):
    def test_preserves_oldest_first_order_and_role(self) -> None:
        rows = [row("user", "crea dos botones"), row("assistant", "Listo.")]

        history = _to_history(rows)

        self.assertEqual([m.role for m in history], ["user", "assistant"])
        self.assertEqual(history[0].content, "crea dos botones")


class LatestLayoutTests(unittest.TestCase):
    def test_returns_none_when_no_assistant_turn_has_a_layout(self) -> None:
        rows = [row("user", "crea dos botones")]
        self.assertIsNone(_latest_layout(rows))

    def test_returns_the_most_recent_layout(self) -> None:
        rows = [
            row("user", "crea dos botones"),
            row("assistant", "Listo.", LAYOUT_A),
            row("user", "ahora ponlos verticales"),
            row("assistant", "Hecho.", LAYOUT_B),
        ]

        latest = _latest_layout(rows)

        self.assertIsInstance(latest, StudioPageNode)
        self.assertEqual(latest.props.title, "B")

    def test_skips_a_trailing_blank_fallback_turn(self) -> None:
        rows = [
            row("user", "crea dos botones"),
            row("assistant", "Listo.", LAYOUT_A),
            row("user", "algo que rompe al proveedor"),
            row("assistant", "No se pudo generar la interfaz.", None),
        ]

        latest = _latest_layout(rows)

        self.assertIsNotNone(latest)
        self.assertEqual(latest.props.title, "A")


class IdsToPruneTests(unittest.TestCase):
    def test_no_pruning_needed_under_the_cap(self) -> None:
        rows = [row("user", "a"), row("assistant", "b")]
        self.assertEqual(_ids_to_prune(rows, keep=20), [])

    def test_prunes_the_oldest_rows_beyond_the_cap(self) -> None:
        rows = [row("user", f"turn {i}") for i in range(5)]

        stale = _ids_to_prune(rows, keep=2)

        self.assertEqual(stale, [rows[0].id, rows[1].id, rows[2].id])

    def test_keep_zero_prunes_everything(self) -> None:
        rows = [row("user", "a"), row("assistant", "b")]
        self.assertEqual(_ids_to_prune(rows, keep=0), [rows[0].id, rows[1].id])


if __name__ == "__main__":
    unittest.main()
