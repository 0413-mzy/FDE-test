"""Closed local DB inspection safety; actual PostgreSQL acceptance is separate."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "commerce_db", Path(__file__).parents[1] / "commerce-db.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DatabaseInspectionSafety(unittest.TestCase):
    def test_invalid_sql_identifiers_uuid_and_limits_fail_before_connection(self):
        for argv in [
            ["--rows", "commerce_orders;DROP TABLE commerce_orders"],
            ["--rows", "schema.commerce_orders"],
            ["--rows", "commerce_orders", "--limit", "0"],
            ["--rows", "commerce_orders", "--limit", "101"],
            ["--history", "commerce_orders", "--id", "not-a-uuid"],
            ["--rows", "commerce_orders", "--id", "00000000-0000-0000-0000-000000000000"],
        ]:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with patch.object(MODULE, "create_engine") as engine:
                    with self.assertRaises(SystemExit):
                        MODULE.main(argv)
                    engine.assert_not_called()

    def test_nested_credentials_are_removed_without_hiding_sku_code(self):
        result = MODULE.safe_rows(
            [
                {
                    "username": "fictional",
                    "password_hash": "never-show-hash",
                    "before_data": {"token_digest": "never-show-token", "sku_code": "SKU-L"},
                    "after_data": {
                        "nested": [{"current_password": "never-show-password", "quantity": 2}]
                    },
                }
            ]
        )
        self.assertNotIn("never-show", repr(result))
        self.assertEqual(result[0]["before_data"]["sku_code"], "SKU-L")
        self.assertEqual(result[0]["after_data"]["nested"][0]["quantity"], 2)

    def test_export_is_private_and_cannot_replace_an_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.csv"
            MODULE.export_csv(path, [{"id": 1, "after_data": {"quantity": 2}}])
            original = path.read_bytes()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                MODULE.export_csv(path, [{"id": 99}])
            self.assertEqual(path.read_bytes(), original)

    def test_connection_failure_does_not_print_credentials_or_url(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(
                MODULE, "configuration", return_value="postgresql://name:ultra-secret@host/db"
            ),
            patch.object(
                MODULE,
                "create_engine",
                side_effect=RuntimeError("postgresql://name:ultra-secret@host/db"),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(MODULE.main(["--tables"]), 1)
        self.assertNotIn("ultra-secret", stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("postgresql://", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
