import tempfile
import unittest
from pathlib import Path

from automation.config import Settings
from automation.service import AutomationService, FileDestination


class AutomationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            app_env="test",
            log_level="INFO",
            output_dir=Path("unused"),
            request_timeout_seconds=1,
        )

    def test_dry_run_does_not_write_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            result = AutomationService(
                self.settings, FileDestination(output)
            ).run("Ada", dry_run=True)

            self.assertTrue(result.dry_run)
            self.assertFalse(output.exists())
            self.assertIn("Se escribirían", result.message)

    def test_real_run_writes_expected_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            result = AutomationService(
                self.settings, FileDestination(output)
            ).run("Ada")

            self.assertFalse(result.dry_run)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "Hola, Ada. Automatización ejecutada en test.\n",
            )

    def test_rejects_empty_name(self) -> None:
        service = AutomationService(self.settings, FileDestination(Path("unused")))
        with self.assertRaises(ValueError):
            service.run("   ", dry_run=True)


if __name__ == "__main__":
    unittest.main()
