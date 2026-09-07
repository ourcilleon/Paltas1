"""Lógica de negocio independiente de la interfaz CLI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from automation.config import Settings
from automation.errors import ExternalOperationError

logger = logging.getLogger(__name__)


class TextDestination(Protocol):
    """Puerto reemplazable por archivos, APIs, correo o Telegram."""

    def send(self, content: str, *, dry_run: bool) -> str:
        """Entrega contenido o describe lo que haría en modo simulación."""


@dataclass(slots=True)
class FileDestination:
    """Adaptador de ejemplo que escribe texto en un archivo."""

    path: Path

    def send(self, content: str, *, dry_run: bool) -> str:
        if dry_run:
            return f"Se escribirían {len(content)} caracteres en {self.path}"

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(content + "\n", encoding="utf-8")
        except OSError as exc:
            raise ExternalOperationError(f"No se pudo escribir {self.path}: {exc}") from exc
        return f"Resultado escrito en {self.path}"


@dataclass(frozen=True, slots=True)
class AutomationResult:
    message: str
    dry_run: bool


class AutomationService:
    """Orquesta la lógica; no conoce argumentos de terminal."""

    def __init__(self, settings: Settings, destination: TextDestination) -> None:
        self.settings = settings
        self.destination = destination

    def run(self, name: str, *, dry_run: bool = False) -> AutomationResult:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("El nombre no puede estar vacío")

        logger.info(
            "Iniciando automatización",
            extra={"app_env": self.settings.app_env, "dry_run": dry_run},
        )
        content = f"Hola, {normalized_name}. Automatización ejecutada en {self.settings.app_env}."
        message = self.destination.send(content, dry_run=dry_run)
        logger.info(message)
        return AutomationResult(message=message, dry_run=dry_run)
