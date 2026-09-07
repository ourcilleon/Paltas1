import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.cli import run


class CliTests(unittest.TestCase):
    def test_dry_run_returns_success_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".env"
            output_dir = root / "output"
            env_file.write_text(f"OUTPUT_DIR={output_dir}\nLOG_LEVEL=CRITICAL\n", encoding="utf-8")

            with patch("builtins.print") as print_mock:
                exit_code = run(["--name", "Grace", "--dry-run", "--env-file", str(env_file)])

            self.assertEqual(exit_code, 0)
            self.assertFalse((output_dir / "result.txt").exists())
            self.assertIn("Se escribirían", print_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
