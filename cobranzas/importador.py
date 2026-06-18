"""
Importador de la "foto" (el Excel que sube la empresa).

Una sola carga hace todo:
  1. lee el Excel (mapeo flexible de columnas),
  2. identifica/crea al cliente solo (por CUIT),
  3. mete las facturas sin duplicar (matcheo por número de factura),
  4. la foto nueva REEMPLAZA a la vieja: lo que desaparece se asume pagado,
  5. guarda un registro de la carga (ImportSnapshot).

Devuelve un ResultadoImport con números y avisos en lenguaje humano.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pandas as pd

from cobranzas.cuit import normalizar_cuit, validar_digito_verificador
from cobranzas.modelos import Cliente, Factura, ImportSnapshot
from cobranzas import motor


# --- Mapeo flexible de columnas -------------------------------------------------
# Cada export contable nombra las columnas distinto. Acá listamos los nombres que
# aceptamos para cada dato. Comparamos en minúsculas y sin espacios de más.
NOMBRES_COLUMNAS = {
    "cuit": ["cuit", "cuil", "cuit/cuil", "documento", "doc"],
    "nombre": ["nombre", "razon social", "razón social", "cliente", "nombre cliente"],
    "numero_factura": ["numero factura", "número factura", "nro factura", "n factura",
                        "factura", "comprobante", "nro comprobante", "numero", "número"],
    "saldo_pendiente": ["saldo pendiente", "saldo", "importe", "monto", "deuda",
                        "saldo adeudado", "total"],
    "fecha_vencimiento": ["fecha vencimiento", "vencimiento", "vence", "fecha vto",
                        "vto", "fecha de vencimiento"],
    "telefono_whatsapp": ["telefono", "teléfono", "whatsapp", "celular", "tel",
                        "telefono whatsapp"],
    "vendedor_asignado": ["vendedor", "vendedor asignado", "comercial", "responsable"],
}

# Cuáles son obligatorias para poder procesar una fila.
COLUMNAS_OBLIGATORIAS = ["cuit", "numero_factura", "saldo_pendiente", "fecha_vencimiento"]


@dataclass
class ResultadoImport:
    """Lo que devolvemos después de importar: para mostrarle al usuario qué pasó."""
    clientes_nuevos: int = 0
    facturas_nuevas: int = 0
    facturas_actualizadas: int = 0
    facturas_pagadas: int = 0  # las que desaparecieron de la foto
    total_pendiente: Decimal = Decimal("0")
    avisos: list[str] = field(default_factory=list)  # mensajes en lenguaje humano
    error: Optional[str] = None  # si hay un error que impide procesar, va acá


def _mapear_columnas(df: pd.DataFrame) -> dict[str, str]:
    """
    Relaciona cada dato que necesitamos con el nombre real de la columna en el Excel.
    Devuelve, por ejemplo, {'cuit': 'CUIT', 'saldo_pendiente': 'Importe', ...}.
    """
    # Normalizamos los encabezados reales del Excel para comparar.
    reales = {str(c).strip().lower(): c for c in df.columns}
    mapa = {}
    for clave, posibles in NOMBRES_COLUMNAS.items():
        for nombre in posibles:
            if nombre in reales:
                mapa[clave] = reales[nombre]
                break
    return mapa


def _a_decimal(valor) -> Decimal:
    """Convierte un saldo (que puede venir como '1.234,50' o 1234.5) a Decimal."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return Decimal("0")
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    # Texto: sacamos símbolos de moneda y normalizamos separadores.
    texto = str(valor).strip().replace("$", "").replace(" ", "")
    # Formato argentino "1.234,50" -> "1234.50".
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def importar_foto(sesion, ruta_excel: str, nombre_archivo: Optional[str] = None) -> ResultadoImport:
    """
    Importa una foto (Excel) a la base. 'sesion' es una sesión de SQLAlchemy.

    Hace toda la lógica de la Fase 1: auto-identificar cliente, no duplicar facturas,
    y reemplazar la foto vieja (lo que desaparece queda pagado).
    """
    resultado = ResultadoImport()
    nombre_archivo = nombre_archivo or str(ruta_excel)

    # 1) Leer el Excel.
    try:
        df = pd.read_excel(ruta_excel)
    except Exception as e:  # archivo roto, no es Excel, etc.
        resultado.error = f"No pudimos leer el archivo. Asegurate de que sea un Excel (.xlsx). Detalle: {e}"
        return resultado

    if df.empty:
        resultado.error = "El archivo está vacío: no tiene ninguna fila para procesar."
        return resultado

    # 2) Mapear columnas y chequear que estén las obligatorias.
    mapa = _mapear_columnas(df)
    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in mapa]
    if faltan:
        nombres_lindos = {
            "cuit": "CUIT",
            "numero_factura": "Número de factura",
            "saldo_pendiente": "Saldo",
            "fecha_vencimiento": "Vencimiento",
        }
        faltan_txt = ", ".join(nombres_lindos[c] for c in faltan)
        resultado.error = (
            f"Al Excel le faltan columnas obligatorias: {faltan_txt}. "
            f"Revisá que el archivo tenga esos encabezados."
        )
        return resultado

    # 3) Marcar TODAS las facturas existentes como 'no presentes' todavía. Las que
    #    aparezcan en esta foto se vuelven a marcar presentes más abajo.
    for f in sesion.query(Factura).all():
        f.presente_en_ultima_foto = False

    numeros_vistos: set[str] = set()
    # Cache de clientes tocados en ESTA foto. Evita intentar crear dos veces el mismo
    # cliente cuando tiene varias facturas (la sesión todavía no lo asentó en la base).
    clientes_en_foto: dict[str, Cliente] = {}

    # 4) Recorrer cada fila de la foto.
    for indice, fila in df.iterrows():
        nro_excel = indice + 2  # +2: fila 1 es el encabezado y pandas arranca en 0.

        cuit = normalizar_cuit(fila[mapa["cuit"]])
        numero = str(fila[mapa["numero_factura"]]).strip()

        # Validaciones básicas de la fila (avisamos y salteamos, no rompemos todo).
        if not cuit:
            resultado.avisos.append(f"Fila {nro_excel}: sin CUIT, la saltamos.")
            continue
        if not numero or numero.lower() == "nan":
            resultado.avisos.append(f"Fila {nro_excel}: sin número de factura, la saltamos.")
            continue
        if numero in numeros_vistos:
            resultado.avisos.append(
                f"Fila {nro_excel}: el número de factura '{numero}' está repetido en el Excel; usamos la primera."
            )
            continue
        numeros_vistos.add(numero)

        # Fecha de vencimiento.
        try:
            fecha_vto = pd.to_datetime(fila[mapa["fecha_vencimiento"]]).date()
        except Exception:
            resultado.avisos.append(
                f"Fila {nro_excel}: no entendimos la fecha de vencimiento, la saltamos."
            )
            continue

        saldo = _a_decimal(fila[mapa["saldo_pendiente"]])

        # 4.a) Auto-identificar / crear el cliente (upsert por CUIT).
        #      Primero miramos el cache de esta foto, después la base.
        cliente = clientes_en_foto.get(cuit) or sesion.get(Cliente, cuit)
        if cliente is None:
            cliente = Cliente(cuit=cuit)
            sesion.add(cliente)
            resultado.clientes_nuevos += 1
            # Avisamos si el dígito verificador no cierra (no bloquea).
            if not validar_digito_verificador(cuit):
                cliente.cuit_sospechoso = True
                resultado.avisos.append(
                    f"Fila {nro_excel}: el CUIT {cuit} no pasa el dígito verificador; lo cargamos igual, revisalo."
                )

        clientes_en_foto[cuit] = cliente

        # Completar/actualizar datos del cliente si vienen en la planilla.
        if "nombre" in mapa and pd.notna(fila[mapa["nombre"]]):
            cliente.nombre = str(fila[mapa["nombre"]]).strip()
        if "telefono_whatsapp" in mapa and pd.notna(fila[mapa["telefono_whatsapp"]]):
            cliente.telefono_whatsapp = str(fila[mapa["telefono_whatsapp"]]).strip()
        if "vendedor_asignado" in mapa and pd.notna(fila[mapa["vendedor_asignado"]]):
            cliente.vendedor_asignado = str(fila[mapa["vendedor_asignado"]]).strip()

        # 4.b) Crear o actualizar la factura (matcheo por número).
        factura = sesion.get(Factura, numero)
        if factura is None:
            factura = Factura(numero_factura=numero, cuit=cuit)
            sesion.add(factura)
            resultado.facturas_nuevas += 1
        else:
            factura.cuit = cuit
            resultado.facturas_actualizadas += 1

        factura.saldo_pendiente = saldo
        factura.fecha_vencimiento = fecha_vto
        factura.estado = "pendiente"
        factura.presente_en_ultima_foto = True

    # Asentamos todo lo creado/modificado en la foto antes de hacer las cuentas, así
    # las consultas de abajo ven también las facturas nuevas (la sesión de la web no
    # hace autoflush).
    sesion.flush()

    # 5) Las facturas que quedaron 'no presentes' y estaban pendientes -> pagadas.
    #    (Desapareció de la foto = se asume cobrada. La foto reemplaza, no suma.)
    for f in sesion.query(Factura).filter_by(presente_en_ultima_foto=False).all():
        if f.estado == "pendiente":
            f.estado = "pagada"
            resultado.facturas_pagadas += 1

    # Total pendiente actual (después de aplicar la foto).
    pendientes = sesion.query(Factura).filter_by(estado="pendiente").all()
    resultado.total_pendiente = sum((Decimal(str(f.saldo_pendiente)) for f in pendientes), Decimal("0"))

    # 6) Registrar el snapshot de esta carga (incluye el DSO aproximado de la foto).
    snap = ImportSnapshot(
        fecha_hora=datetime.now(),
        nombre_archivo=nombre_archivo,
        cantidad_facturas=len(pendientes),
        total_pendiente=resultado.total_pendiente,
        dso_aprox=motor.dias_cobranza_aprox(pendientes, date.today()),
    )
    sesion.add(snap)

    sesion.commit()
    return resultado
