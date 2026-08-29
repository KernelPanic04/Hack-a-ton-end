from unittest.mock import patch
import unittest

from app.core.database import _env_flag, _to_asyncpg_url


class DatabaseConfigTests(unittest.TestCase):
    def test_sql_echo_defaults_to_disabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_env_flag("SQL_ECHO"))

    def test_boolean_environment_flag_is_explicit(self) -> None:
        for enabled in ("1", "true", "YES", "on"):
            with self.subTest(enabled=enabled), patch.dict(
                "os.environ", {"SQL_ECHO": enabled}, clear=True
            ):
                self.assertTrue(_env_flag("SQL_ECHO"))

        with patch.dict("os.environ", {"SQL_ECHO": "false"}, clear=True):
            self.assertFalse(_env_flag("SQL_ECHO"))

    def test_railway_postgres_url_uses_async_driver(self) -> None:
        self.assertEqual(
            _to_asyncpg_url("postgresql://user:pass@db:5432/runtime"),
            "postgresql+asyncpg://user:pass@db:5432/runtime",
        )
