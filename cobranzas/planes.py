"""
Los 3 planes de COBRUM, como datos (una sola fuente de verdad).

Principio de precios que manda en todo:
  - Los precios se definen en USD y se cobran en PESOS al valor del dólar del día.
  - NUNCA se guarda un precio fijo en pesos (con la inflación se desactualiza solo).
    El peso se calcula al vuelo: precio_usd * valor_dolar configurable.
  - El modelo es suscripción mensual + cobro por VENDEDOR (asiento): el valor del
    producto crece con cada vendedor que usa la agenda.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# Precio del add-on "vendedor adicional" (aplica a Arranque y Crecimiento; en Pro no,
# porque ya es ilimitado).
ADDON_VENDEDOR_USD = 19

# Al pagar el año completo, se regalan 2 meses (pagás 10, usás 12).
MESES_GRATIS_ANUAL = 2


@dataclass(frozen=True)
class Plan:
    clave: str                       # identificador interno: "arranque", "crecimiento", "pro"
    nombre: str                      # "Arranque"
    precio_usd: int                  # 79
    desde: bool                      # True en Pro: se muestra "desde USD 299"
    max_vendedores: Optional[int]    # None = ilimitado
    max_clientes: Optional[int]      # None = ilimitado
    texto_limites: str               # cómo mostrar los límites en la tarjeta
    resumen: str                     # para quién es el plan
    destacado: bool                  # True en Crecimiento ("El más elegido")
    permite_addon: bool              # True en Arranque y Crecimiento
    beneficios: list[str] = field(default_factory=list)

    def precio_en_pesos(self, valor_dolar) -> Decimal:
        """El precio mensual en pesos, al valor del dólar configurado."""
        return (Decimal(str(self.precio_usd)) * Decimal(str(valor_dolar))).quantize(Decimal("1"))

    def precio_anual_usd(self) -> int:
        """Precio del año pagando 10 meses (2 gratis)."""
        return self.precio_usd * (12 - MESES_GRATIS_ANUAL)


PLANES: list[Plan] = [
    Plan(
        clave="arranque",
        nombre="Arranque",
        precio_usd=79,
        desde=False,
        max_vendedores=3,
        max_clientes=150,
        texto_limites="Hasta 3 vendedores · hasta 150 clientes activos · 1 usuario admin",
        resumen="Para distribuidoras chicas o que recién empiezan.",
        destacado=False,
        permite_addon=True,
        beneficios=[
            "Motor de cobranza completo (importar Excel, foto que reemplaza, sin duplicar)",
            "Agenda diaria priorizada por “lo más cobrable hoy”",
            "Recordatorios por WhatsApp con los 3 botones (Ya pagué / Pido unos días / Tengo un reclamo)",
            "Confirmación de pago por comprobante + cruce contra extracto bancario",
            "Dashboard con el DSO (días de cobranza)",
            "Modo copiloto (el sistema propone, un humano envía)",
            "Soporte por email",
        ],
    ),
    Plan(
        clave="crecimiento",
        nombre="Crecimiento",
        precio_usd=149,
        desde=False,
        max_vendedores=8,
        max_clientes=600,
        texto_limites="Hasta 8 vendedores · hasta 600 clientes activos · usuarios admin múltiples",
        resumen="Para distribuidoras con un equipo de vendedores en marcha.",
        destacado=True,
        permite_addon=True,
        beneficios=[
            "Todo lo de Arranque, más:",
            "Modo automático (los mensajes salen solos según reglas)",
            "Secuencias de tono escalonado configurables (amable → alternativa → fecha + consecuencia)",
            "Email de respaldo automático si el cliente no tiene WhatsApp",
            "Reportes avanzados y exportación de datos",
            "Promesas de pago con seguimiento automático destacado",
            "Soporte prioritario por WhatsApp",
        ],
    ),
    Plan(
        clave="pro",
        nombre="Pro",
        precio_usd=299,
        desde=True,
        max_vendedores=None,
        max_clientes=None,
        texto_limites="Vendedores ilimitados · clientes ilimitados (uso razonable)",
        resumen="Para mayoristas grandes con muchos vendedores.",
        destacado=False,
        permite_addon=False,
        beneficios=[
            "Todo lo de Crecimiento, más:",
            "Módulo de reventa “reestockeate con [vendedor]” (cuando esté disponible)",
            "Personalización de mensajes por rubro",
            "Onboarding dedicado y soporte premium",
            "Acceso anticipado a nuevas funciones",
            "(Futuro) API e integraciones",
        ],
    ),
]


def plan_por_clave(clave: str) -> Plan:
    """Devuelve el Plan por su clave; si no existe, cae en Arranque."""
    for p in PLANES:
        if p.clave == clave:
            return p
    return PLANES[0]


def chequear_limites(plan: Plan, cantidad_vendedores: int, cantidad_clientes: int,
                     vendedores_adicionales: int = 0) -> list[str]:
    """
    Devuelve avisos (en lenguaje humano) si el uso supera los límites del plan.
    Lista vacía = todo dentro del plan. NO bloquea nada: solo avisa y sugiere.
    """
    avisos: list[str] = []

    # Vendedores: el add-on suma asientos en los planes que lo permiten.
    if plan.max_vendedores is not None:
        tope = plan.max_vendedores + (vendedores_adicionales if plan.permite_addon else 0)
        if cantidad_vendedores > tope:
            sugerencia = "sumá un vendedor adicional (+USD 19/mes) o pasá a un plan mayor"
            if not plan.permite_addon:
                sugerencia = "pasá a un plan mayor"
            avisos.append(
                f"Tu plan {plan.nombre} permite hasta {tope} vendedor(es) y tenés "
                f"{cantidad_vendedores}. Para no quedar corto, {sugerencia}."
            )

    # Clientes activos (con deuda gestionada).
    if plan.max_clientes is not None and cantidad_clientes > plan.max_clientes:
        avisos.append(
            f"Tu plan {plan.nombre} permite hasta {plan.max_clientes} clientes activos y "
            f"tenés {cantidad_clientes}. Te conviene pasar a un plan mayor."
        )

    return avisos
