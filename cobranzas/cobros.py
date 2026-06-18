"""
Lógica de cobros y conciliación (Fase 5).

Cubre los dos caminos para confirmar un pago:
  - EFECTIVO: el vendedor marca que cobró. La plata queda 'a rendir' hasta que la entrega
    o deposita (ahí se marca 'rendido'). Así seguimos la "plata en la calle".
  - TRANSFERENCIA: se registra el cobro 'a conciliar' y se cruza contra el extracto del
    banco (subido como Excel). Si el monto aparece en el extracto, se marca 'conciliado'.

Al registrar un cobro, el cliente deja de perseguirse (estado de gestión 'pagado').
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from cobranzas.modelos import Cobro, Cliente


# Nombres de columna que aceptamos en el extracto del banco para el importe.
COLUMNAS_MONTO = ["monto", "importe", "credito", "crédito", "haber", "ingreso", "deposito", "depósito"]


def registrar_cobro(sesion, cliente: Cliente, monto, metodo: str) -> Cobro:
    """
    Registra un cobro para un cliente y lo saca de la cola de cobranza.
    'metodo' es 'efectivo' o 'transferencia'.
    """
    estado = "a_rendir" if metodo == "efectivo" else "a_conciliar"
    cobro = Cobro(
        cuit=cliente.cuit,
        monto=Decimal(str(monto)),
        metodo=metodo,
        vendedor=cliente.vendedor_asignado,
        fecha_hora=datetime.now(),
        estado=estado,
    )
    sesion.add(cobro)
    # El cliente pagó: dejamos de perseguirlo (la plata se sigue en la pantalla Caja).
    cliente.estado_gestion = "pagado"
    cliente.gestion_hasta = None
    sesion.commit()
    return cobro


def marcar_rendido(sesion, cobro_id: int) -> None:
    """Marca un cobro en efectivo como rendido (el vendedor entregó la plata)."""
    cobro = sesion.get(Cobro, cobro_id)
    if cobro is not None and cobro.estado == "a_rendir":
        cobro.estado = "rendido"
        sesion.commit()


@dataclass
class ResultadoConciliacion:
    conciliados: int = 0
    sin_match: int = 0
    error: str = None


def _montos_del_extracto(ruta_excel: str):
    """Lee el extracto y devuelve la lista de importes (positivos = ingresos)."""
    df = pd.read_excel(ruta_excel)
    reales = {str(c).strip().lower(): c for c in df.columns}
    col = None
    for nombre in COLUMNAS_MONTO:
        if nombre in reales:
            col = reales[nombre]
            break
    if col is None:
        return None  # no encontramos la columna de importe

    montos = []
    for valor in df[col]:
        try:
            if pd.isna(valor):
                continue
            d = Decimal(str(valor).replace("$", "").replace(".", "").replace(",", ".")) \
                if isinstance(valor, str) else Decimal(str(valor))
            if d > 0:
                montos.append(d)
        except InvalidOperation:
            continue
    return montos


def conciliar_con_extracto(sesion, ruta_excel: str) -> ResultadoConciliacion:
    """
    Cruza las transferencias 'a conciliar' contra los ingresos del extracto, por monto.
    Cada ingreso del extracto matchea como mucho una transferencia.
    """
    resultado = ResultadoConciliacion()
    try:
        montos = _montos_del_extracto(ruta_excel)
    except Exception as e:
        resultado.error = f"No pudimos leer el extracto. Asegurate de que sea un Excel. Detalle: {e}"
        return resultado

    if montos is None:
        resultado.error = ("Al extracto no le encontramos la columna de importe. "
                           "Tiene que tener una columna tipo 'Monto', 'Importe' o 'Crédito'.")
        return resultado

    disponibles = list(montos)
    a_conciliar = (sesion.query(Cobro)
                   .filter(Cobro.metodo == "transferencia", Cobro.estado == "a_conciliar")
                   .order_by(Cobro.fecha_hora.asc()).all())

    for cobro in a_conciliar:
        monto = Decimal(str(cobro.monto))
        if monto in disponibles:
            disponibles.remove(monto)  # ese ingreso ya se usó
            cobro.estado = "conciliado"
            resultado.conciliados += 1
        else:
            resultado.sin_match += 1

    sesion.commit()
    return resultado
