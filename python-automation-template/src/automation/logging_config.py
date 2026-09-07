"""Configuración centralizada de logging."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
    # httpx incluye URLs completas en INFO; las peticiones de Telegram pueden
    # contener el token del bot en la ruta y nunca deben aparecer en logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
