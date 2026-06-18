"""
Tests de la Fase 3 (mensajería WhatsApp simulada):
  - la etapa de tono según los días de atraso,
  - la ventana de 24 hs (responder gratis vs plantilla con costo),
  - el texto se firma con el negocio/vendedor y nunca arranca con tono duro.
"""

from datetime import datetime, timedelta

from cobranzas import mensajeria


def test_etapa_segun_dias():
    assert mensajeria.etapa_por_dias(1) == 1
    assert mensajeria.etapa_por_dias(7) == 1
    assert mensajeria.etapa_por_dias(8) == 2
    assert mensajeria.etapa_por_dias(30) == 2
    assert mensajeria.etapa_por_dias(31) == 3
    assert mensajeria.etapa_por_dias(120) == 3


def test_ventana_abierta_si_respondio_hace_menos_de_24hs():
    ahora = datetime(2026, 6, 18, 12, 0)
    hace_2hs = ahora - timedelta(hours=2)
    hace_30hs = ahora - timedelta(hours=30)
    assert mensajeria.ventana_abierta(hace_2hs, ahora) is True
    assert mensajeria.ventana_abierta(hace_30hs, ahora) is False
    assert mensajeria.ventana_abierta(None, ahora) is False


def test_tipo_de_mensaje_gratis_dentro_de_ventana():
    ahora = datetime(2026, 6, 18, 12, 0)
    assert mensajeria.tipo_de_mensaje(ahora - timedelta(hours=1), ahora) == "respuesta_ventana"
    assert mensajeria.tipo_de_mensaje(ahora - timedelta(hours=25), ahora) == "plantilla"
    assert mensajeria.tipo_de_mensaje(None, ahora) == "plantilla"


def test_mensaje_etapa1_es_amable_y_firmado():
    texto = mensajeria.redactar_recordatorio(
        "Kiosco La Esquina", "Distribuidora del Oeste", "Juan",
        "A-0002", 8500, 3, etapa=1)
    # Firmado por el vendedor a nombre del negocio.
    assert "Juan de Distribuidora del Oeste" in texto
    # Tono amable: asume olvido, no amenaza.
    assert "olvido" in texto.lower()
    assert "frenar" not in texto.lower()


def test_mensaje_etapa3_pone_fecha_y_consecuencia_sin_arrancar_duro():
    texto = mensajeria.redactar_recordatorio(
        "Almacén Doña Rosa", "Distribuidora del Oeste", "María",
        "A-0003", 20000, 72, etapa=3)
    assert "fecha de pago" in texto.lower()
    assert "frenar los próximos envíos" in texto.lower()


def test_mensaje_sin_vendedor_firma_solo_el_negocio():
    texto = mensajeria.redactar_recordatorio(
        "Ferretería", "Distribuidora del Oeste", None,
        "A-0004", 5000, 10, etapa=2)
    assert "Distribuidora del Oeste" in texto
