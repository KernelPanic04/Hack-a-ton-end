import unittest
from datetime import datetime, timedelta, timezone

from app.studio.schema import StudioPageNode
from app.studio.store import StudioConversationStore


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

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


class StudioConversationStoreTests(unittest.TestCase):
    def test_each_conversation_keeps_its_own_independent_history(self) -> None:
        store = StudioConversationStore()
        chat_a = store.create_conversation()
        chat_b = store.create_conversation()

        store.append_message(chat_a, "user", "crea dos botones", now=NOW)
        store.append_message(chat_b, "user", "crea una tabla", now=NOW)

        self.assertEqual([m.content for m in store.get_history(chat_a, now=NOW)], ["crea dos botones"])
        self.assertEqual([m.content for m in store.get_history(chat_b, now=NOW)], ["crea una tabla"])

    def test_a_process_restart_clears_everything(self) -> None:
        store = StudioConversationStore()
        chat = store.create_conversation()
        store.append_message(chat, "user", "crea dos botones", now=NOW)

        restarted_store = StudioConversationStore()  # simulates the app restarting

        self.assertFalse(restarted_store.conversation_exists(chat))
        self.assertEqual(restarted_store.get_history(chat, now=NOW), [])

    def test_while_alive_history_survives_well_within_the_retention_window(self) -> None:
        store = StudioConversationStore()
        chat = store.create_conversation()
        store.append_message(chat, "user", "crea dos botones", now=NOW)

        almost_two_months_later = NOW + timedelta(days=59)
        history = store.get_history(chat, now=almost_two_months_later)

        self.assertEqual([m.content for m in history], ["crea dos botones"])

    def test_turns_older_than_two_months_age_out(self) -> None:
        store = StudioConversationStore()
        chat = store.create_conversation()
        store.append_message(chat, "user", "mensaje viejo", now=NOW)

        more_than_two_months_later = NOW + timedelta(days=61)
        store.append_message(chat, "user", "mensaje nuevo", now=more_than_two_months_later)
        history = store.get_history(chat, now=more_than_two_months_later)

        self.assertEqual([m.content for m in history], ["mensaje nuevo"])

    def test_get_last_layout_skips_a_trailing_blank_fallback(self) -> None:
        store = StudioConversationStore()
        chat = store.create_conversation()
        store.append_message(
            chat, "assistant", "Listo.", layout=StudioPageNode.model_validate(LAYOUT_A), now=NOW
        )
        store.append_message(chat, "assistant", "No se pudo generar.", layout=None, now=NOW)

        latest = store.get_last_layout(chat, now=NOW)

        self.assertIsNotNone(latest)
        self.assertEqual(latest.props.title, "A")

    def test_get_last_layout_returns_the_most_recent_one(self) -> None:
        store = StudioConversationStore()
        chat = store.create_conversation()
        store.append_message(
            chat, "assistant", "Listo.", layout=StudioPageNode.model_validate(LAYOUT_A), now=NOW
        )
        store.append_message(
            chat, "assistant", "Hecho.", layout=StudioPageNode.model_validate(LAYOUT_B), now=NOW
        )

        latest = store.get_last_layout(chat, now=NOW)

        self.assertEqual(latest.props.title, "B")

    def test_history_is_capped_independently_of_retention(self) -> None:
        store = StudioConversationStore(max_history=3)
        chat = store.create_conversation()
        for i in range(5):
            store.append_message(chat, "user", f"turno {i}", now=NOW)

        history = store.get_history(chat, now=NOW)

        self.assertEqual([m.content for m in history], ["turno 2", "turno 3", "turno 4"])

    def test_conversation_exists_is_false_for_an_unknown_id(self) -> None:
        import uuid

        store = StudioConversationStore()
        self.assertFalse(store.conversation_exists(uuid.uuid4()))


if __name__ == "__main__":
    unittest.main()
