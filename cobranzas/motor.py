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


def puntaje_cobrabilidad(cliente, facturas: list[Factura], hoy: date) -> float:
    """
    SEAM Fase 2 — "worklist prioritization" (a quién conviene perseguir hoy primero).

    La idea (estilo HighRadius/Upflow) es priorizar por lo más cobrable: combinar monto,
    días de atraso, historial de pago y si hay una ventana de WhatsApp abierta. En la
    Fase 1 todavía no se calcula; queda esbozada para que la Fase 2 la complete.
    """
    return 0.0
