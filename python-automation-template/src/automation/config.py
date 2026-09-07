"""Carga y validación de configuración desde el entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from automation.errors import ConfigurationError

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def load_dotenv(path: Path) -> None:
    """Carga un archivo .env sin reemplazar variables ya exportadas."""
    if not path.exists():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Línea {line_number} inválida en {path}")

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigurationError(f"Clave vacía en la línea {line_number} de {path}")
        os.environ.setdefault(key, value.strip().strip("\"'"))


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuración validada de la automatización."""

    app_env: str
    log_level: str
    output_dir: Path
    request_timeout_seconds: float

    @classmethod
    def from_env(cls, env_file: Path | None = Path(".env")) -> "Settings":
        if env_file is not None:
            load_dotenv(env_file)

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"LOG_LEVEL debe ser uno de: {', '.join(sorted(VALID_LOG_LEVELS))}"
            )

        try:
            timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise ConfigurationError("REQUEST_TIMEOUT_SECONDS debe ser numérico") from exc
        if timeout <= 0:
            raise ConfigurationError("REQUEST_TIMEOUT_SECONDS debe ser mayor que cero")

        output_dir = Path(os.getenv("OUTPUT_DIR", "output")).expanduser()
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=log_level,
            output_dir=output_dir,
            request_timeout_seconds=timeout,
        )
