"""Bot de Telegram para el registro de Entrada y Salida de Paltas."""

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

# Servidor HTTP en segundo plano para Render
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot de Paltas Activo")

    def log_message(self, format, *args):
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# Definición de Estados de la Conversación
(
    FLUJO_TIPO,
    CANTIDAD,
    PROVEEDOR,
    ORIGEN,
    FORMATO,
    CAJAS_OBTENIDAS,
    KILOS_BRUTOS,
    TARA,
) = range(8)

# Teclados y Opciones
OPCIONES_MENU: Final = [["Entrada"], ["Salida"]]
OPCIONES_SALIDA: Final = [
    ["Bandeja 10kg"],
    ["Bandeja 15kg"],
    ["Gamela 10kg"],
    ["Gamela 15kg"],
]
OPCIONES_PROVEEDORES: Final = [
    ["Proveedor 1"],
    ["Proveedor 2"],
    ["Proveedor 3"],
    ["Proveedor 4"],
    ["Proveedor 5"],
]
OPCIONES_ORIGEN: Final = [["Chile"], ["Perú"]]
OPCIONES_FORMATO: Final = [["Bean (Cajón)"], ["Pallet (Bandejas)"]]

CHILE_TIMEZONE: Final = ZoneInfo("America/Santiago")
NEXT_ORDER_BUTTON: Final = "Ingresar siguiente registro"


def _message_text(update: Update) -> str:
    if update.message is None or update.message.text is None:
        raise ValueError("El mensaje no contiene texto")
    return update.message.text.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el registro seleccionando el tipo de flujo."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "1. Selecciona el tipo de registro:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_MENU, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return FLUJO_TIPO


async def flujo_tipo_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa si es Entrada o Salida."""
    if update.message is None:
        return ConversationHandler.END

    opcion = _message_text(update)
    if opcion not in ["Entrada", "Salida"]:
        await update.message.reply_text("Por favor selecciona una opción válida usando los botones.")
        return FLUJO_TIPO

    context.user_data["tipo_flujo"] = opcion

    if opcion == "Entrada":
        await update.message.reply_text(
            "2. Ingrese Cantidad:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return CANTIDAD
    else:
        await update.message.reply_text(
            "2. Selecciona el formato de Salida:",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_SALIDA, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return CANTIDAD


async def cantidad_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la cantidad o la opción de Salida e ingresa a Proveedores."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["cantidad_o_formato_salida"] = _message_text(update)

    await update.message.reply_text(
        "3. Selecciona el Proveedor:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_PROVEEDORES, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return PROVEEDOR


async def proveedor_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la selección de proveedor e ingresa a Origen."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["proveedor"] = _message_text(update)

    await update.message.reply_text(
        "4. Selecciona el Origen:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_ORIGEN, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ORIGEN


async def origen_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa Origen e ingresa a Formato (tanto para Entrada como para Salida)."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["origen"] = _message_text(update)

    await update.message.reply_text(
        "5. Selecciona el Formato:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_FORMATO, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return FORMATO


async def formato_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa Formato e ingresa a Cajas Obtenidas."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["formato"] = _message_text(update)

    await update.message.reply_text(
        "6. Ingresar Cajas Obtenidas:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CAJAS_OBTENIDAS


async def cajas_obtenidas_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa Cajas Obtenidas e ingresa a Kilos Brutos."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["cajas_obtenidas"] = _message_text(update)

    await update.message.reply_text(
        "7. Ingresar Kilos Brutos:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return KILOS_BRUTOS


async def kilos_brutos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa Kilos Brutos e ingresa a Tara."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["kilos_brutos"] = _message_text(update)

    await update.message.reply_text(
        "8. Ingresar Tara:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TARA


async def tara_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la Tara y finaliza el registro."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data["tara"] = _message_text(update)
    return await finalizar_y_guardar(update, context)


async def finalizar_y_guardar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Genera el resumen, envía a Google Sheets y concluye el flujo."""
    registered_at = datetime.now(CHILE_TIMEZONE).strftime("%d/%m/%Y %H:%M")
    tipo = context.user_data.get("tipo_flujo", "")

    payload = {
        "fecha": registered_at,
        "tipo_flujo": tipo,
        "cantidad_o_salida": context.user_data.get("cantidad_o_formato_salida", ""),
        "proveedor": context.user_data.get("proveedor", ""),
        "origen": context.user_data.get("origen", ""),
        "formato": context.user_data.get("formato", ""),
        "cajas_obtenidas": context.user_data.get("cajas_obtenidas", ""),
        "kilos_brutos": context.user_data.get("kilos_brutos", ""),
        "tara": context.user_data.get("tara", ""),
    }

    # Envío mediante Webhook
    sheets_url = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    if sheets_url:
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                sheets_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
            logger.info("Datos del flujo guardados correctamente en Google Sheets.")
        except Exception as e:
            logger.error("Error al enviar payload a Google Sheets: %s", e)

    # Resumen unificado en texto para Telegram
    resumen = (
        f"*Registro de {tipo} Completado*\n\n"
        f"• Fecha: {registered_at}\n"
        f"• Cantidad/Detalle: {payload['cantidad_o_salida']}\n"
        f"• Proveedor: {payload['proveedor']}\n"
        f"• Origen: {payload['origen']}\n"
        f"• Formato: {payload['formato']}\n"
        f"• Cajas Obtenidas: {payload['cajas_obtenidas']}\n"
        f"• Kilos Brutos: {payload['kilos_brutos']}\n"
        f"• Tara: {payload['tara']}"
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
    """Cancela el proceso activo."""
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
            FLUJO_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, flujo_tipo_chosen)],
            CANTIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cantidad_entered)],
            PROVEEDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, proveedor_chosen)],
            ORIGEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, origen_chosen)],
            FORMATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, formato_chosen)],
            CAJAS_OBTENIDAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cajas_obtenidas_entered)],
            KILOS_BRUTOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, kilos_brutos_entered)],
            TARA: [MessageHandler(filters.TEXT & ~filters.COMMAND, tara_entered)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conversation)
    return application


def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.error("Falta la variable BOT_TOKEN.")
        sys.exit(2)

    threading.Thread(target=run_dummy_server, daemon=True).start()

    try:
        logger.info("Iniciando bot de Telegram en modo Polling...")
        application = build_application(token)
        application.run_polling(drop_pending_updates=True)
    except InvalidToken:
        logger.error("Token de Telegram rechazado.")
        sys.exit(2)
    except Exception:
        logger.exception("Error en ejecución del bot.")
        sys.exit(1)


if __name__ == "__main__":
    main()
