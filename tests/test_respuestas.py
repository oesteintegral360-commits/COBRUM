"""
Tests de la Fase 4 (lógica de respuestas): cada botón cambia el estado de gestión, la
cobranza se pausa cuando corresponde, y el modo automático lo respeta.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Factura
from cobranzas import respuestas, auto

HOY = date(2026, 6, 18)


class ClienteStub:
    """Objeto mínimo con los campos de gestión, para testear la lógica pura."""
    def __init__(self):
        self.estado_gestion = "activo"
        self.gestion_hasta = None


def test_ya_pague_pausa_y_queda_a_verificar():
    c = ClienteStub()
    respuestas.aplicar_respuesta(c, "Ya pagué", HOY)
    assert c.estado_gestion == "pago_informado"
    assert respuestas.cobranza_pausada(c, HOY) is True


def test_pido_unos_dias_da_plazo_de_7_dias():
    c = ClienteStub()
    respuestas.aplicar_respuesta(c, "Pido unos días", HOY)
    assert c.estado_gestion == "promesa_pago"
    assert c.gestion_hasta == HOY + timedelta(days=7)
    # Dentro del plazo: pausada. Pasado el plazo: vuelve a la agenda.
    assert respuestas.cobranza_pausada(c, HOY) is True
    assert respuestas.cobranza_pausada(c, HOY + timedelta(days=8)) is False


def test_reclamo_pausa_y_pide_atencion():
    c = ClienteStub()
    respuestas.aplicar_respuesta(c, "Tengo un reclamo", HOY)
    assert c.estado_gestion == "reclamo"
    assert respuestas.cobranza_pausada(c, HOY) is True
    assert "Reclamo" in respuestas.resumen_estado(c, HOY)


def test_reactivar_vuelve_a_gestion_normal():
    c = ClienteStub()
    respuestas.aplicar_respuesta(c, "Tengo un reclamo", HOY)
    respuestas.reactivar(c)
    assert c.estado_gestion == "activo"
    assert respuestas.cobranza_pausada(c, HOY) is False


def test_promesa_no_cumplida_cambia_la_etiqueta():
    c = ClienteStub()
    respuestas.aplicar_respuesta(c, "Pido unos días", HOY)
    assert "recontactar" in respuestas.resumen_estado(c, HOY).lower()
    # Pasado el plazo, el texto cambia a "no cumplió".
    assert "no cumplió" in respuestas.resumen_estado(c, HOY + timedelta(days=8)).lower()


# --- Integración con el modo automático ---------------------------------------
@pytest.fixture
def sesion():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_automatico_no_le_manda_a_quien_dijo_que_pago(sesion):
    sesion.add(Cliente(cuit="1", nombre="A", estado_gestion="pago_informado"))
    sesion.add(Factura(numero_factura="F1", cuit="1", saldo_pendiente=10000,
                       fecha_vencimiento=HOY - timedelta(days=20), estado="pendiente"))
    sesion.commit()
    resumen = auto.ejecutar_cobranza(sesion, HOY)
    assert resumen["enviados"] == 0
    assert resumen["pausados"] == 1
