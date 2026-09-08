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
    ORIGEN,
    FLUJO_TIPO,
    # Estados de ENTRADA
    ENT_PROVEEDOR,
    ENT_FORMATO,
    ENT_CANTIDAD,
    ENT_CALIBRE,
    ENT_TIPO_PALTA,
    ENT_CATEGORIA,
    ENT_KILOS_BRUTOS,
    ENT_TARA,
    # Estados de SALIDA
    SAL_FORMATO,
    SAL_KILOS,
    SAL_CAJAS,
    SAL_CALIBRE,
    SAL_TIPO_PALTA,
    SAL_CATEGORIA,
    # Estados de VENTA
    VEN_CLIENTE,
    VEN_KILOS_VENDIDOS,
    VEN_TIPO_PAGO,
    VEN_CALIBRE,
    VEN_TIPO_PALTA,
    VEN_CATEGORIA,
    VEN_MONTO_TOTAL,
    VEN_MONTO_PAGADO,
    # Nuevo estado de Confirmación
    CONFIRMACION,
) = range(25)

# Teclados y Opciones
OPCIONES_ORIGEN: Final = [["Curacaví"], ["Lo Valledor"]]
OPCIONES_TIPO_REGISTRO: Final = [["Entrada"], ["Salida"], ["Venta"]]

BTN_CONFIRMAR: Final = "✅ Confirmar y Guardar"
BTN_CORREGIR: Final = "🔄 Corregir / Recomenzar"

OPCIONES_CONFIRMACION: Final = [[BTN_CONFIRMAR], [BTN_CORREGIR]]

# Opciones Flujo Entrada
OPCIONES_PROVEEDORES: Final = [
    ["Vida Pal"],
    ["Frutos del Rancho"],
    ["Chile Pal"],
    ["Superior"],
]
OPCIONES_FORMATO_ENTRADA: Final = [
    ["Pallet (Bandejas)"],
    ["Bins"],
    ["Gamelas"],
]

# Opciones Flujo Salida
OPCIONES_FORMATO_SALIDA: Final = [
    ["Bandeja 10Kg"],
    ["Gamela 15Kg"],
    ["Cajas 4Kg"],
]

# Opciones Flujo Venta
OPCIONES_TIPO_PAGO: Final = [
    ["Efectivo"],
    ["Cheque"],
    ["Transferencia"],
    ["Parte Transferencia / Parte Efectivo"],
    ["Transbank"],
    ["Deudor"],
]

# Opciones Compartidas
OPCIONES_CALIBRE: Final = [
    ["Extra"],
    ["Primera con Extra"],
    ["Primera"],
    ["Segunda"],
    ["Tercera"],
    ["Cuarta"],
    ["Quinta"],
    ["Comercial A"],
    ["Comercial B"],
    ["Comercial C"],
    ["Comercial"],
]

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
    """
    Valida si el texto es un número.
    Si es válido, devuelve el número formateado con separadores de miles (.) y coma decimal (,).
    Si no es un número, retorna None.
    """
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
    """Guarda el origen y solicita el Tipo de Registro."""
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
    """Dirige al flujo correspondiente según el tipo seleccionado."""
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
    await update.message.reply_text(
        "4. Selecciona el Calibre:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CALIBRE, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ENT_CALIBRE


async def ent_calibre_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["calibre"] = _message_text(update)
    await update.message.reply_text(
        "5. Selecciona el Tipo de Palta:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ENT_TIPO_PALTA


async def ent_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["tipo_palta"] = _message_text(update)
    await update.message.reply_text(
        "6. Selecciona la Categoría:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return ENT_CATEGORIA


async def ent_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["categoria"] = _message_text(update)
    await update.message.reply_text(
        "7. Ingresa Kilos Brutos (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENT_KILOS_BRUTOS


async def ent_kilos_brutos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos Brutos (ej: 1500 ó 1500.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENT_KILOS_BRUTOS

    context.user_data["kilos_brutos"] = num_formateado
    await update.message.reply_text(
        "8. Ingresa Tara (Kilos) (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENT_TARA


async def ent_tara_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Tara (Kilos) (ej: 20 ó 20.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENT_TARA

    context.user_data["tara"] = num_formateado
    return await mostrar_resumen_previo(update, context)


# ==============================================================================
# FLUJO SALIDA
# ==============================================================================

async def sal_formato_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["formato"] = _message_text(update)
    await update.message.reply_text(
        "2. Ingresa Kilos que Salieron (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SAL_KILOS


async def sal_kilos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos que Salieron (ej: 800 ó 800.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SAL_KILOS

    context.user_data["kilos_salieron"] = num_formateado
    await update.message.reply_text(
        "3. Ingresa Cajas Hechas (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SAL_CAJAS


async def sal_cajas_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Cajas Hechas (ej: 100):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return SAL_CAJAS

    context.user_data["cajas_hechas"] = num_formateado
    await update.message.reply_text(
        "4. Selecciona el Calibre:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CALIBRE, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return SAL_CALIBRE


async def sal_calibre_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["calibre"] = _message_text(update)
    await update.message.reply_text(
        "5. Selecciona el Tipo de Palta:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return SAL_TIPO_PALTA


async def sal_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["tipo_palta"] = _message_text(update)
    await update.message.reply_text(
        "6. Selecciona la Categoría:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return SAL_CATEGORIA


async def sal_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["categoria"] = _message_text(update)
    return await mostrar_resumen_previo(update, context)


# ==============================================================================
# FLUJO VENTA
# ==============================================================================

async def ven_cliente_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["cliente"] = _message_text(update)
    await update.message.reply_text(
        "2. Ingresa Kilos Vendidos (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VEN_KILOS_VENDIDOS


async def ven_kilos_vendidos_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para Kilos Vendidos (ej: 1500 ó 1500.5):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_KILOS_VENDIDOS

    context.user_data["kilos_vendidos"] = num_formateado
    await update.message.reply_text(
        "3. Selecciona el Tipo de Pago:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_TIPO_PAGO, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return VEN_TIPO_PAGO


async def ven_tipo_pago_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["tipo_pago"] = _message_text(update)
    await update.message.reply_text(
        "4. Selecciona el Calibre:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CALIBRE, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return VEN_CALIBRE


async def ven_calibre_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["calibre"] = _message_text(update)
    await update.message.reply_text(
        "5. Selecciona el Tipo de Palta:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_TIPO_PALTA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return VEN_TIPO_PALTA


async def ven_tipo_palta_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["tipo_palta"] = _message_text(update)
    await update.message.reply_text(
        "6. Selecciona la Categoría:",
        reply_markup=ReplyKeyboardMarkup(
            OPCIONES_CATEGORIA, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return VEN_CATEGORIA


async def ven_categoria_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    context.user_data["categoria"] = _message_text(update)
    await update.message.reply_text(
        "7. Ingresa Monto Total de Venta (sólo números):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return VEN_MONTO_TOTAL


async def ven_monto_total_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    texto = _message_text(update)
    num_formateado = parsear_y_formatear_numero(texto)

    if num_formateado is None:
        await update.message.reply_text(
            "⚠️ Por favor ingresa un valor numérico válido para el Monto Total (ej: 250000):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return VEN_MONTO_TOTAL

    context.user_data["monto_total"] = num_formateado
    await update.message.reply_text(
        "8. Ingresa Monto Pagado (sólo números):",
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

async def mostrar_resumen_previo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra el resumen de los datos ingresados y solicita confirmación del usuario."""
    # Formato MM/DD/YYYY HH:MM
    fecha_formateada = datetime.now(CHILE_TIMEZONE).strftime("%d/%m/%Y %H:%M")
    context.user_data["fecha_registro"] = fecha_formateada
    
    tipo = context.user_data.get("tipo_flujo", "")
    origen = context.user_data.get("origen", "")

    if tipo == "Entrada":
        resumen = (
            f"📋 *REVISA LOS DATOS DE ENTRADA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Proveedor:* {context.user_data.get('proveedor', '')}\n"
            f"• *Formato:* {context.user_data.get('formato', '')}\n"
            f"• *Cantidad Entrada:* {context.user_data.get('cantidad', '')}\n"
            f"• *Calibre:* {context.user_data.get('calibre', '')}\n"
            f"• *Tipo de Palta:* {context.user_data.get('tipo_palta', '')}\n"
            f"• *Categoría:* {context.user_data.get('categoria', '')}\n"
            f"• *Kilos Brutos:* {context.user_data.get('kilos_brutos', '')} Kg\n"
            f"• *Tara:* {context.user_data.get('tara', '')} Kg\n\n"
            f"¿Deseas guardar este registro en la planilla?"
        )
    elif tipo == "Salida":
        resumen = (
            f"📋 *REVISA LOS DATOS DE SALIDA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Formato Salida:* {context.user_data.get('formato', '')}\n"
            f"• *Kilos que Salieron:* {context.user_data.get('kilos_salieron', '')} Kg\n"
            f"• *Cajas Hechas:* {context.user_data.get('cajas_hechas', '')}\n"
            f"• *Calibre:* {context.user_data.get('calibre', '')}\n"
            f"• *Tipo de Palta:* {context.user_data.get('tipo_palta', '')}\n"
            f"• *Categoría:* {context.user_data.get('categoria', '')}\n\n"
            f"¿Deseas guardar este registro en la planilla?"
        )
    else:  # Venta
        resumen = (
            f"📋 *REVISA LOS DATOS DE VENTA* 🥑\n\n"
            f"• *Fecha:* {fecha_formateada}\n"
            f"• *Origen:* {origen}\n"
            f"• *Cliente:* {context.user_data.get('cliente', '')}\n"
            f"• *Kilos Vendidos:* {context.user_data.get('kilos_vendidos', '')} Kg\n"
            f"• *Tipo de Pago:* {context.user_data.get('tipo_pago', '')}\n"
            f"• *Calibre:* {context.user_data.get('calibre', '')}\n"
            f"• *Tipo de Palta:* {context.user_data.get('tipo_palta', '')}\n"
            f"• *Categoría:* {context.user_data.get('categoria', '')}\n"
            f"• *Monto Total Venta:* ${context.user_data.get('monto_total', '')}\n"
            f"• *Monto Pagado:* ${context.user_data.get('monto_pagado', '')}\n\n"
            f"¿Deseas guardar este registro en la planilla?"
        )

    if update.message is not None:
        await update.message.reply_text(
            resumen,
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                OPCIONES_CONFIRMACION,
                one_time_keyboard=True,
                resize_keyboard=True,
            ),
        )
    return CONFIRMACION


async def procesar_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la decisión del usuario (Guardar o Recomenzar)."""
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

    # Si se presionó Confirmar -> Enviar a Webhook con formato MM/DD/YYYY HH:MM
    registered_at = context.user_data.get(
        "fecha_registro", 
        datetime.now(CHILE_TIMEZONE).strftime("%m/%d/%Y %H:%M")
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
        "monto_pagado": context.user_data.get("monto_pagado", ""),
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
            ORIGEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, origen_chosen)],
            FLUJO_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, flujo_tipo_chosen)],
            
            # Estados Entrada
            ENT_PROVEEDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_proveedor_chosen)],
            ENT_FORMATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_formato_chosen)],
            ENT_CANTIDAD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_cantidad_entered)],
            ENT_CALIBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_calibre_chosen)],
            ENT_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_tipo_palta_chosen)],
            ENT_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_categoria_chosen)],
            ENT_KILOS_BRUTOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_kilos_brutos_entered)],
            ENT_TARA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ent_tara_entered)],
            
            # Estados Salida
            SAL_FORMATO: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_formato_chosen)],
            SAL_KILOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_kilos_entered)],
            SAL_CAJAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_cajas_entered)],
            SAL_CALIBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_calibre_chosen)],
            SAL_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_tipo_palta_chosen)],
            SAL_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, sal_categoria_chosen)],

            # Estados Venta
            VEN_CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_cliente_entered)],
            VEN_KILOS_VENDIDOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_kilos_vendidos_entered)],
            VEN_TIPO_PAGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_tipo_pago_chosen)],
            VEN_CALIBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_calibre_chosen)],
            VEN_TIPO_PALTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_tipo_palta_chosen)],
            VEN_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_categoria_chosen)],
            VEN_MONTO_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ven_monto_total_entered)],
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
