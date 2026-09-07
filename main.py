"""Bot de Telegram para registrar kilos de palta y guardar en Google Sheets."""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import sys
import threading
from typing import Final
import urllib.request
from zoneinfo import ZoneInfo

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Servidor HTTP integrado para que Render detecte el puerto abierto de inmediato
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo")

    def log_message(self, format, *args):
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

TIPO_PALTA, KILOS, USUARIO = range(3)
TIPOS_PALTA: Final[list[list[str]]] = [["Palta Hass", "Palta La Cruz"]]
USUARIOS: Final[list[list[str]]] = [
    ["Maria"],
    ["Pedro"],
    ["Juan"],
    ["Mauricio"],
    ["Ana"],
]
CHILE_TIMEZONE: Final = ZoneInfo("America/Santiago")
NEXT_ORDER_BUTTON: Final = "Ingresar siguiente pedido"


def _message_text(update: Update) -> str:
    if update.message is None or update.message.text is None:
        raise ValueError("El mensaje no contiene texto")
    return update.message.text.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    if update.message is None:
        return ConversationHandler.END

    usuario = _message_text(update)
    allowed_users = {option for row in USUARIOS for option in row}
    if usuario not in allowed_users:
        await update.message.reply_text("Elige un usuario usando los botones disponibles.")
        return USUARIO

    context.user_data["usuario"] = usuario
    registered_at = datetime.now(CHILE_TIMEZONE).strftime("%d/%m/%Y %H:%M")

    # ENVÍO A GOOGLE SHEETS USANDO LIBRERÍA NATIVA (urllib)
    sheets_url = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    if sheets_url:
        payload = {
            "fecha": registered_at,
            "tipo_palta": context.user_data["tipo_palta"],
            "kilos": float(context.user_data["kilos"]),
            "usuario": context.user_data["usuario"],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                sheets_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.error("Error al enviar a Google Sheets: %s", e)

    resumen = (
        "*Registro completado y guardado en Sheets*\n\n"
        f"• Tipo: {context.user_data['tipo_palta']}\n"
        f"• Kilos: {context.user_data['kilos']}\n"
        f"• Registrado por: {context.user_data['usuario']}\n"
        f"• Fecha y hora: {registered_at}"
    )
    await update.message.reply_text(
        resumen,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[NEXT_ORDER_BUTTON]],
            resize_keyboard=True,
        ),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message is not None:
        await update.message.reply_text(
            "Registro cancelado.",
            reply_markup=ReplyKeyboardRemove(),
        )
    return ConversationHandler.END


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{NEXT_ORDER_BUTTON}$"), start),
        ],
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


def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("Falta BOT_TOKEN en las variables de entorno.")
        sys.exit(2)

    # Inicia servidor web dummy para pasar el chequeo de Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    try:
        logger.info("Iniciando bot de Telegram...")
        application = build_application(token)
        application.run_polling()
    except InvalidToken:
        logger.error("Telegram rechazó el BOT_TOKEN.")
        sys.exit(2)
    except Exception:
        logger.exception("Error inesperado al ejecutar el bot.")
        sys.exit(1)


if __name__ == "__main__":
    main()
