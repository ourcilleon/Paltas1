"""Bot de Telegram para el registro de Entrada, Salida y Venta de Paltas."""

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

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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
    ORIGEN,
    FLUJO_TIPO,
    # Estados de ENTRADA
    ENT_PROVEEDOR,
    ENT_FORMATO,
    ENT_CANTIDAD,
    ENT_CALIBRES_MULTI,
    ENT_LOOP_TIPO_PALTA,
    ENT_LOOP_CATEGORIA,
    ENT_LOOP_KILOS_BRUTOS,
    ENT_LOOP_TARA,
    # Estados de SALIDA
    SAL_FORMATO,
    SAL_CALIBRES_MULTI,
    SAL_LOOP_TIPO_PALTA,
    SAL_LOOP_CATEGORIA,
    SAL_LOOP_KILOS_SALIERON,
    SAL_LOOP_CAJAS_HECHAS,
    # Estados de VENTA
    VEN_CLIENTE,
    VEN_CALIBRES_MULTI,
    VEN_LOOP_TIPO_PALTA,
    VEN_LOOP_CATEGORIA,
    VEN_LOOP_KILOS_VENDIDOS,
    VEN_LOOP_PRECIO_KILO,
    VEN_TIPO_PAGO,
    VEN_MONTO_PAGADO,
    # Estado de Confirmación
    CONFIRMACION,
) = range(25)

# Teclados y Opciones
OPCIONES_ORIGEN: Final = [["Curacaví"], ["Lo Valledor"]]
OPCIONES_TIPO_REGISTRO: Final = [["Entrada"], ["Salida"], ["Venta"]]

BTN_CONFIRMAR: Final = "✅ Confirmar y Guardar"
BTN_CORREGIR: Final = "🔄 Corregir / Recomenzar"

OPCIONES_CONFIRMACION: Final = [[BTN_CONFIRMAR], [BTN_CORREGIR]]

OPCIONES_PROVEEDORES: Final = [
    ["Vida Pal"],
    ["Frutos del Rancho"],
    ["Chile Pal"],
    ["Superior"],
]
OPCIONES_FORMATO_ENTRADA: Final = [
    ["Pallets"],
    ["Bandejas"],
    ["Gamelas"],
    ["Bins"],
]

OPCIONES_FORMATO_SALIDA: Final = [
    ["Bandeja 10Kg"],
    ["Gamela 15Kg"],
    ["Cajas 4Kg"],
]

OPCIONES_TIPO_PAGO: Final = [
    ["Efectivo"],
    ["Cheque"],
    ["Transferencia"],
    ["Parte Transferencia / Parte Efectivo"],
    ["Transbank"],
    ["Deudor"],
]

# Lista completa de Calibres
LISTA_CALIBRES: Final = [
    "12", "14", "16", "18", "20", "22", "24", "26", "28", "30", "32",
    "Extra", "Primera con Extra", "Primera", "Segunda", "Tercera", "Cuarta", "Quinta",
    "Comercial A", "Comercial B", "Comercial C", "Comercial"
]

OPCIONES_CALIBRE_INDIVIDUAL: Final = [[c] for c in LISTA_CALIBRES]

OPCIONES_TIPO_PALTA: Final = [
    ["Palta Hass"],
    ["Palta Edranol"],
    ["Palta Esther"],
    ["Palta Fuerte"],
    ["Negra de la Cruz"],
]

OPCIONES_CATEGORIA: Final = [
    ["Categoría 1"],
    ["Categoría 1 1/2"],
    ["Categoría 2"],
    ["Comercial (Descarte)"],
]

CHILE_TIMEZONE: Final = ZoneInfo("America/Santiago")
NEXT_ORDER_BUTTON: Final = "Ingresar siguiente registro"


def _message_text(update: Update) -> str:
    if update.message is None or update.message.text is None:
        raise ValueError("El mensaje no contiene texto")
    return update.message.text.strip()


def parsear_y_formatear_numero(texto: str) -> str | None:
    """Valida si el texto es numérico y aplica formato de miles."""
    limpio = texto.replace(" ", "").replace("$", "")
    
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")

    try:
        val = float(limpio)
        if val.is_integer():
            return f"{int(val):,}".replace(",", ".")
        else:
            partes = f"{val:,.2f}".split(".")
            entera = partes[0].replace(",", ".")
            decimal = partes[1]
            return f"{entera},{decimal}"
    except ValueError:
        return None


def convertir_a_float(valor_str: str) -> float:
    """Convierte un string formateado con puntos de miles a float."""
    try:
        limpio = str(valor_str).replace(".", "").replace(",", ".")
        return float(limpio)
    except ValueError:
        return 0.0


def formatear_monto(val: float) -> str:
    """Formatea float a representación con separador de miles."""
    if val.is_integer():
        return f"{int(val):,}".replace(",", ".")
    else:
        partes = f"{val:,.2f}".split(".")
        entera = partes[0].replace(",", ".")
        decimal = partes[1]
        return f"{entera},{decimal}"


def construir_teclado_calibres_inline(seleccionados: set[str], prefix_callback: str = "cal_") -> InlineKeyboardMarkup:
    """Construye un teclado inline para selección múltiple de calibres."""
    keyboard = []
    for i in range(0, len(LISTA_CALIBRES), 2):
        row = []
        c1 = LISTA_CALIBRES[i]
        prefix1 = "✅ " if c1 in seleccionados else "⬜ "
        row.append(InlineKeyboardButton(f"{prefix1}{c1}", callback_data=f"{prefix_callback}{c1}"))
        
        if i + 1 < len(LISTA_CALIBRES):
            c2 = LISTA_CALIBRES[i + 1]
            prefix2 = "✅ " if c2 in seleccionados else "⬜ "
            row.append(InlineKeyboardButton(f"{prefix2}{c2}", callback_data=f"{prefix_callback}{c2}"))
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("➡️ Finalizar Selección", callback_data=f"{prefix_callback}DONE")])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el registro solicitando el Origen."""
    if update.message is None:
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "1. Selecciona el Origen:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_ORIGEN, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ORIGEN


async def origen_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    opcion = _message_text(update)
    if opcion not in ["Curacaví", "Lo Valledor"]:
        await update.message.reply_text("Por favor selecciona una opción válida usando los botones.")
        return ORIGEN

    context.user_data["origen"] = opcion

    await update.message.reply_text(
        "2. Selecciona el Tipo de Registro:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_TIPO_REGISTRO, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return FLUJO_TIPO


async def flujo_tipo_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    opcion = _message_text(update)
    if opcion not in ["Entrada", "Salida", "Venta"]:
        await update.message.reply_text("Por favor selecciona una opción válida usando los botones.")
        return FLUJO_TIPO

    context.user_data["tipo_flujo"] = opcion

    if opcion == "Entrada":
        await update.message.reply_text(
            "1. Selecciona el Proveedor:",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_PROVEEDORES, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return ENT_PROVEEDOR
    elif opcion == "Salida":
        await update.message.reply_text(
            "1. Selecciona el Formato de Salida:",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_FORMATO_SALIDA, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return SAL_FORMATO
    else:  # Venta
        await update.message.reply_text(
            "1. Ingresa el Nombre del Cliente:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_CLIENTE


# ==============================================================================
# FLUJO ENTRADA
# ==============================================================================

async def ent_proveedor_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["proveedor"] = _message_text(update)
    await update.message.reply_text(
        "2. Selecciona el Formato de Entrada:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_FORMATO_ENTRADA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ENT_FORMATO


async def ent_formato_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["formato"] = _message_text(update)
    await update.message.reply_text(
        "3. Ingresa la Cantidad Entrada (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENT_CANTIDAD


async def ent_cantidad_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para la Cantidad Entrada (ej: 50 ó 1200):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENT_CANTIDAD

    context.user_data["cantidad"] = num_formateado
    context.user_data["calibres_seleccionados"] = set()

    reply_markup = construir_teclado_calibres_inline(set(), "cal_")
    await update.message.reply_text(
        "4. Selecciona uno o varios calibres tocando los botones. Cuando termines, presiona 'Finalizar Selección':",
        reply_markup=reply_markup,
    )
    return ENT_CALIBRES_MULTI


async def ent_calibres_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ENT_CALIBRES_MULTI

    await query.answer()
    data = query.data
    seleccionados: set[str] = context.user_data.get("calibres_seleccionados", set())

    if data == "cal_DONE":
        if not seleccionados:
            await query.edit_message_text(
                "⚠️ Debes seleccionar al menos un calibre antes de continuar.\n\n"
                "Selecciona los calibres que necesitas ingresar:",
                reply_markup=construir_teclado_calibres_inline(seleccionados, "cal_")
            )
            return ENT_CALIBRES_MULTI

        lista_calibres_ordenada = [c for c in LISTA_CALIBRES if c in seleccionados]
        context.user_data["calibres_queue"] = lista_calibres_ordenada
        context.user_data["calibres_detalles"] = []
        context.user_data["current_calibre_idx"] = 0

        await query.edit_message_text(f"Calibres seleccionados: {', '.join(lista_calibres_ordenada)}")
        return await pedir_siguiente_calibre_atributo_ent(query, context)

    if data.startswith("cal_"):
        calibre = data.replace("cal_", "")
        if calibre in seleccionados:
            seleccionados.remove(calibre)
        else:
            seleccionados.add(calibre)

        context.user_data["calibres_seleccionados"] = seleccionados
        await query.edit_message_reply_markup(
            reply_markup=construir_teclado_calibres_inline(seleccionados, "cal_")
        )

    return ENT_CALIBRES_MULTI


async def pedir_siguiente_calibre_atributo_ent(event_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])

    if idx >= len(queue):
        return await mostrar_resumen_previo(event_or_update, context)

    calibre_actual = queue[idx]
    total = len(queue)
    mensaje = f"📦 *Detalles de Entrada para Calibre {calibre_actual}* ({idx + 1}/{total})\n\nSelecciona el Tipo de Palta:"
    markup = ReplyKeyboardMarkup(OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True)
    
    if hasattr(event_or_update, 'message') and event_or_update.message is not None:
        await event_or_update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=markup)

    return ENT_LOOP_TIPO_PALTA


async def ent_loop_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_tipo_palta"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📦 *Calibre {calibre_actual}*\nSelecciona la Categoría:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ENT_LOOP_CATEGORIA


async def ent_loop_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_categoria"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📦 *Calibre {calibre_actual}*\nIngresa Kilos Brutos (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENT_LOOP_KILOS_BRUTOS


async def ent_loop_kilos_brutos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos Brutos (ej: 1500 ó 1500.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENT_LOOP_KILOS_BRUTOS

    context.user_data["temp_kilos_brutos"] = num_formateado
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📦 *Calibre {calibre_actual}*\nIngresa Tara en Kilos (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENT_LOOP_TARA


async def ent_loop_tara_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Tara (ej: 20 ó 20.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENT_LOOP_TARA

    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])
    calibre_actual = queue[idx]

    detalle = {
        "calibre": calibre_actual,
        "tipo_palta": context.user_data.get("temp_tipo_palta", ""),
        "categoria": context.user_data.get("temp_categoria", ""),
        "kilos_brutos": context.user_data.get("temp_kilos_brutos", ""),
        "tara": num_formateado,
    }

    context.user_data.setdefault("calibres_detalles", []).append(detalle)
    context.user_data["current_calibre_idx"] = idx + 1
    return await pedir_siguiente_calibre_atributo_ent(update, context)


# ==============================================================================
# FLUJO SALIDA
# ==============================================================================

async def sal_formato_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["formato"] = _message_text(update)
    context.user_data["calibres_seleccionados"] = set()

    reply_markup = construir_teclado_calibres_inline(set(), "salcal_")
    await update.message.reply_text(
        "2. Selecciona uno o varios calibres tocando los botones. Cuando termines, presiona 'Finalizar Selección':",
        reply_markup=reply_markup,
    )
    return SAL_CALIBRES_MULTI


async def sal_calibres_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return SAL_CALIBRES_MULTI

    await query.answer()
    data = query.data
    seleccionados: set[str] = context.user_data.get("calibres_seleccionados", set())

    if data == "salcal_DONE":
        if not seleccionados:
            await query.edit_message_text(
                "⚠️ Debes seleccionar al menos un calibre antes de continuar.\n\n"
                "Selecciona los calibres que salieron:",
                reply_markup=construir_teclado_calibres_inline(seleccionados, "salcal_")
            )
            return SAL_CALIBRES_MULTI

        lista_calibres_ordenada = [c for c in LISTA_CALIBRES if c in seleccionados]
        context.user_data["calibres_queue"] = lista_calibres_ordenada
        context.user_data["calibres_detalles"] = []
        context.user_data["current_calibre_idx"] = 0

        await query.edit_message_text(f"Calibres seleccionados: {', '.join(lista_calibres_ordenada)}")
        return await pedir_siguiente_calibre_atributo_sal(query, context)

    if data.startswith("salcal_"):
        calibre = data.replace("salcal_", "")
        if calibre in seleccionados:
            seleccionados.remove(calibre)
        else:
            seleccionados.add(calibre)

        context.user_data["calibres_seleccionados"] = seleccionados
        await query.edit_message_reply_markup(
            reply_markup=construir_teclado_calibres_inline(seleccionados, "salcal_")
        )

    return SAL_CALIBRES_MULTI


async def pedir_siguiente_calibre_atributo_sal(event_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])

    if idx >= len(queue):
        return await mostrar_resumen_previo(event_or_update, context)

    calibre_actual = queue[idx]
    total = len(queue)
    mensaje = f"📤 *Detalles de Salida para Calibre {calibre_actual}* ({idx + 1}/{total})\n\nSelecciona el Tipo de Palta:"
    markup = ReplyKeyboardMarkup(OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True)

    if hasattr(event_or_update, 'message') and event_or_update.message is not None:
        await event_or_update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=markup)

    return SAL_LOOP_TIPO_PALTA


async def sal_loop_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_tipo_palta"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📤 *Calibre {calibre_actual}*\nSelecciona la Categoría:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return SAL_LOOP_CATEGORIA


async def sal_loop_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_categoria"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📤 *Calibre {calibre_actual}*\nIngresa Kilos que Salieron (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SAL_LOOP_KILOS_SALIERON


async def sal_loop_kilos_salieron_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos que Salieron (ej: 800 ó 800.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SAL_LOOP_KILOS_SALIERON

    context.user_data["temp_kilos_salieron"] = num_formateado
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"📤 *Calibre {calibre_actual}*\nIngresa Cajas Hechas (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SAL_LOOP_CAJAS_HECHAS


async def sal_loop_cajas_hechas_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Cajas Hechas (ej: 100):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SAL_LOOP_CAJAS_HECHAS

    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])
    calibre_actual = queue[idx]

    detalle = {
        "calibre": calibre_actual,
        "tipo_palta": context.user_data.get("temp_tipo_palta", ""),
        "categoria": context.user_data.get("temp_categoria", ""),
        "kilos_salieron": context.user_data.get("temp_kilos_salieron", ""),
        "cajas_hechas": num_formateado,
    }

    context.user_data.setdefault("calibres_detalles", []).append(detalle)
    context.user_data["current_calibre_idx"] = idx + 1
    return await pedir_siguiente_calibre_atributo_sal(update, context)


# ==============================================================================
# FLUJO VENTA
# ==============================================================================

async def ven_cliente_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["cliente"] = _message_text(update)
    context.user_data["calibres_seleccionados"] = set()

    reply_markup = construir_teclado_calibres_inline(set(), "vencal_")
    await update.message.reply_text(
        "2. Selecciona uno o varios calibres tocando los botones. Cuando termines, presiona 'Finalizar Selección':",
        reply_markup=reply_markup,
    )
    return VEN_CALIBRES_MULTI


async def ven_calibres_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return VEN_CALIBRES_MULTI

    await query.answer()
    data = query.data
    seleccionados: set[str] = context.user_data.get("calibres_seleccionados", set())

    if data == "vencal_DONE":
        if not seleccionados:
            await query.edit_message_text(
                "⚠️ Debes seleccionar al menos un calibre antes de continuar.\n\n"
                "Selecciona los calibres para la venta:",
                reply_markup=construir_teclado_calibres_inline(seleccionados, "vencal_")
            )
            return VEN_CALIBRES_MULTI

        lista_calibres_ordenada = [c for c in LISTA_CALIBRES if c in seleccionados]
        context.user_data["calibres_queue"] = lista_calibres_ordenada
        context.user_data["calibres_detalles"] = []
        context.user_data["current_calibre_idx"] = 0

        await query.edit_message_text(f"Calibres seleccionados: {', '.join(lista_calibres_ordenada)}")
        return await pedir_siguiente_calibre_atributo_ven(query, context)

    if data.startswith("vencal_"):
        calibre = data.replace("vencal_", "")
        if calibre in seleccionados:
            seleccionados.remove(calibre)
        else:
            seleccionados.add(calibre)

        context.user_data["calibres_seleccionados"] = seleccionados
        await query.edit_message_reply_markup(
            reply_markup=construir_teclado_calibres_inline(seleccionados, "vencal_")
        )

    return VEN_CALIBRES_MULTI


async def pedir_siguiente_calibre_atributo_ven(event_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])

    if idx >= len(queue):
        detalles = context.user_data.get("calibres_detalles", [])
        monto_total_num = sum(convertir_a_float(d.get("subtotal_num", 0)) for d in detalles)
        context.user_data["monto_total"] = formatear_monto(monto_total_num)

        mensaje = "💰 Selecciona el Tipo de Pago:"
        markup = ReplyKeyboardMarkup(OPCIONES_TIPO_PAGO, one_time_keyboard=True, resize_keyboard=True)
        if hasattr(event_or_update, 'message') and event_or_update.message is not None:
            await event_or_update.message.reply_text(mensaje, reply_markup=markup)

        return VEN_TIPO_PAGO

    calibre_actual = queue[idx]
    total = len(queue)
    mensaje = f"💰 *Detalles de Venta para Calibre {calibre_actual}* ({idx + 1}/{total})\n\nSelecciona el Tipo de Palta:"
    markup = ReplyKeyboardMarkup(OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True)

    if hasattr(event_or_update, 'message') and event_or_update.message is not None:
        await event_or_update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=markup)

    return VEN_LOOP_TIPO_PALTA


async def ven_loop_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_tipo_palta"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"💰 *Calibre {calibre_actual}*\nSelecciona la Categoría:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return VEN_LOOP_CATEGORIA


async def ven_loop_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["temp_categoria"] = _message_text(update)
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"💰 *Calibre {calibre_actual}*\nIngresa Kilos Vendidos (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VEN_LOOP_KILOS_VENDIDOS


async def ven_loop_kilos_vendidos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos Vendidos (ej: 1500 ó 1500.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_LOOP_KILOS_VENDIDOS

    context.user_data["temp_kilos_vendidos"] = num_formateado
    idx = context.user_data.get("current_calibre_idx", 0)
    calibre_actual = context.user_data.get("calibres_queue", [])[idx]

    await update.message.reply_text(
        f"💰 *Calibre {calibre_actual}*\nIngresa Precio por Kilo (sólo números):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VEN_LOOP_PRECIO_KILO


async def ven_loop_precio_kilo_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    precio_formateado = parsear_y_formatear_numero(texto)

    if precio_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para el Precio por Kilo (ej: 2500):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_LOOP_PRECIO_KILO

    kilos_str = context.user_data.get("temp_kilos_vendidos", "0")
    kilos_num = convertir_a_float(kilos_str)
    precio_num = convertir_a_float(precio_formateado)
    subtotal = kilos_num * precio_num

    idx = context.user_data.get("current_calibre_idx", 0)
    queue = context.user_data.get("calibres_queue", [])
    calibre_actual = queue[idx]

    detalle = {
        "calibre": calibre_actual,
        "tipo_palta": context.user_data.get("temp_tipo_palta", ""),
        "categoria": context.user_data.get("temp_categoria", ""),
        "kilos_vendidos": kilos_str,
        "precio_kilo": precio_formateado,
        "subtotal_num": subtotal,
        "subtotal_venta": formatear_monto(subtotal),
    }

    context.user_data.setdefault("calibres_detalles", []).append(detalle)
    context.user_data["current_calibre_idx"] = idx + 1
    return await pedir_siguiente_calibre_atributo_ven(update, context)


async def ven_tipo_pago_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    tipo_pago = _message_text(update)
    context.user_data["tipo_pago"] = tipo_pago

    if tipo_pago == "Deudor":
        context.user_data["monto_pagado"] = "0"
        return await mostrar_resumen_previo(update, context)

    await update.message.reply_text(
        "Ingresa Monto Pagado (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VEN_MONTO_PAGADO


async def ven_monto_pagado_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para el Monto Pagado (ej: 250000):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_MONTO_PAGADO

    context.user_data["monto_pagado"] = num_formateado
    return await mostrar_resumen_previo(update, context)


# ==============================================================================
# RESUMEN PREVIO Y CONFIRMACIÓN
# ==============================================================================

async def mostrar_resumen_previo(event_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    now = datetime.now(CHILE_TIMEZONE)
    context.user_data["fecha_registro"] = now.strftime("%Y-%m-%d %H:%M:%S")
    fecha_formateada = now.strftime("%d/%m/%Y %H:%M")
    
    tipo = context.user_data.get("tipo_flujo", "")
    origen = context.user_data.get("origen", "")

    if tipo == "Entrada":
        detalles = context.user_data.get("calibres_detalles", [])
        bloque_calibres = ""
        for det in detalles:
            bloque_calibres += (
                f"\n  • *Calibre {det['calibre']}*:\n"
                f"      - Tipo Palta: {det['tipo_palta']}\n"
                f"      - Categoría: {det['categoria']}\n"
                f"      - Kilos Brutos: {det['kilos_brutos']} Kg\n"
                f"      - Tara: {det['tara']} Kg\n"
            )

        resumen = (
            f"📋 *REVISA LOS DATOS DE ENTRADA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Proveedor:* {context.user_data.get('proveedor', '')}\n"
            f"• *Formato:* {context.user_data.get('formato', '')}\n"
            f"• *Cantidad Entrada:* {context.user_data.get('cantidad', '')}\n"
            f"• *Detalle por Calibres ({len(detalles)}):*{bloque_calibres}\n"
            f"¿Deseas guardar este registro en la planilla?"
        )
    elif tipo == "Salida":
        detalles = context.user_data.get("calibres_detalles", [])
        bloque_calibres = ""
        for det in detalles:
            bloque_calibres += (
                f"\n  • *Calibre {det['calibre']}*:\n"
                f"      - Tipo Palta: {det['tipo_palta']}\n"
                f"      - Categoría: {det['categoria']}\n"
                f"      - Kilos que Salieron: {det['kilos_salieron']} Kg\n"
                f"      - Cajas Hechas: {det['cajas_hechas']}\n"
            )

        resumen = (
            f"📋 *REVISA LOS DATOS DE SALIDA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Formato Salida:* {context.user_data.get('formato', '')}\n"
            f"• *Detalle por Calibres ({len(detalles)}):*{bloque_calibres}\n"
            f"¿Deseas guardar este registro en la planilla?"
        )
    else:  # Venta
        detalles = context.user_data.get("calibres_detalles", [])
        bloque_calibres = ""
        for det in detalles:
            bloque_calibres += (
                f"\n  • *Calibre {det['calibre']}*:\n"
                f"      - Tipo Palta: {det['tipo_palta']}\n"
                f"      - Categoría: {det['categoria']}\n"
                f"      - Kilos Vendidos: {det['kilos_vendidos']} Kg\n"
                f"      - Precio/Kg: ${det['precio_kilo']}\n"
                f"      - Subtotal: ${det['subtotal_venta']}\n"
            )

        monto_pag_str = context.user_data.get("monto_pagado", "0")

        resumen = (
            f"📋 *REVISA LOS DATOS DE VENTA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Cliente:* {context.user_data.get('cliente', '')}\n"
            f"• *Detalle por Calibres ({len(detalles)}):*{bloque_calibres}\n"
            f"• *Monto Total Venta:* ${context.user_data.get('monto_total', '')}\n"
            f"• *Tipo de Pago:* {context.user_data.get('tipo_pago', '')}\n"
            f"• *Monto Pagado:* ${monto_pag_str}\n\n"
            f"¿Deseas guardar este registro en la planilla?"
        )

    markup = ReplyKeyboardMarkup(OPCIONES_CONFIRMACION, one_time_keyboard=True, resize_keyboard=True)

    if hasattr(event_or_update, 'message') and event_or_update.message is not None:
        await event_or_update.message.reply_text(resumen, parse_mode="Markdown", reply_markup=markup)

    return CONFIRMACION


async def procesar_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    opcion = _message_text(update)

    if opcion == BTN_CORREGIR:
        context.user_data.clear()
        await update.message.reply_text(
            "🔄 Registro descartado. Comenzando nuevamente.\n\n1. Selecciona el Origen:",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_ORIGEN, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return ORIGEN

    if opcion != BTN_CONFIRMAR:
        await update.message.reply_text(
            "Por favor, selecciona una opción válida usando los botones:",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_CONFIRMACION, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return CONFIRMACION

    registered_at = context.user_data.get(
        "fecha_registro", 
        datetime.now(CHILE_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    )
    tipo = context.user_data.get("tipo_flujo", "")
    origen = context.user_data.get("origen", "")

    payload = {
        "fecha": registered_at,
        "origen": origen,
        "tipo_flujo": tipo,
        "proveedor": context.user_data.get("proveedor", ""),
        "formato": context.user_data.get("formato", ""),
        "cantidad": context.user_data.get("cantidad", ""),
        "detalles_calibres": context.user_data.get("calibres_detalles", []),
        "calibre": context.user_data.get("calibre", ""),
        "tipo_palta": context.user_data.get("tipo_palta", ""),
        "categoria": context.user_data.get("categoria", ""),
        "kilos_brutos": context.user_data.get("kilos_brutos", ""),
        "tara": context.user_data.get("tara", ""),
        "kilos_salieron": context.user_data.get("kilos_salieron", ""),
        "cajas_hechas": context.user_data.get("cajas_hechas", ""),
        "cliente": context.user_data.get("cliente", ""),
        "kilos_vendidos": context.user_data.get("kilos_vendidos", ""),
        "tipo_pago": context.user_data.get("tipo_pago", ""),
        "monto_total": context.user_data.get("monto_total", ""),
        "monto_pagado": context.user_data.get("monto_pagado", "0"),
    }

    sheets_url = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    if sheets_url:
        try:
            data = json.dumps(payload).encode("utf-8")
            
            class RedirectHandler(urllib.request.HTTPRedirectHandler):
                def http_error_302(self, req, fp, code, msg, headers):
                    return self.parent.open(headers['Location'], data=data)
                http_error_301 = http_error_302
                http_error_303 = http_error_302
                http_error_307 = http_error_302

            opener = urllib.request.build_opener(RedirectHandler)
            req = urllib.request.Request(
                sheets_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with opener.open(req, timeout=10) as response:
                respuesta_texto = response.read().decode("utf-8")
                logger.info("Respuesta de Google Sheets Webhook: %s", respuesta_texto)
                
        except Exception as e:
            logger.error("Error al enviar payload a Google Sheets: %s", e)

    await update.message.reply_text(
        "🎉🥑 *¡Registro guardado con éxito en la planilla!*",
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
            ORIGEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, origen_chosen)],
            FLUJO_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, flujo_tipo_chosen)],
            
            # Estados Entrada
            ENT_PROVEEDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_proveedor_chosen)],
            ENT_FORMATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_formato_chosen)],
            ENT_CANTIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_cantidad_entered)],
            ENT_CALIBRES_MULTI: [CallbackQueryHandler(ent_calibres_toggle_callback)],
            ENT_LOOP_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_loop_tipo_palta_chosen)],
            ENT_LOOP_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_loop_categoria_chosen)],
            ENT_LOOP_KILOS_BRUTOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_loop_kilos_brutos_entered)],
            ENT_LOOP_TARA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_loop_tara_entered)],
            
            # Estados Salida
            SAL_FORMATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_formato_chosen)],
            SAL_CALIBRES_MULTI: [CallbackQueryHandler(sal_calibres_toggle_callback)],
            SAL_LOOP_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_loop_tipo_palta_chosen)],
            SAL_LOOP_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_loop_categoria_chosen)],
            SAL_LOOP_KILOS_SALIERON: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_loop_kilos_salieron_entered)],
            SAL_LOOP_CAJAS_HECHAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_loop_cajas_hechas_entered)],

            # Estados Venta
            VEN_CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_cliente_entered)],
            VEN_CALIBRES_MULTI: [CallbackQueryHandler(ven_calibres_toggle_callback)],
            VEN_LOOP_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_loop_tipo_palta_chosen)],
            VEN_LOOP_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_loop_categoria_chosen)],
            VEN_LOOP_KILOS_VENDIDOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_loop_kilos_vendidos_entered)],
            VEN_LOOP_PRECIO_KILO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_loop_precio_kilo_entered)],
            VEN_TIPO_PAGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_tipo_pago_chosen)],
            VEN_MONTO_PAGADO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_monto_pagado_entered)],

            # Estado Confirmación
            CONFIRMACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_confirmacion)],
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
