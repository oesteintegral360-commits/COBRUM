"""
El motor de cálculos.

Todo lo que se puede deducir, se deduce acá (no se le pide a la empresa): si una factura
está vencida, hace cuántos días, en qué tramo de atraso, y cuánto debe cada cliente.

Regla de oro: estas funciones NO tocan la base. Reciben datos y devuelven cálculos.
Así son fáciles de testear y de reusar desde la web.
"""

from datetime import date
from decimal import Decimal

from cobranzas.modelos import Factura


def esta_vencida(factura: Factura, hoy: date) -> bool:
    """True si la factura está pendiente y su vencimiento ya pasó."""
    return factura.estado == "pendiente" and factura.fecha_vencimiento < hoy


def dias_atraso(factura: Factura, hoy: date) -> int:
    """
    Cuántos días hace que venció. 0 si todavía no venció (o vence hoy).
    No depende del estado: es la distancia en días desde el vencimiento.
    """
    diferencia = (hoy - factura.fecha_vencimiento).days
    return max(diferencia, 0)


def tramo_atraso(dias: int) -> str:
    """
    Agrupa los días de atraso en tramos estándar (aging buckets), para escanear la
    lista de un vistazo.
    """
    if dias <= 0:
        return "al día"
    if dias <= 30:
        return "1-30 días"
    if dias <= 60:
        return "31-60 días"
    if dias <= 90:
        return "61-90 días"
    return "+90 días"


def total_por_cliente(facturas: list[Factura]) -> Decimal:
    """Suma los saldos de las facturas PENDIENTES de una lista (las de un cliente)."""
    return sum(
        (Decimal(str(f.saldo_pendiente)) for f in facturas if f.estado == "pendiente"),
        Decimal("0"),
    )


def puntaje_cobrabilidad(facturas: list[Factura], hoy: date) -> float:
    """
    Puntaje "a quién cobrar primero" (worklist, estilo HighRadius/Upflow).

    Es BALANCEADO: combina cuánto debe vencido (impacto) con hace cuánto está vencido
    (urgencia). Más alto = más prioridad. Devuelve 0 si el cliente no tiene nada vencido
    (no entra en la agenda de hoy).
    """
    total_vencido = Decimal("0")
    max_dias = 0
    for f in facturas:
        if esta_vencida(f, hoy):
            total_vencido += Decimal(str(f.saldo_pendiente))
            max_dias = max(max_dias, dias_atraso(f, hoy))

    if total_vencido <= 0:
        return 0.0

    # Urgencia: de 1.0 (recién vencida) a 2.0 (90+ días). Cap a 90 para que un monto
    # enorme pero antiquísimo no distorsione el orden.
    urgencia = 1 + min(max_dias, 90) / 90
    return float(total_vencido) * urgencia


def dias_cobranza_aprox(facturas: list[Factura], hoy: date) -> int:
    """
    Días de cobranza aproximado (proxy del DSO), calculado solo con la foto.

    Es el promedio de días de atraso PONDERADO por monto, sobre lo pendiente: "tu plata,
    en promedio, está vencida hace X días". 0 = todo al día. Sirve para ver la tendencia
    foto a foto (el norte es que baje).
    """
    suma_saldo = Decimal("0")
    suma_ponderada = Decimal("0")
    for f in facturas:
        if f.estado != "pendiente":
            continue
        saldo = Decimal(str(f.saldo_pendiente))
        suma_saldo += saldo
        suma_ponderada += saldo * dias_atraso(f, hoy)

    if suma_saldo <= 0:
        return 0
    return round(float(suma_ponderada / suma_saldo))
