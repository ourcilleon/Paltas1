"""Punto de entrada de línea de comandos."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from automation.config import Settings
from automation.errors import AutomationError
from automation.logging_config import configure_logging
from automation.service import AutomationService, FileDestination

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="automation",
        description="Ejecuta una automatización de ejemplo extensible.",
    )
    parser.add_argument("--name", required=True, help="Nombre usado por la tarea de ejemplo.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra lo que ocurriría sin producir efectos externos.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Archivo de entorno (por defecto: .env).",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = Settings.from_env(args.env_file)
        configure_logging(settings.log_level)
        destination = FileDestination(settings.output_dir / "result.txt")
        result = AutomationService(settings, destination).run(args.name, dry_run=args.dry_run)
        print(result.message)
        return 0
    except (AutomationError, ValueError) as exc:
        logger.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        logger.warning("Ejecución cancelada por el usuario")
        return 130
    except Exception:
        logger.exception("Error inesperado durante la automatización")
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
