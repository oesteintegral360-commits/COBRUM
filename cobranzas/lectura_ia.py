"""
Lectura de cuentas corrientes con IA (Claude) — REAL (no simulado).

Toma una FOTO, un PDF o una planilla en cualquier formato y usa Claude (que "mira" la
imagen) para entender el formato y extraer las filas: CUIT, nombre, número de factura,
saldo, vencimiento, teléfono y vendedor — sin importar cómo esté armado el archivo.

Antes de importar, el usuario CONFIRMA lo que la IA entendió (pantalla de revisión), así
una cifra mal leída nunca entra sola.

Necesita la variable de entorno ANTHROPIC_API_KEY (cada empresa la crea en Anthropic).
Se usa el modelo balanceado (buena precisión a bajo costo).
"""

import base64
import json
import os

# Modelo balanceado: buena precisión leyendo números a bajo costo (centavos por foto).
MODELO = "claude-sonnet-5"

# Le pedimos a la IA que devuelva SIEMPRE esta estructura (una fila por factura).
ESQUEMA = {
    "type": "object",
    "properties": {
        "filas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cuit": {"type": "string", "description": "CUIT/CUIL del cliente, como aparezca"},
                    "nombre": {"type": "string", "description": "Nombre o razón social del cliente"},
                    "numero_factura": {"type": "string", "description": "Número de factura o comprobante"},
                    "saldo": {"type": "number", "description": "Saldo pendiente de esa factura (número, sin símbolos)"},
                    "fecha_vencimiento": {"type": "string", "description": "Vencimiento en formato YYYY-MM-DD"},
                    "telefono": {"type": "string", "description": "Teléfono/WhatsApp si aparece; vacío si no"},
                    "vendedor": {"type": "string", "description": "Vendedor asignado si aparece; vacío si no"},
                },
                "required": ["cuit", "nombre", "numero_factura", "saldo",
                             "fecha_vencimiento", "telefono", "vendedor"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["filas"],
    "additionalProperties": False,
}

INSTRUCCION = (
    "Sos un asistente que lee cuentas corrientes / listados de deuda de clientes, en "
    "CUALQUIER formato (foto sacada con el celular, PDF, planilla desprolija). Extraé UNA "
    "fila por cada factura o comprobante IMPAGO que veas. Para cada una devolvé: CUIT del "
    "cliente, nombre o razón social, número de factura, saldo pendiente (como número, sin "
    "símbolos de moneda ni separadores de miles), fecha de vencimiento en formato "
    "YYYY-MM-DD, y teléfono y vendedor si figuran (si no, dejalos vacíos). NO inventes "
    "datos: si un campo no está, dejalo vacío (o 0 en el saldo). Copiá los montos EXACTOS "
    "como figuran. Si la imagen no es una cuenta corriente, devolvé una lista vacía."
)


class ErrorLecturaIA(Exception):
    """Error legible para mostrarle al usuario cuando la lectura con IA falla."""


def hay_clave() -> bool:
    """True si está configurada la clave de IA."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _bloque_archivo(ruta: str, nombre: str) -> dict:
    """Arma el bloque de contenido (imagen o documento) para mandarle a la IA."""
    n = nombre.lower()
    datos = base64.standard_b64encode(open(ruta, "rb").read()).decode()
    if n.endswith(".pdf"):
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": datos}}
    media = None
    if n.endswith(".png"):
        media = "image/png"
    elif n.endswith((".jpg", ".jpeg")):
        media = "image/jpeg"
    elif n.endswith(".webp"):
        media = "image/webp"
    elif n.endswith(".gif"):
        media = "image/gif"
    if media is None:
        raise ErrorLecturaIA("Formato no soportado. Subí una foto (JPG/PNG), un PDF, o un Excel.")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": datos}}


def extraer_filas(ruta_archivo: str, nombre_archivo: str) -> list:
    """
    Lee el archivo con IA y devuelve la lista de filas (dicts) que entendió.
    Lanza ErrorLecturaIA (con mensaje legible) si algo falla.
    """
    if not hay_clave():
        raise ErrorLecturaIA(
            "Todavía no está configurada la clave de IA. Cargá ANTHROPIC_API_KEY para leer fotos.")
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ErrorLecturaIA("Falta instalar la librería de IA (anthropic).")

    bloque = _bloque_archivo(ruta_archivo, nombre_archivo)
    cliente = Anthropic()  # toma la clave de ANTHROPIC_API_KEY
    try:
        respuesta = cliente.messages.create(
            model=MODELO,
            max_tokens=8000,
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
            messages=[{"role": "user", "content": [bloque, {"type": "text", "text": INSTRUCCION}]}],
        )
    except Exception as e:
        raise ErrorLecturaIA(f"No pudimos leer el archivo con la IA. Detalle: {e}")

    texto = next((b.text for b in respuesta.content if b.type == "text"), "")
    try:
        datos = json.loads(texto)
    except Exception:
        raise ErrorLecturaIA("La IA no devolvió un resultado que pudiéramos leer. Probá de nuevo.")
    return datos.get("filas", [])
