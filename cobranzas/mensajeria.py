"""
Mensajería de WhatsApp (Fase 3) — SIMULADA.

Acá vive la lógica de los recordatorios, sin conectar todavía la API real:
  - en qué ETAPA de tono está el cliente según hace cuánto está vencida la deuda,
  - si hay una VENTANA de 24 hs abierta (responder sale gratis) o no (plantilla, con costo),
  - cómo se REDACTA el mensaje (firmado por el negocio, nunca por la plataforma).

Decisiones de producto que respeta (ver CLAUDE.md → Principios de diseño del producto):
  - Nunca arrancar con tono duro ni amenazas.
  - Preferir responder dentro de la ventana (gratis).
  - Los 3 botones cuentan como mensaje entrante y abren la ventana.
"""

from datetime import datetime, timedelta
from typing import Optional

# Los 3 botones que lleva cada mensaje. Tocar uno = mensaje entrante (abre la ventana).
BOTONES = ["Ya pagué", "Pido unos días", "Tengo un reclamo"]

# Costo estimado de un mensaje de PLANTILLA (con markup del proveedor). Cuando el cliente
# responde se abre la ventana de 24 hs y los siguientes salen gratis. Hoy es solo para
# proyectar el gasto: WhatsApp está simulado, el costo real actual es 0.
COSTO_PLANTILLA_USD = 0.05

# Duración de la ventana gratis desde el último mensaje entrante del cliente.
VENTANA_HORAS = 24


def etapa_por_dias(dias_atraso: int) -> int:
    """
    En qué etapa de tono va el mensaje según los días de atraso de la deuda más vieja.
      - Etapa 1 (1 a 7 días): amable, asumir olvido.
      - Etapa 2 (8 a 30 días): ofrecer alternativa / coordinar.
      - Etapa 3 (más de 30 días): fecha concreta + consecuencia clara (sin amenaza).
    (Los cortes son configurables más adelante.)
    """
    if dias_atraso <= 7:
        return 1
    if dias_atraso <= 30:
        return 2
    return 3


def ventana_abierta(ultimo_mensaje_entrante, ahora: datetime) -> bool:
    """True si el cliente respondió hace menos de 24 hs (responder sale gratis)."""
    if ultimo_mensaje_entrante is None:
        return False
    return (ahora - ultimo_mensaje_entrante) < timedelta(hours=VENTANA_HORAS)


def tipo_de_mensaje(ultimo_mensaje_entrante, ahora: datetime) -> str:
    """
    Clasifica un saliente: 'respuesta_ventana' (gratis) si hay ventana abierta, o
    'plantilla' (con costo) si no.
    """
    return "respuesta_ventana" if ventana_abierta(ultimo_mensaje_entrante, ahora) else "plantilla"


def redactar_recordatorio(nombre_cliente: str, nombre_negocio: str, vendedor: Optional[str],
                          numero_factura: str, total_vencido: float, dias_atraso: int,
                          etapa: int) -> str:
    """
    Arma el texto del recordatorio según la etapa. Firmado por el vendedor (si hay) a
    nombre del negocio. Tono escalonado: amable → coordinar → fecha + consecuencia.
    """
    monto = f"${total_vencido:,.0f}".replace(",", ".")
    firma = f"{vendedor} de {nombre_negocio}" if vendedor else nombre_negocio

    if etapa == 1:
        cuerpo = (
            f"¡Hola {nombre_cliente}! 👋 Te escribo de parte de {firma}. "
            f"Se nos pasó la factura {numero_factura} por {monto}. Seguro fue un olvido 🙂. "
            f"Cuando puedas, ¿la coordinás? Si ya la pagaste, avisame con un toque acá abajo. ¡Gracias!"
        )
    elif etapa == 2:
        cuerpo = (
            f"Hola {nombre_cliente}, ¿cómo va? Te recuerdo de parte de {firma} que tenés "
            f"{monto} pendientes (la factura {numero_factura} venció hace {dias_atraso} días). "
            f"Si necesitás unos días o arreglar una forma de pago, decime y lo vemos juntos. ¿Coordinamos?"
        )
    else:
        cuerpo = (
            f"Hola {nombre_cliente}. Desde {firma} necesitamos regularizar {monto} "
            f"(la factura {numero_factura}, vencida hace {dias_atraso} días). "
            f"¿Podés confirmarme una fecha de pago para esta semana? Si no llegamos a un acuerdo, "
            f"vamos a tener que frenar los próximos envíos hasta ponernos al día."
        )

    return cuerpo
