"""Run with backend Python: python -m unittest discover -s scripts/tests."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    "commerce_demo", Path(__file__).parents[1] / "commerce-demo.py"
)


class DemoSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_rejects_production_and_missing_explicit_database(self):
        for env in (
            {},
            {
                "APP_ENV": "production",
                "TEST_DATABASE_URL": "postgresql+psycopg://localhost/test",
            },
        ):
            with self.assertRaises(ValueError):
                self.module.configuration(env)

    def test_unique_owned_schema_and_safe_password(self):
        a = self.module.configuration(
            {
                "APP_ENV": "test",
                "TEST_DATABASE_URL": "postgresql+psycopg://localhost/test",
            }
        )
        b = self.module.configuration(
            {
                "APP_ENV": "test",
                "TEST_DATABASE_URL": "postgresql+psycopg://localhost/test",
            }
        )
        self.assertRegex(a["schema"], r"^commerce_demo_[0-9a-f]{32}$")
        self.assertNotEqual(a["schema"], b["schema"])
        self.assertGreaterEqual(len(a["password"]), 32)
        self.assertNotEqual(a["password"], b["password"])

    def test_nonpostgres_and_nested_search_path_rejected(self):
        for url in (
            "sqlite:///test",
            "postgresql+psycopg://localhost/test?options=-c%20search_path%3Dpublic",
        ):
            with self.assertRaises(ValueError):
                self.module.configuration({"APP_ENV": "test", "TEST_DATABASE_URL": url})

    def test_http_204_logout_has_no_json(self):
        response = MagicMock()
        response.status = 204
        response.__enter__.return_value = response
        with patch.object(self.module.urllib.request, "urlopen", return_value=response):
            self.assertIsNone(
                self.module.request("http://127.0.0.1:1", "/auth/logout", "fictional", {})
            )

    def test_interrupted_acceptance_overwrites_stale_success_and_exits_nonzero(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "results.json"
            result.write_text('{"status":"PASSED"}')
            env = {
                "APP_ENV": "test",
                "TEST_DATABASE_URL": "postgresql+psycopg://localhost/test",
            }
            with (
                patch.dict(self.module.os.environ, env),
                patch.object(
                    self.module.sys,
                    "argv",
                    ["demo", "--scenario", "purchase", "--evidence-dir", directory],
                ),
                patch.object(self.module, "run_scenario", side_effect=KeyboardInterrupt),
                self.assertRaises(SystemExit) as stopped,
            ):
                self.module.main()
            self.assertEqual(stopped.exception.code, 130)
            self.assertEqual(json.loads(result.read_text())["status"], "INTERRUPTED")
