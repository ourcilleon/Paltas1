"""Bot de Telegram para registrar kilos de palta.

La lógica del flujo está separada de la configuración y el proceso de arranque
para que pueda reutilizarse o reemplazarse por otra interfaz en el futuro.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Final, Sequence

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from automation.config import Settings
from automation.errors import ConfigurationError
from automation.logging_config import configure_logging

logger = logging.getLogger(__name__)

TIPO_PALTA, KILOS, USUARIO = range(3)
TIPOS_PALTA: Final[list[list[str]]] = [["Palta 1", "Palta 2"]]
USUARIOS: Final[list[list[str]]] = [["Usuario 1"], ["Usuario 2"], ["Usuario 3"]]


def _message_text(update: Update) -> str:
    """Obtiene texto de un mensaje y falla claramente si no existe."""
    if update.message is None or update.message.text is None:
        raise ValueError("El mensaje no contiene texto")
    return update.message.text.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el registro de una nueva carga."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "1. Elige el tipo de palta que quieres ingresar:",
        reply_markup=ReplyKeyboardMarkup(
            TIPOS_PALTA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return TIPO_PALTA


async def tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el tipo de palta seleccionado."""
    if update.message is None:
        return ConversationHandler.END

    tipo_palta = _message_text(update)
    if tipo_palta not in {option for row in TIPOS_PALTA for option in row}:
        await update.message.reply_text("Elige una opción usando los botones disponibles.")
        return TIPO_PALTA

    context.user_data["tipo_palta"] = tipo_palta
    await update.message.reply_text(
        "2. Ingresa los kilos:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return KILOS


async def kilos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Valida y guarda la cantidad de kilos."""
    if update.message is None:
        return ConversationHandler.END

    kilos_text = _message_text(update).replace(",", ".")
    try:
        kilos = float(kilos_text)
    except ValueError:
        await update.message.reply_text("Ingresa un número válido de kilos, por ejemplo: 12.5")
        return KILOS

    if kilos <= 0:
        await update.message.reply_text("Los kilos deben ser mayores que cero.")
        return KILOS

    context.user_data["kilos"] = kilos_text
    await update.message.reply_text(
        "3. ¿Quién está registrando esto?",
        reply_markup=ReplyKeyboardMarkup(
            USUARIOS, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return USUARIO


async def usuario_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Completa el registro y muestra un resumen."""
    if update.message is None:
        return ConversationHandler.END

    usuario = _message_text(update)
    allowed_users = {option for row in USUARIOS for option in row}
    if usuario not in allowed_users:
        await update.message.reply_text("Elige un usuario usando los botones disponibles.")
        return USUARIO

    context.user_data["usuario"] = usuario
    resumen = (
        "*Registro completado*\n\n"
        f"• Tipo: {context.user_data['tipo_palta']}\n"
        f"• Kilos: {context.user_data['kilos']}\n"
        f"• Registrado por: {context.user_data['usuario']}"
    )
    await update.message.reply_text(
        resumen,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela el registro en curso."""
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text(
            "Registro cancelado.",
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


def build_application(token: str) -> Application:
    """Construye la aplicación sin arrancar el polling."""
    application = Application.builder().token(token).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TIPO_PALTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, tipo_palta_chosen)
            ],
            KILOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, kilos_entered)],
            USUARIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, usuario_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conversation)
    return application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bot de Telegram para registrar kilos de palta.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Archivo de variables de entorno (por defecto: .env).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida la configuración sin iniciar el bot ni conectarse a Telegram.",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Valida configuración y arranca el bot cuando corresponde."""
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env(args.env_file)
        configure_logging(settings.log_level)
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ConfigurationError("Falta BOT_TOKEN en el entorno o en el archivo .env")

        application = build_application(token)
        if args.dry_run:
            logger.info("Configuración válida; no se inició el polling (--dry-run).")
            print("Configuración válida. El bot no se inició porque se usó --dry-run.")
            return 0

        logger.info("Iniciando bot de Telegram en entorno %s", settings.app_env)
        application.run_polling()
        return 0
    except (ConfigurationError, ValueError) as exc:
        logger.error("%s", exc)
        return 2
    except InvalidToken:
        logger.error("Telegram rechazó BOT_TOKEN. Genera un token nuevo en BotFather.")
        return 2
    except KeyboardInterrupt:
        logger.warning("Bot detenido por el usuario")
        return 130
    except Exception:
        logger.exception("Error inesperado al ejecutar el bot")
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()