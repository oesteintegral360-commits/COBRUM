"""
Cobranza automática (Fase 3, modo automático) — SIMULADA.

Cuando la empresa está en modo 'automatico', el sistema manda solo los recordatorios que
corresponden, sin que un humano toque el botón por cada cliente. Esto se dispara:
  - al subir una foto nueva, o
  - al tocar "Ejecutar cobranza de hoy".

Respeta las mismas reglas que el modo copiloto (etapa de tono, ventana de 24 hs / costo) y
agrega un freno ANTI-SPAM: no le vuelve a escribir a un cliente al que ya le escribimos en
las últimas horas, para no bombardearlo si se corre la cobranza varias veces.
"""

from datetime import datetime, timedelta

from cobranzas.modelos import Cliente, Mensaje, Configuracion
from cobranzas import motor, mensajeria, respuestas, pagos

# No le volvemos a escribir a un cliente si ya le mandamos algo hace menos de estas horas.
HORAS_ANTI_SPAM = 20


def ejecutar_cobranza(sesion, hoy) -> dict:
    """
    Manda (simulado) un recordatorio a cada cliente con deuda vencida que no haya sido
    contactado hace poco. Devuelve un resumen para mostrarle a la empresa qué hizo.
    """
    config = Configuracion.obtener(sesion)
    ahora = datetime.now()
    resumen = {"enviados": 0, "plantillas": 0, "gratis": 0, "salteados": 0, "pausados": 0}

    for cliente in sesion.query(Cliente).all():
        vencidas = [f for f in cliente.facturas if motor.esta_vencida(f, hoy)]
        if not vencidas:
            continue

        # Respeta la Fase 4: no le mandamos a quien dijo que pagó, tiene un reclamo
        # abierto, o prometió pagar y está dentro del plazo.
        if respuestas.cobranza_pausada(cliente, hoy):
            resumen["pausados"] += 1
            continue

        # Freno anti-spam: ¿ya le escribimos hace poco?
        reciente = (sesion.query(Mensaje)
                    .filter(Mensaje.cuit == cliente.cuit,
                            Mensaje.direccion == "saliente",
                            Mensaje.fecha_hora >= ahora - timedelta(hours=HORAS_ANTI_SPAM))
                    .first())
        if reciente is not None:
            resumen["salteados"] += 1
            continue

        total_vencido = sum(float(f.saldo_pendiente) for f in vencidas)
        max_dias = max(motor.dias_atraso(f, hoy) for f in vencidas)
        factura_ref = max(vencidas, key=lambda f: motor.dias_atraso(f, hoy)).numero_factura
        etapa = mensajeria.etapa_por_dias(max_dias)
        tipo = mensajeria.tipo_de_mensaje(cliente.ultimo_mensaje_entrante, ahora)
        texto = mensajeria.redactar_recordatorio(
            cliente.nombre or "cliente", config.nombre_negocio, cliente.vendedor_asignado,
            factura_ref, total_vencido, max_dias, etapa)
        # Sumamos el link de pago "de un toque" (a nombre de la empresa).
        texto = pagos.agregar_link_al_mensaje(
            sesion, cliente, total_vencido, texto, config.nombre_negocio)

        sesion.add(Mensaje(cuit=cliente.cuit, direccion="saliente", tipo=tipo,
                           etapa=etapa, fecha_hora=ahora, texto=texto))
        resumen["enviados"] += 1
        resumen["plantillas" if tipo == "plantilla" else "gratis"] += 1

    sesion.commit()
    return resumen
