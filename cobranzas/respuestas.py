"""
Lógica de respuestas (Fase 4).

Cuando el cliente toca uno de los 3 botones, el sistema reacciona solo:
  - "Ya pagué"        -> dijo que pagó: pausa la cobranza, queda a verificar (Fase 5).
  - "Pido unos días"  -> promesa de pago: pausa unos días y después reaparece en la agenda.
  - "Tengo un reclamo"-> reclamo abierto: pausa y pide atención humana.

Estas funciones operan sobre un objeto cliente (con estado_gestion / gestion_hasta) y NO
tocan la base directamente: el que llama hace el commit. Así son fáciles de testear.
"""

from datetime import timedelta

# Cuántos días de plazo le damos cuando pide "unos días".
DIAS_PROMESA = 7


def aplicar_respuesta(cliente, boton: str, hoy) -> None:
    """Cambia el estado de gestión del cliente según el botón que tocó."""
    if boton == "Ya pagué":
        cliente.estado_gestion = "pago_informado"
        cliente.gestion_hasta = None
    elif boton == "Pido unos días":
        cliente.estado_gestion = "promesa_pago"
        cliente.gestion_hasta = hoy + timedelta(days=DIAS_PROMESA)
    elif boton == "Tengo un reclamo":
        cliente.estado_gestion = "reclamo"
        cliente.gestion_hasta = None


def reactivar(cliente) -> None:
    """Vuelve a poner al cliente en gestión normal (resolvió el reclamo, etc.)."""
    cliente.estado_gestion = "activo"
    cliente.gestion_hasta = None


def cobranza_pausada(cliente, hoy) -> bool:
    """
    True si NO hay que mandarle recordatorios ahora:
      - dijo que pagó (a verificar) o tiene un reclamo abierto, o
      - prometió pagar y todavía está dentro del plazo.
    """
    estado = cliente.estado_gestion
    if estado in ("pago_informado", "reclamo", "pagado"):
        return True
    if estado == "promesa_pago" and cliente.gestion_hasta and hoy < cliente.gestion_hasta:
        return True
    return False


def esperando_respuesta(cliente, hoy) -> bool:
    """True si está en una pausa 'informativa' (dijo que pagó, promesa vigente o ya cobrado)."""
    estado = cliente.estado_gestion
    if estado in ("pago_informado", "pagado"):
        return True
    if estado == "promesa_pago" and cliente.gestion_hasta and hoy < cliente.gestion_hasta:
        return True
    return False


def resumen_estado(cliente, hoy) -> str:
    """Etiqueta humana del estado de gestión (vacío si está activo y sin novedad)."""
    estado = cliente.estado_gestion
    if estado == "pagado":
        return "✓ Cobro registrado — seguimiento en Caja"
    if estado == "pago_informado":
        return "🧾 Dijo que pagó — a verificar contra el extracto"
    if estado == "reclamo":
        return "⚠️ Reclamo abierto — necesita que lo veas"
    if estado == "promesa_pago" and cliente.gestion_hasta:
        if hoy < cliente.gestion_hasta:
            return f"📅 Pidió plazo — recontactar el {cliente.gestion_hasta.strftime('%d/%m')}"
        return "📅 Prometió pagar y no cumplió — volver a insistir"
    return ""
