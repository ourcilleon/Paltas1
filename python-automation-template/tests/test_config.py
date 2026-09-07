import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.config import Settings
from automation.errors import ConfigurationError


class SettingsTests(unittest.TestCase):
    def test_loads_values_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "APP_ENV=test\nLOG_LEVEL=DEBUG\nOUTPUT_DIR=tmp/results\n"
                "REQUEST_TIMEOUT_SECONDS=4.5\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.output_dir, Path("tmp/results"))
        self.assertEqual(settings.request_timeout_seconds, 4.5)

    def test_exported_environment_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
            with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.log_level, "ERROR")

    def test_rejects_invalid_timeout(self) -> None:
        with patch.dict(os.environ, {"REQUEST_TIMEOUT_SECONDS": "never"}, clear=True):
            with self.assertRaises(ConfigurationError):
                Settings.from_env(None)


if __name__ == "__main__":
    unittest.main()
