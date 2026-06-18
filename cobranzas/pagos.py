"""
Links de pago "de un toque" (Fase 5) — SIMULADO.

COBRUM arma un link, se lo manda al cliente dentro del mensaje, y cuando el cliente paga,
la deuda se salda sola. La plata va a la cuenta de la EMPRESA (no de COBRUM).

Hoy es simulado (no hay Mercado Pago real ni costo). El día de la nube, cada empresa
conecta su propio Mercado Pago (OAuth) y este módulo crea el cobro real y escucha el aviso
de pago (webhook). La interfaz queda igual: por eso el resto de la app no se entera del
cambio de simulado a real.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from cobranzas.config import BASE_URL
from cobranzas.modelos import LinkPago, Cobro, Cliente


def url_de(token: str) -> str:
    """La URL completa del link de pago (lo que se manda al cliente)."""
    return f"{BASE_URL}/pagar/{token}"


def crear_link(sesion, cliente: Cliente, monto) -> LinkPago:
    """Crea un link de pago pendiente para un cliente y lo guarda."""
    link = LinkPago(
        token=uuid.uuid4().hex,
        cuit=cliente.cuit,
        monto=Decimal(str(monto)),
        estado="pendiente",
        fecha_hora=datetime.now(),
    )
    sesion.add(link)
    sesion.commit()
    return link


def agregar_link_al_mensaje(sesion, cliente: Cliente, monto, texto_base: str,
                            nombre_negocio: str) -> str:
    """Crea un link de pago y lo pega al final del mensaje (lo que ve el cliente)."""
    link = crear_link(sesion, cliente, monto)
    return (f"{texto_base}\n\n💳 Pagá de un toque (a {nombre_negocio}): "
            f"{url_de(link.token)}")


def registrar_pago_link(sesion, token: str) -> bool:
    """
    Marca un link como pagado (simula que el cliente pagó). Registra el cobro como
    'acreditado' (la plata entró a la cuenta de la empresa, ya confirmada) y saca al
    cliente de la cobranza. Devuelve True si lo procesó, False si el link no existe o
    ya estaba pagado.
    """
    link = sesion.get(LinkPago, token)
    if link is None or link.estado == "pagado":
        return False

    ahora = datetime.now()
    link.estado = "pagado"
    link.fecha_pago = ahora

    cliente = sesion.get(Cliente, link.cuit)
    sesion.add(Cobro(
        cuit=link.cuit,
        monto=link.monto,
        metodo="link",              # pago online con el link
        vendedor=cliente.vendedor_asignado if cliente else None,
        fecha_hora=ahora,
        estado="acreditado",        # online = ya confirmado (no hace falta conciliar)
    ))
    if cliente is not None:
        cliente.estado_gestion = "pagado"
        cliente.gestion_hasta = None

    sesion.commit()
    return True
